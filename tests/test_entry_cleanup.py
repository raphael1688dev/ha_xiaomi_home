"""Cleanup paths that run when an entry is not (fully) set up."""
# pylint: disable=protected-access
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import custom_components.xiaomi_home as xiaomi_home
from custom_components.xiaomi_home.miot.const import DOMAIN
from custom_components.xiaomi_home.miot.miot_client import (
    CtrlMode, MIoTClient)


@pytest.mark.asyncio
async def test_deinit_after_an_early_init_failure() -> None:
    """init_async can fail before the cloud MQTT, OAuth and HTTP clients
    exist; deinit then raised AttributeError and hid the real error."""
    with patch.object(MIoTClient, "__init__", lambda self, *a, **k: None):
        client = MIoTClient()  # pylint: disable=no-value-for-parameter
    client._uid, client._cloud_server = "u1", "cn"
    client._network = MagicMock()
    client._mips_cloud = client._oauth = client._http = None
    client._ctrl_mode = CtrlMode.CLOUD
    client._refresh_props_timer = None
    client._refresh_props_list = {}
    client._refresh_cloud_devices_timer = None
    client._refresh_token_timer = client._refresh_cert_timer = None
    client._show_devices_changed_notify_timer = None
    client._persistence_notify = MagicMock()
    client._MIoTClient__show_client_error_notify = MagicMock()
    client._background_tasks = set()

    await client.deinit_async()

    client._network.unsub_network_status.assert_called_once()


def _entry() -> SimpleNamespace:
    return SimpleNamespace(entry_id="entry1", data={
        "uid": "u1", "cloud_server": "cn", "storage_path": "/tmp/xh"})


@pytest.mark.asyncio
async def test_remove_entry_without_storage_in_this_run() -> None:
    """Removing an entry that was not set up since boot raised KeyError and
    left its tokens, certificate and device cache on disk."""
    hass = MagicMock()
    hass.data = {DOMAIN: {}}
    storage = MagicMock()
    storage.remove_async = AsyncMock()
    storage.update_user_config_async = AsyncMock()
    cert = MagicMock()
    cert.remove_user_cert_async = AsyncMock()
    cert.remove_user_key_async = AsyncMock()
    with patch.object(xiaomi_home, "MIoTStorage",
                      return_value=storage) as storage_cls, \
            patch.object(xiaomi_home, "MIoTCert", return_value=cert):
        await xiaomi_home.async_remove_entry(hass, _entry())

    storage_cls.assert_called_once_with("/tmp/xh")
    storage.update_user_config_async.assert_awaited_once_with(
        uid="u1", cloud_server="cn", config=None)
    cert.remove_user_cert_async.assert_awaited_once()
    cert.remove_user_key_async.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("cached,allowed", [
    ({"123": {}}, False),  # still in the device list: it would come back
    ({"456": {}}, True),   # stale device
    (None, True),          # no device cache at all
])
async def test_remove_device_of_an_unloaded_entry(cached, allowed) -> None:
    """Without a loaded client this raised 'entry data is None'."""
    storage = MagicMock()
    storage.load_async = AsyncMock(return_value=cached)
    hass = MagicMock()
    hass.data = {DOMAIN: {"miot_clients": {}, "miot_storage": storage}}
    device = SimpleNamespace(id="dev1", identifiers={(DOMAIN, "cn_123")})

    assert await xiaomi_home.async_remove_config_entry_device(
        hass, _entry(), device) is allowed
