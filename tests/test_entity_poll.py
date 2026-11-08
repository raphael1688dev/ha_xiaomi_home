"""Unit tests for the poll Home Assistant runs right after a command."""
# pylint: disable=protected-access
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.xiaomi_home.climate import FeatureFanMode
from custom_components.xiaomi_home.miot.miot_error import MIoTClientError
from custom_components.xiaomi_home.switch import Switch

from .test_climate_light import _prop
from .test_ha_compliance import _mock_miot_device, _mock_service_entity_data


def _lan_device() -> tuple[MagicMock, list]:
    """A polled (LAN capable) device whose loop clock the test controls."""
    now = [100.0]
    miot_device = _mock_miot_device()
    miot_device.is_lan_capable = True
    miot_device.props_cache = {}
    miot_device.miot_client.main_loop = SimpleNamespace(
        time=lambda: now[0], call_later=MagicMock())
    miot_device.miot_client.set_prop_async = AsyncMock(return_value=True)
    return miot_device, now


def _switch(miot_device: MagicMock) -> Switch:
    spec = _prop("on", "switch", "bool")
    spec.service.description_trans = "Switch"
    spec.platform = "switch"
    entity = Switch(miot_device=miot_device, spec=spec)
    entity.async_write_ha_state = MagicMock()
    return entity


def _refreshes(miot_device: MagicMock) -> int:
    return miot_device.miot_client.request_refresh_prop.call_count


@pytest.mark.asyncio
async def test_service_entity_skips_the_poll_right_after_a_command() -> None:
    """raphael1688dev/ha_xiaomi_home#4: the post-command poll read stale data.

    A read right after a LAN command can return the old value (the cloud
    learns about the command later), and the pending state write a second
    later showed it, so the fan speed flipped back for a moment.
    """
    miot_device, now = _lan_device()
    prop = _prop("fan-level", "fan-control", "uint8", [1, 4, 1])
    entity_data = _mock_service_entity_data("fan-control", [prop])
    entity_data.get_prop = lambda name, service=None: None
    entity = FeatureFanMode(miot_device=miot_device, entity_data=entity_data)
    assert entity.should_poll

    await entity.async_update()
    assert _refreshes(miot_device) == 1

    await entity.set_property_async(
        prop=prop, value=3, write_ha_state=False)
    await entity.async_update()  # Home Assistant's poll after the service
    assert _refreshes(miot_device) == 1
    assert entity.get_prop_value(prop=prop) == 3

    now[0] += 30  # the next regular poll still refreshes
    await entity.async_update()
    assert _refreshes(miot_device) == 2


@pytest.mark.asyncio
async def test_property_entity_skips_the_poll_right_after_a_command() -> None:
    miot_device, now = _lan_device()
    entity = _switch(miot_device)
    assert entity.should_poll

    await entity.async_turn_on()
    await entity.async_update()  # Home Assistant's poll after the service
    assert _refreshes(miot_device) == 0
    assert entity.is_on

    now[0] += 30
    await entity.async_update()
    assert _refreshes(miot_device) == 1


@pytest.mark.asyncio
async def test_failed_command_does_not_skip_the_poll() -> None:
    """Without a successful write there is nothing to protect."""
    miot_device, _ = _lan_device()
    miot_device.miot_client.set_prop_async = AsyncMock(
        side_effect=MIoTClientError("offline"))
    entity = _switch(miot_device)

    with pytest.raises(RuntimeError):
        await entity.async_turn_on()
    await entity.async_update()
    assert _refreshes(miot_device) == 1
