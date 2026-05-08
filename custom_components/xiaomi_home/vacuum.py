# -*- coding: utf-8 -*-
"""
Vacuum entities for Xiaomi Home.
"""
from __future__ import annotations
from typing import Any, Optional
import re
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.components.vacuum import (StateVacuumEntity,
                                             VacuumEntityFeature)

from .miot.const import DOMAIN
from .miot.miot_device import MIoTDevice, MIoTServiceEntity, MIoTEntityData
from .miot.miot_spec import (MIoTSpecAction, MIoTSpecProperty)

try:  # VacuumActivity is introduced in HA core 2025.1.0
    from homeassistant.components.vacuum import VacuumActivity
    HA_CORE_HAS_ACTIVITY = True
except ImportError:
    HA_CORE_HAS_ACTIVITY = False

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    device_list: list[MIoTDevice] = hass.data[DOMAIN]['devices'][
        config_entry.entry_id]
        
    # 優化: 扁平化巢狀迴圈改用 List Comprehension，提升初始化載入效能
    new_entities = [
        Vacuum(miot_device=miot_device, entity_data=data)
        for miot_device in device_list
        for data in miot_device.entity_list.get('vacuum', [])
    ]
    
    if new_entities:
        async_add_entities(new_entities)


class Vacuum(MIoTServiceEntity, StateVacuumEntity):
    """Vacuum entities for Xiaomi Home."""
    # pylint: disable=unused-argument
    _prop_status: Optional[MIoTSpecProperty]
    _prop_fan_level: Optional[MIoTSpecProperty]
    
    # 優化: 將 list 改為 set，提升頻繁狀態輪詢時的 in 操作效能 (O(N) -> O(1))
    _prop_status_cleaning: set[int]
    _prop_status_docked: set[int]
    _prop_status_paused: set[int]
    _prop_status_returning: set[int]
    _prop_status_error: set[int]

    _action_start_sweep: Optional[MIoTSpecAction]
    _action_stop_sweeping: Optional[MIoTSpecAction]
    _action_pause_sweeping: Optional[MIoTSpecAction]
    _action_continue_sweep: Optional[MIoTSpecAction]
    _action_stop_and_gocharge: Optional[MIoTSpecAction]
    _action_identify: Optional[MIoTSpecAction]

    _status_map: Optional[dict[int, str]]
    _fan_level_map: Optional[dict[int, str]]
    _fan_level_reverse_map: dict[str, int]

    _device_name: str

    def __init__(self, miot_device: MIoTDevice,
                 entity_data: MIoTEntityData) -> None:
        super().__init__(miot_device=miot_device, entity_data=entity_data)
        self._device_name = miot_device.name
        self._attr_supported_features = VacuumEntityFeature(0)

        self._prop_status = None
        self._prop_fan_level = None
        self._prop_status_cleaning = set()
        self._prop_status_docked = set()
        self._prop_status_paused = set()
        self._prop_status_returning = set()
        self._prop_status_error = set()
        
        self._action_start_sweep = None
        self._action_stop_sweeping = None
        self._action_pause_sweeping = None
        self._action_continue_sweep = None
        self._action_stop_and_gocharge = None
        self._action_identify = None
        self._status_map = None
        self._fan_level_map = None
        self._fan_level_reverse_map = {}

        # properties
        for prop in entity_data.props:
            if prop.name == 'status':
                if not prop.value_list:
                    _LOGGER.error('invalid status value_list, %s',
                                  self.entity_id)
                    continue
                self._status_map = prop.value_list.to_map()
                self._attr_supported_features |= VacuumEntityFeature.STATE
                self._prop_status = prop
                for item in prop.value_list.items:
                    item_str: str = item.name
                    item_name: str = re.sub(r'[^a-z]', '', item_str)
                    if item_name in {
                            'charging', 'charged', 'chargingcompleted',
                            'fullcharge', 'fullpower', 'findchargerpause',
                            'drying', 'washing', 'wash', 'inthewash',
                            'inthedry', 'stationworking', 'dustcollecting',
                            'upgrade', 'upgrading', 'updating'
                    }:
                        self._prop_status_docked.add(item.value)
                    elif item_name in {'paused', 'pause'}:
                        self._prop_status_paused.add(item.value)
                    elif item_name in {
                            'gocharging', 'cleancompletegocharging',
                            'findchargewash', 'backtowashmop', 'gowash',
                            'gowashing', 'summon'
                    }:
                        self._prop_status_returning.add(item.value)
                    elif item_name in {
                            'error', 'breakcharging', 'gochargebreak'
                    }:
                        self._prop_status_error.add(item.value)
                    elif (item_name.find('sweeping') != -1) or (
                            item_name.find('mopping') != -1) or (item_name in {
                                'cleaning', 'remoteclean', 'continuesweep',
                                'busy', 'building', 'buildingmap', 'mapping'
                            }):
                        self._prop_status_cleaning.add(item.value)
            elif prop.name == 'fan-level':
                if not prop.value_list:
                    _LOGGER.error('invalid fan-level value_list, %s',
                                  self.entity_id)
                    continue
                self._fan_level_map = prop.value_list.to_map()
                # 優化: 預先建立 O(1) 風速反向查找字典，取代 O(N) 掃描
                self._fan_level_reverse_map = {v: k for k, v in self._fan_level_map.items()}
                self._attr_fan_speed_list = list(self._fan_level_map.values())
                self._attr_supported_features |= VacuumEntityFeature.FAN_SPEED
                self._prop_fan_level = prop
                
        # action
        for action in entity_data.actions:
            if action.name == 'start-sweep':
                self._attr_supported_features |= VacuumEntityFeature.START
                self._action_start_sweep = action
            elif action.name == 'stop-sweeping':
                self._attr_supported_features |= VacuumEntityFeature.STOP
                self._action_stop_sweeping = action
            elif action.name == 'pause-sweeping':
                self._attr_supported_features |= VacuumEntityFeature.PAUSE
                self._action_pause_sweeping = action
            elif action.name == 'continue-sweep':
                self._action_continue_sweep = action
            elif action.name == 'stop-and-gocharge':
                self._attr_supported_features |= VacuumEntityFeature.RETURN_HOME
                self._action_stop_and_gocharge = action
            elif action.name == 'identify':
                self._attr_supported_features |= VacuumEntityFeature.LOCATE
                self._action_identify = action

        # Use start-charge from battery service as fallback
        # if stop-and-gocharge is not available
        if self._action_stop_and_gocharge is None:
            for action in entity_data.actions:
                if action.name == 'start-charge':
                    self._attr_supported_features |= (
                        VacuumEntityFeature.RETURN_HOME)
                    self._action_stop_and_gocharge = action
                    break

    async def async_start(self) -> None:
        """Start or resume the cleaning task."""
        if self._prop_status is not None:
            status = self.get_prop_value(prop=self._prop_status)
            # 優化: 防護 status 為 None，避免潛在例外
            if (status is not None and status in self._prop_status_paused
               ) and self._action_continue_sweep:
                await self.action_async(action=self._action_continue_sweep)
                return
        await self.action_async(action=self._action_start_sweep)

    async def async_stop(self, **kwargs: Any) -> None:
        """Stop the vacuum cleaner, do not return to base."""
        await self.action_async(action=self._action_stop_sweeping)

    async def async_pause(self) -> None:
        """Pause the cleaning task."""
        await self.action_async(action=self._action_pause_sweeping)

    async def async_return_to_base(self, **kwargs: Any) -> None:
        """Set the vacuum cleaner to return to the dock."""
        await self.action_async(action=self._action_stop_and_gocharge)

    async def async_locate(self, **kwargs: Any) -> None:
        """Locate the vacuum cleaner."""
        await self.action_async(action=self._action_identify)

    async def async_set_fan_speed(self, fan_speed: str, **kwargs: Any) -> None:
        """Set fan speed."""
        # 優化: O(1) 字典查找取代 O(N) 遍歷
        fan_level_value = self._fan_level_reverse_map.get(fan_speed)
        if fan_level_value is not None:
            await self.set_property_async(prop=self._prop_fan_level,
                                          value=fan_level_value)

    @property
    def name(self) -> Optional[str]:
        """Name of the vacuum entity."""
        return self._device_name

    @property
    def fan_speed(self) -> Optional[str]:
        """The current fan speed of the vacuum cleaner."""
        if not self._fan_level_map or not self._prop_fan_level:
            return None
        val = self.get_prop_value(prop=self._prop_fan_level)
        # 優化: 直接使用 O(1) 字典獲取並加上安全過濾
        return self._fan_level_map.get(val) if val is not None else None

    if HA_CORE_HAS_ACTIVITY:

        @property
        def activity(self) -> Optional[str]:
            """The current vacuum activity."""
            if not self._prop_status:
                return None
            status = self.get_prop_value(prop=self._prop_status)
            if status is None:
                return None
            if status in self._prop_status_cleaning:
                return VacuumActivity.CLEANING
            if status in self._prop_status_docked:
                return VacuumActivity.DOCKED
            if status in self._prop_status_paused:
                return VacuumActivity.PAUSED
            if status in self._prop_status_returning:
                return VacuumActivity.RETURNING
            if status in self._prop_status_error:
                return VacuumActivity.ERROR
            return VacuumActivity.IDLE

    else:

        @property
        def state(self) -> Optional[str]:
            """The current state of the vacuum."""
            if not self._status_map or not self._prop_status:
                return None
            status = self.get_prop_value(prop=self._prop_status)
            return self._status_map.get(status) if status is not None else None