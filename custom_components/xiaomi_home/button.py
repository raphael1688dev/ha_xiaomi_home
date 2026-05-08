# -*- coding: utf-8 -*-
"""
Button entities for Xiaomi Home.
"""
from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.components.button import ButtonEntity

from .miot.miot_device import MIoTActionEntity, MIoTDevice
from .miot.miot_spec import MIoTSpecAction
from .miot.const import DOMAIN


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up a config entry."""
    device_list: list[MIoTDevice] = hass.data[DOMAIN]['devices'][
        config_entry.entry_id]

    # 優化: 扁平化巢狀迴圈改用 List Comprehension，提升初始化載入效能
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
        # 優化: 移除多餘的 return，符合 async_press -> None 的型別宣告規範
        await self.action_async()