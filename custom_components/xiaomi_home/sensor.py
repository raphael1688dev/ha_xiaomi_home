# -*- coding: utf-8 -*-
"""
Sensor entities for Xiaomi Home.
"""
from __future__ import annotations
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.components.sensor import SensorEntity, SensorDeviceClass
from homeassistant.components.sensor import DEVICE_CLASS_UNITS

from .miot.miot_device import MIoTDevice, MIoTPropertyEntity
from .miot.miot_spec import MIoTSpecProperty
from .miot.const import DOMAIN

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up a config entry."""
    device_list: list[MIoTDevice] = hass.data[DOMAIN]['devices'][
        config_entry.entry_id]

    # 優化: 扁平化巢狀迴圈，改用效能更好的列表推導式
    new_entities = [
        Sensor(miot_device=miot_device, spec=prop)
        for miot_device in device_list
        for prop in miot_device.prop_list.get('sensor', [])
    ]

    # 處理將 Binary Sensor 作為一般文本 Sensor 顯示的邏輯
    new_entities.extend([
        Sensor(miot_device=miot_device, spec=prop)
        for miot_device in device_list
        if miot_device.miot_client.display_binary_text
        for prop in miot_device.prop_list.get('binary_sensor', [])
        if prop.value_list
    ])

    if new_entities:
        async_add_entities(new_entities)


class Sensor(MIoTPropertyEntity, SensorEntity):
    """Sensor entities for Xiaomi Home."""

    def __init__(self, miot_device: MIoTDevice, spec: MIoTSpecProperty) -> None:
        """Initialize the Sensor."""
        super().__init__(miot_device=miot_device, spec=spec)
        self._attr_device_class = spec.device_class
        
        # 優化: 預先建立 O(1) 的數值到描述反查字典，避免頻繁查詢時的效能損耗
        self._val_desc_map = {}
        if spec.value_list:
            self._val_desc_map = {
                item.value: item.description 
                for item in spec.value_list.items
            }

        # Set unit
        if spec.device_class == SensorDeviceClass.ENUM:
            pass
        elif spec.value_list:
            self._attr_device_class = SensorDeviceClass.ENUM
            self._attr_options = spec.value_list.descriptions
        else:
            if spec.external_unit:
                self._attr_native_unit_of_measurement = spec.external_unit
            else:
                # device_class is not empty but unit is empty.
                # Set the default unit according to device_class.
                unit_sets = DEVICE_CLASS_UNITS.get(
                    self._attr_device_class, None)  # type: ignore
                self._attr_native_unit_of_measurement = list(
                    unit_sets)[0] if unit_sets else None
                    
            # Set suggested precision
            if spec.format_ == float:
                self._attr_suggested_display_precision = spec.precision
            # Set state_class
            if spec.state_class:
                self._attr_state_class = spec.state_class
                
        # Set icon
        if spec.icon and not self.device_class:
            self._attr_icon = spec.icon

    @property
    def native_value(self) -> Any:
        """Return the current value of the sensor."""
        # 優化: 保護尚未取得設備狀態時的情境
        if self._value is None:
            return None

        if self._value_range and isinstance(self._value, (int, float)):
            if (
                self._value < self._value_range.min_
                or self._value > self._value_range.max_
            ):
                # 優化: 降級為 debug 避免某些設備回報公差時造成日誌洗頻
                _LOGGER.debug(
                    '%s, data exception, out of range, %s, %s',
                    self.entity_id, self._value, self._value_range)
                    
        if self._value_list:
            # 優化: O(1) 字典查找，取代原本的 O(N) 遍歷
            return self._val_desc_map.get(self._value, self._value)
            
        if isinstance(self._value, str):
            return self._value[:255]
            
        return self._value