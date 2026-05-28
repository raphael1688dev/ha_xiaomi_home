# -*- coding: utf-8 -*-
"""
Binary sensor entities for Xiaomi Home.
"""

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

    # 優化: 扁平化巢狀迴圈並改為 List Comprehension，提升大量設備時的載入效能
    new_entities = [
        BinarySensor(miot_device=miot_device, spec=prop)
        for miot_device in device_list
        if miot_device.miot_client.display_binary_bool
        for prop in miot_device.prop_list.get('binary_sensor', [])
    ]

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
    def is_on(self) -> bool | None:
        """On/Off state. True if the binary sensor is on, False otherwise."""
        # 優化: 阻擋啟動初期 _value 為 None 時所導致的「幽靈觸發 (Ghost Triggers)」
        if self._value is None:
            return None

        # 針對門窗感測器 (contact-state) 的反轉邏輯
        if self.spec.name == 'contact-state':
            return not bool(self._value)
            
        # 優化: 確保嚴格回傳 boolean 型別，符合 HA 規範
        return bool(self._value)