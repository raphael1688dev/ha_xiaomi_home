# -*- coding: utf-8 -*-
"""
Fan entities for Xiaomi Home.
"""
from __future__ import annotations
from typing import Any, Optional
import logging
import asyncio

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.components.fan import (
    FanEntity,
    FanEntityFeature,
    DIRECTION_FORWARD,
    DIRECTION_REVERSE
)
from homeassistant.util.percentage import (
    percentage_to_ranged_value,
    ranged_value_to_percentage,
    ordered_list_item_to_percentage,
    percentage_to_ordered_list_item
)

from .miot.miot_spec import MIoTSpecProperty
from .miot.const import DOMAIN
from .miot.miot_device import MIoTDevice, MIoTEntityData, MIoTServiceEntity

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
        hass: HomeAssistant,
        config_entry: ConfigEntry,
        async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up a config entry."""
    device_list: list[MIoTDevice] = hass.data[DOMAIN]['devices'][
        config_entry.entry_id]
        
    # 優化: 扁平化雙層迴圈改用 List Comprehension
    new_entities = [
        Fan(miot_device=miot_device, entity_data=data)
        for miot_device in device_list
        for data in miot_device.entity_list.get('fan', [])
    ]

    if new_entities:
        async_add_entities(new_entities)


class Fan(MIoTServiceEntity, FanEntity):
    """Fan entities for Xiaomi Home."""
    # pylint: disable=unused-argument
    _prop_on: MIoTSpecProperty
    _prop_fan_level: Optional[MIoTSpecProperty]
    _prop_mode: Optional[MIoTSpecProperty]
    _prop_horizontal_swing: Optional[MIoTSpecProperty]
    _prop_wind_reverse: Optional[MIoTSpecProperty]
    _prop_wind_reverse_forward: Any
    _prop_wind_reverse_reverse: Any

    _speed_min: int
    _speed_max: int
    _speed_step: int
    _speed_names: Optional[list]
    _speed_name_map: Optional[dict[int, str]]
    _speed_name_reverse_map: dict[str, int]
    
    _mode_map: Optional[dict[Any, Any]]
    _mode_reverse_map: dict[Any, Any]

    def __init__(
        self, miot_device: MIoTDevice, entity_data: MIoTEntityData
    ) -> None:
        """Initialize the Fan."""
        super().__init__(miot_device=miot_device,  entity_data=entity_data)
        self._attr_preset_modes = []
        self._attr_current_direction = None
        self._attr_supported_features = FanEntityFeature(0)
        self._is_turning_on = False

        # _prop_on is required
        self._prop_fan_level = None
        self._prop_mode = None
        self._prop_horizontal_swing = None
        self._prop_wind_reverse = None
        self._prop_wind_reverse_forward = None
        self._prop_wind_reverse_reverse = None
        
        self._speed_min = 65535
        self._speed_max = 0
        self._speed_step = 1
        self._speed_names = []
        self._speed_name_map = {}
        self._speed_name_reverse_map = {}

        self._mode_map = None
        self._mode_reverse_map = {}

        # properties
        if prop := entity_data.get_prop('on'):
            self._attr_supported_features |= FanEntityFeature.TURN_ON
            self._attr_supported_features |= FanEntityFeature.TURN_OFF
            self._prop_on = prop
            
        if prop := entity_data.get_prop('fan-level'):
            if prop.value_range:
                # Fan level with value-range
                self._speed_min = prop.value_range.min_
                self._speed_max = prop.value_range.max_
                self._speed_step = prop.value_range.step
                self._attr_speed_count = int((
                    self._speed_max - self._speed_min)/self._speed_step)+1
                self._attr_supported_features |= FanEntityFeature.SET_SPEED
                self._prop_fan_level = prop
            elif (
                self._prop_fan_level is None
                and prop.value_list
            ):
                # Fan level with value-list
                self._speed_name_map = prop.value_list.to_map()
                # 優化: 預先建立 O(1) 速度反查字典
                self._speed_name_reverse_map = {v: k for k, v in self._speed_name_map.items()}
                self._speed_names = list(self._speed_name_map.values())
                self._attr_speed_count = len(self._speed_names)
                self._attr_supported_features |= FanEntityFeature.SET_SPEED
                self._prop_fan_level = prop
                
        if prop := entity_data.get_prop('mode'):
            if not prop.value_list:
                _LOGGER.error(
                    'mode value_list is None, %s', self.entity_id)
            else:
                self._mode_map = prop.value_list.to_map()
                # 優化: 預先建立 O(1) 模式反查字典
                self._mode_reverse_map = {v: k for k, v in self._mode_map.items()}
                self._attr_preset_modes = list(self._mode_map.values())
                self._attr_supported_features |= FanEntityFeature.PRESET_MODE
                self._prop_mode = prop
                
        if prop := entity_data.get_prop('horizontal-swing'):
            self._attr_supported_features |= FanEntityFeature.OSCILLATE
            self._prop_horizontal_swing = prop
            
        if prop := entity_data.get_prop('wind-reverse'):
            if prop.format_ == bool:
                self._prop_wind_reverse_forward = False
                self._prop_wind_reverse_reverse = True
            elif prop.value_list:
                for item in prop.value_list.items:
                    if item.name in {'foreward', 'forward'}:
                        self._prop_wind_reverse_forward = item.value
                    elif item.name in {'reversal', 'reverse'}:
                        self._prop_wind_reverse_reverse = item.value
            if (
                self._prop_wind_reverse_forward is None
                or self._prop_wind_reverse_reverse is None
            ):
                _LOGGER.error(
                    'invalid wind-reverse, %s', self.entity_id)
            else:
                self._attr_supported_features |= FanEntityFeature.DIRECTION
                self._prop_wind_reverse = prop

    async def async_turn_on(
        self, percentage: Optional[int] = None,
        preset_mode: Optional[str] = None, **kwargs: Any
    ) -> None:
        """Turn the fan on."""
        # 先確認啟動，避免關機狀態下被設備拒絕其它指令
        if not self.is_on and not self._is_turning_on:
            self._is_turning_on = True
            try:
                await self.set_property_async(prop=self._prop_on, value=True)
            finally:
                self._is_turning_on = False

        # 優化: 使用 asyncio.gather 並發執行後續指令，改善卡頓感
        tasks = []
        if percentage is not None:
            tasks.append(self.async_set_percentage(percentage))
        if preset_mode is not None:
            tasks.append(self.async_set_preset_mode(preset_mode))
            
        if tasks:
            await asyncio.gather(*tasks)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the fan off."""
        await self.set_property_async(prop=self._prop_on, value=False)

    async def async_toggle(self, **kwargs: Any) -> None:
        """Toggle the fan."""
        await self.set_property_async(prop=self._prop_on, value=not self.is_on)

    async def async_set_percentage(self, percentage: int) -> None:
        """Set the percentage of the fan speed."""
        if percentage > 0:
            if not self.is_on and not self._is_turning_on:
                self._is_turning_on = True
                try:
                    await self.set_property_async(prop=self._prop_on, value=True)
                finally:
                    self._is_turning_on = False
                
            if self._speed_names:
                # 優化: 使用 O(1) 字典反查，取代原本低效的 O(N) get_map_key 掃描
                speed_str = percentage_to_ordered_list_item(self._speed_names, percentage)
                speed_val = self._speed_name_reverse_map.get(speed_str)
                if speed_val is not None:
                    await self.set_property_async(prop=self._prop_fan_level, value=speed_val)
            else:
                await self.set_property_async(
                    prop=self._prop_fan_level,
                    value=int(percentage_to_ranged_value(
                        low_high_range=(self._speed_min, self._speed_max),
                        percentage=percentage)))
        else:
            await self.set_property_async(prop=self._prop_on, value=False)

    async def async_set_preset_mode(self, preset_mode: str) -> None:
        """Set the preset mode."""
        # 優化: 使用 O(1) 字典反查
        mode_val = self._mode_reverse_map.get(preset_mode)
        if mode_val is not None:
            await self.set_property_async(prop=self._prop_mode, value=mode_val)

    async def async_set_direction(self, direction: str) -> None:
        """Set the direction of the fan."""
        if not self._prop_wind_reverse:
            return
        await self.set_property_async(
            prop=self._prop_wind_reverse,
            value=(
                self._prop_wind_reverse_reverse
                if direction == DIRECTION_REVERSE
                else self._prop_wind_reverse_forward))

    async def async_oscillate(self, oscillating: bool) -> None:
        """Oscillate the fan."""
        await self.set_property_async(
            prop=self._prop_horizontal_swing, value=oscillating)

    @property
    def is_on(self) -> Optional[bool]:
        """Return if the fan is on."""
        if not self._prop_on:
            return None
        val = self.get_prop_value(prop=self._prop_on)
        # 優化: 嚴格轉換為 bool 型別，避免 HA 警告
        return bool(val) if val is not None else None

    @property
    def preset_mode(self) -> Optional[str]:
        """Return the current preset mode,
        e.g., auto, smart, eco, favorite."""
        if not self._prop_mode or not self._mode_map:
            return None
        val = self.get_prop_value(prop=self._prop_mode)
        return self._mode_map.get(val) if val is not None else None

    @property
    def current_direction(self) -> Optional[str]:
        """Return the current direction of the fan."""
        if not self._prop_wind_reverse:
            return None
        return DIRECTION_REVERSE if self.get_prop_value(
            prop=self._prop_wind_reverse
        ) == self._prop_wind_reverse_reverse else DIRECTION_FORWARD

    @property
    def percentage(self) -> Optional[int]:
        """Return the current percentage of the fan speed."""
        if not self._prop_fan_level:
            return None
        fan_level = self.get_prop_value(prop=self._prop_fan_level)
        if fan_level is None:
            return None
            
        if self._speed_names and self._speed_name_map:
            speed_str = self._speed_name_map.get(fan_level)
            if speed_str is not None:
                return ordered_list_item_to_percentage(self._speed_names, speed_str)
            return None
        else:
            return ranged_value_to_percentage(
                low_high_range=(self._speed_min, self._speed_max),
                value=fan_level)

    @property
    def oscillating(self) -> Optional[bool]:
        """Return if the fan is oscillating."""
        if not self._prop_horizontal_swing:
            return None
        val = self.get_prop_value(prop=self._prop_horizontal_swing)
        return bool(val) if val is not None else None