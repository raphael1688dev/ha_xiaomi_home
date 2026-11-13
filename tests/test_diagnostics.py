"""Diagnostics must help to troubleshoot without leaking the account."""
import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from homeassistant.components.diagnostics import REDACTED

from custom_components.xiaomi_home import diagnostics
from custom_components.xiaomi_home.miot.const import DOMAIN

_SECRETS = ("tok-secret", "192.168.1.23", "HomeWiFi", "aa:bb:cc",
            "Living room fan", "did-123", "1234567", "Raphael",
            "virtual-9", "uuid-9", "/config/.storage/xiaomi_home")


def _entry() -> SimpleNamespace:
    return SimpleNamespace(
        entry_id="entry1",
        title="Raphael: 1234567 [cn]",
        data={
            "uid": "1234567", "nick_name": "Raphael", "cloud_server": "cn",
            "virtual_did": "virtual-9", "uuid": "uuid-9",
            "storage_path": "/config/.storage/xiaomi_home",
            "oauth_redirect_url": "http://ha.local/api/webhook/virtual-9",
            "home_selected": {"h1": {"home_name": "Raphael home"}},
            "devices_filter": {"did": {"items": ["did-123"]}},
            "ctrl_mode": "auto", "integration_language": "en",
        },
        options={},
    )


def _client() -> SimpleNamespace:
    return SimpleNamespace(
        cloud_server="cn",
        auth_rejected=False,
        miot_network=SimpleNamespace(network_status=True),
        mips_local={"g1": SimpleNamespace(mips_state=True)},
        device_list_lan={"did-123": {}},
        device_list_gateway={},
        device_list={"did-123": {
            "did": "did-123", "name": "Living room fan",
            "model": "zhimi.fan.za5", "urn": "urn:miot-spec-v2:device:fan:1",
            "connect_type": 0, "online": True, "fw_version": "2.1.2",
            "token": "tok-secret", "local_ip": "192.168.1.23",
            "ssid": "HomeWiFi", "bssid": "aa:bb:cc", "rssi": -50,
            "home_name": "Raphael home", "room_name": "Living room",
        }},
        get_device_control_path=lambda did: "LAN",
    )


def _hass(client) -> MagicMock:
    hass = MagicMock()
    hass.data = {DOMAIN: {
        "miot_clients": {"entry1": client} if client else {}}}
    return hass


@pytest.mark.asyncio
async def test_entry_diagnostics_hide_the_account_and_devices() -> None:
    data = await diagnostics.async_get_config_entry_diagnostics(
        _hass(_client()), _entry())

    dumped = json.dumps(data)
    for secret in _SECRETS:
        assert secret not in dumped, secret
    assert data["entry"]["title"] == REDACTED
    assert data["entry"]["data"]["uid"] == REDACTED
    assert data["entry"]["data"]["ctrl_mode"] == "auto"
    assert data["client"]["devices_by_control_path"] == {"LAN": 1}
    assert data["client"]["gateways_connected"] == [True]
    assert data["devices"] == [{
        "model": "zhimi.fan.za5", "urn": "urn:miot-spec-v2:device:fan:1",
        "connect_type": 0, "online": True, "fw_version": "2.1.2",
        "rssi": -50, "voice_ctrl": None, "control_path": "LAN"}]


@pytest.mark.asyncio
async def test_entry_diagnostics_of_an_entry_that_is_not_loaded() -> None:
    data = await diagnostics.async_get_config_entry_diagnostics(
        _hass(None), _entry())
    assert data["client"] is None
    assert data["entry"]["data"]["nick_name"] == REDACTED


@pytest.mark.asyncio
async def test_device_diagnostics() -> None:
    hass = _hass(_client())
    miot_device = SimpleNamespace(
        did="did-123", did_tag="cn_did-123", is_lan_capable=True,
        entity_list={"fan": [object()], "climate": []},
        prop_list={"sensor": [object(), object()]},
        event_list={}, action_list={"button": [object()]})
    entry = _entry()
    entry.runtime_data = SimpleNamespace(devices=[miot_device])

    data = await diagnostics.async_get_device_diagnostics(
        hass, entry, SimpleNamespace(identifiers={(DOMAIN, "cn_did-123")}))

    for secret in _SECRETS:
        assert secret not in json.dumps(data), secret
    assert data["model"] == "zhimi.fan.za5"
    assert data["lan_capable"] is True
    assert data["entities"] == {"fan": 1}
    assert data["properties"] == {"sensor": 2}
    assert data["events"] == {}
    assert data["actions"] == {"button": 1}

    other = await diagnostics.async_get_device_diagnostics(
        hass, entry, SimpleNamespace(identifiers={(DOMAIN, "cn_other")}))
    assert other == {"device": None}
