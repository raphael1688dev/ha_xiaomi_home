"""Unit tests for the target humidity of humidifier entities."""
# pylint: disable=protected-access
from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.xiaomi_home.humidifier import Humidifier

from .test_climate_light import _prop
from .test_ha_compliance import _mock_miot_device, _mock_service_entity_data


def _humidifier(target_prop) -> Humidifier:
    miot_device = _mock_miot_device()
    miot_device.props_cache = {}
    miot_device.miot_client.set_prop_async = AsyncMock(return_value=True)
    entity = Humidifier(
        miot_device=miot_device,
        entity_data=_mock_service_entity_data("dehumidifier", [target_prop]))
    entity.async_write_ha_state = MagicMock()
    return entity


def _written(entity: Humidifier) -> int:
    client = entity.miot_device.miot_client
    return client.set_prop_async.call_args.kwargs["value"]


@pytest.mark.asyncio
async def test_enumerated_target_humidity_is_bound_and_snapped() -> None:
    """XiaoMi/ha_xiaomi_home#1856: nwt.derh.330ef lists 30 to 70 in tens."""
    entity = _humidifier(_prop(
        "target-humidity", "dehumidifier", "uint8", value_list=[
            {"name": f"target_humidity_{value}", "value": value,
             "description": f"Target Humidity {value}"}
            for value in (50, 30, 70, 40, 60)]))

    assert entity._prop_target_humidity is not None
    assert (entity.min_humidity, entity.max_humidity) == (30, 70)
    assert entity.target_humidity_step == 10

    for requested, expected in ((44, 40), (46, 50), (45, 40), (70, 70)):
        await entity.async_set_humidity(requested)
        assert _written(entity) == expected
        assert entity.target_humidity == expected


@pytest.mark.asyncio
async def test_ranged_target_humidity_is_written_as_requested() -> None:
    entity = _humidifier(_prop(
        "target-humidity", "dehumidifier", "uint8", value_range=[40, 80, 1]))

    assert (entity.min_humidity, entity.max_humidity) == (40, 80)
    assert entity._target_humidity_values is None
    await entity.async_set_humidity(57)
    assert _written(entity) == 57


def test_target_humidity_without_range_or_list_is_not_bound() -> None:
    entity = _humidifier(_prop("target-humidity", "dehumidifier", "uint8"))

    assert entity._prop_target_humidity is None
    assert entity.target_humidity is None


def test_unevenly_spaced_targets_get_no_step() -> None:
    entity = _humidifier(_prop(
        "target-humidity", "dehumidifier", "uint8", value_list=[
            {"name": f"h{value}", "value": value, "description": str(value)}
            for value in (30, 40, 60)]))

    assert (entity.min_humidity, entity.max_humidity) == (30, 60)
    assert entity.target_humidity_step is None
