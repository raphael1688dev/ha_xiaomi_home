"""Home Assistant's reauthentication flow for a rejected Xiaomi login."""
# pylint: disable=protected-access
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant import config_entries
from homeassistant.data_entry_flow import AbortFlow

from custom_components.xiaomi_home import config_flow
from custom_components.xiaomi_home.config_flow import XiaomiMihomeConfigFlow
from custom_components.xiaomi_home.miot.const import DOMAIN

ENTRY_DATA = {
    "virtual_did": "4242", "storage_path": "/tmp/xh", "cloud_server": "cn",
    "uuid": "u" * 32, "uid": "1001", "nick_name": "Raphael",
    "oauth_redirect_url": "http://homeassistant.local:8123/api/webhook/4242",
    "integration_language": "en"}


def _flow() -> XiaomiMihomeConfigFlow:
    flow = XiaomiMihomeConfigFlow()
    flow.hass = MagicMock()
    flow.hass.data = {DOMAIN: {"miot_storage": MagicMock()}}
    flow.context = {"source": config_entries.SOURCE_REAUTH,
                    "entry_id": "entry1"}
    return flow


@pytest.mark.asyncio
async def test_reauth_loads_the_entry_and_asks_to_log_in() -> None:
    flow = _flow()
    with patch.object(config_flow, "MIoTI18n") as i18n:
        i18n.return_value.init_async = AsyncMock()
        result = await flow.async_step_reauth(ENTRY_DATA)

    assert result["type"] == "form"
    assert result["step_id"] == "reauth_confirm"
    assert result["description_placeholders"]["nick_name"] == "Raphael"
    assert flow._virtual_did == "4242"
    assert flow._oauth_redirect_url_full == ENTRY_DATA["oauth_redirect_url"]
    assert flow._uuid == "u" * 32
    assert "4242" in flow.hass.data[DOMAIN]


def _logged_in_flow(uid: str) -> XiaomiMihomeConfigFlow:
    flow = _flow()
    flow._cloud_server, flow._uid, flow._virtual_did = "cn", "1001", "4242"
    flow._auth_info = {"access_token": "a", "refresh_token": "r"}
    flow._miot_storage = MagicMock()
    flow._miot_storage.update_user_config_async = AsyncMock(return_value=True)
    flow._miot_http = MagicMock()
    flow._miot_http.get_uid_async = AsyncMock(return_value=uid)
    flow._miot_http.deinit_async = AsyncMock()
    flow._cc_get_mihome_cert = AsyncMock()
    entry = SimpleNamespace(unique_id="cn1001", entry_id="entry1")
    flow._get_reauth_entry = MagicMock(return_value=entry)
    flow.hass.config_entries.async_entry_for_domain_unique_id = MagicMock(
        return_value=None)
    return flow


@pytest.mark.asyncio
async def test_reauth_with_another_account_stores_nothing() -> None:
    flow = _logged_in_flow(uid="2002")
    with pytest.raises(AbortFlow) as aborted:
        await flow._XiaomiMihomeConfigFlow__finish_reauth_login_async()

    assert aborted.value.reason == "reauth_account_mismatch"
    flow._miot_storage.update_user_config_async.assert_not_awaited()


@pytest.mark.asyncio
async def test_reauth_with_the_same_account_stores_the_login() -> None:
    flow = _logged_in_flow(uid="1001")
    with patch.object(config_flow, "webhook_async_unregister") as unreg:
        await flow._XiaomiMihomeConfigFlow__finish_reauth_login_async()

    flow._miot_storage.update_user_config_async.assert_awaited_once_with(
        uid="1001", cloud_server="cn", config={"auth_info": flow._auth_info})
    unreg.assert_called_once_with(flow.hass, webhook_id="4242")
    assert flow._miot_http is None


def test_reauth_strings_exist() -> None:
    import json  # pylint: disable=import-outside-toplevel
    from pathlib import Path  # pylint: disable=import-outside-toplevel
    strings = json.loads((Path(config_flow.__file__).parent
                          / "translations/en.json").read_text())
    assert "reauth_confirm" in strings["config"]["step"]
    assert "reauth_account_mismatch" in strings["config"]["abort"]
