# -*- coding: utf-8 -*-
"""Diagnostics for Xiaomi Home.

Only what helps to troubleshoot goes in, and nothing that identifies the
account, the home or the network: the device records are copied field by
field from an allow list, so the device token, IP address, Wi-Fi names,
device names and device IDs never reach the download.
"""
from __future__ import annotations

from typing import Any, Optional

from homeassistant.components.diagnostics import REDACTED, async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntry

from .data import XiaomiHomeData
from .miot.const import DOMAIN
from .miot.miot_client import MIoTClient
from .miot.miot_device import MIoTDevice

# Entry data that identifies the account, the home or this installation
TO_REDACT: frozenset[str] = frozenset({
    'devices_filter',
    'home_selected',
    'nick_name',
    'oauth_redirect_url',
    'storage_path',
    'uid',
    'uuid',
    'virtual_did',
})

# Device record fields that are safe to share
_DEVICE_FIELDS: tuple[str, ...] = (
    'model',
    'urn',
    'connect_type',
    'online',
    'fw_version',
    'rssi',
    'voice_ctrl',
)


def _get_client(
    hass: HomeAssistant, entry: ConfigEntry
) -> Optional[MIoTClient]:
    return hass.data.get(DOMAIN, {}).get('miot_clients', {}).get(
        entry.entry_id)


def _device_summary(miot_client: MIoTClient, did: str) -> dict[str, Any]:
    record = miot_client.device_list.get(did, {})
    summary = {field: record.get(field) for field in _DEVICE_FIELDS}
    summary['control_path'] = miot_client.get_device_control_path(did)
    return summary


def _client_summary(miot_client: MIoTClient) -> dict[str, Any]:
    paths: dict[str, int] = {}
    for did in miot_client.device_list:
        path = miot_client.get_device_control_path(did)
        paths[path] = paths.get(path, 0) + 1
    return {
        'cloud_server': miot_client.cloud_server,
        'auth_rejected': miot_client.auth_rejected,
        'network_online': miot_client.miot_network.network_status,
        'gateways_connected': sorted(
            mips.mips_state for mips in miot_client.mips_local.values()),
        'lan_devices': len(miot_client.device_list_lan),
        'gateway_devices': len(miot_client.device_list_gateway),
        'devices_by_control_path': paths,
    }


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    """Return the diagnostics of a config entry."""
    data: dict[str, Any] = {
        'entry': {
            # The title is '<nick name>: <uid> [<region>]'
            'title': REDACTED,
            'data': async_redact_data(dict(entry.data), TO_REDACT),
            'options': async_redact_data(dict(entry.options), TO_REDACT),
        },
    }
    miot_client = _get_client(hass, entry)
    if miot_client is None:
        data['client'] = None
        return data
    data['client'] = _client_summary(miot_client)
    data['devices'] = [
        _device_summary(miot_client, did)
        for did in miot_client.device_list]
    return data


async def async_get_device_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry, device: DeviceEntry
) -> dict[str, Any]:
    """Return the diagnostics of one device."""
    miot_client = _get_client(hass, entry)
    if miot_client is None:
        return {'client': None}
    runtime_data: Optional[XiaomiHomeData] = getattr(
        entry, 'runtime_data', None)
    miot_devices: list[MIoTDevice] = (
        runtime_data.devices if runtime_data else [])
    for miot_device in miot_devices:
        if (DOMAIN, miot_device.did_tag) not in device.identifiers:
            continue
        summary = _device_summary(miot_client, miot_device.did)
        summary['lan_capable'] = miot_device.is_lan_capable
        for name, items in (
            ('entities', miot_device.entity_list),
            ('properties', miot_device.prop_list),
            ('events', miot_device.event_list),
            ('actions', miot_device.action_list),
        ):
            summary[name] = {
                platform: len(specs)
                for platform, specs in sorted(items.items()) if specs}
        return summary
    return {'device': None}
