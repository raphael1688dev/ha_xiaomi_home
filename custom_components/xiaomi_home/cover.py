# -*- coding: utf-8 -*-
"""
Cover entities for Xiaomi Home.
"""
from typing import Any, Optional
import re
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.components.cover import (ATTR_POSITION, CoverEntity,
                                            CoverEntityFeature,
                                            CoverDeviceClass)

from .miot.miot_spec import MIoTSpecProperty
from .miot.miot_device import MIoTDevice, MIoTEntityData, MIoTServiceEntity
from .miot.const import DOMAIN

_LOGGER = logging.getLogger(__name__)

# 優化: 提取常數映射表，取代原本冗長的 if-elif 判斷
_DEVICE_CLASS_MAP = {
    'curtain': CoverDeviceClass.CURTAIN,
    'window-opener': CoverDeviceClass.WINDOW,
    'motor-controller': CoverDeviceClass.SHUTTER,
    'airer': CoverDeviceClass.BLIND
}

async def async_setup_entry(hass: HomeAssistant, config_entry: ConfigEntry,
                            async_add_entities: AddEntitiesCallback) -> None:
    """Set up a config entry."""
    device_list: list[MIoTDevice] = hass.data[DOMAIN]['devices'][
        config_entry.entry_id]

    new_entities = []
    for miot_device in device_list:
        for data in miot_device.entity_list.get('cover', []):
            # 優化: O(1) 字典查找設備類別
            if data.spec.name in _DEVICE_CLASS_MAP:
                data.spec.device_class = _DEVICE_CLASS_MAP[data.spec.name]
            new_entities.append(Cover(miot_device=miot_device, entity_data=data))

    if new_entities:
        async_add_entities(new_entities)


class Cover(MIoTServiceEntity, CoverEntity):
    """Cover entities for Xiaomi Home."""
    # pylint: disable=unused-argument
    _cover_dead_zone_width: int
    _prop_motor_control: Optional[MIoTSpecProperty]
    _prop_motor_value_open: Optional[int]
    _prop_motor_value_close: Optional[int]
    _prop_motor_value_pause: Optional[int]
    _prop_status: Optional[MIoTSpecProperty]
    
    # 優化: 將 list 改為 set，提升 in 判斷的查詢效能至 O(1)
    _prop_status_opening: set[int]
    _prop_status_closing: set[int]
    _prop_status_closed: set[int]
    
    _prop_current_position: Optional[MIoTSpecProperty]
    _prop_target_position: Optional[MIoTSpecProperty]
    _prop_position_value_min: Optional[int]
    _prop_position_value_max: Optional[int]
    _prop_position_value_range: Optional[int]
    _prop_pos_closing: bool
    _prop_pos_opening: bool

    def __init__(self, miot_device: MIoTDevice,
                 entity_data: MIoTEntityData) -> None:
        """Initialize the Cover."""
        super().__init__(miot_device=miot_device, entity_data=entity_data)
        self._attr_device_class = entity_data.spec.device_class
        self._attr_supported_color_modes = set()
        self._attr_supported_features = CoverEntityFeature(0)

        self._cover_dead_zone_width = (
            miot_device.miot_client.cover_dead_zone_width)

        self._prop_motor_control = None
        self._prop_motor_value_open = None
        self._prop_motor_value_close = None
        self._prop_motor_value_pause = None
        self._prop_status = None
        self._prop_status_opening = set()
        self._prop_status_closing = set()
        self._prop_status_closed = set()
        self._prop_current_position = None
        self._prop_target_position = None
        self._prop_position_value_min = None
        self._prop_position_value_max = None
        self._prop_position_value_range = None
        self._prop_pos_closing = False
        self._prop_pos_opening = False

        # properties
        for prop in entity_data.props:
            if prop.name == 'motor-control':
                if not prop.value_list:
                    _LOGGER.error('motor-control value_list is None, %s',
                                  self.entity_id)
                    continue
                for item in prop.value_list.items:
                    if item.name in {'open', 'up'}:
                        self._attr_supported_features |= CoverEntityFeature.OPEN
                        self._prop_motor_value_open = item.value
                    elif item.name in {'close', 'down'}:
                        self._attr_supported_features |= CoverEntityFeature.CLOSE
                        self._prop_motor_value_close = item.value
                    elif item.name in {'pause', 'stop'}:
                        self._attr_supported_features |= CoverEntityFeature.STOP
                        self._prop_motor_value_pause = item.value
                self._prop_motor_control = prop
            elif prop.name == 'status':
                if not prop.value_list:
                    _LOGGER.error('status value_list is None, %s',
                                  self.entity_id)
                    continue
                for item in prop.value_list.items:
                    item_str: str = item.name
                    item_name: str = re.sub(r'[^a-z]', '', item_str)
                    if item_name in {
                            'opening', 'open', 'up', 'uping', 'rise', 'rising'
                    }:
                        self._prop_status_opening.add(item.value)
                    elif item_name in {
                            'closing', 'close', 'down', 'dowm', 'falling',
                            'fallin', 'dropping', 'downing', 'lower'
                    }:
                        self._prop_status_closing.add(item.value)
                    elif item_name in {
                            'closed', 'closeover', 'stopatlowest',
                            'stoplowerlimit', 'lowerlimitstop', 'floor',
                            'lowerlimit'
                    }:
                        self._prop_status_closed.add(item.value)
                self._prop_status = prop
            elif prop.name == 'current-position':
                if not prop.value_range:
                    _LOGGER.error(
                        'invalid current-position value_range format, %s',
                        self.entity_id)
                    continue
                self._prop_position_value_min = prop.value_range.min_
                self._prop_position_value_max = prop.value_range.max_
                self._prop_position_value_range = (prop.value_range.max_ -
                                                   prop.value_range.min_)
                self._prop_current_position = prop
            elif prop.name == 'target-position':
                if not prop.value_range:
                    _LOGGER.error(
                        'invalid target-position value_range format, %s',
                        self.entity_id)
                    continue
                self._prop_position_value_min = prop.value_range.min_
                self._prop_position_value_max = prop.value_range.max_
                self._prop_position_value_range = (prop.value_range.max_ -
                                                   prop.value_range.min_)
                self._attr_supported_features |= CoverEntityFeature.SET_POSITION
                self._prop_target_position = prop
                
        if (self._prop_status is None) and (self._prop_current_position
                                            is not None):
            self.sub_prop_changed(self._prop_current_position,
                                  self._position_changed_handler)

    def _position_changed_handler(self, prop: MIoTSpecProperty,
                                  ctx: Any) -> None:
        self._prop_pos_closing = False
        self._prop_pos_opening = False
        self.async_write_ha_state()

    async def async_open_cover(self, **kwargs) -> None:
        """Open the cover."""
        current = None if (self._prop_current_position
                           is None) else self.get_prop_value(
                               prop=self._prop_current_position)
        if (current is not None) and (current < self._prop_position_value_max):
            self._prop_pos_opening = True
            self._prop_pos_closing = False
        await self.set_property_async(self._prop_motor_control,
                                      self._prop_motor_value_open)

    async def async_close_cover(self, **kwargs) -> None:
        """Close the cover."""
        current = None if (self._prop_current_position
                           is None) else self.get_prop_value(
                               prop=self._prop_current_position)
        if (current is not None) and (current > self._prop_position_value_min):
            self._prop_pos_opening = False
            self._prop_pos_closing = True
        await self.set_property_async(self._prop_motor_control,
                                      self._prop_motor_value_close)

    async def async_stop_cover(self, **kwargs) -> None:
        """Stop the cover."""
        self._prop_pos_opening = False
        self._prop_pos_closing = False
        await self.set_property_async(self._prop_motor_control,
                                      self._prop_motor_value_pause)

    async def async_set_cover_position(self, **kwargs) -> None:
        """Set the position of the cover."""
        pos = kwargs.get(ATTR_POSITION, None)
        if pos is None:
            return None
        current = self.current_cover_position
        if current is not None:
            self._prop_pos_opening = pos > current
            self._prop_pos_closing = pos < current
        
        # 優化: 防護 ZeroDivisionError 並修正 min 偏移值的邏輯漏洞
        if self._prop_position_value_range and self._prop_position_value_range > 0:
            pos_val = (pos * self._prop_position_value_range / 100) + (self._prop_position_value_min or 0)
            pos = round(pos_val)
        else:
            pos = round(pos)

        await self.set_property_async(prop=self._prop_target_position,
                                      value=pos)

    @property
    def current_cover_position(self) -> Optional[int]:
        """Return the current position.

        0: the cover is closed, 100: the cover is fully opened, None: unknown.
        """
        if self._prop_current_position is None:
            if self._prop_target_position is None:
                return None
            self._prop_pos_opening = False
            self._prop_pos_closing = False
            pos_val = self.get_prop_value(prop=self._prop_target_position)
        else:
            pos_val = self.get_prop_value(prop=self._prop_current_position)
            
        if pos_val is None:
            return None
            
        # 優化: 防護 ZeroDivisionError 並補上 min 偏移值的正確計算
        if self._prop_position_value_range and self._prop_position_value_range > 0:
            pos = round((pos_val - (self._prop_position_value_min or 0)) * 100 / self._prop_position_value_range)
        else:
            pos = round(pos_val)
            
        if pos <= self._cover_dead_zone_width:
            pos = 0
        elif pos >= (100 - self._cover_dead_zone_width):
            pos = 100
        return pos

    @property
    def is_opening(self) -> Optional[bool]:
        """Return if the cover is opening."""
        if self._prop_status and self._prop_status_opening:
            val = self.get_prop_value(prop=self._prop_status)
            return val in self._prop_status_opening if val is not None else False
        return self._prop_pos_opening

    @property
    def is_closing(self) -> Optional[bool]:
        """Return if the cover is closing."""
        if self._prop_status and self._prop_status_closing:
            val = self.get_prop_value(prop=self._prop_status)
            return val in self._prop_status_closing if val is not None else False
        return self._prop_pos_closing

    @property
    def is_closed(self) -> Optional[bool]:
        """Return if the cover is closed."""
        if self.current_cover_position is not None:
            return self.current_cover_position == 0
        if self._prop_status and self._prop_status_closed:
            val = self.get_prop_value(prop=self._prop_status)
            return val in self._prop_status_closed if val is not None else False
        return None