"""Unit tests for climate fan modes and light turn on commands."""
# pylint: disable=protected-access
from types import SimpleNamespace
from typing import Optional
from unittest.mock import MagicMock

import pytest

from homeassistant.components.climate import (
    FAN_OFF, ClimateEntityFeature)
from homeassistant.components.light import ATTR_BRIGHTNESS, ATTR_EFFECT

from custom_components.xiaomi_home.climate import FeatureFanMode
from custom_components.xiaomi_home.light import Light
from custom_components.xiaomi_home.miot.miot_spec import MIoTSpecProperty

from .test_ha_compliance import _mock_miot_device, _mock_service_entity_data


def _prop(
    name: str, service: str, format_: str, value_range: Optional[list] = None,
    value_list: Optional[list] = None, precision: Optional[int] = None
) -> MIoTSpecProperty:
    return MIoTSpecProperty(
        spec={"iid": 2, "name": name, "description": name,
              "type": f"urn:miot-spec-v2:property:{name}:00000016"},
        service=SimpleNamespace(iid=5, name=service),
        format_=format_, access=["read", "write", "notify"],
        value_range=value_range, value_list=value_list, precision=precision)


def _fan_entity(*props: MIoTSpecProperty) -> FeatureFanMode:
    entity_data = _mock_service_entity_data("fan-control", list(props))
    entity_data.get_prop = lambda name, service: next(
        (p for p in props if p.name == name and p.service.name == service),
        None)
    return FeatureFanMode(
        miot_device=_mock_miot_device(), entity_data=entity_data)


@pytest.mark.parametrize("service", ["fan-control", "thermostat"])
@pytest.mark.parametrize("value_range,format_,precision,modes", [
    ([1, 5, 1], "uint8", None, {1: "1", 2: "2", 3: "3", 4: "4", 5: "5"}),
    ([1, 6, 2], "uint8", None, {1: "1", 3: "3", 5: "5"}),
    ([2, 2, 1], "uint8", None, {2: "2"}),
    ([0.1, 0.3, 0.1], "float", 1, {0.1: "0.1", 0.2: "0.2", 0.3: "0.3"}),
])
def test_fan_level_range_becomes_fan_modes(
    service, value_range, format_, precision, modes
) -> None:
    """A fan-level value range lists every step as a fan mode."""
    entity = _fan_entity(
        _prop("fan-level", service, format_, value_range=value_range,
              precision=precision))
    assert entity._fan_mode_map == modes
    assert entity.fan_modes == list(modes.values())
    assert entity.supported_features & ClimateEntityFeature.FAN_MODE


@pytest.mark.asyncio
async def test_fan_level_range_reads_and_writes_values() -> None:
    prop = _prop("fan-level", "fan-control", "uint8", value_range=[1, 5, 1])
    entity = _fan_entity(prop)
    sent: list = []

    async def fake_set_property_async(prop, value, **kwargs):
        # pylint: disable=unused-argument
        sent.append(value)
        return True

    entity.set_property_async = fake_set_property_async
    entity._prop_value_map[prop] = 4
    assert entity.fan_mode == "4"
    await entity.async_set_fan_mode("2")
    assert sent == [2]
    with pytest.raises(RuntimeError):
        await entity.async_set_fan_mode("9")


@pytest.mark.parametrize("value_range", [[1, 5, 0], [5, 1, 1]])
def test_invalid_fan_level_range_is_skipped(value_range) -> None:
    entity = _fan_entity(
        _prop("fan-level", "fan-control", "uint8", value_range=value_range))
    assert entity._prop_fan_level is None
    assert not entity.supported_features & ClimateEntityFeature.FAN_MODE


def test_fan_level_value_list_wins_and_off_is_appended() -> None:
    """A value list keeps its labels, and adding off leaves the spec alone."""
    level = _prop(
        "fan-level", "fan-control", "uint8", value_range=[0, 2, 1],
        value_list=[{"name": "low", "value": 1, "description": "Low"},
                    {"name": "high", "value": 2, "description": "High"}])
    entity = _fan_entity(
        level, _prop("on", "fan-control", "bool"))
    assert entity.fan_modes == ["Low", "High", FAN_OFF]
    assert level.value_list.descriptions == ["Low", "High"]


def _light(is_on: Optional[bool]) -> tuple[Light, list]:
    light: Light = object.__new__(Light)
    light._prop_on = _prop("on", "light", "bool")
    light._prop_brightness = _prop(
        "brightness", "light", "uint8", value_range=[1, 100, 1])
    light._brightness_scale = (1, 100)
    light._prop_color_temp = None
    light._prop_color = None
    light._effect_map = {"Night": (light._prop_brightness, 1)}
    light._prop_value_map = {light._prop_on: is_on}
    light.async_write_ha_state = MagicMock()
    sent: list = []

    async def fake_set_property_async(prop, value, **kwargs):
        sent.append((prop.name, value, kwargs.get("write_ha_state", True)))
        return True

    light.set_property_async = fake_set_property_async
    return light, sent


@pytest.mark.asyncio
@pytest.mark.parametrize("is_on,kwargs,expected", [
    # Adjusting a light that is on does not send on again
    (True, {ATTR_BRIGHTNESS: 255}, [("brightness", 100, False)]),
    (True, {ATTR_EFFECT: "Night"}, [("brightness", 1, False)]),
    # A plain turn on is always sent, the cached state may be stale
    (True, {}, [("on", True, False)]),
    (None, {}, [("on", True, False)]),
    # A light that is off is turned on before it is adjusted
    (False, {ATTR_BRIGHTNESS: 255},
     [("on", True, False), ("brightness", 100, False)]),
])
async def test_light_turn_on_sends_on_only_when_needed(
    is_on, kwargs, expected
) -> None:
    light, sent = _light(is_on)
    await light.async_turn_on(**kwargs)
    assert sent == expected
    light.async_write_ha_state.assert_called_once()
