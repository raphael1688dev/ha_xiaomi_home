# -*- coding: utf-8 -*-
"""
Select entities for Xiaomi Home.
"""
from __future__ import annotations
from typing import Optional

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.components.select import SelectEntity

from .miot.const import DOMAIN
from .miot.miot_device import MIoTDevice, MIoTPropertyEntity
from .miot.miot_spec import MIoTSpecProperty


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
        for prop in miot_device.prop_list.get('select', []):
            new_entities.append(Select(miot_device=miot_device, spec=prop))

    if new_entities:
        async_add_entities(new_entities)


class Select(MIoTPropertyEntity, SelectEntity):
    """Select entities for Xiaomi Home."""

    def __init__(self, miot_device: MIoTDevice, spec: MIoTSpecProperty) -> None:
        """Initialize the Select."""
        super().__init__(miot_device=miot_device, spec=spec)
        if self._value_list:
            self._attr_options = self._value_list.descriptions

    async def async_select_option(self, option: str) -> None:
        """Change the selected option."""
        await self.set_property_async(
            value=self.get_vlist_value(description=option))

    @property
    def current_option(self) -> Optional[str]:
        """Return the current selected option."""
        return self.get_vlist_description(value=self._value)
