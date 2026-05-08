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

    new_entities = []
    for miot_device in device_list:
        for action in miot_device.action_list.get('notify', []):
            new_entities.append(Notify(miot_device=miot_device, spec=action))

    if new_entities:
        async_add_entities(new_entities)


class Notify(MIoTActionEntity, NotifyEntity):
    """Notify entities for Xiaomi Home."""
    # pylint: disable=unused-argument

    def __init__(self, miot_device: MIoTDevice, spec: MIoTSpecAction) -> None:
        """Initialize the Notify."""
        super().__init__(miot_device=miot_device, spec=spec)
        self._attr_extra_state_attributes = {}
        action_in: str = ', '.join([
            f'{prop.description_trans}({prop.format_.__name__})'
            for prop in self.spec.in_])
        self._attr_extra_state_attributes['action params'] = f'[{action_in}]'

    async def async_send_message(
        self, message: str, title: Optional[str] = None
    ) -> None:
        """Send a message."""
        if not message:
            _LOGGER.error(
                'action exec failed, %s(%s), empty action params',
                self.name, self.entity_id)
            return
        in_list: Any = None
        try:
            # YAML will convert yes, no, on, off, true, false to the bool type,
            # and if it is a string, quotation marks need to be added.
            in_list = yaml.parse_yaml(content=message)
        except HomeAssistantError:
            _LOGGER.error(
                'action exec failed, %s(%s), invalid action params format, %s',
                self.name, self.entity_id, message)
            return
        if len(self.spec.in_) == 1 and not isinstance(in_list, list):
            in_list = [in_list]
        if not isinstance(in_list, list) or len(in_list) != len(self.spec.in_):
            _LOGGER.error(
                'action exec failed, %s(%s), invalid action params, %s',
                self.name, self.entity_id, message)
            return
        in_value: list[dict] = []
        for index, prop in enumerate(self.spec.in_):
            if prop.format_ == str:
                if isinstance(in_list[index], (bool, int, float, str)):
                    in_value.append(
                        {'piid': prop.iid, 'value': str(in_list[index])})
                    continue
            elif prop.format_ == bool:
                if isinstance(in_list[index], (bool, int)):
                    # yes, no, on, off, true, false and other bool types
                    # will also be parsed as 0 and 1 of int.
                    in_value.append(
                        {'piid': prop.iid, 'value': bool(in_list[index])})
                    continue
            elif prop.format_ == float:
                if isinstance(in_list[index], (int, float)):
                    in_value.append(
                        {'piid': prop.iid, 'value': in_list[index]})
                    continue
            elif prop.format_ == int:
                if isinstance(in_list[index], int):
                    in_value.append(
                        {'piid': prop.iid, 'value': in_list[index]})
                    continue
            # Invalid params type, raise error.
            _LOGGER.error(
                'action exec failed, %s(%s), invalid params item, '
                'which item(%s) in the list must be %s, %s type was %s, %s',
                self.name, self.entity_id, prop.description_trans,
                prop.format_, in_list[index], type(
                    in_list[index]).__name__, message)
            return
        await self.action_async(in_list=in_value)
