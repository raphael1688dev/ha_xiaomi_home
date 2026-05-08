# -*- coding: utf-8 -*-
"""
Device tracker entities for Xiaomi Home.
"""
from __future__ import annotations
from typing import Optional

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.components.device_tracker import TrackerEntity

from .miot.const import DOMAIN
from .miot.miot_device import MIoTDevice, MIoTServiceEntity, MIoTEntityData
from .miot.miot_spec import MIoTSpecProperty


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    device_list: list[MIoTDevice] = hass.data[DOMAIN]['devices'][
        config_entry.entry_id]
    new_entities = []
    for miot_device in device_list:
        for data in miot_device.entity_list.get('device_tracker', []):
            new_entities.append(
                DeviceTracker(miot_device=miot_device, entity_data=data))
    if new_entities:
        async_add_entities(new_entities)


class DeviceTracker(MIoTServiceEntity, TrackerEntity):
    """Tracker entities for Xiaomi Home."""
    _prop_battery_level: Optional[MIoTSpecProperty]
    _prop_latitude: Optional[MIoTSpecProperty]
    _prop_longitude: Optional[MIoTSpecProperty]
    _prop_area_id: Optional[MIoTSpecProperty]

    def __init__(self, miot_device: MIoTDevice,
                 entity_data: MIoTEntityData) -> None:
        super().__init__(miot_device=miot_device, entity_data=entity_data)
        self._prop_battery_level = None
        self._prop_latitude = None
        self._prop_longitude = None
        self._prop_area_id = None

        # properties
        for prop in entity_data.props:
            if prop.name == 'battery-level':
                self._prop_battery_level = prop
            elif prop.name == 'latitude':
                self._prop_latitude = prop
            elif prop.name == 'longitude':
                self._prop_longitude = prop
            elif prop.name == 'area-id':
                self._prop_area_id = prop

    @property
    def battery_level(self) -> Optional[int]:
        """The battery level of the device."""
        return None if (self._prop_battery_level
                        is None) else self.get_prop_value(
                            prop=self._prop_battery_level)

    @property
    def latitude(self) -> Optional[float]:
        """The latitude coordinate of the device."""
        return None if self._prop_latitude is None else self.get_prop_value(
            prop=self._prop_latitude)

    @property
    def longitude(self) -> Optional[float]:
        """The longitude coordinate of the device."""
        return None if self._prop_longitude is None else self.get_prop_value(
            prop=self._prop_longitude)

    @property
    def location_name(self) -> Optional[str]:
        """The location name of the device."""
        return None if self._prop_area_id is None else self.get_prop_value(
            prop=self._prop_area_id)
