# -*- coding: utf-8 -*-
"""
Notify entities for Xiaomi Home.
"""
import logging
from typing import Optional

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.components.notify import NotifyEntity
from homeassistant.util import yaml
from homeassistant.exceptions import (
    HomeAssistantError, ServiceValidationError)

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

    # Optimization: flatten nested loop with list comprehension for
    # initialization performance
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
        # Bad input used to be logged and dropped, so the call looked
        # successful; report it to the caller instead
        except HomeAssistantError as err:
            raise ServiceValidationError(
                f'action exec failed, {self.name}({self.entity_id}), '
                f'parse message error, {err}') from err

        if not isinstance(in_list, list):
            raise ServiceValidationError(
                f'action exec failed, {self.name}({self.entity_id}), '
                f'params must be a list, {message}')

        if len(in_list) != len(self.spec.in_):
            raise ServiceValidationError(
                f'action exec failed, {self.name}({self.entity_id}), '
                f'missing params, requires {len(self.spec.in_)} params, '
                f'but {len(in_list)} provided, {message}')

        in_value: list[dict] = []
        for index, prop in enumerate(self.spec.in_):
            raw_val = in_list[index]
            parsed_val = None
            is_valid = False

            # Optimization: simplify type checking logic to improve readability
            # and performance
            if prop.format_ is str and isinstance(raw_val,
                                                  (bool, int, float, str)):
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
                raise ServiceValidationError(
                    f'action exec failed, {self.name}({self.entity_id}), '
                    f'invalid params item, which item '
                    f'({prop.description_trans}) in the list must be '
                    f'{prop.format_.__name__}, {raw_val} type was '
                    f'{type(raw_val).__name__}, {message}')

            in_value.append({'piid': prop.iid, 'value': parsed_val})

        await self.action_async(in_list=in_value)
