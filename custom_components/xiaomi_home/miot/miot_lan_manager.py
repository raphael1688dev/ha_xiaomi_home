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
        futures = []
        task_keys = []
        for key in list(self.client.refresh_props_list.keys()):
            did = key.split('|')[0]
            if any(k.startswith(f'{did}|') for k in task_keys):
                continue
            if did not in self.client.device_list_lan:
                continue
            params = self.client.refresh_props_list.pop(key)
            if not isinstance(params, dict) or 'did' not in params or 'siid' not in params or 'piid' not in params:
                continue
            clean_param = {
                'did': params['did'],
                'siid': params['siid'],
                'piid': params['piid'],
            }
            request_list[key] = clean_param
            task_keys.append(key)
            futures.append(self.client.miot_lan.get_prop_async(
                did=did, siid=params['siid'], piid=params['piid'],
                timeout_ms=6000))

        if not futures:
            return False

        results = await asyncio.gather(*futures, return_exceptions=True)
        succeed_once = False
        failed_requests = {}
        for key, result in zip(task_keys, results):
            if result is None or isinstance(result, Exception):
                failed_requests[key] = request_list[key]
                continue
            param = request_list[key]
            self.client.on_prop_msg(
                params={
                    'did': param['did'],
                    'siid': param['siid'],
                    'piid': param['piid'],
                    'value': result},
                ctx=None)
            succeed_once = True

        if failed_requests:
            _LOGGER.debug(
                'refresh props failed, lan, %s', list(failed_requests.keys()))
            self.client.refresh_props_list.update(failed_requests)

        return succeed_once

    async def refresh_props_from_gw(self) -> bool:
        if not self.client.mips_local or not self.client.device_list_gateway:
            return False
        request_list = {}
        futures = []
        task_keys = []
        for key in list(self.client.refresh_props_list.keys()):
            did = key.split('|')[0]
            if any(k.startswith(f'{did}|') for k in task_keys):
                continue
            device_gw = self.client.device_list_gateway.get(did, None)
            if not device_gw:
                continue
            mips_gw = self.client.mips_local.get(device_gw['group_id'], None)
            if not mips_gw:
                _LOGGER.error('mips gateway not exist, %s', key)
                continue
            params = self.client.refresh_props_list.pop(key)
            if not isinstance(params, dict) or 'did' not in params or 'siid' not in params or 'piid' not in params:
                continue
            clean_param = {
                'did': params['did'],
                'siid': params['siid'],
                'piid': params['piid'],
            }
            request_list[key] = clean_param
            task_keys.append(key)
            futures.append(mips_gw.get_prop_async(
                did=did, siid=params['siid'], piid=params['piid'],
                timeout_ms=6000))

        if not futures:
            return False

        results = await asyncio.gather(*futures, return_exceptions=True)
        succeed_once = False
        failed_requests = {}
        for key, result in zip(task_keys, results):
            if result is None or isinstance(result, Exception):
                failed_requests[key] = request_list[key]
                continue
            param = request_list[key]
            self.client.on_prop_msg(
                params={
                    'did': param['did'],
                    'siid': param['siid'],
                    'piid': param['piid'],
                    'value': result},
                ctx=None)
            succeed_once = True

        if failed_requests:
            _LOGGER.debug(
                'refresh props failed, gw, %s', list(failed_requests.keys()))
            self.client.refresh_props_list.update(failed_requests)

        return succeed_once
