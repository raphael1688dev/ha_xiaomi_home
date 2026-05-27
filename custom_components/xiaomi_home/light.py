# -*- coding: utf-8 -*-
"""
Light entities for Xiaomi Home.
"""
from __future__ import annotations
import logging
import asyncio
from typing import Any, Optional

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ATTR_COLOR_TEMP_KELVIN,
    ATTR_RGB_COLOR,
    ATTR_EFFECT,
    LightEntity,
    LightEntityFeature,
    ColorMode
)
from homeassistant.util.color import (
    value_to_brightness,
    brightness_to_value
)

from .miot.miot_spec import MIoTSpecProperty
from .miot.miot_device import MIoTDevice, MIoTEntityData,  MIoTServiceEntity
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

    # 優化: 扁平化雙層迴圈改用 List Comprehension，加速設備載入
    new_entities = [
        Light(miot_device=miot_device, entity_data=data)
        for miot_device in device_list
        for data in miot_device.entity_list.get('light', [])
    ]

    if new_entities:
        async_add_entities(new_entities)


class Light(MIoTServiceEntity, LightEntity):
    """Light entities for Xiaomi Home."""
    # pylint: disable=unused-argument
    _VALUE_RANGE_MODE_COUNT_MAX = 30
    _prop_on: Optional[MIoTSpecProperty]
    _prop_brightness: Optional[MIoTSpecProperty]
    _prop_color_temp: Optional[MIoTSpecProperty]
    _prop_color: Optional[MIoTSpecProperty]
    _prop_mode: Optional[MIoTSpecProperty]

    _brightness_scale: Optional[tuple[int, int]]
    _effect_map: dict[str, tuple[MIoTSpecProperty, Any]]
    _effect_reverse_map: dict[tuple[MIoTSpecProperty, Any], str]

    def __init__(
        self, miot_device: MIoTDevice,  entity_data: MIoTEntityData
    ) -> None:
        """Initialize the Light."""
        super().__init__(miot_device=miot_device,  entity_data=entity_data)
        self._attr_color_mode = None
        self._attr_supported_color_modes = set()
        self._attr_supported_features = LightEntityFeature(0)
        if miot_device.did.startswith('group.'):
            self._attr_icon = 'mdi:lightbulb-group'

        self._prop_on = None
        self._prop_brightness = None
        self._prop_color_temp = None
        self._prop_color = None
        self._prop_mode = None
        self._brightness_scale = None
        self._effect_map = {}
        self._effect_reverse_map = {}

        # properties
        if prop := entity_data.get_prop('on'):
            self._prop_on = prop
            
        if prop := entity_data.get_prop('brightness'):
            if prop.value_range:
                self._brightness_scale = (
                    prop.value_range.min_, prop.value_range.max_)
                self._prop_brightness = prop
            elif prop.value_list:
                # For value-list brightness
                for val, desc in prop.value_list.to_map().items():
                    effect_name = f"Brightness: {desc}"
                    self._effect_map[effect_name] = (prop, val)
                    self._effect_reverse_map[(prop, val)] = effect_name
                self._attr_effect_list = list(self._effect_map.keys())
                self._attr_supported_features |= LightEntityFeature.EFFECT
                self._prop_brightness = prop
            else:
                _LOGGER.info(
                    'invalid brightness format, %s', self.entity_id)
                    
        if prop := entity_data.get_prop('color-temperature'):
            if not prop.value_range:
                _LOGGER.info(
                    'invalid color-temperature value_range format, %s',
                    self.entity_id)
            else:
                self._attr_min_color_temp_kelvin = prop.value_range.min_
                self._attr_max_color_temp_kelvin = prop.value_range.max_
                self._attr_supported_color_modes.add(ColorMode.COLOR_TEMP)
                self._attr_color_mode = ColorMode.COLOR_TEMP
                self._prop_color_temp = prop
                
        if prop := entity_data.get_prop('color'):
            self._attr_supported_color_modes.add(ColorMode.RGB)
            self._attr_color_mode = ColorMode.RGB
            self._prop_color = prop
            
        if prop := entity_data.get_prop('mode'):
            mode_list = None
            if prop.value_list:
                mode_list = prop.value_list.to_map()
            elif prop.value_range:
                mode_list = {}
                if (
                    int((
                        prop.value_range.max_
                        - prop.value_range.min_
                    ) / prop.value_range.step)
                    > self._VALUE_RANGE_MODE_COUNT_MAX
                ):
                    _LOGGER.error(
                        'too many mode values, %s, %s, %s',
                        self.entity_id, prop.name, prop.value_range)
                else:
                    for value in range(
                            prop.value_range.min_,
                            prop.value_range.max_ + prop.value_range.step,
                            prop.value_range.step):
                        mode_list[value] = f'mode {value}'
            if mode_list:
                for val, desc in mode_list.items():
                    effect_name = f"Mode: {desc}" if desc in self._effect_map else desc
                    self._effect_map[effect_name] = (prop, val)
                    self._effect_reverse_map[(prop, val)] = effect_name
                self._attr_effect_list = list(self._effect_map.keys())
                self._attr_supported_features |= LightEntityFeature.EFFECT
                self._prop_mode = prop
            else:
                _LOGGER.info('invalid mode format, %s', self.entity_id)

        if not self._attr_supported_color_modes:
            if self._prop_brightness:
                self._attr_supported_color_modes.add(ColorMode.BRIGHTNESS)
                self._attr_color_mode = ColorMode.BRIGHTNESS
            elif self._prop_on:
                self._attr_supported_color_modes.add(ColorMode.ONOFF)
                self._attr_color_mode = ColorMode.ONOFF

    @property
    def is_on(self) -> Optional[bool]:
        """Return if the light is on."""
        value_on = self.get_prop_value(prop=self._prop_on)
        if value_on is None:
            return None
        # 優化: 移除原先冗長的特例寫法，直接用 bool() 安全轉型，兼容 int(1/0) 與 bool(True/False)
        return bool(value_on)

    @property
    def brightness(self) -> Optional[int]:
        """Return the brightness."""
        brightness_value = self.get_prop_value(prop=self._prop_brightness)
        if brightness_value is None:
            return None
        return value_to_brightness(self._brightness_scale, brightness_value)

    @property
    def color_temp_kelvin(self) -> Optional[int]:
        """Return the color temperature."""
        return self.get_prop_value(prop=self._prop_color_temp)

    @property
    def rgb_color(self) -> Optional[tuple[int, int, int]]:
        """Return the rgb color value."""
        rgb = self.get_prop_value(prop=self._prop_color)
        if rgb is None:
            return None
        r = (rgb >> 16) & 0xFF
        g = (rgb >> 8) & 0xFF
        b = rgb & 0xFF
        return r, g, b

    @property
    def effect(self) -> Optional[str]:
        """Return the current mode."""
        if not self._effect_map:
            return None
        # Check mode property first (since it's typically the "main" effect)
        if self._prop_mode:
            val = self.get_prop_value(prop=self._prop_mode)
            if val is not None and (self._prop_mode, val) in self._effect_reverse_map:
                return self._effect_reverse_map[(self._prop_mode, val)]
        # Then check brightness property
        if self._prop_brightness and not self._brightness_scale:
            val = self.get_prop_value(prop=self._prop_brightness)
            if val is not None and (self._prop_brightness, val) in self._effect_reverse_map:
                return self._effect_reverse_map[(self._prop_brightness, val)]
        return None

    async def async_turn_on(self, **kwargs) -> None:
        """Turn the light on.

        Shall set attributes in kwargs if applicable.
        """
        # 1. 確保燈光是開啟的 (避免尚未開機時，屬性指令被設備忽略)
        if self._prop_on and not self.is_on:
            value_on = True if self._prop_on.format_ == bool else 1
            await self.set_property_async(
                prop=self._prop_on, value=value_on, write_ha_state=False)

        # 優化: 2. 將所有屬性設定打包為任務，併發傳送以消除「瀑布式」延遲卡頓
        tasks = []

        # brightness
        if ATTR_BRIGHTNESS in kwargs and self._prop_brightness:
            brightness = brightness_to_value(
                self._brightness_scale, kwargs[ATTR_BRIGHTNESS])
            tasks.append(self.set_property_async(
                prop=self._prop_brightness, value=brightness,
                write_ha_state=False))
                
        # color-temperature
        if ATTR_COLOR_TEMP_KELVIN in kwargs and self._prop_color_temp:
            tasks.append(self.set_property_async(
                prop=self._prop_color_temp,
                value=kwargs[ATTR_COLOR_TEMP_KELVIN],
                write_ha_state=False))
            self._attr_color_mode = ColorMode.COLOR_TEMP
            
        # rgb color
        if ATTR_RGB_COLOR in kwargs and self._prop_color:
            r, g, b = kwargs[ATTR_RGB_COLOR]  # 優化: 簡化陣列取值
            rgb = (r << 16) | (g << 8) | b
            tasks.append(self.set_property_async(
                prop=self._prop_color, value=rgb,
                write_ha_state=False))
            self._attr_color_mode = ColorMode.RGB
            
        # effect
        if ATTR_EFFECT in kwargs and self._effect_map:
            effect_val = self._effect_map.get(kwargs[ATTR_EFFECT])
            if effect_val is not None:
                prop, val = effect_val
                tasks.append(self.set_property_async(
                    prop=prop, value=val,
                    write_ha_state=False))

        # 併發執行所有屬性調整
        if tasks:
            await asyncio.gather(*tasks)

        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs) -> None:
        """Turn the light off."""
        if not self._prop_on:
            return
        value_on = False if self._prop_on.format_ == bool else 0
        await self.set_property_async(prop=self._prop_on, value=value_on)