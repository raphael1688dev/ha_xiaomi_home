# -*- coding: utf-8 -*-
"""
Notify entities for Xiaomi Home.
"""
from __future__ import annotations
import logging
from typing import Any, Optional

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.components.notify import NotifyEntity
from homeassistant.util import yaml
from homeassistant.exceptions import HomeAssistantError

from .miot.miot_spec import MIoTSpecAction
from .miot.miot_device import MIoTDevice, MIoTActionEntity
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

    # 優化: 扁平化巢狀迴圈改用 List Comprehension，提升初始化載入效能
    new_entities = [
        Notify(miot_device=miot_device, spec=action)
        for miot_device in device_list
        for action in miot_device.action_list.get('notify', [])
    ]

    if new_entities:
        async_add_entities(new_entities)


class Notify(MIoTActionEntity, NotifyEntity):
    """Notify entities for Xiaomi Home."""
    # pylint: disable=unused-argument

    def __init__(self, miot_device: MIoTDevice, spec: MIoTSpecAction) -> None:
        """Initialize the Notify."""
        super().__init__(miot_device=miot_device, spec=spec)

    async def async_send_message(
        self, message: str, title: Optional[str] = None
    ) -> None:
        """Send a message."""
        in_list = []
        try:
            in_list = yaml.parse_yaml(message)
        except HomeAssistantError as err:
            _LOGGER.error(
                'action exec failed, %s(%s), parse message error, %s',
                self.name, self.entity_id, err)
            return

        if not isinstance(in_list, list):
            _LOGGER.error(
                'action exec failed, %s(%s), params must be a list, %s',
                self.name, self.entity_id, message)
            return

        if len(in_list) != len(self.spec.in_):
            _LOGGER.error(
                'action exec failed, %s(%s), missing params, '
                'requires %s params, but %s provided, %s',
                self.name, self.entity_id, len(self.spec.in_),
                len(in_list), message)
            return

        in_value: list[dict] = []
        for index, prop in enumerate(self.spec.in_):
            raw_val = in_list[index]
            parsed_val = None
            is_valid = False

            # 優化: 簡化型別判斷邏輯，去除冗餘的 append 與 continue，提升可讀性與執行效率
            if prop.format_ is str and isinstance(raw_val, (bool, int, float, str)):
                parsed_val = str(raw_val)
                is_valid = True
            elif prop.format_ is bool and isinstance(raw_val, (bool, int)):
                parsed_val = bool(raw_val)
                is_valid = True
            elif prop.format_ is float and isinstance(raw_val, (int, float)):
                parsed_val = float(raw_val)
                is_valid = True
            elif prop.format_ is int and isinstance(raw_val, int):
                parsed_val = int(raw_val)
                is_valid = True

            # Invalid params type, raise error.
            if not is_valid:
                _LOGGER.error(
                    'action exec failed, %s(%s), invalid params item, '
                    'which item(%s) in the list must be %s, %s type was %s, %s',
                    self.name, self.entity_id, prop.description_trans,
                    prop.format_.__name__, raw_val, type(raw_val).__name__, message)
                return
                
            in_value.append({'piid': prop.iid, 'value': parsed_val})

        await self.action_async(in_list=in_value)