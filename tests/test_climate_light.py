"""Unit tests for climate fan modes and light turn on commands."""
# pylint: disable=protected-access
from types import SimpleNamespace
from typing import Optional
from unittest.mock import MagicMock

import pytest

from homeassistant.components.climate import (
    FAN_OFF, ClimateEntityFeature, HVACMode)
from homeassistant.util.unit_system import METRIC_SYSTEM
from homeassistant.components.light import (
    ATTR_BRIGHTNESS, ATTR_EFFECT, ColorMode)

from custom_components.xiaomi_home.climate import (
    FeatureFanMode, PtcBathHeater)
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


def _built_light(brightness: MIoTSpecProperty) -> Light:
    props = [_prop("on", "light", "bool"), brightness]
    entity_data = _mock_service_entity_data("light", props)
    entity_data.get_prop = lambda name, service=None: next(
        (p for p in props if p.name == name), None)
    light = Light(miot_device=_mock_miot_device(), entity_data=entity_data)
    light.async_write_ha_state = MagicMock()
    light._prop_value_map = {props[0]: True, brightness: 2}
    return light


@pytest.mark.asyncio
async def test_value_list_brightness_is_an_effect_not_a_brightness() -> None:
    """It has no scale: claiming ColorMode.BRIGHTNESS made every state write
    raise TypeError while the light was on."""
    light = _built_light(_prop(
        "brightness", "light", "uint8", value_list=[
            {"name": "low", "value": 1, "description": "Low"},
            {"name": "high", "value": 2, "description": "High"}]))
    sent: list = []

    async def fake_set_property_async(prop, value, **_kwargs):
        sent.append((prop.name, value))
        return True
    light.set_property_async = fake_set_property_async

    assert light.supported_color_modes == {ColorMode.ONOFF}
    assert light.color_mode == ColorMode.ONOFF
    assert light.brightness is None
    assert light.effect == "Brightness: High"
    assert light.state_attributes["effect"] == "Brightness: High"

    await light.async_turn_on(**{ATTR_BRIGHTNESS: 128})
    assert not sent
    await light.async_turn_on(**{ATTR_EFFECT: "Brightness: Low"})
    assert sent == [("brightness", 1)]


def test_ranged_brightness_keeps_brightness_mode() -> None:
    light = _built_light(_prop(
        "brightness", "light", "uint8", value_range=[1, 100, 1]))
    assert light.supported_color_modes == {ColorMode.BRIGHTNESS}
    assert light.brightness == 5


def _bath_heater(*items) -> tuple[PtcBathHeater, MIoTSpecProperty]:
    mode = _prop("mode", "ptc-bath-heater", "uint8", value_list=[
        {"value": value, "description": name.title(), "name": name}
        for value, name in items])
    entity_data = _mock_service_entity_data("ptc-bath-heater", [mode])
    entity_data.get_prop = lambda name, service=None: (
        mode if name == "mode" else None)
    heater = PtcBathHeater(
        miot_device=_mock_miot_device(), entity_data=entity_data)
    heater.hass = MagicMock()
    heater.hass.config.units = METRIC_SYSTEM
    return heater, mode


def test_bath_heater_without_off_mode_can_be_added() -> None:
    """hvac_modes was never set without an off/idle item: AttributeError on
    the first state write, so the entity was not added."""
    heater, mode = _bath_heater((1, "heat"), (2, "ventilate"))
    assert heater.hvac_modes == [HVACMode.AUTO]
    heater._prop_value_map = {mode: 2}
    assert heater.hvac_mode == HVACMode.AUTO
    assert "hvac_modes" in heater.capability_attributes


def test_bath_heater_with_idle_mode_reports_off() -> None:
    heater, mode = _bath_heater((0, "idle"), (1, "heat"))
    assert heater.hvac_modes == [HVACMode.AUTO, HVACMode.OFF]
    heater._prop_value_map = {mode: 0}
    assert heater.hvac_mode == HVACMode.OFF
    heater._prop_value_map = {mode: 1}
    assert heater.hvac_mode == HVACMode.AUTO
