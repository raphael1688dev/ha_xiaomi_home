# -*- coding: utf-8 -*-
"""
Number entities for Xiaomi Home.
"""
from typing import Optional

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.components.number import NumberEntity

from .miot.const import DOMAIN
from .miot.miot_spec import MIoTSpecProperty
from .miot.miot_device import MIoTDevice, MIoTPropertyEntity


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
        Number(miot_device=miot_device, spec=prop)
        for miot_device in device_list
        for prop in miot_device.prop_list.get('number', [])
    ]

    if new_entities:
        async_add_entities(new_entities)


class Number(MIoTPropertyEntity, NumberEntity):
    """Number entities for Xiaomi Home."""

    def __init__(self, miot_device: MIoTDevice, spec: MIoTSpecProperty) -> None:
        """Initialize the Number."""
        super().__init__(miot_device=miot_device, spec=spec)
        # Set device_class
        self._attr_device_class = spec.device_class
        # Set unit
        if self.spec.external_unit:
            self._attr_native_unit_of_measurement = self.spec.external_unit
        # Set icon
        if self.spec.icon and not self.device_class:
            self._attr_icon = self.spec.icon
        # Set value range
        if self._value_range:
            # Optimization: strictly convert to float to meet HA core NumberEntity specification
            self._attr_native_min_value = float(self._value_range.min_)
            self._attr_native_max_value = float(self._value_range.max_)
            self._attr_native_step = float(self._value_range.step)

    @property
    def native_value(self) -> Optional[float]:
        """Return the current value of the number."""
        # Optimization: prevent None value exception during startup and strictly convert to float
        if self._value is None:
            return None
        try:
            return float(self._value)
        except (ValueError, TypeError):
            return None

    async def async_set_native_value(self, value: float) -> None:
        """Set new value."""
        await self.set_property_async(value=value)