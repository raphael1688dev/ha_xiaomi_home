# -*- coding: utf-8 -*-
"""
Humidifier entities for Xiaomi Home.
"""
import logging
from typing import Any, Optional

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.components.humidifier import (HumidifierEntity,
                                                 HumidifierDeviceClass,
                                                 HumidifierEntityFeature,
                                                 HumidifierAction)

from .miot.miot_spec import MIoTSpecProperty
from .miot.miot_device import MIoTDevice, MIoTEntityData, MIoTServiceEntity
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

    new_entities = []
    for miot_device in device_list:
        # 處理加濕器實體
        for data in miot_device.entity_list.get('humidifier', []):
            data.platform = 'humidifier'
            data.device_class = HumidifierDeviceClass.HUMIDIFIER
            new_entities.append(
                Humidifier(miot_device=miot_device, entity_data=data))
                
        # 處理除濕器實體
        for data in miot_device.entity_list.get('dehumidifier', []):
            data.platform = 'dehumidifier'
            data.device_class = HumidifierDeviceClass.DEHUMIDIFIER
            new_entities.append(
                Humidifier(miot_device=miot_device, entity_data=data))

    if new_entities:
        async_add_entities(new_entities)


class Humidifier(MIoTServiceEntity, HumidifierEntity):
    """Humidifier entities for Xiaomi Home."""
    # pylint: disable=unused-argument
    _prop_on: Optional[MIoTSpecProperty]
    _prop_target_humidity: Optional[MIoTSpecProperty]
    _prop_humidity: Optional[MIoTSpecProperty]
    _prop_mode: Optional[MIoTSpecProperty]

    _mode_map: Optional[dict[Any, Any]]
    _mode_reverse_map: dict[Any, Any]

    def __init__(self, miot_device: MIoTDevice,
                 entity_data: MIoTEntityData) -> None:
        """Initialize the Humidifier."""
        super().__init__(miot_device=miot_device, entity_data=entity_data)
        self._attr_device_class = entity_data.device_class
        self._attr_supported_features = HumidifierEntityFeature(0)

        self._prop_on = None
        self._prop_target_humidity = None
        self._prop_humidity = None
        self._prop_mode = None
        self._mode_map = None
        self._mode_reverse_map = {}

        # properties
        for prop in entity_data.props:
            if prop.name == 'on':
                self._prop_on = prop
            elif prop.name == 'target-humidity':
                if not prop.value_range:
                    _LOGGER.error(
                        'invalid target-humidity value_range format, %s',
                        self.entity_id)
                    continue
                self._attr_min_humidity = prop.value_range.min_
                self._attr_max_humidity = prop.value_range.max_
                self._prop_target_humidity = prop
            elif prop.name in ['relative-humidity', 'humidity']:
                self._prop_humidity = prop
            elif prop.name == 'mode':
                if not prop.value_list:
                    _LOGGER.error('mode value_list is None, %s',
                                  self.entity_id)
                    continue
                self._mode_map = prop.value_list.to_map()
                # 優化: 預先建立 O(1) 的模式反向查找字典，避免執行期效能損耗
                self._mode_reverse_map = {v: k for k, v in self._mode_map.items()}
                
                self._attr_available_modes = list(self._mode_map.values())
                self._attr_supported_features |= HumidifierEntityFeature.MODES
                self._prop_mode = prop

    async def async_turn_on(self, **kwargs) -> None:
        """Turn the device on."""
        await self.set_property_async(prop=self._prop_on, value=True)

    async def async_turn_off(self, **kwargs) -> None:
        """Turn the device off."""
        await self.set_property_async(prop=self._prop_on, value=False)

    async def async_set_humidity(self, humidity: int) -> None:
        """Set new target humidity."""
        await self.set_property_async(prop=self._prop_target_humidity,
                                      value=humidity)

    async def async_set_mode(self, mode: str) -> None:
        """Set new target preset mode."""
        # 優化: 使用 O(1) 字典查找取代 O(N) 遍歷
        mode_val = self._mode_reverse_map.get(mode)
        if mode_val is not None:
            await self.set_property_async(prop=self._prop_mode, value=mode_val)

    @property
    def is_on(self) -> Optional[bool]:
        """Return if the humidifier is on."""
        if not self._prop_on:
            return None
        val = self.get_prop_value(prop=self._prop_on)
        # 優化: 嚴格轉換為 bool 型別並安全過濾 None，符合 HA 規範
        return bool(val) if val is not None else None

    @property
    def action(self) -> Optional[HumidifierAction]:
        """Return the current status of the device."""
        if not self.is_on:
            return HumidifierAction.OFF
        if self._attr_device_class == HumidifierDeviceClass.HUMIDIFIER:
            return HumidifierAction.HUMIDIFYING
        return HumidifierAction.DRYING

    @property
    def current_humidity(self) -> Optional[int]:
        """Return the current humidity."""
        if not self._prop_humidity:
            return None
        val = self.get_prop_value(prop=self._prop_humidity)
        return int(val) if val is not None else None

    @property
    def target_humidity(self) -> Optional[int]:
        """Return the target humidity."""
        if not self._prop_target_humidity:
            return None
        val = self.get_prop_value(prop=self._prop_target_humidity)
        return int(val) if val is not None else None

    @property
    def mode(self) -> Optional[str]:
        """Return the current preset mode."""
        if not self._mode_map or not self._prop_mode:
            return None
        val = self.get_prop_value(prop=self._prop_mode)
        return self._mode_map.get(val) if val is not None else None