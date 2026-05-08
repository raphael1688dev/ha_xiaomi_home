# -*- coding: utf-8 -*-
"""
MIoT central hub gateway service discovery.
"""
import asyncio
import base64
import copy
from enum import Enum
from typing import Callable, Coroutine, Optional
import logging

from zeroconf import (
    DNSQuestionType,
    IPVersion,
    ServiceStateChange,
    Zeroconf)
from zeroconf.asyncio import (
    AsyncServiceInfo,
    AsyncZeroconf,
    AsyncServiceBrowser)

# pylint: disable=relative-beyond-top-level
from .miot_error import MipsServiceError

_LOGGER = logging.getLogger(__name__)

MIPS_MDNS_TYPE = '_miot-central._tcp.local.'
MIPS_MDNS_REQUEST_TIMEOUT_MS = 5000
MIPS_MDNS_UPDATE_INTERVAL_S = 600


class MipsServiceState(Enum):
    ADDED = 1
    REMOVED = 2
    UPDATED = 3


class MipsServiceData:
    """Mips service data."""
    profile: str
    profile_bin: bytes

    name: str
    addresses: list[str]
    port: int
    type: str
    server: str

    did: str
    group_id: str
    role: int
    suite_mqtt: bool

    def __init__(self, service_info: AsyncServiceInfo) -> None:
        if service_info is None:
            raise MipsServiceError('invalid params')
        properties: dict = service_info.decoded_properties
        if not properties:
            raise MipsServiceError('invalid service properties')
        
        self.profile = properties.get('profile', None)
        if self.profile is None:
            raise MipsServiceError('invalid service profile')
            
        self.profile_bin = base64.b64decode(self.profile)
        self.name = service_info.name
        self.addresses = service_info.parsed_addresses(version=IPVersion.V4Only)
        if not self.addresses:
            raise MipsServiceError('invalid addresses')
        if not service_info.port:
            raise MipsServiceError('invalid port')
            
        self.port = service_info.port
        self.type = service_info.type
        self.server = service_info.server or ''
        
        # Parse profile
        self.did = str(int.from_bytes(self.profile_bin[1:9], byteorder='big'))
        # 優化: 使用 bytes 內建的 .hex() 取代 binascii 模組
        self.group_id = self.profile_bin[9:17][::-1].hex()
        self.role = int(self.profile_bin[20] >> 4)
        self.suite_mqtt = ((self.profile_bin[22] >> 1) & 0x01) == 0x01

    def valid_service(self) -> bool:
        return self.role == 1 and self.suite_mqtt

    def to_dict(self) -> dict:
        return {
            'name': self.name,
            'addresses': self.addresses,
            'port': self.port,
            'type': self.type,
            'server': self.server,
            'did': self.did,
            'group_id': self.group_id,
            'role': self.role,
            'suite_mqtt': self.suite_mqtt
        }

    def __str__(self) -> str:
        return str(self.to_dict())


class MipsService:
    """MIPS service discovery."""
    _aiozc: AsyncZeroconf
    _main_loop: asyncio.AbstractEventLoop
    _aio_browser: AsyncServiceBrowser
    _services: dict[str, dict]
    # key = (key, group_id)
    _sub_list: dict[tuple[str, str], Callable[[
        str, MipsServiceState, dict], Coroutine]]

    def __init__(
        self, aiozc: AsyncZeroconf,
        loop: Optional[asyncio.AbstractEventLoop] = None
    ) -> None:
        self._aiozc = aiozc
        self._main_loop = loop or asyncio.get_running_loop()

        self._services = {}
        self._sub_list = {}

    async def init_async(self) -> None:
        await self._aiozc.zeroconf.async_wait_for_start()

        self._aio_browser = AsyncServiceBrowser(
            zeroconf=self._aiozc.zeroconf,
            type_=MIPS_MDNS_TYPE,
            handlers=[self.__on_service_state_change],
            question_type=DNSQuestionType.QM)

    async def deinit_async(self) -> None:
        if hasattr(self, '_aio_browser'):
            await self._aio_browser.async_cancel()
        self._services.clear()
        self._sub_list.clear()

    def get_services(self, group_id: Optional[str] = None) -> dict[str, dict]:
        """get mips services."""
        if group_id:
            if group_id not in self._services:
                return {}
            return {group_id: copy.deepcopy(self._services[group_id])}
        return copy.deepcopy(self._services)

    def sub_service_change(
            self, key: str, group_id: str,
            handler: Callable[[str, MipsServiceState, dict], Coroutine]
    ) -> None:
        if not key or not group_id or not handler:
            raise MipsServiceError('invalid params')
        self._sub_list[(key, group_id)] = handler

    def unsub_service_change(self, key: str) -> None:
        if not key:
            return
        # 優化: 找出目標 keys 一次性移除，避免在迴圈中做無謂的 tuple 索引存取
        keys_to_remove = [k for k in self._sub_list if k[0] == key]
        for k in keys_to_remove:
            self._sub_list.pop(k, None)

    def __on_service_state_change(
            self, zeroconf: Zeroconf, service_type: str, name: str,
            state_change: ServiceStateChange
    ) -> None:
        _LOGGER.debug(
            'mdns discovery changed, %s, %s, %s',
            state_change, name, service_type)

        # 優化: 修正原本穿透造成對已離線設備發送 async_request 引發 5 秒超時阻塞的問題
        if state_change is ServiceStateChange.Removed:
            _LOGGER.debug('Ignore mdns REMOVED package for: %s', name)
            return
            
        self._main_loop.create_task(
            self.__request_service_info_async(zeroconf, service_type, name))

    async def __request_service_info_async(
            self, zeroconf: Zeroconf, service_type: str, name: str
    ) -> None:
        info = AsyncServiceInfo(service_type, name)
        await info.async_request(
            zeroconf, MIPS_MDNS_REQUEST_TIMEOUT_MS,
            question_type=DNSQuestionType.QU)

        try:
            service_data = MipsServiceData(info)
            if not service_data.valid_service():
                raise MipsServiceError(
                    'no primary role, no support mqtt connection')
                    
            if service_data.group_id in self._services:
                # Update mips service
                buffer_data = self._services[service_data.group_id]
                if (
                    service_data.did != buffer_data['did']
                    or service_data.addresses != buffer_data['addresses']
                    or service_data.port != buffer_data['port']
                ):
                    self._services[service_data.group_id].update(
                        service_data.to_dict())
                    self.__call_service_change(
                        state=MipsServiceState.UPDATED,
                        data=service_data.to_dict())
            else:
                # Add mips service
                self._services[service_data.group_id] = service_data.to_dict()
                self.__call_service_change(
                    state=MipsServiceState.ADDED,
                    data=self._services[service_data.group_id])
        except MipsServiceError as error:
            # 加上 info.name 方便除錯，避免印出整個 info 物件造成 log 過於凌亂
            _LOGGER.error('invalid mips service, %s, %s', error, info.name)

    def __call_service_change(
        self, state: MipsServiceState, data: dict
    ) -> None:
        _LOGGER.info('call service change, %s, %s', state, data)
        target_group = data.get('group_id')
        
        # 優化: 透過 tuple 解構讓配對邏輯更清晰
        for (k_key, k_group), handler in list(self._sub_list.items()):
            if k_group in (target_group, '*'):
                self._main_loop.create_task(
                    handler(target_group, state, data))