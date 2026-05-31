# -*- coding: utf-8 -*-
"""
Sensor entities for Xiaomi Home.
"""
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.components.sensor import SensorEntity, SensorDeviceClass
from homeassistant.components.sensor import DEVICE_CLASS_UNITS
from homeassistant.const import EntityCategory

from .miot.miot_device import MIoTDevice, MIoTPropertyEntity
from .miot.miot_spec import MIoTSpecProperty
from .miot.const import DOMAIN, LAN_CAPABLE_CONNECT_TYPES

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up a config entry."""
    device_list: list[MIoTDevice] = hass.data[DOMAIN]['devices'][
        config_entry.entry_id]

    # 扁平化巢狀迴圈，改用效能更好的列表推導式
    new_entities = [
        Sensor(miot_device=miot_device, spec=prop)
        for miot_device in device_list
        for prop in miot_device.prop_list.get('sensor', [])
    ]

    # Handle logic to display Binary Sensor as generic text Sensor
    new_entities.extend([
        Sensor(miot_device=miot_device, spec=prop)
        for miot_device in device_list
        if miot_device.miot_client.display_binary_text
        for prop in miot_device.prop_list.get('binary_sensor', [])
        if prop.value_list
    ])

    # Add Control Path diagnostic sensor
    new_entities.extend([
        MIoTControlPathSensor(miot_device=miot_device, entry_id=config_entry.entry_id)
        for miot_device in device_list
    ])

    # Add IP Address diagnostic sensor
    new_entities.extend([
        MIoTIPAddressSensor(miot_device=miot_device, entry_id=config_entry.entry_id)
        for miot_device in device_list
        if miot_device.connect_type in LAN_CAPABLE_CONNECT_TYPES
    ])

    if new_entities:
        async_add_entities(new_entities)


class Sensor(MIoTPropertyEntity, SensorEntity):
    """Sensor entities for Xiaomi Home."""

    def __init__(self, miot_device: MIoTDevice, spec: MIoTSpecProperty) -> None:
        """Initialize the Sensor."""
        super().__init__(miot_device=miot_device, spec=spec)
        self._attr_device_class = spec.device_class
        
        # Pre-build O(1) reverse lookup dict, and force str conversion to prevent int/str mismatch
        self._val_desc_map = {}
        if spec.value_list:
            self._val_desc_map = {
                str(item.value): item.description 
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
        # 保護尚未取得設備狀態時的情境
        if self._value is None:
            return None

        if self._value_range and isinstance(self._value, (int, float)):
            if (
                self._value < self._value_range.min_
                or self._value > self._value_range.max_
            ):
                _LOGGER.debug(
                    '%s, data exception, out of range, %s, %s',
                    self.entity_id, self._value, self._value_range)
                return None
                    
        if self._value_list:
            str_val = str(self._value)
            # O(1) 字典查找
            if str_val in self._val_desc_map:
                return self._val_desc_map[str_val]
                
            # Fix Enum error caused by undefined options:
            # If device reports an undocumented value (e.g. 0), dynamically add it to _attr_options
            _opts = self._attr_options or []
            if str_val not in _opts:
                if len(_opts) > 64:
                    _LOGGER.warning(
                        "Device returned too many undocumented values for %s. Ignoring '%s'.",
                        self.entity_id, str_val
                    )
                else:
                    self._attr_options = list(_opts) + [str_val]
                    _LOGGER.debug(
                        "Device returned undocumented value '%s' for %s. Dynamically added to Enum options.", 
                        str_val, self.entity_id
                    )
                
            return str_val
            
        if isinstance(self._value, str):
            return self._value[:255]
            
        return self._value

class MIoTControlPathSensor(SensorEntity):
    """Diagnostic sensor to display the current control path of the device."""

    def __init__(self, miot_device: MIoTDevice, entry_id: str) -> None:
        self.miot_device = miot_device
        self._attr_unique_id = f"{entry_id}_{miot_device.did}_control_path"
        self._attr_name = "Control Path"
        self._attr_entity_category = EntityCategory.DIAGNOSTIC
        self._attr_entity_registry_enabled_default = False
        self._attr_icon = "mdi:transit-connection-variant"
        self._attr_has_entity_name = True
        self._attr_should_poll = True
        self.entity_id = f"sensor.{miot_device.entity_id_prefix}_control_path"

    @property
    def device_info(self):
        return self.miot_device.device_info

    @property
    def available(self) -> bool:
        return True

    @property
    def native_value(self) -> str:
        if self.miot_device and self.miot_device.miot_client:
            return self.miot_device.miot_client.get_device_control_path(self.miot_device.did)
        return "Unknown"

class MIoTIPAddressSensor(SensorEntity):
    """Diagnostic sensor to display the local IP address of the device."""

    def __init__(self, miot_device: MIoTDevice, entry_id: str) -> None:
        self.miot_device = miot_device
        self._attr_unique_id = f"{entry_id}_{miot_device.did}_ip_address"
        self._attr_name = "IP Address"
        self._attr_entity_category = EntityCategory.DIAGNOSTIC
        self._attr_entity_registry_enabled_default = False
        self._attr_icon = "mdi:ip-network"
        self._attr_has_entity_name = True
        self._attr_should_poll = True
        self.entity_id = f"sensor.{miot_device.entity_id_prefix}_ip_address"

    @property
    def device_info(self):
        return self.miot_device.device_info

    @property
    def available(self) -> bool:
        return self.miot_device.online

    @property
    def native_value(self) -> str:
        return self.miot_device.local_ip or "Unknown"
