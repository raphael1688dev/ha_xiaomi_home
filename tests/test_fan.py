"""Unit tests for fan speeds given as a value range."""
# pylint: disable=protected-access
import pytest
from homeassistant.exceptions import HomeAssistantError

from custom_components.xiaomi_home.fan import Fan

from .test_climate_light import _prop
from .test_ha_compliance import _mock_miot_device, _mock_service_entity_data


def _fan(value_range: list, level: int) -> tuple[Fan, list]:
    on = _prop("on", "fan", "bool")
    fan_level = _prop("fan-level", "fan", "uint8", value_range=value_range)
    props = [on, fan_level]
    entity_data = _mock_service_entity_data("fan", props)
    entity_data.get_prop = lambda name, service=None: next(
        (p for p in props if p.name == name), None)
    fan = Fan(miot_device=_mock_miot_device(), entity_data=entity_data)
    fan._prop_value_map = {on: True, fan_level: level}
    sent: list = []

    async def fake_set_property_async(prop, value, **_kwargs):
        sent.append(value)
        fan._prop_value_map[prop] = value
        return True

    fan.set_property_async = fake_set_property_async
    return fan, sent


@pytest.mark.asyncio
@pytest.mark.parametrize("percentage,level", [
    (1, 1), (33, 1), (34, 2), (66, 2), (67, 3), (100, 3)])
async def test_three_level_range_maps_like_ha_speed_steps(
        percentage: int, level: int) -> None:
    """int() used to send 0 for 33 %, below the range."""
    fan, sent = _fan([1, 3, 1], 2)
    await fan.async_set_percentage(percentage)
    assert sent == [level]


@pytest.mark.asyncio
async def test_percentage_round_trip_and_speed_steps() -> None:
    fan, sent = _fan([1, 3, 1], 2)
    assert (fan.speed_count, fan.percentage) == (3, 66)
    await fan.async_set_percentage(fan.percentage)
    await fan.async_decrease_speed()
    assert sent == [2, 1]
    assert fan.percentage == 33
    # Below the lowest level the fan turns off, as FanEntity does
    await fan.async_decrease_speed()
    assert sent == [2, 1, False]


@pytest.mark.asyncio
@pytest.mark.parametrize("value_range,percentage,level,reported", [
    ([0, 100, 10], 50, 50, 54),  # 11 levels, the step is kept
    ([0, 100, 10], 1, 0, 9),
    ([1, 5, 2], 100, 5, 100),    # levels 1, 3, 5
    ([1, 5, 2], 50, 3, 66),
    ([1, 100, 1], 47, 47, 47),
])
async def test_range_step_is_respected(
        value_range: list, percentage: int, level: int, reported: int
) -> None:
    fan, sent = _fan(value_range, value_range[0])
    await fan.async_set_percentage(percentage)
    assert sent == [level]
    # The reported percentage maps back to the same level
    assert fan.percentage == reported
    await fan.async_set_percentage(reported)
    assert sent == [level, level]


def test_reported_level_off_the_steps_does_not_crash() -> None:
    fan, _ = _fan([1, 5, 2], 9)  # above the range
    assert fan.percentage == 100


def _off_fan(refuse_level_while_off: bool = False) -> tuple[Fan, list]:
    """A 1-4 level fan that is off at level 2; sent records (name, value)."""
    on = _prop("on", "fan", "bool")
    fan_level = _prop("fan-level", "fan", "uint8", value_range=[1, 4, 1])
    props = [on, fan_level]
    entity_data = _mock_service_entity_data("fan", props)
    entity_data.get_prop = lambda name, service=None: next(
        (p for p in props if p.name == name), None)
    fan = Fan(miot_device=_mock_miot_device(), entity_data=entity_data)
    fan.miot_device.props_cache = {}
    fan._prop_value_map = {on: False, fan_level: 2}
    sent: list = []

    async def fake_set_property_async(prop, value, **_kwargs):
        if (refuse_level_while_off and prop.name == "fan-level"
                and not fan._prop_value_map.get(on)):
            sent.append((prop.name, "refused"))
            raise HomeAssistantError("refused while off")
        sent.append((prop.name, value))
        fan._prop_value_map[prop] = value
        return True

    fan.set_property_async = fake_set_property_async
    return fan, sent


@pytest.mark.asyncio
async def test_turn_on_with_percentage_writes_the_level_first() -> None:
    """raphael1688dev/ha_xiaomi_home#5: the fan ran at its previous speed
    because power-on was sent before the requested level."""
    fan, sent = _off_fan()
    await fan.async_turn_on(percentage=75)
    assert sent == [("fan-level", 3), ("on", True), ("fan-level", 3)]
    assert fan.is_on
    assert fan.percentage == 75


@pytest.mark.asyncio
async def test_set_percentage_while_off_writes_the_level_first() -> None:
    fan, sent = _off_fan()
    await fan.async_set_percentage(100)
    assert sent == [("fan-level", 4), ("on", True), ("fan-level", 4)]


@pytest.mark.asyncio
async def test_device_refusing_the_level_while_off_still_turns_on() -> None:
    """Such a device gets today's order: power on, then the level."""
    fan, sent = _off_fan(refuse_level_while_off=True)
    await fan.async_turn_on(percentage=75)
    assert sent == [("fan-level", "refused"), ("on", True), ("fan-level", 3)]
    assert fan.is_on
    assert fan.percentage == 75


@pytest.mark.asyncio
async def test_plain_turn_on_and_on_fan_are_unchanged() -> None:
    fan, sent = _off_fan()
    await fan.async_turn_on()
    assert sent == [("on", True)]
    await fan.async_set_percentage(25)  # already on: just the level
    assert sent == [("on", True), ("fan-level", 1)]
    await fan.async_turn_on(percentage=50)
    assert sent == [("on", True), ("fan-level", 1), ("fan-level", 2)]
