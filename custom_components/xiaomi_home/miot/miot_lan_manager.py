import asyncio
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .miot_client import MIoTClient

_LOGGER = logging.getLogger(__name__)

class MIoTLanManager:
    """Manager for handling MIoT LAN and GW polling and sync logic."""

    def __init__(self, client: "MIoTClient") -> None:
        self.client = client

    async def refresh_props_from_lan(self) -> bool:
        if not self.client.miot_lan.init_done:
            return False
        request_list = {}
        succeed_once = False
        for key in list(self.client.refresh_props_list.keys()):
            did = key.split('|')[0]
            if did in request_list:
                continue
            if did not in self.client.device_list_lan:
                continue
            params = self.client.refresh_props_list.pop(key)
            request_list[did] = {
                **params,
                'fut': self.client.miot_lan.get_prop_async(
                    did=did, siid=params['siid'], piid=params['piid'],
                    timeout_ms=6000)}
        results = await asyncio.gather(
            *[v['fut'] for v in request_list.values()])
        for (did, param), result in zip(request_list.items(), results):
            if result is None:
                continue
            self.client.on_prop_msg(
                params={
                    'did': did,
                    'siid': param['siid'],
                    'piid': param['piid'],
                    'value': result},
                ctx=None)
            succeed_once = True
        if succeed_once:
            return True
        _LOGGER.debug(
            'refresh props failed, lan, %s', list(request_list.keys()))
        self.client.refresh_props_list.update(request_list)
        return False

    async def refresh_props_from_gw(self) -> bool:
        if not self.client.mips_local or not self.client.device_list_gateway:
            return False
        request_list = {}
        succeed_once = False
        for key in list(self.client.refresh_props_list.keys()):
            did = key.split('|')[0]
            if did in request_list:
                continue
            device_gw = self.client.device_list_gateway.get(did, None)
            if not device_gw:
                continue
            mips_gw = self.client.mips_local.get(device_gw['group_id'], None)
            if not mips_gw:
                _LOGGER.error('mips gateway not exist, %s', key)
                continue
            params = self.client.refresh_props_list.pop(key)
            request_list[did] = {
                **params,
                'fut': mips_gw.get_prop_async(
                    did=did, siid=params['siid'], piid=params['piid'],
                    timeout_ms=6000)}
        results = await asyncio.gather(
            *[v['fut'] for v in request_list.values()])
        for (did, param), result in zip(request_list.items(), results):
            if result is None:
                continue
            self.client.on_prop_msg(
                params={
                    'did': did,
                    'siid': param['siid'],
                    'piid': param['piid'],
                    'value': result},
                ctx=None)
            succeed_once = True
        if succeed_once:
            return True
        _LOGGER.debug(
            'refresh props failed, gw, %s', list(request_list.keys()))
        self.client.refresh_props_list.update(request_list)
        return False
