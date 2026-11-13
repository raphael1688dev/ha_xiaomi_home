# -*- coding: utf-8 -*-
"""
Button entities for Xiaomi Home.
"""

from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.components.button import ButtonEntity

from .data import XiaomiHomeConfigEntry
from .miot.miot_device import MIoTActionEntity, MIoTDevice
from .miot.miot_spec import MIoTSpecAction


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
        Button(miot_device=miot_device, spec=action)
        for miot_device in device_list
        for action in miot_device.action_list.get('button', [])
    ]

    if new_entities:
        async_add_entities(new_entities)


class Button(MIoTActionEntity, ButtonEntity):
    """Button entities for Xiaomi Home."""

    def __init__(self, miot_device: MIoTDevice, spec: MIoTSpecAction) -> None:
        """Initialize the Button."""
        super().__init__(miot_device=miot_device, spec=spec)
        # Use default device class

    async def async_press(self) -> None:
        """Press the button."""
        # Optimized: Remove redundant return to conform with async_press -> None
        # type specification
        await self.action_async()
