import asyncio
import logging
import traceback
from itertools import islice
from typing import TYPE_CHECKING, Optional

import aiohttp

from .miot_error import MIoTClientError, MIoTErrorCode

if TYPE_CHECKING:
    from .miot_client import MIoTClient

_LOGGER = logging.getLogger(__name__)

class MIoTCloudManager:
    """Manager for handling MIoT cloud polling and sync logic."""

    def __init__(self, client: "MIoTClient") -> None:
        self.client = client

    async def refresh_props(self, patch_len: int = 150) -> bool:
        if not self.client.miot_network.network_status:
            return False

        if not self.client.refresh_props_list:
            return False

        request_items = {}
        if len(self.client.refresh_props_list) <= patch_len:
            request_items = self.client.refresh_props_list.copy()
            self.client.refresh_props_list.clear()
        else:
            # PERFORMANCE FIX: Efficient dictionary slicing using itertools
            request_items = dict(islice(self.client.refresh_props_list.items(), patch_len))
            for k in request_items:
                del self.client.refresh_props_list[k]

        clean_request_list = {}
        clean_params = []
        for key, val in request_items.items():
            if isinstance(val, dict) and 'did' in val and 'siid' in val and 'piid' in val:
                clean_item = {
                    'did': str(val['did']),
                    'siid': int(val['siid']),
                    'piid': int(val['piid']),
                }
                clean_request_list[key] = clean_item
                clean_params.append(clean_item)

        if not clean_params:
            return False

        try:
            results = await self.client.miot_http.get_props_async(
                params=clean_params)
            if not results:
                raise MIoTClientError('get_props_async failed')
            for result in results:
                if (
                    not isinstance(result, dict)
                    or 'did' not in result
                    or 'siid' not in result
                    or 'piid' not in result
                    or 'value' not in result
                ):
                    continue
                clean_request_list.pop(
                    f'{result["did"]}|{result["siid"]}|{result["piid"]}',
                    None)
                self.client.on_prop_msg(params=result, ctx=None)
            if clean_request_list:
                _LOGGER.debug(
                    'refresh props failed, cloud, %s',
                    list(clean_request_list.keys()))
            return True
        except (TimeoutError, asyncio.TimeoutError, aiohttp.ClientError) as err:
            _LOGGER.warning(
                'refresh props failed, cloud network/timeout: %s', err)
            self.client.refresh_props_list.update(clean_request_list)
            return False
        except MIoTClientError as err:
            err_str = str(err).lower()
            if getattr(err, 'code', None) == MIoTErrorCode.CODE_HTTP_INVALID_ACCESS_TOKEN or 'unauthorized(401)' in err_str:
                _LOGGER.warning(
                    'refresh props failed, cloud: unauthorized(401). Access token is likely invalid or expired. Please re-authenticate.'
                )
            elif getattr(err, 'code', None) in [500, 502, 503, 504] or getattr(err, 'status_code', None) in [500, 502, 503, 504] or any(code in err_str for code in ['500', '502', '503', '504']):
                _LOGGER.warning(
                    'refresh props failed, cloud: server error (5xx). Xiaomi cloud might be temporarily down or unstable. Details: %s', err
                )
            else:
                _LOGGER.error(
                    'refresh props error, cloud, %s, %s',
                    err, traceback.format_exc())
            # Add failed request back to the list
            self.client.refresh_props_list.update(clean_request_list)
            return False
        except Exception as err:
            _LOGGER.error(
                'refresh props error, cloud, %s, %s',
                err, traceback.format_exc())
            self.client.refresh_props_list.update(clean_request_list)
            return False

