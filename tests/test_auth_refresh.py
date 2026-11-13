"""Token and certificate refreshes retry after transient failures."""
# pylint: disable=protected-access
import time
from unittest.mock import AsyncMock, MagicMock, patch

import aiohttp
import pytest

from custom_components.xiaomi_home.miot.miot_client import (
    REFRESH_AUTH_RETRY_DELAY_MAX, REFRESH_AUTH_RETRY_DELAY_MIN, MIoTClient)
from custom_components.xiaomi_home.miot.miot_error import (
    MIoTErrorCode, MIoTHttpError, MIoTOauthError)


def _client(refresh_error: Exception) -> MIoTClient:
    with patch.object(MIoTClient, "__init__", lambda self, *a, **k: None):
        client = MIoTClient()  # pylint: disable=no-value-for-parameter
    client._uid = "u1"
    client._cloud_server = "cn"
    client._storage = MagicMock()
    client._storage.load_user_config_async = AsyncMock(return_value={
        "auth_info": {"expires_ts": int(time.time()) - 1,
                      "access_token": "a", "refresh_token": "r"}})
    client._oauth = MagicMock()
    client._oauth.refresh_access_token_async = AsyncMock(
        side_effect=refresh_error)
    client._refresh_token_retry_delay = REFRESH_AUTH_RETRY_DELAY_MIN
    client._refresh_cert_retry_delay = REFRESH_AUTH_RETRY_DELAY_MIN
    client._i18n = MagicMock()
    client._MIoTClient__show_client_error_notify = MagicMock()
    client._MIoTClient__request_refresh_auth_info = MagicMock()
    client._MIoTClient__request_refresh_user_cert = MagicMock()
    return client


@pytest.mark.asyncio
@pytest.mark.parametrize("error", [
    MIoTOauthError("invalid http status code, 502",
                   MIoTErrorCode.CODE_UNAVAILABLE),
    aiohttp.ClientConnectionError("down"),
    TimeoutError(),
])
async def test_transient_token_failure_retries_with_backoff(error) -> None:
    """One failed refresh used to end the chain: the token then expired and
    the user was asked to log in again after a mere 502 or timeout."""
    client = _client(error)
    schedule = client._MIoTClient__request_refresh_auth_info

    for _ in range(7):
        assert await client.refresh_oauth_info_async() is False

    delays = [c.args[0] for c in schedule.call_args_list]
    assert delays == [60, 120, 240, 480, 960, 1800, 1800]
    assert max(delays) == REFRESH_AUTH_RETRY_DELAY_MAX
    client._MIoTClient__show_client_error_notify.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("error", [
    MIoTOauthError("unauthorized(401)", MIoTErrorCode.CODE_OAUTH_UNAUTHORIZED),
    MIoTOauthError("oauth API error: invalid refresh token"),
])
async def test_rejected_token_asks_the_user_and_does_not_retry(error) -> None:
    client = _client(error)

    assert await client.refresh_oauth_info_async() is False

    client._MIoTClient__request_refresh_auth_info.assert_not_called()
    client._MIoTClient__show_client_error_notify.assert_called_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("error", [
    MIoTHttpError("mihome api post failed, 503"),
    aiohttp.ClientConnectionError("down"),
])
async def test_transient_cert_failure_retries(error) -> None:
    """MIoTHttpError and aiohttp errors used to escape the handler."""
    client = _client(MIoTOauthError("unused"))
    client._entry_data = {"virtual_did": "1"}
    client._cert = MagicMock()
    client._cert.verify_ca_cert_async = AsyncMock(return_value=True)
    client._cert.user_cert_remaining_time_async = AsyncMock(return_value=0)
    client._cert.load_user_key_async = AsyncMock(return_value="key")
    client._cert.gen_user_csr = MagicMock(return_value="csr")
    client._http = MagicMock()
    client._http.get_central_cert_async = AsyncMock(side_effect=error)

    with patch("custom_components.xiaomi_home.miot.miot_client."
               "SUPPORT_CENTRAL_GATEWAY_CTRL", ["cn"]):
        assert await client.refresh_user_cert_async() is False
        assert await client.refresh_user_cert_async() is False

    delays = [c.args[0] for c in
              client._MIoTClient__request_refresh_user_cert.call_args_list]
    assert delays == [60, 120]
    client._MIoTClient__show_client_error_notify.assert_not_called()
