# -*- coding: utf-8 -*-
"""
Switch entities for Xiaomi Home.
"""
from __future__ import annotations
from typing import Any, Optional

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.components.switch import SwitchEntity

from .miot.miot_device import MIoTDevice, MIoTPropertyEntity
from .miot.miot_spec import MIoTSpecProperty
from .miot.const import DOMAIN


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up a config entry."""
    device_list: list[MIoTDevice] = hass.data[DOMAIN]['devices'][
        config_entry.entry_id]

    # 優化: 扁平化巢狀迴圈改用 List Comprehension，提升初始化載入效能
    new_entities = [
        Switch(miot_device=miot_device, spec=prop)
        for miot_device in device_list
        for prop in miot_device.prop_list.get('switch', [])
    ]

    if new_entities:
        async_add_entities(new_entities)


class Switch(MIoTPropertyEntity, SwitchEntity):
    """Switch entities for Xiaomi Home."""
    # pylint: disable=unused-argument

    def __init__(self, miot_device: MIoTDevice, spec: MIoTSpecProperty) -> None:
        """Initialize the Switch."""
        super().__init__(miot_device=miot_device, spec=spec)
        # Set device_class
        self._attr_device_class = spec.device_class

    @property
    def is_on(self) -> Optional[bool]:
        """On/Off state."""
        # 優化: 防護啟動初期 value 為 None 的狀況，並使用 bool() 避免 is True 帶來的型別誤判
        if self._value is None:
            return None
        return bool(self._value)

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the switch on."""
        await self.set_property_async(value=True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the switch off."""
        await self.set_property_async(value=False)