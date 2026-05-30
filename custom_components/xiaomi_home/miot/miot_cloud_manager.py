import logging
import traceback
from itertools import islice
from typing import TYPE_CHECKING, Optional

from .miot_error import MIoTClientError, MIoTErrorCode

if TYPE_CHECKING:
    from .miot_client import MIoTClient

_LOGGER = logging.getLogger(__name__)

class MIoTCloudManager:
    """Manager for handling MIoT cloud polling and sync logic."""

    def __init__(self, client: "MIoTClient") -> None:
        self.client = client

    async def refresh_props(self, patch_len: int = 150) -> bool:
        if not self.client._network.network_status:
            return False

        request_list = None
        if len(self.client._refresh_props_list) < patch_len:
            request_list = self.client._refresh_props_list
            self.client._refresh_props_list = {}
        else:
            # PERFORMANCE FIX: Efficient dictionary slicing using itertools
            request_list = dict(islice(self.client._refresh_props_list.items(), patch_len))
            for k in request_list:
                del self.client._refresh_props_list[k]
                
        try:
            results = await self.client._http.get_props_async(
                params=list(request_list.values()))
            if not results:
                raise MIoTClientError('get_props_async failed')
            for result in results:
                if (
                    'did' not in result
                    or 'siid' not in result
                    or 'piid' not in result
                    or 'value' not in result
                ):
                    continue
                request_list.pop(
                    f'{result["did"]}|{result["siid"]}|{result["piid"]}',
                    None)
                self.client.on_prop_msg(params=result, ctx=None)
            if request_list:
                _LOGGER.debug(
                    'refresh props failed, cloud, %s',
                    list(request_list.keys()))
                request_list = None
            return True
        except MIoTClientError as err:
            err_str = str(err).lower()
            if getattr(err, 'code', None) == MIoTErrorCode.CODE_HTTP_INVALID_ACCESS_TOKEN or 'unauthorized(401)' in err_str:
                _LOGGER.warning(
                    'refresh props failed, cloud: unauthorized(401). Access token is likely invalid or expired. Please re-authenticate.'
                )
            elif any(code in err_str for code in [', 500,', ', 502,', ', 503,', ', 504,']):
                _LOGGER.warning(
                    'refresh props failed, cloud: server error (5xx). Xiaomi cloud might be temporarily down or unstable. Details: %s', err
                )
            else:
                _LOGGER.error(
                    'refresh props error, cloud, %s, %s',
                    err, traceback.format_exc())
            # Add failed request back to the list
            self.client._refresh_props_list.update(request_list)
            return False
        except Exception as err:
            _LOGGER.error(
                'refresh props error, cloud, %s, %s',
                err, traceback.format_exc())
            self.client._refresh_props_list.update(request_list)
            return False
