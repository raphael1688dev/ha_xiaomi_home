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

    new_entities = []
    for miot_device in device_list:
        for prop in miot_device.prop_list.get('sensor', []):
            new_entities.append(Sensor(miot_device=miot_device, spec=prop))

        if miot_device.miot_client.display_binary_text:
            for prop in miot_device.prop_list.get('binary_sensor', []):
                if not prop.value_list:
                    continue
                new_entities.append(Sensor(miot_device=miot_device, spec=prop))

    if new_entities:
        async_add_entities(new_entities)


class Sensor(MIoTPropertyEntity, SensorEntity):
    """Sensor entities for Xiaomi Home."""

    def __init__(self, miot_device: MIoTDevice, spec: MIoTSpecProperty) -> None:
        """Initialize the Sensor."""
        super().__init__(miot_device=miot_device, spec=spec)
        # Set device_class
        if self._value_list:
            self._attr_device_class = SensorDeviceClass.ENUM
            self._attr_icon = 'mdi:format-text'
            self._attr_native_unit_of_measurement = None
            self._attr_options = self._value_list.descriptions
        else:
            self._attr_device_class = spec.device_class
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
        if self._value_range and isinstance(self._value, (int, float)):
            if (
                self._value < self._value_range.min_
                or self._value > self._value_range.max_
            ):
                _LOGGER.info(
                    '%s, data exception, out of range, %s, %s',
                    self.entity_id, self._value, self._value_range)
        if self._value_list:
            return self.get_vlist_description(self._value)
        if isinstance(self._value, str):
            return self._value[:255]
        return self._value
