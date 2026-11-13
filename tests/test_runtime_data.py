"""Per-entry data lives in the config entry's runtime_data."""
import importlib
import inspect
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from homeassistant.config_entries import ConfigEntry

from custom_components.xiaomi_home.data import (
    XiaomiHomeConfigEntry, XiaomiHomeData)
from custom_components.xiaomi_home.miot.const import SUPPORTED_PLATFORMS


def test_alias_is_a_typed_config_entry() -> None:
    assert XiaomiHomeConfigEntry.__value__ == ConfigEntry[XiaomiHomeData]


@pytest.mark.asyncio
@pytest.mark.parametrize("platform", SUPPORTED_PLATFORMS)
async def test_platforms_read_devices_from_runtime_data(platform) -> None:
    """hass.data no longer holds the devices; an entry without devices adds
    no entities and does not touch hass.data."""
    module = importlib.import_module(
        f"custom_components.xiaomi_home.{platform}")
    assert "hass.data" not in inspect.getsource(module.async_setup_entry)
    hass = MagicMock()
    hass.data = {}
    entry = SimpleNamespace(
        entry_id="entry1",
        runtime_data=XiaomiHomeData(miot_client=MagicMock(), devices=[]))
    add_entities = MagicMock()

    await module.async_setup_entry(hass, entry, add_entities)

    assert not hass.data
