# -*- coding: utf-8 -*-
"""
Text entities for Xiaomi Home.
"""
from __future__ import annotations
import logging
from typing import Any, Optional

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.components.text import TextEntity
from homeassistant.util import yaml
from homeassistant.exceptions import HomeAssistantError

from .miot.const import DOMAIN
from .miot.miot_spec import MIoTSpecAction, MIoTSpecProperty
from .miot.miot_device import MIoTActionEntity, MIoTDevice, MIoTPropertyEntity

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
        Text(miot_device=miot_device, spec=prop)
        for miot_device in device_list
        for prop in miot_device.prop_list.get('text', [])
    ]

    # 附加 Debug 模式下的 ActionText 實體
    new_entities.extend([
        ActionText(miot_device=miot_device, spec=action)
        for miot_device in device_list
        if miot_device.miot_client.action_debug
        for action in miot_device.action_list.get('notify', [])
    ])

    if new_entities:
        async_add_entities(new_entities)


class Text(MIoTPropertyEntity, TextEntity):
    """Text entities for Xiaomi Home."""

    def __init__(self, miot_device: MIoTDevice, spec: MIoTSpecProperty) -> None:
        """Initialize the Text."""
        super().__init__(miot_device=miot_device, spec=spec)

    @property
    def native_value(self) -> Optional[str]:
        """Return the current text value."""
        # 優化: 確保啟動時若尚未取得資料回傳 None，且將其他型別強制轉為字串並截斷
        if self._value is None:
            return None
        return str(self._value)[:255]

    async def async_set_value(self, value: str) -> None:
        """Set the text value."""
        await self.set_property_async(value=value)


class ActionText(MIoTActionEntity, TextEntity):
    """Text entities for Xiaomi Home."""

    def __init__(self, miot_device: MIoTDevice, spec: MIoTSpecAction) -> None:
        super().__init__(miot_device=miot_device, spec=spec)
        self._attr_extra_state_attributes = {}
        self._attr_native_value = ''
        action_in: str = ', '.join([
            f'{prop.description_trans}({prop.format_.__name__})'
            for prop in self.spec.in_])
        self._attr_extra_state_attributes['action params'] = f'[{action_in}]'

    async def async_set_value(self, value: str) -> None:
        if not value:
            return
        in_list: Any = None
        try:
            in_list = yaml.parse_yaml(content=value)
        except HomeAssistantError as e:
            _LOGGER.error(
                'action exec failed, %s(%s), invalid action params format, %s',
                self.name, self.entity_id, value)
            raise ValueError(
                f'action exec failed, {self.name}({self.entity_id}), '
                f'invalid action params format, {value}') from e
                
        if len(self.spec.in_) == 1 and not isinstance(in_list, list):
            in_list = [in_list]
            
        if not isinstance(in_list, list) or len(in_list) != len(self.spec.in_):
            _LOGGER.error(
                'action exec failed, %s(%s), invalid action params, %s',
                self.name, self.entity_id, value)
            raise ValueError(
                f'action exec failed, {self.name}({self.entity_id}), '
                f'invalid action params, {value}')
                
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
                    prop.format_.__name__, raw_val, type(raw_val).__name__, value)
                raise ValueError(
                    f'action exec failed, {self.name}({self.entity_id}), '
                    f'invalid params item, which item({prop.description_trans}) '
                    f'in the list must be {prop.format_.__name__}, {raw_val} type '
                    f'was {type(raw_val).__name__}, {value}')
                    
            in_value.append({'piid': prop.iid, 'value': parsed_val})

        self._attr_native_value = value
        if await self.action_async(in_list=in_value):
            self.async_write_ha_state()