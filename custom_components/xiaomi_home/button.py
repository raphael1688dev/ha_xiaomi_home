# -*- coding: utf-8 -*-
"""
Button entities for Xiaomi Home.
"""
from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.components.button import ButtonEntity

from .miot.miot_device import MIoTActionEntity, MIoTDevice
from .miot.miot_spec import MIoTSpecAction
from .miot.const import DOMAIN


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up a config entry."""
    device_list: list[MIoTDevice] = hass.data[DOMAIN]['devices'][
        config_entry.entry_id]

    new_entities = []
    for miot_device in device_list:
        for action in miot_device.action_list.get('button', []):
            new_entities.append(Button(miot_device=miot_device, spec=action))

    if new_entities:
        async_add_entities(new_entities)


class Button(MIoTActionEntity, ButtonEntity):
    """Button entities for Xiaomi Home."""

    def __init__(self, miot_device: MIoTDevice, spec: MIoTSpecAction) -> None:
        """Initialize the Button."""
        super().__init__(miot_device=miot_device, spec=spec)
        # Use default device class

    async def async_press(self) -> None:
        """Press the button."""
        return await self.action_async()
