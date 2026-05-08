# -*- coding: utf-8 -*-
"""
Binary sensor entities for Xiaomi Home.
"""
from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.components.binary_sensor import BinarySensorEntity

from .miot.miot_spec import MIoTSpecProperty
from .miot.miot_device import MIoTDevice, MIoTPropertyEntity
from .miot.const import DOMAIN


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
        if miot_device.miot_client.display_binary_bool:
            for prop in miot_device.prop_list.get('binary_sensor', []):
                new_entities.append(
                    BinarySensor(miot_device=miot_device, spec=prop))

    if new_entities:
        async_add_entities(new_entities)


class BinarySensor(MIoTPropertyEntity, BinarySensorEntity):
    """Binary sensor entities for Xiaomi Home."""

    def __init__(self, miot_device: MIoTDevice, spec: MIoTSpecProperty) -> None:
        """Initialize the BinarySensor."""
        super().__init__(miot_device=miot_device, spec=spec)
        # Set device_class
        self._attr_device_class = spec.device_class

    @property
    def is_on(self) -> bool:
        """On/Off state. True if the binary sensor is on, False otherwise."""
        if self.spec.name == 'contact-state':
            return bool(self._value) is False
        elif self.spec.name == 'occupancy-status':
            return bool(self._value)
        return self._value is True
