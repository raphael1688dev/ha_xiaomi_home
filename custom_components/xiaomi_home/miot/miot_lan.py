# -*- coding: utf-8 -*-

import json
import time
import asyncio
from dataclasses import dataclass
from enum import Enum, auto
import logging
import random
import secrets
import socket
import struct
import threading
from typing import Any, Callable, Coroutine, Optional, final
import hashlib  # 使用內建 hashlib 提升效能

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives import padding
from cryptography.hazmat.backends import default_backend

# pylint: disable=relative-beyond-top-level
from .miot_error import MIoTError, MIoTLanError, MIoTErrorCode
from .miot_network import InterfaceStatus, MIoTNetwork, NetworkInfo
from .miot_mdns import MipsService, MipsServiceState
from .common import (
    randomize_float, load_yaml_file, gen_absolute_path, MIoTMatcher)

try:
    from .miio_specs import MIIO_SPECS
except ImportError:
    MIIO_SPECS = {}

_LOGGER = logging.getLogger(__name__)


@dataclass
class _MIoTLanGetDevListData:
    handler: Callable[[dict, Any], None]
    handler_ctx: Any
    timeout_ms: int


@dataclass
class _MIoTLanUnregisterBroadcastData:
    key: str


@dataclass
class _MIoTLanRegisterBroadcastData:
    key: str
    handler: Callable[[dict, Any], None]
    handler_ctx: Any


@dataclass
class _MIoTLanUnsubDeviceData:
    key: str


@dataclass
class _MIoTLanSubDeviceData:
    key: str
    handler: Callable[[str, dict, Any], Coroutine]
    handler_ctx: Any


@dataclass
class _MIoTLanNetworkUpdateData:
    status: InterfaceStatus
    if_name: str


@dataclass
class _MIoTLanRequestData:
    msg_id: int
    handler: Optional[Callable[[dict, Any], None]]
    handler_ctx: Any
    timeout: Optional[asyncio.TimerHandle]


class _MIoTLanDeviceState(Enum):
    FRESH = 0
    PING1 = auto()
    PING2 = auto()
    PING3 = auto()
    DEAD = auto()


class _MIoTLanDevice:
    """MIoT lan device."""
    # pylint: disable=unused-argument
    OT_HEADER: int = 0x2131
    OT_HEADER_LEN: int = 32
    NETWORK_UNSTABLE_CNT_TH: int = 10
    NETWORK_UNSTABLE_TIME_TH: float = 120
    NETWORK_UNSTABLE_RESUME_TH: float = 300
    FAST_PING_INTERVAL: float = 5
    CONSTRUCT_STATE_PENDING: float = 15
    KA_INTERVAL_MIN: float = 10
    KA_INTERVAL_MAX: float = 50

    did: str
    token: bytes
    cipher: Cipher
    ip: Optional[str]
    model: Optional[str]

    offset: int
    subscribed: bool
    sub_ts: int
    supported_wildcard_sub: bool

    _manager: 'MIoTLan'
    _if_name: Optional[str]
    _sub_locked: bool
    _state: _MIoTLanDeviceState
    _online: bool
    _online_offline_history: list[dict[str, Any]]
    _online_offline_timer: Optional[asyncio.TimerHandle]

    _ka_timer: Optional[asyncio.TimerHandle]
    _ka_internal: float

# All functions SHOULD be called from the internal loop

    def __init__(
        self,
        manager: 'MIoTLan',
        did: str,
        token: str,
        ip: Optional[str] = None,
        model: Optional[str] = None
    ) -> None:
        self._manager: MIoTLan = manager
        self.did = did
        self.token = bytes.fromhex(token)
        aes_key: bytes = self.__md5(self.token)
        aex_iv: bytes = self.__md5(aes_key + self.token)
        self.cipher = Cipher(
            algorithms.AES128(aes_key), modes.CBC(aex_iv), default_backend())
        self.ip = ip
        self.model = model
        self.offset = 0
        self.subscribed = False
        self.sub_ts = 0
        self.supported_wildcard_sub = False
        self._if_name = None
        self._sub_locked = False
        self._state = _MIoTLanDeviceState.DEAD
        self._online = False
        self._online_offline_history = []
        self._online_offline_timer = None

        def ka_init_handler() -> None:
            self._ka_internal = self.KA_INTERVAL_MIN
            self.__update_keep_alive(state=_MIoTLanDeviceState.DEAD)
        self._ka_timer = self._manager.internal_loop.call_later(
            randomize_float(self.CONSTRUCT_STATE_PENDING, 0.5),
            ka_init_handler,)
        _LOGGER.debug('miot lan device add, %s', self.did)

    def keep_alive(self, ip: str, if_name: str) -> None:
        self.ip = ip
        if self._if_name != if_name:
            self._if_name = if_name
            _LOGGER.info(
                'device if_name change, %s, %s', self._if_name, self.did)
        self.__update_keep_alive(state=_MIoTLanDeviceState.FRESH)

    @property
    def online(self) -> bool:
        return self._online

    @online.setter
    def online(self, online: bool) -> None:
        if self._online == online:
            return
        self._online = online
        self._manager.broadcast_device_state(
            did=self.did, state={
                'online': self._online, 'push_available': self.subscribed})

    @property
    def if_name(self) -> Optional[str]:
        return self._if_name

    def gen_packet(
        self, out_buffer: bytearray, clear_data: dict, did: str, offset: int
    ) -> int:
        clear_bytes = json.dumps(clear_data, ensure_ascii=False).encode('utf-8')
        padder = padding.PKCS7(algorithms.AES128.block_size).padder()
        padded_data = padder.update(clear_bytes) + padder.finalize()
        if len(padded_data) + self.OT_HEADER_LEN > len(out_buffer):
            raise ValueError('rpc too long')
        encryptor = self.cipher.encryptor()
        encrypted_data = encryptor.update(padded_data) + encryptor.finalize()
        data_len: int = len(encrypted_data)+self.OT_HEADER_LEN
        out_buffer[:32] = struct.pack(
            '>HHQI16s', self.OT_HEADER, data_len, int(did), offset,
            self.token)
        out_buffer[32:data_len] = encrypted_data
        msg_md5: bytes = self.__md5(out_buffer[0:data_len])
        out_buffer[16:32] = msg_md5
        return data_len

    def decrypt_packet(self, encrypted_data: bytearray) -> dict:
        data_len: int = struct.unpack('>H', encrypted_data[2:4])[0]
        md5_orig: bytes = encrypted_data[16:32]
        encrypted_data[16:32] = self.token
        md5_calc: bytes = self.__md5(encrypted_data[0:data_len])
        if md5_orig != md5_calc:
            raise ValueError(f'invalid md5, {md5_orig}, {md5_calc}')
        decryptor = self.cipher.decryptor()
        decrypted_padded_data = decryptor.update(
            encrypted_data[32:data_len]) + decryptor.finalize()
        unpadder = padding.PKCS7(algorithms.AES128.block_size).unpadder()
        decrypted_data = unpadder.update(
            decrypted_padded_data) + unpadder.finalize()
        # Some device will add a redundant \0 at the end of JSON string
        decrypted_data = decrypted_data.rstrip(b'\x00')
        return json.loads(decrypted_data)

    def subscribe(self) -> None:
        if self._sub_locked:
            return
        self._sub_locked = True
        try:
            sub_ts: int = int(time.time())
            self._manager.send2device(
                did=self.did,
                msg={
                    'method': 'miIO.sub',
                    'params': {
                        'version': '2.0',
                        'did': self._manager.virtual_did,
                        'update_ts': sub_ts,
                        'sub_method': '.'
                    }
                },
                handler=self.__subscribe_handler,
                handler_ctx=sub_ts,
                timeout_ms=5000)
        except Exception as err:  # pylint: disable=broad-exception-caught
            _LOGGER.error('subscribe device error, %s', err)

        self._sub_locked = False

    def unsubscribe(self) -> None:
        if not self.subscribed:
            return
        self._manager.send2device(
            did=self.did,
            msg={
                'method': 'miIO.unsub',
                'params': {
                    'version': '2.0',
                    'did': self._manager.virtual_did,
                    'update_ts': self.sub_ts or 0,
                    'sub_method': '.'
                }
            },
            handler=self.__unsubscribe_handler,
            timeout_ms=5000)
        self.subscribed = False
        self._manager.broadcast_device_state(
            did=self.did, state={
                'online': self._online, 'push_available': self.subscribed})

    def on_delete(self) -> None:
        if self._ka_timer:
            self._ka_timer.cancel()
            self._ka_timer = None
        if self._online_offline_timer:
            self._online_offline_timer.cancel()
            self._online_offline_timer = None
        _LOGGER.debug('miot lan device delete, %s', self.did)

    def update_info(self, info: dict) -> None:
        if (
            'token' in info
            and len(info['token']) == 32
            and info['token'].upper() != self.token.hex().upper()
        ):
            # Update token
            self.token = bytes.fromhex(info['token'])
            aes_key: bytes = self.__md5(self.token)
            aex_iv: bytes = self.__md5(aes_key + self.token)
            self.cipher = Cipher(
                algorithms.AES128(aes_key),
                modes.CBC(aex_iv), default_backend())
            _LOGGER.debug('update token, %s', self.did)
        if 'ip' in info and info['ip']:
            self.ip = info['ip']

    def __subscribe_handler(self, msg: dict, sub_ts: int) -> None:
        if (
            'result' not in msg
            or 'code' not in msg['result']
            or msg['result']['code'] != 0
        ):
            _LOGGER.error('subscribe device error, %s, %s', self.did, msg)
            return
        self.subscribed = True
        self.sub_ts = sub_ts
        self._manager.broadcast_device_state(
            did=self.did, state={
                'online': self._online, 'push_available': self.subscribed})
        _LOGGER.info('subscribe success, %s, %s', self._if_name, self.did)

    def __unsubscribe_handler(self, msg: dict, ctx: Any) -> None:
        if (
            'result' not in msg
            or 'code' not in msg['result']
            or msg['result']['code'] != 0
        ):
            _LOGGER.error('unsubscribe device error, %s, %s', self.did, msg)
            return
        _LOGGER.info('unsubscribe success, %s, %s', self._if_name, self.did)

    def __update_keep_alive(self, state: _MIoTLanDeviceState) -> None:
        last_state: _MIoTLanDeviceState = self._state
        self._state = state
        if self._state != _MIoTLanDeviceState.FRESH:
            _LOGGER.debug('device status, %s, %s', self.did, self._state)
        if self._ka_timer:
            self._ka_timer.cancel()
            self._ka_timer = None
        match state:
            case _MIoTLanDeviceState.FRESH:
                if last_state == _MIoTLanDeviceState.DEAD:
                    self._ka_internal = self.KA_INTERVAL_MIN
                    self.__change_online(True)
                self._ka_timer = self._manager.internal_loop.call_later(
                    self.__get_next_ka_timeout(), self.__update_keep_alive,
                    _MIoTLanDeviceState.PING1)
            case (
                    _MIoTLanDeviceState.PING1
                    | _MIoTLanDeviceState.PING2
                    | _MIoTLanDeviceState.PING3
            ):
                # Set the timer first to avoid Any early returns
                self._ka_timer = self._manager.internal_loop.call_later(
                    self.FAST_PING_INTERVAL, self.__update_keep_alive,
                    _MIoTLanDeviceState(state.value+1))
                # Fast ping
                if self._if_name is None:
                    _LOGGER.error(
                        'if_name is Not set for device, %s', self.did)
                    return
                if self.ip is None:
                    _LOGGER.error('ip is Not set for device, %s', self.did)
                    return
                self._manager.ping(if_name=self._if_name, target_ip=self.ip)
            case _MIoTLanDeviceState.DEAD:
                if last_state == _MIoTLanDeviceState.PING3:
                    self._ka_internal = self.KA_INTERVAL_MIN
                    self.__change_online(False)
            case _:
                _LOGGER.error('invalid state, %s', state)

    def __get_next_ka_timeout(self) -> float:
        self._ka_internal = min(self._ka_internal*2, self.KA_INTERVAL_MAX)
        return randomize_float(self._ka_internal, 0.1)

    def __change_online(self, online: bool) -> None:
        _LOGGER.info('change online, %s, %s', self.did, online)
        ts_now: int = int(time.time())
        self._online_offline_history.append({'ts': ts_now, 'online': online})
        if len(self._online_offline_history) > self.NETWORK_UNSTABLE_CNT_TH:
            self._online_offline_history.pop(0)
        if self._online_offline_timer:
            self._online_offline_timer.cancel()
            self._online_offline_timer = None
        if not online:
            self.online = False
        else:
            if (
                len(self._online_offline_history) < self.NETWORK_UNSTABLE_CNT_TH
                or (
                    ts_now - self._online_offline_history[0]['ts'] >
                    self.NETWORK_UNSTABLE_TIME_TH)
            ):
                self.online = True
            else:
                _LOGGER.info('unstable device detected, %s', self.did)
                self._online_offline_timer = (
                    self._manager.internal_loop.call_later(
                        self.NETWORK_UNSTABLE_RESUME_TH,
                        self.__online_resume_handler))

    def __online_resume_handler(self) -> None:
        _LOGGER.info('unstable resume threshold past, %s', self.did)
        self.online = True

    def __md5(self, data: bytes) -> bytes:
        # Optimized: 使用 hashlib.md5，底層為 C 實作，大幅提升運算效率
        return hashlib.md5(data).digest()


class MIoTLan:
    """MIoT lan device control."""
    # pylint: disable=unused-argument
    # pylint: disable=inconsistent-quotes
    OT_HEADER: bytes = b'\x21\x31'
    OT_PORT: int = 54321
    OT_PROBE_LEN: int = 32
    OT_MSG_LEN: int = 1400
    OT_SUPPORT_WILDCARD_SUB: int = 0xFE

    OT_PROBE_INTERVAL_MIN: float = 5
    OT_PROBE_INTERVAL_MAX: float = 45

    PROFILE_MODELS_FILE: str = 'lan/profile_models.yaml'

    _main_loop: asyncio.AbstractEventLoop
    _net_ifs: set[str]
    _network: MIoTNetwork
    _mips_service: MipsService
    _enable_subscribe: bool
    _lan_devices: dict[str, _MIoTLanDevice]
    _virtual_did: str
    _probe_msg: bytes
    _write_buffer: bytearray
    _read_buffer: bytearray

    _internal_loop: asyncio.AbstractEventLoop
    _thread: threading.Thread

    _available_net_ifs: set[str]
    _broadcast_socks: dict[str, socket.socket]
    _local_port: Optional[int]
    _scan_timer: Optional[asyncio.TimerHandle]
    _last_scan_interval: Optional[float]
    _msg_id_counter: int
    _pending_requests: dict[int, _MIoTLanRequestData]
    _device_msg_matcher: MIoTMatcher
    _device_state_sub_map: dict[str, _MIoTLanSubDeviceData]
    _reply_msg_buffer: dict[str, asyncio.TimerHandle]

    _lan_state_sub_map: dict[str, Callable[[bool], Coroutine]]
    _lan_ctrl_vote_map: dict[str, bool]

    _profile_models: dict[str, dict]

    _init_lock: asyncio.Lock
    _init_done: bool
    _ignore_mips_service: bool

# The following should be called from the main loop

    def __init__(
        self,
        net_ifs: list[str],
        network: MIoTNetwork,
        mips_service: MipsService,
        enable_subscribe: bool = False,
        ignore_mips_service: bool = False,
        virtual_did: Optional[int] = None,
        loop: Optional[asyncio.AbstractEventLoop] = None
    ) -> None:
        if not network:
            raise ValueError('network is required')
        if not mips_service:
            raise ValueError('mips_service is required')
        self._main_loop = loop or asyncio.get_event_loop()
        self._net_ifs = set(net_ifs)
        self._network = network
        self._network.sub_network_info(
            key='miot_lan',
            handler=self.__on_network_info_change_external_async)
        self._mips_service = mips_service
        self._mips_service.sub_service_change(
            key='miot_lan', group_id='*',
            handler=self.__on_mips_service_change)
        self._enable_subscribe = enable_subscribe
        self._virtual_did = (
            str(virtual_did) if (virtual_did is not None)
            else str(secrets.randbits(64)))
        # Init socket probe message
        probe_bytes = bytearray(self.OT_PROBE_LEN)
        probe_bytes[:20] = (
            b'!1\x00\x20\xFF\xFF\xFF\xFF\xFF\xFF\xFF\xFF\xFF\xFF\xFF\xFFMDID')
        probe_bytes[20:28] = struct.pack('>Q', int(self._virtual_did))
        probe_bytes[28:32] = b'\x00\x00\x00\x00'
        self._probe_msg = bytes(probe_bytes)
        self._read_buffer = bytearray(self.OT_MSG_LEN)
        self._write_buffer = bytearray(self.OT_MSG_LEN)

        self._lan_devices = {}
        self._available_net_ifs = set()
        self._broadcast_socks = {}
        self._local_port = None
        self._scan_timer = None
        self._last_scan_interval = None
        self._msg_id_counter = int(random.random()*0x7FFFFFFF)
        self._pending_requests = {}
        self._device_msg_matcher = MIoTMatcher()
        self._device_state_sub_map = {}
        self._reply_msg_buffer = {}

        self._lan_state_sub_map = {}
        self._lan_ctrl_vote_map = {}

        self._ignore_mips_service = ignore_mips_service
        self._init_lock = asyncio.Lock()
        self._init_done = False

        if (
            (self._ignore_mips_service or len(self._mips_service.get_services()) == 0)
            and len(self._net_ifs) > 0
        ):
            _LOGGER.info('miot lan init condition met (no central hub or ignored), init miot lan')
            self._main_loop.call_later(
                0, lambda: self._main_loop.create_task(
                    self.init_async()))

    def __assert_service_ready(self) -> None:
        if not self._init_done:
            raise MIoTLanError(
                'MIoT lan is not ready',
                MIoTErrorCode.CODE_LAN_UNAVAILABLE)

    @property
    def virtual_did(self) -> str:
        return self._virtual_did

    @property
    def internal_loop(self) -> asyncio.AbstractEventLoop:
        return self._internal_loop

    @property
    def init_done(self) -> bool:
        return self._init_done

    def set_ignore_mips_service(self, ignore: bool) -> None:
        if self._ignore_mips_service == ignore:
            return
        self._ignore_mips_service = ignore
        if self._ignore_mips_service and not self._init_done:
            self._main_loop.create_task(self.init_async())

    async def init_async(self) -> None:
        # Avoid race condition
        async with self._init_lock:
            if self._init_done:
                _LOGGER.info('miot lan already init')
                return
            if len(self._net_ifs) == 0:
                _LOGGER.info('no net_ifs')
                return
            if not any(self._lan_ctrl_vote_map.values()):
                _LOGGER.info('no vote for lan ctrl')
                return
            if not self._ignore_mips_service and len(self._mips_service.get_services()) > 0:
                _LOGGER.info('central hub gateway service exist, skipping lan init')
                return
            for if_name in list(self._network.network_info.keys()):
                self._available_net_ifs.add(if_name)
            if len(self._available_net_ifs) == 0:
                _LOGGER.info('no available net_ifs')
                return
            if self._net_ifs.isdisjoint(self._available_net_ifs):
                _LOGGER.info('no valid net_ifs')
                return
            try:
                self._profile_models = await self._main_loop.run_in_executor(
                    None, load_yaml_file,
                    gen_absolute_path(self.PROFILE_MODELS_FILE))
            except Exception as err:  # pylint: disable=broad-exception-caught
                _LOGGER.error('load profile models error, %s', err)
                self._profile_models = {}
            self._internal_loop = asyncio.new_event_loop()
            # All tasks meant for the internal loop should happen in this thread
            self._thread = threading.Thread(target=self.__internal_loop_thread)
            self._thread.name = 'miot_lan'
            self._thread.daemon = True
            self._thread.start()
            self._init_done = True
            for handler in list(self._lan_state_sub_map.values()):
                self._main_loop.create_task(handler(True))
            _LOGGER.info(
                'miot lan init, %s ,%s', self._net_ifs, self._available_net_ifs)

    def __internal_loop_thread(self) -> None:
        _LOGGER.info('miot lan thread start')
        self.__init_socket()
        self._scan_timer = self._internal_loop.call_later(
            int(3*random.random()), self.__scan_devices)
        self._internal_loop.run_forever()
        _LOGGER.info('miot lan thread exit')

    async def deinit_async(self) -> None:
        if not self._init_done:
            _LOGGER.info('miot lan not init')
            return
        self._init_done = False
        self._internal_loop.call_soon_threadsafe(self.__deinit)
        self._thread.join()
        self._internal_loop.close()

        self._profile_models = {}
        self._lan_devices = {}
        self._broadcast_socks = {}
        self._local_port = None
        self._scan_timer = None
        self._last_scan_interval = None
        self._msg_id_counter = int(random.random()*0x7FFFFFFF)
        self._pending_requests = {}
        self._device_msg_matcher = MIoTMatcher()
        self._device_state_sub_map = {}
        self._reply_msg_buffer = {}
        for handler in list(self._lan_state_sub_map.values()):
            self._main_loop.create_task(handler(False))
        _LOGGER.info('miot lan deinit')

    async def update_net_ifs_async(self, net_ifs: list[str]) -> None:
        _LOGGER.info('update net_ifs, %s', net_ifs)
        if not isinstance(net_ifs, list):
            _LOGGER.error('invalid net_ifs, %s', net_ifs)
            return
        if len(net_ifs) == 0:
            # Deinit lan
            await self.deinit_async()
            self._net_ifs = set(net_ifs)
            return
        available_net_ifs = set()
        for if_name in list(self._network.network_info.keys()):
            available_net_ifs.add(if_name)
        if set(net_ifs).isdisjoint(available_net_ifs):
            _LOGGER.error('no valid net_ifs, %s', net_ifs)
            await self.deinit_async()
            self._net_ifs = set(net_ifs)
            self._available_net_ifs = available_net_ifs
            return
        if not self._init_done:
            self._net_ifs = set(net_ifs)
            await self.init_async()
            return
        self._internal_loop.call_soon_threadsafe(
            self.__update_net_ifs,
            net_ifs)

    async def vote_for_lan_ctrl_async(self, key: str, vote: bool) -> None:
        _LOGGER.info('vote for lan ctrl, %s, %s', key, vote)
        self._lan_ctrl_vote_map[key] = vote
        if not any(self._lan_ctrl_vote_map.values()):
            await self.deinit_async()
            return
        await self.init_async()

    async def update_subscribe_option(self, enable_subscribe: bool) -> None:
        _LOGGER.info('update subscribe option, %s', enable_subscribe)
        if not self._init_done:
            self._enable_subscribe = enable_subscribe
            return
        self._internal_loop.call_soon_threadsafe(
            self.__update_subscribe_option,
            {'enable_subscribe': enable_subscribe})

    def update_devices(self, devices: dict[str, dict]) -> bool:
        _LOGGER.info('update devices, %s', devices)
        if not self._init_done:
            return False
        self._internal_loop.call_soon_threadsafe(
            self.__update_devices, devices)
        return True

    def delete_devices(self, devices: list[str]) -> bool:
        _LOGGER.info('delete devices, %s', devices)
        if not self._init_done:
            return False
        self._internal_loop.call_soon_threadsafe(
            self.__delete_devices, devices)
        return True

    def sub_lan_state(
        self, key: str, handler: Callable[[bool], Coroutine]
    ) -> None:
        self._lan_state_sub_map[key] = handler

    def unsub_lan_state(self, key: str) -> None:
        self._lan_state_sub_map.pop(key, None)

    @final
    def sub_device_state(
        self, key: str, handler: Callable[[str, dict, Any], Coroutine],
        handler_ctx: Any = None
    ) -> bool:
        if not self._init_done:
            return False
        self._internal_loop.call_soon_threadsafe(
            self.__sub_device_state,
            _MIoTLanSubDeviceData(
                key=key, handler=handler, handler_ctx=handler_ctx))
        return True

    @final
    def unsub_device_state(self, key: str) -> bool:
        if not self._init_done:
            return False
        self._internal_loop.call_soon_threadsafe(
            self.__unsub_device_state, _MIoTLanUnsubDeviceData(key=key))
        return True

    @final
    def sub_prop(
        self,
        did: str,
        handler: Callable[[dict, Any], None],
        siid: Optional[int] = None,
        piid: Optional[int] = None,
        handler_ctx: Any = None
    ) -> bool:
        if not self._init_done:
            return False
        if not self._enable_subscribe:
            return False
        key = (
            f'{did}/p/'
            f'{"#" if siid is None or piid is None else f"{siid}/{piid}"}')
        self._internal_loop.call_soon_threadsafe(
            self.__sub_broadcast,
            _MIoTLanRegisterBroadcastData(
                key=key, handler=handler, handler_ctx=handler_ctx))
        return True

    @final
    def unsub_prop(
        self,
        did: str,
        siid: Optional[int] = None,
        piid: Optional[int] = None
    ) -> bool:
        if not self._init_done:
            return False
        if not self._enable_subscribe:
            return False
        key = (
            f'{did}/p/'
            f'{"#" if siid is None or piid is None else f"{siid}/{piid}"}')
        self._internal_loop.call_soon_threadsafe(
            self.__unsub_broadcast,
            _MIoTLanUnregisterBroadcastData(key=key))
        return True

    @final
    def sub_event(
        self,
        did: str,
        handler: Callable[[dict, Any], None],
        siid: Optional[int] = None,
        eiid: Optional[int] = None,
        handler_ctx: Any = None
    ) -> bool:
        if not self._init_done:
            return False
        if not self._enable_subscribe:
            return False
        key = (
            f'{did}/e/'
            f'{"#" if siid is None or eiid is None else f"{siid}/{eiid}"}')
        self._internal_loop.call_soon_threadsafe(
            self.__sub_broadcast,
            _MIoTLanRegisterBroadcastData(
                key=key, handler=handler, handler_ctx=handler_ctx))
        return True

    @final
    def unsub_event(
        self,
        did: str,
        siid: Optional[int] = None,
        eiid: Optional[int] = None
    ) -> bool:
        if not self._init_done:
            return False
        if not self._enable_subscribe:
            return False
        key = (
            f'{did}/e/'
            f'{"#" if siid is None or eiid is None else f"{siid}/{eiid}"}')
        self._internal_loop.call_soon_threadsafe(
            self.__unsub_broadcast,
            _MIoTLanUnregisterBroadcastData(key=key))
        return True

    @final
    async def get_prop_async(
        self, did: str, siid: int, piid: int, timeout_ms: int = 10000
    ) -> Any:
        self.__assert_service_ready()
        
        device = self._lan_devices.get(did)
        if device and device.model and device.model in MIIO_SPECS:
            return await self.__get_prop_miio_async(device, siid, piid, timeout_ms)
            
        result_obj = await self.__call_api_async(
            did=did, msg={
                'method': 'get_properties',
                'params': [{'did': did, 'siid': siid, 'piid': piid}]
            }, timeout_ms=timeout_ms)

        if (
            result_obj and 'result' in result_obj
            and len(result_obj['result']) == 1
            and 'did' in result_obj['result'][0]
            and result_obj['result'][0]['did'] == did
        ):
            return result_obj['result'][0].get('value', None)
        return None

    @final
    async def set_prop_async(
        self, did: str, siid: int, piid: int, value: Any,
        timeout_ms: int = 10000, props: dict = None, max_val: int = 100
    ) -> dict:
        self.__assert_service_ready()
        
        device = self._lan_devices.get(did)
        if device and device.model and device.model in MIIO_SPECS:
            return await self.__set_prop_miio_async(device, siid, piid, value, timeout_ms, props, max_val)
            
        result_obj = await self.__call_api_async(
            did=did, msg={
                'method': 'set_properties',
                'params': [{
                    'did': did, 'siid': siid, 'piid': piid, 'value': value}]
            }, timeout_ms=timeout_ms)
        if result_obj:
            if (
                'result' in result_obj
                and len(result_obj['result']) == 1
                and 'did' in result_obj['result'][0]
                and result_obj['result'][0]['did'] == did
                and 'code' in result_obj['result'][0]
            ):
                return result_obj['result'][0]
            if 'code' in result_obj:
                return result_obj
        raise MIoTError('Invalid result', MIoTErrorCode.CODE_INTERNAL_ERROR)

    async def __get_prop_miio_async(self, device: _MIoTLanDevice, siid: int, piid: int, timeout_ms: int) -> Any:
        spec = MIIO_SPECS[device.model]
        prop_key = f"prop.{siid}.{piid}"
        if "miio_specs" not in spec or prop_key not in spec["miio_specs"]:
            return None
        
        prop_cfg = spec["miio_specs"][prop_key]
        prop_name = prop_cfg.get("prop")
        if not prop_name:
            return None
            
        # Call get_prop
        result_obj = await self.__call_api_async(
            did=device.did, msg={
                'method': 'get_prop',
                'params': [prop_name]
            }, timeout_ms=timeout_ms)
            
        if result_obj and 'result' in result_obj and len(result_obj['result']) > 0:
            val = result_obj['result'][0]
            
            # Inverse translate the value using dict mapping if exists
            # (In practice, Jinja templates in MIIO_TO_MIOT_SPECS mostly translate in one direction for set_prop, 
            #  for get_prop we check if 'dict' has a reverse mapping or we just return it)
            if 'dict' in prop_cfg:
                for k, v in prop_cfg['dict'].items():
                    if str(v) == str(val):
                        # Some values might be bools or ints in python but returned as string
                        if k.isdigit():
                            val = int(k)
                        else:
                            val = k
                        break
            
            # Apply format cast if needed
            if prop_cfg.get('format') == 'onoff':
                return val == 'on' or val == True
                
            return val
            
        return None
        
    async def __set_prop_miio_async(
        self, device: _MIoTLanDevice, siid: int, piid: int, value: Any,
        timeout_ms: int, props: dict = None, max_val: int = 100
    ) -> dict:
        spec = MIIO_SPECS[device.model]
        prop_key = f"prop.{siid}.{piid}"
        if "miio_specs" not in spec or prop_key not in spec["miio_specs"]:
            raise MIoTError('Unsupported property', MIoTErrorCode.CODE_INVALID_PROPERTY)
            
        prop_cfg = spec["miio_specs"][prop_key]
        setter = prop_cfg.get("setter")
        if not setter:
            raise MIoTError('Property not writable', MIoTErrorCode.CODE_PROPERTY_NOT_WRITABLE)
            
        method = setter if isinstance(setter, str) else f"set_{prop_cfg.get('prop')}"
        params = [value]
        
        # Apply forward mapping
        if 'dict' in prop_cfg and str(value) in prop_cfg['dict']:
            params = [prop_cfg['dict'][str(value)]]
            
        if 'set_template' in prop_cfg and callable(prop_cfg['set_template']):
            try:
                # set_template is our Python lambda!
                # Signature: lambda value, props, max_val
                new_params = prop_cfg['set_template'](value, props or {}, max_val)
                if isinstance(new_params, dict) and 'method' in new_params:
                    method = new_params.get('method', method)
                    params = new_params.get('params', params)
                elif isinstance(new_params, list):
                    params = new_params
                else:
                    params = [new_params]
            except Exception as err:
                _LOGGER.error("Failed to execute set_template lambda for %s %s: %s", device.did, prop_key, err)
        elif prop_cfg.get('format') == 'onoff':
            params = ["on" if value else "off"]
            
        result_obj = await self.__call_api_async(
            did=device.did, msg={
                'method': method,
                'params': params
            }, timeout_ms=timeout_ms)
            
        if result_obj and 'result' in result_obj:
            return {'did': device.did, 'siid': siid, 'piid': piid, 'code': 0}
            
        if result_obj and 'code' in result_obj:
            return result_obj
            
        raise MIoTError('Invalid result', MIoTErrorCode.CODE_INTERNAL_ERROR)

    @final
    async def action_async(
        self, did: str, siid: int, aiid: int, in_list: list,
        timeout_ms: int = 10000
    ) -> dict:
        self.__assert_service_ready()
        result_obj = await self.__call_api_async(
            did=did, msg={
                'method': 'action',
                'params': {
                    'did': did, 'siid': siid, 'aiid': aiid, 'in': in_list}
            }, timeout_ms=timeout_ms)
        if result_obj:
            if 'result' in result_obj and 'code' in result_obj['result']:
                return result_obj['result']
            if 'code' in result_obj:
                return result_obj
        raise MIoTError('Invalid result', MIoTErrorCode.CODE_INTERNAL_ERROR)

    @final
    async def get_dev_list_async(
        self, timeout_ms: int = 10000
    ) -> dict[str, dict]:
        if not self._init_done:
            return {}

        def get_device_list_handler(msg: dict, fut: asyncio.Future):
            self._main_loop.call_soon_threadsafe(
                fut.set_result, msg)

        fut: asyncio.Future = self._main_loop.create_future()
        self._internal_loop.call_soon_threadsafe(
            self.__get_dev_list,
            _MIoTLanGetDevListData(
                handler=get_device_list_handler,
                handler_ctx=fut,
                timeout_ms=timeout_ms))
        return await fut

    async def __call_api_async(
        self, did: str, msg: dict, timeout_ms: int = 10000
    ) -> dict:
        def call_api_handler(msg: dict, fut: asyncio.Future):
            self._main_loop.call_soon_threadsafe(
                fut.set_result, msg)

        fut: asyncio.Future = self._main_loop.create_future()
        self._internal_loop.call_soon_threadsafe(
            self.__call_api, did, msg, call_api_handler, fut, timeout_ms)
        return await fut

    async def __on_network_info_change_external_async(
        self,
        status: InterfaceStatus,
        info: NetworkInfo
    ) -> None:
        _LOGGER.info(
            'on network info change, status: %s, info: %s', status, info)
        available_net_ifs = set()
        for if_name in list(self._network.network_info.keys()):
            available_net_ifs.add(if_name)
        if len(available_net_ifs) == 0:
            await self.deinit_async()
            self._available_net_ifs = available_net_ifs
            return
        if self._net_ifs.isdisjoint(available_net_ifs):
            _LOGGER.info('no valid net_ifs')
            await self.deinit_async()
            self._available_net_ifs = available_net_ifs
            return
        if not self._init_done:
            self._available_net_ifs = available_net_ifs
            await self.init_async()
            return
        self._internal_loop.call_soon_threadsafe(
            self.__on_network_info_change,
            _MIoTLanNetworkUpdateData(status=status, if_name=info.name))

    async def __on_mips_service_change(
        self, group_id: str,  state: MipsServiceState, data: dict
    ) -> None:
        _LOGGER.info(
            'on mips service change, %s, %s, %s',  group_id, state, data)
        if self._ignore_mips_service:
            _LOGGER.info('ignore mips service change due to ignore_mips_service flag, init miot lan')
            if not self._init_done:
                await self.init_async()
            return

        if len(self._mips_service.get_services()) > 0:
            _LOGGER.info('find central service, deinit miot lan')
            await self.deinit_async()
        else:
            _LOGGER.info('no central service, init miot lan')
            await self.init_async()

# The following methods SHOULD ONLY be called in the internal loop


    def ping(self, if_name: Optional[str], target_ip: str) -> None:
        if not target_ip:
            return
        self.__sendto(
            if_name=if_name, data=self._probe_msg, address=target_ip,
            port=self.OT_PORT)

    def send2device(
        self, did: str,
        msg: dict,
        handler: Optional[Callable[[dict, Any], None]] = None,
        handler_ctx: Any = None,
        timeout_ms: Optional[int] = None
    ) -> None:
        if timeout_ms and not handler:
            raise ValueError('handler is required when timeout_ms is set')
        device: Optional[_MIoTLanDevice] = self._lan_devices.get(did)
        if not device:
            raise ValueError('invalid device')
        if not device.cipher:
            raise ValueError('invalid device cipher')
        if not device.if_name:
            raise ValueError('invalid device if_name')
        if not device.ip:
            raise ValueError('invalid device ip')
        in_msg = {'id': self.__gen_msg_id(), **msg}
        msg_len = device.gen_packet(
            out_buffer=self._write_buffer,
            clear_data=in_msg,
            did=did,
            offset=int(time.time())-device.offset)

        return self.__make_request(
            msg_id=in_msg['id'],
            msg=self._write_buffer[0: msg_len],
            if_name=device.if_name,
            ip=device.ip,
            handler=handler,
            handler_ctx=handler_ctx,
            timeout_ms=timeout_ms)

    def __make_request(
        self,
        msg_id: int,
        msg: bytearray,
        if_name: str,
        ip: str,
        handler: Optional[Callable[[dict, Any], None]],
        handler_ctx: Any = None,
        timeout_ms: Optional[int] = None
    ) -> None:
        def request_timeout_handler(req_data: _MIoTLanRequestData):
            self._pending_requests.pop(req_data.msg_id, None)
            if req_data and req_data.handler:
                req_data.handler({
                    'code': MIoTErrorCode.CODE_TIMEOUT.value,
                    'error': 'timeout'},
                    req_data.handler_ctx)

        timer: Optional[asyncio.TimerHandle] = None
        request_data = _MIoTLanRequestData(
            msg_id=msg_id,
            handler=handler,
            handler_ctx=handler_ctx,
            timeout=timer)
        if timeout_ms:
            timer = self._internal_loop.call_later(
                timeout_ms/1000, request_timeout_handler, request_data)
            request_data.timeout = timer
        self._pending_requests[msg_id] = request_data
        self.__sendto(if_name=if_name, data=msg, address=ip, port=self.OT_PORT)

    def broadcast_device_state(self, did: str, state: dict) -> None:
        # Optimized: 使用原生的 run_coroutine_threadsafe 將任務安全排入主迴圈
        for handler in self._device_state_sub_map.values():
            asyncio.run_coroutine_threadsafe(
                handler.handler(did, state, handler.handler_ctx),
                self._main_loop
            )

    def __gen_msg_id(self) -> int:
        if not self._msg_id_counter:
            self._msg_id_counter = int(random.random()*0x7FFFFFFF)
        self._msg_id_counter += 1
        if self._msg_id_counter > 0x80000000:
            self._msg_id_counter = 1
        return self._msg_id_counter

    def __call_api(
        self,
        did: str,
        msg: dict,
        handler: Callable,
        handler_ctx: Any,
        timeout_ms: int = 10000
    ) -> None:
        try:
            self.send2device(
                did=did,
                msg={'from': 'ha.xiaomi_home', **msg},
                handler=handler,
                handler_ctx=handler_ctx,
                timeout_ms=timeout_ms)
        except Exception as err:  # pylint: disable=broad-exception-caught
            _LOGGER.error('send2device error, %s', err)
            handler({
                'code': MIoTErrorCode.CODE_INTERNAL_ERROR.value,
                'error': str(err)},
                handler_ctx)

    def __sub_device_state(self, data: _MIoTLanSubDeviceData) -> None:
        self._device_state_sub_map[data.key] = data

    def __unsub_device_state(self, data: _MIoTLanUnsubDeviceData) -> None:
        self._device_state_sub_map.pop(data.key, None)

    def __sub_broadcast(self, data: _MIoTLanRegisterBroadcastData) -> None:
        self._device_msg_matcher[data.key] = data
        _LOGGER.debug('lan register broadcast, %s', data.key)

    def __unsub_broadcast(self, data: _MIoTLanUnregisterBroadcastData) -> None:
        if self._device_msg_matcher.get(topic=data.key):
            del self._device_msg_matcher[data.key]
        _LOGGER.debug('lan unregister broadcast, %s', data.key)

    def __get_dev_list(self, data: _MIoTLanGetDevListData) -> None:
        dev_list = {
            device.did: {
                'online': device.online,
                'push_available': device.subscribed
            }
            for device in self._lan_devices.values()
            if device.online}
        data.handler(
            dev_list, data.handler_ctx)

    def __update_devices(self, devices: dict[str, dict]) -> None:
        for did, info in devices.items():
            # did MUST be digit(UINT64)
            if not did.isdigit():
                _LOGGER.info('invalid did, %s', did)
                continue
                
            model = info.get('model')
            
            if model in MIIO_SPECS:
                _LOGGER.info('model supports miio native transpilation, %s, %s', did, model)
            elif (
                    'model' not in info
                    or info['model'] in self._profile_models):
                # Do not support the local control of
                # Profile device for the time being
                _LOGGER.info(
                    'model not support local ctrl, %s, %s',
                    did, model)
                continue
                
            if did not in self._lan_devices:
                if 'token' not in info:
                    _LOGGER.error(
                        'token not found, %s, %s', did, info)
                    continue
                if len(info['token']) != 32:
                    _LOGGER.error(
                        'invalid device token, %s, %s', did, info)
                    continue
                self._lan_devices[did] = _MIoTLanDevice(
                    manager=self, did=did, token=info['token'],
                    ip=info.get('ip', None), model=model)
            else:
                self._lan_devices[did].update_info(info)
                self._lan_devices[did].model = model

    def __delete_devices(self, devices: list[str]) -> None:
        for did in devices:
            lan_device = self._lan_devices.pop(did, None)
            if not lan_device:
                continue
            lan_device.on_delete()

    def __on_network_info_change(self, data: _MIoTLanNetworkUpdateData) -> None:
        if data.status == InterfaceStatus.ADD:
            self._available_net_ifs.add(data.if_name)
            if data.if_name in self._net_ifs:
                self.__create_socket(if_name=data.if_name)
        elif data.status == InterfaceStatus.REMOVE:
            self._available_net_ifs.remove(data.if_name)
            self.__destroy_socket(if_name=data.if_name)

    def __update_net_ifs(self, net_ifs: list[str]) -> None:
        if self._net_ifs != set(net_ifs):
            self._net_ifs = set(net_ifs)
            for if_name in self._net_ifs:
                self.__create_socket(if_name=if_name)
            for if_name in list(self._broadcast_socks.keys()):
                if if_name not in self._net_ifs:
                    self.__destroy_socket(if_name=if_name)

    def __update_subscribe_option(self, options: dict) -> None:
        if 'enable_subscribe' in options:
            if options['enable_subscribe'] != self._enable_subscribe:
                self._enable_subscribe = options['enable_subscribe']
                if not self._enable_subscribe:
                    # Unsubscribe all
                    for device in self._lan_devices.values():
                        device.unsubscribe()

    def __deinit(self) -> None:
        # Release all resources
        if self._scan_timer:
            self._scan_timer.cancel()
            self._scan_timer = None
        for device in self._lan_devices.values():
            device.on_delete()
        self._lan_devices.clear()
        for req_data in self._pending_requests.values():
            if req_data.timeout:
                req_data.timeout.cancel()
                req_data.timeout = None
        self._pending_requests.clear()
        for timer in self._reply_msg_buffer.values():
            timer.cancel()
        self._reply_msg_buffer.clear()
        self._device_msg_matcher = MIoTMatcher()
        self.__deinit_socket()
        self._internal_loop.stop()

    def __init_socket(self) -> None:
        self.__deinit_socket()
        for if_name in self._net_ifs:
            if if_name not in self._available_net_ifs:
                return
            self.__create_socket(if_name=if_name)

    def __create_socket(self, if_name: str) -> None:
        if if_name in self._broadcast_socks:
            _LOGGER.info('socket already created, %s', if_name)
            return
        # Create socket
        try:
            sock = socket.socket(
                socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            # Set SO_BINDTODEVICE
            sock.setsockopt(
                socket.SOL_SOCKET, socket.SO_BINDTODEVICE, if_name.encode())
            sock.bind(('', self._local_port or 0))
            self._internal_loop.add_reader(
                sock.fileno(), self.__socket_read_handler, (if_name, sock))
            self._broadcast_socks[if_name] = sock
            self._local_port = self._local_port or sock.getsockname()[1]
            _LOGGER.info(
                'created socket, %s, %s', if_name, self._local_port)
        except Exception as err:  # pylint: disable=broad-exception-caught
            _LOGGER.error('create socket error, %s, %s', if_name, err)

    def __deinit_socket(self) -> None:
        for if_name in list(self._broadcast_socks.keys()):
            self.__destroy_socket(if_name)
        self._broadcast_socks.clear()

    def __destroy_socket(self, if_name: str) -> None:
        sock = self._broadcast_socks.pop(if_name, None)
        if not sock:
            return
        self._internal_loop.remove_reader(sock.fileno())
        sock.close()
        _LOGGER.info('destroyed socket, %s', if_name)

    def __socket_read_handler(self, ctx: tuple[str, socket.socket]) -> None:
        try:
            data_len, addr = ctx[1].recvfrom_into(
                self._read_buffer, self.OT_MSG_LEN, socket.MSG_DONTWAIT)
            if data_len < 0:
                # Socket error
                _LOGGER.error('socket read error, %s, %s', ctx[0], data_len)
                return
            if addr[1] != self.OT_PORT:
                # Not ot msg
                return
            self.__raw_message_handler(
                self._read_buffer[:data_len], data_len, addr[0], ctx[0])
        except Exception as err:  # pylint: disable=broad-exception-caught
            _LOGGER.error('socket read handler error, %s', err)

    def __raw_message_handler(
        self, data: bytearray, data_len: int, ip: str, if_name: str
    ) -> None:
        if data[:2] != self.OT_HEADER:
            return
        # Keep alive message
        did: str = str(struct.unpack('>Q', data[4:12])[0])
        device: Optional[_MIoTLanDevice] = self._lan_devices.get(did)
        if not device:
            return
        timestamp: int = struct.unpack('>I', data[12:16])[0]
        device.offset = int(time.time()) - timestamp
        # Keep alive if this is a probe
        if data_len == self.OT_PROBE_LEN or device.subscribed:
            device.keep_alive(ip=ip, if_name=if_name)
        # Manage device subscribe status
        if (
            self._enable_subscribe
            and data_len == self.OT_PROBE_LEN
            and data[16:20] == b'MSUB'
            and data[24:27] == b'PUB'
        ):
            device.supported_wildcard_sub = (
                int(data[28]) == self.OT_SUPPORT_WILDCARD_SUB)
            sub_ts = struct.unpack('>I', data[20:24])[0]
            sub_type = int(data[27])
            if (
                device.supported_wildcard_sub
                and sub_type in [0, 1, 4]
                and sub_ts != device.sub_ts
            ):
                device.subscribed = False
                try:
                    device.subscribe()
                except Exception as err:
                    _LOGGER.error('subscribe device error, %s, %s', did, err)
        if data_len > self.OT_PROBE_LEN:
            # handle device message
            try:
                decrypted_data = device.decrypt_packet(data)
            except Exception as err:   # pylint: disable=broad-exception-caught
                _LOGGER.error('decrypt packet error, %s, %s', did, err)
                return
            
            # Since decryption succeeded, the packet is authentic. Update IP and if_name.
            device.keep_alive(ip=ip, if_name=if_name)
            
            try:
                self.__message_handler(did, decrypted_data)
            except Exception as err:
                _LOGGER.error('handle lan message error, %s, %s', did, err)
                return

    def __message_handler(self, did: str, msg: dict) -> None:
        if 'id' not in msg:
            _LOGGER.warning('invalid message, no id, %s, %s', did, msg)
            return
        # Reply
        req: Optional[_MIoTLanRequestData] = (
            self._pending_requests.pop(msg['id'], None))
        if req:
            if req.timeout:
                req.timeout.cancel()
                req.timeout = None
            if req.handler is not None:
                self._main_loop.call_soon_threadsafe(
                    req.handler, msg, req.handler_ctx)
            return
        # Handle up link message
        if 'method' not in msg or 'params' not in msg:
            _LOGGER.debug(
                'invalid message, no method or params, %s, %s', did, msg)
            return
        # Filter dup message
        if self.__filter_dup_message(did, msg['id']):
            self.send2device(
                did=did, msg={'id': msg['id'], 'result': {'code': 0}})
            return
        _LOGGER.debug('lan message, %s, %s', did, msg)
        if msg['method'] == 'properties_changed':
            for param in msg['params']:
                if 'siid' not in param and 'piid' not in param:
                    _LOGGER.debug(
                        'invalid message, no siid or piid, %s, %s', did, msg)
                    continue
                key = f'{did}/p/{param["siid"]}/{param["piid"]}'
                subs: list[_MIoTLanRegisterBroadcastData] = list(
                    self._device_msg_matcher.iter_match(key))
                for sub in subs:
                    self._main_loop.call_soon_threadsafe(
                        sub.handler, param, sub.handler_ctx)
        elif (
                msg['method'] == 'event_occured'
                and 'siid' in msg['params']
                and 'eiid' in msg['params']
        ):
            key = f'{did}/e/{msg["params"]["siid"]}/{msg["params"]["eiid"]}'
            subs: list[_MIoTLanRegisterBroadcastData] = list(
                self._device_msg_matcher.iter_match(key))
            for sub in subs:
                self._main_loop.call_soon_threadsafe(
                    sub.handler, msg['params'], sub.handler_ctx)
        else:
            _LOGGER.debug(
                'invalid message, unknown method, %s, %s', did, msg)
        # Reply
        self.send2device(
            did=did, msg={'id': msg['id'], 'result': {'code': 0}})

    def __filter_dup_message(self, did: str, msg_id: int) -> bool:
        filter_id = f'{did}.{msg_id}'
        if filter_id in self._reply_msg_buffer:
            return True
            
        # Optimized: 移除不必要的 lambda，直接將 pop 方法與參數傳給 call_later
        self._reply_msg_buffer[filter_id] = self._internal_loop.call_later(
            5, self._reply_msg_buffer.pop, filter_id, None
        )
        return False

    def __sendto(
        self, if_name: Optional[str], data: bytes, address: str, port: int
    ) -> None:
        if if_name is None:
            # Broadcast
            for if_n, sock in self._broadcast_socks.items():
                _LOGGER.debug('send broadcast, %s', if_n)
                sock.sendto(data, socket.MSG_DONTWAIT, (address, port))
        else:
            # Unicast
            sock = self._broadcast_socks.get(if_name, None)
            if not sock:
                _LOGGER.error('invalid socket, %s', if_name)
                return
            sock.sendto(data, socket.MSG_DONTWAIT, (address, port))

    def __scan_devices(self) -> None:
        if self._scan_timer:
            self._scan_timer.cancel()
            self._scan_timer = None
        try:
            # Broadcast probe
            self.ping(if_name=None, target_ip='255.255.255.255')
            # Unicast probe to known IPs
            for device in self._lan_devices.values():
                if device.ip:
                    # Send unicast probe out of all broadcast sockets to ensure routing handles it
                    for if_name in self._broadcast_socks:
                        self.ping(if_name=if_name, target_ip=device.ip)
        except Exception as err:  # pylint: disable=broad-exception-caught
            # Optimized: 移除了多餘且無意義的 pass
            _LOGGER.error('ping device error, %s', err)
            
        scan_time = self.__get_next_scan_time()
        self._scan_timer = self._internal_loop.call_later(
            scan_time, self.__scan_devices)
        _LOGGER.debug('next scan time: %ss', scan_time)

    def __get_next_scan_time(self) -> float:
        if not self._last_scan_interval:
            self._last_scan_interval = self.OT_PROBE_INTERVAL_MIN
        self._last_scan_interval = min(
            self._last_scan_interval*2, self.OT_PROBE_INTERVAL_MAX)
        return self._last_scan_interval