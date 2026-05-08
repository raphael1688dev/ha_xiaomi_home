# -*- coding: utf-8 -*-
"""
Number entities for Xiaomi Home.
"""
from __future__ import annotations
from typing import Optional

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.components.number import NumberEntity

from .miot.const import DOMAIN
from .miot.miot_spec import MIoTSpecProperty
from .miot.miot_device import MIoTDevice, MIoTPropertyEntity


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
        Number(miot_device=miot_device, spec=prop)
        for miot_device in device_list
        for prop in miot_device.prop_list.get('number', [])
    ]

    if new_entities:
        async_add_entities(new_entities)


class Number(MIoTPropertyEntity, NumberEntity):
    """Number entities for Xiaomi Home."""

    def __init__(self, miot_device: MIoTDevice, spec: MIoTSpecProperty) -> None:
        """Initialize the Number."""
        super().__init__(miot_device=miot_device, spec=spec)
        # Set device_class
        self._attr_device_class = spec.device_class
        # Set unit
        if self.spec.external_unit:
            self._attr_native_unit_of_measurement = self.spec.external_unit
        # Set icon
        if self.spec.icon and not self.device_class:
            self._attr_icon = self.spec.icon
        # Set value range
        if self._value_range:
            # 優化: 嚴格轉換為 float 型別，符合 HA 核心對 NumberEntity 的規範
            self._attr_native_min_value = float(self._value_range.min_)
            self._attr_native_max_value = float(self._value_range.max_)
            self._attr_native_step = float(self._value_range.step)

    @property
    def native_value(self) -> Optional[float]:
        """Return the current value of the number."""
        # 優化: 防止啟動時 value 為 None 造成的異常，並嚴格轉換為 float
        if self._value is None:
            return None
        try:
            return float(self._value)
        except (ValueError, TypeError):
            return None

    async def async_set_native_value(self, value: float) -> None:
        """Set new value."""
        await self.set_property_async(value=value)