# -*- coding: utf-8 -*-
"""
Event entities for Xiaomi Home.
"""
from __future__ import annotations
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.components.event import EventEntity

from .miot.miot_spec import MIoTSpecEvent
from .miot.miot_device import MIoTDevice, MIoTEventEntity
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

    # Optimization: flatten nested loop with list comprehension for initialization performance
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

    def on_event_occurred(
        self, name: str, arguments: dict[str, Any] | None = None
    ) -> None:
        """Trigger event."""
        # 優化: 確保 arguments 為 None 時能安全給予空字典，避免潛在的 HA 屬性報錯
        self._trigger_event(
            event_type=name,
            event_attributes=arguments or {}
        )