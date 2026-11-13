# -*- coding: utf-8 -*-
"""Runtime data of a loaded Xiaomi Home config entry."""
from __future__ import annotations

from dataclasses import dataclass

from homeassistant.config_entries import ConfigEntry

from .miot.miot_client import MIoTClient
from .miot.miot_device import MIoTDevice


@dataclass
class XiaomiHomeData:
    """What the platforms of one loaded entry share.

    Home Assistant drops it when the entry unloads. The client registry in
    `hass.data` stays, the configuration and options flows look clients up
    there before or without a loaded entry.
    """

    miot_client: MIoTClient
    devices: list[MIoTDevice]


type XiaomiHomeConfigEntry = ConfigEntry[XiaomiHomeData]
