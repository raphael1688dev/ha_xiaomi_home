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

    # Optimization: flatten nested loop with list comprehension for initialization performance
    new_entities = [
        Select(miot_device=miot_device, spec=prop)
        for miot_device in device_list
        for prop in miot_device.prop_list.get('select', [])
    ]

    if new_entities:
        async_add_entities(new_entities)


class Select(MIoTPropertyEntity, SelectEntity):
    """Select entities for Xiaomi Home."""

    def __init__(self, miot_device: MIoTDevice, spec: MIoTSpecProperty) -> None:
        """Initialize the Select."""
        super().__init__(miot_device=miot_device, spec=spec)
        
        # 優化: 預先建立 O(1) 的雙向查找字典，取代原本低效的 O(N) 陣列掃描
        self._val_to_desc = {}
        self._desc_to_val = {}
        
        if self._value_list:
            self._attr_options = self._value_list.descriptions
            for item in self._value_list.items:
                self._val_to_desc[item.value] = item.description
                self._desc_to_val[item.description] = item.value

    async def async_select_option(self, option: str) -> None:
        """Change the selected option."""
        # 優化: 使用 O(1) 字典反向查找
        val = self._desc_to_val.get(option)
        if val is not None:
            await self.set_property_async(value=val)

    @property
    def current_option(self) -> Optional[str]:
        """Return the current selected option."""
        # Optimization: protect against None value during startup
        if self._value is None:
            return None
            
        # 優化: 使用 O(1) 字典正向查找
        return self._val_to_desc.get(self._value)