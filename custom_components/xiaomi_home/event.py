# -*- coding: utf-8 -*-
"""
Event entities for Xiaomi Home.
"""
import logging
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.components.event import (
    DoorbellEventType, EventDeviceClass, EventEntity)

from .data import XiaomiHomeConfigEntry
from .miot.miot_spec import MIoTSpecEvent
from .miot.miot_device import MIoTDevice, MIoTEventEntity

_LOGGER = logging.getLogger(__name__)

# Commands and polls go to the cloud, the gateway or the device on their
# own; Home Assistant does not need to serialise them
PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: XiaomiHomeConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up a config entry."""
    # pylint: disable=unused-argument
    device_list: list[MIoTDevice] = config_entry.runtime_data.devices

    # Optimization: flatten nested loop with list comprehension for
    # initialization performance
    new_entities = [
        Event(miot_device=miot_device, spec=event)
        for miot_device in device_list
        for event in miot_device.event_list.get('event', [])
    ]

    if new_entities:
        async_add_entities(new_entities)


class Event(MIoTEventEntity, EventEntity):
    """Event entities for Xiaomi Home."""

    def __init__(self, miot_device: MIoTDevice, spec: MIoTSpecEvent) -> None:
        """Initialize the Event."""
        super().__init__(miot_device=miot_device, spec=spec)
        # Set device_class
        self._attr_device_class = spec.device_class
        # Doorbells must offer the standard ring event, required in 2027.4
        if self._attr_device_class == EventDeviceClass.DOORBELL:
            self._attr_event_types = [DoorbellEventType.RING]

    def on_event_occurred(
        self, name: str, arguments: dict[str, Any] | None = None
    ) -> None:
        """Trigger event."""
        if self._attr_device_class == EventDeviceClass.DOORBELL:
            name = DoorbellEventType.RING
        # Optimized: Safely fallback to empty dict when arguments is None to
        # avoid HA attribute errors
        self._trigger_event(
            event_type=name,
            event_attributes=arguments or {}
        )
