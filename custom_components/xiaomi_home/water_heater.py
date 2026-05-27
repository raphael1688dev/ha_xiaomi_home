# -*- coding: utf-8 -*-
"""
Water heater entities for Xiaomi Home.
"""
from __future__ import annotations
import logging
from typing import Any, Optional

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.components.water_heater import (STATE_ON, STATE_OFF,
                                                   ATTR_TEMPERATURE,
                                                   WaterHeaterEntity,
                                                   WaterHeaterEntityFeature)

from .miot.const import DOMAIN
from .miot.miot_device import MIoTDevice, MIoTEntityData, MIoTServiceEntity
from .miot.miot_spec import MIoTSpecProperty

_LOGGER = logging.getLogger(__name__)


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
        WaterHeater(miot_device=miot_device, entity_data=data)
        for miot_device in device_list
        for data in miot_device.entity_list.get('water_heater', [])
    ]

    if new_entities:
        async_add_entities(new_entities)


class WaterHeater(MIoTServiceEntity, WaterHeaterEntity):
    """Water heater entities for Xiaomi Home."""
    _prop_on: Optional[MIoTSpecProperty]
    _prop_temp: Optional[MIoTSpecProperty]
    _prop_target_temp: Optional[MIoTSpecProperty]
    _prop_mode: Optional[MIoTSpecProperty]

    _mode_map: Optional[dict[Any, Any]]
    _mode_reverse_map: dict[str, Any]

    def __init__(self, miot_device: MIoTDevice,
                 entity_data: MIoTEntityData) -> None:
        """Initialize the Water heater."""
        super().__init__(miot_device=miot_device, entity_data=entity_data)
        self._attr_temperature_unit = None
        self._attr_supported_features = WaterHeaterEntityFeature(0)
        self._prop_on = None
        self._prop_temp = None
        self._prop_target_temp = None
        self._prop_mode = None
        self._mode_map = None
        self._mode_reverse_map = {}

        # properties
        for prop in entity_data.props:
            # on
            if prop.name == 'on':
                self._attr_supported_features |= WaterHeaterEntityFeature.ON_OFF
                self._prop_on = prop
            # temperature
            if prop.name == 'temperature':
                if not prop.value_range:
                    _LOGGER.error('invalid temperature value_range format, %s',
                                  self.entity_id)
                    continue
                if prop.external_unit:
                    self._attr_temperature_unit = prop.external_unit
                self._prop_temp = prop
            # target-temperature
            if prop.name == 'target-temperature':
                if not prop.value_range:
                    _LOGGER.error(
                        'invalid target-temperature value_range format, %s',
                        self.entity_id)
                    continue
                self._attr_min_temp = prop.value_range.min_
                self._attr_max_temp = prop.value_range.max_
                self._attr_target_temperature_step = prop.value_range.step
                if self._attr_temperature_unit is None and prop.external_unit:
                    self._attr_temperature_unit = prop.external_unit
                self._attr_supported_features |= (
                    WaterHeaterEntityFeature.TARGET_TEMPERATURE)
                self._prop_target_temp = prop
            # mode
            if prop.name == 'mode':
                if not prop.value_list:
                    _LOGGER.error('mode value_list is None, %s', self.entity_id)
                    continue
                self._mode_map = prop.value_list.to_map()
                # 優化: 預先建立 O(1) 模式反向查找字典，取代 O(N) 掃描
                self._mode_reverse_map = {v: k for k, v in self._mode_map.items()}
                self._attr_operation_list = list(self._mode_map.values())
                self._prop_mode = prop
                
        if not self._attr_operation_list:
            self._attr_operation_list = [STATE_ON]
        self._attr_operation_list.append(STATE_OFF)
        self._attr_supported_features |= WaterHeaterEntityFeature.OPERATION_MODE

    async def async_turn_on(self) -> None:
        """Turn the water heater on."""
        await self.set_property_async(prop=self._prop_on, value=True)

    async def async_turn_off(self) -> None:
        """Turn the water heater off."""
        await self.set_property_async(prop=self._prop_on, value=False)

    async def async_set_temperature(self, **kwargs: Any) -> None:
        """Set the target temperature."""
        await self.set_property_async(prop=self._prop_target_temp,
                                      value=kwargs[ATTR_TEMPERATURE])

    async def async_set_operation_mode(self, operation_mode: str) -> None:
        """Set the operation mode of the water heater."""
        if operation_mode == STATE_OFF:
            await self.set_property_async(prop=self._prop_on, value=False)
            return
        if operation_mode == STATE_ON:
            await self.set_property_async(prop=self._prop_on, value=True)
            return
            
        # 優化: 使用 O(1) 字典查找模式對應數值
        mode_val = self._mode_reverse_map.get(operation_mode)
        if mode_val is not None:
            # 確保設備在切換模式前處於開機狀態
            val_on = self.get_prop_value(prop=self._prop_on)
            if val_on is None or not bool(val_on):
                await self.set_property_async(prop=self._prop_on,
                                              value=True,
                                              write_ha_state=False)
            await self.set_property_async(prop=self._prop_mode, value=mode_val)

    @property
    def current_temperature(self) -> Optional[float]:
        """The current temperature."""
        if not self._prop_temp:
            return None
        val = self.get_prop_value(prop=self._prop_temp)
        # Optimization: strictly convert to float
        return float(val) if val is not None else None

    @property
    def target_temperature(self) -> Optional[float]:
        """The target temperature."""
        if not self._prop_target_temp:
            return None
        val = self.get_prop_value(prop=self._prop_target_temp)
        # Optimization: strictly convert to float
        return float(val) if val is not None else None

    @property
    def current_operation(self) -> Optional[str]:
        """The current mode."""
        if not self._prop_on:
            return None
            
        val_on = self.get_prop_value(prop=self._prop_on)
        if val_on is None:
            return None
            
        # Optimization: safely use bool to check power status to avoid 'is False' type trap
        if not bool(val_on):
            return STATE_OFF
            
        if not self._prop_mode or not self._mode_map:
            return STATE_ON
            
        val_mode = self.get_prop_value(prop=self._prop_mode)
        return self._mode_map.get(val_mode) if val_mode is not None else STATE_ON