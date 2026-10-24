# -*- coding: utf-8 -*-
"""
Device tracker entities for Xiaomi Home.
"""
from typing import Any, Optional

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

    # Optimization: flatten nested loop with list comprehension for initialization performance
    new_entities = [
        DeviceTracker(miot_device=miot_device, entity_data=data)
        for miot_device in device_list
        for data in miot_device.entity_list.get('device_tracker', [])
    ]

    if new_entities:
        async_add_entities(new_entities)


class DeviceTracker(MIoTServiceEntity, TrackerEntity):
    """Tracker entities for Xiaomi Home."""
    _prop_latitude: Optional[MIoTSpecProperty]
    _prop_longitude: Optional[MIoTSpecProperty]
    _prop_area_id: Optional[MIoTSpecProperty]

    def __init__(self, miot_device: MIoTDevice, entity_data: MIoTEntityData) -> None:
        """Initialize the DeviceTracker."""
        super().__init__(miot_device=miot_device, entity_data=entity_data)

        self._prop_latitude = None
        self._prop_longitude = None
        self._prop_area_id = None

        # properties
        for prop in entity_data.props:
            if prop.name == 'latitude':
                self._prop_latitude = prop
            elif prop.name == 'longitude':
                self._prop_longitude = prop
            elif prop.name == 'area-id':
                self._prop_area_id = prop

    @property
    def latitude(self) -> Optional[float]:
        """Return latitude value of the device."""
        if not self._prop_latitude:
            return None
        val = self.get_prop_value(prop=self._prop_latitude)
        return float(val) if val is not None else None

    @property
    def longitude(self) -> Optional[float]:
        """Return longitude value of the device."""
        if not self._prop_longitude:
            return None
        val = self.get_prop_value(prop=self._prop_longitude)
        return float(val) if val is not None else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the extra state attributes of the device tracker."""
        attrs = super().extra_state_attributes
        if self._prop_area_id:
            val = self.get_prop_value(prop=self._prop_area_id)
            # _attr_location_name is deprecated (removed in HA 2027.7) and
            # area-id is not a zone, so expose it as an attribute only.
            if val is not None:
                attrs['location_name'] = str(val)
        return attrs
