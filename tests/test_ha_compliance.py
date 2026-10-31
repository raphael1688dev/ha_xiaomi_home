"""Unit tests for Home Assistant 2026.10 compliance fixes."""
# pylint: disable=protected-access
import importlib
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from homeassistant.components.climate import ClimateEntity
from homeassistant.components.event import (
    DoorbellEventType, EventDeviceClass)
from homeassistant.components.humidifier.const import (
    MODE_AUTO, MODE_NORMAL, MODE_SLEEP)
from homeassistant.components.water_heater import WaterHeaterEntity
from homeassistant.helpers.entity import Entity

from custom_components.xiaomi_home import climate, water_heater
from custom_components.xiaomi_home.button import Button
from custom_components.xiaomi_home.event import Event
from custom_components.xiaomi_home.humidifier import Humidifier
from custom_components.xiaomi_home.light import Light
from custom_components.xiaomi_home.miot.miot_cloud import MIoTOauthClient
from custom_components.xiaomi_home.miot.miot_device import (
    MIoTActionEntity, MIoTEventEntity, MIoTPropertyEntity, MIoTServiceEntity)
from custom_components.xiaomi_home.miot.miot_error import MIoTOauthError
from custom_components.xiaomi_home.miot.miot_spec import (
    MIoTSpecInstance, MIoTSpecService, MIoTSpecValueListItem)
from custom_components.xiaomi_home.sensor import Sensor
from custom_components.xiaomi_home.text import Text


def _mock_miot_device() -> MagicMock:
    miot_device = MagicMock()
    miot_device.entity_id_prefix = "xiaomi_test"
    miot_device.is_lan_capable = False
    miot_device.online = True
    return miot_device


def _mock_service_entity_data(platform: str, props: list) -> MagicMock:
    spec = MagicMock(spec=MIoTSpecService)
    spec.name = platform
    spec.description = platform
    spec.description_trans = platform
    spec.proprietary = False
    spec.entity_category = None
    spec.iid = 2
    entity_data = MagicMock()
    entity_data.spec = spec
    entity_data.props = props
    entity_data.platform = platform
    entity_data.device_class = None
    return entity_data


def _mode_prop(items: list[tuple[str, int, str]]) -> SimpleNamespace:
    """Build a mode property; names go through the real spec slugify."""
    return SimpleNamespace(
        name="mode",
        value_list=SimpleNamespace(items=[
            MIoTSpecValueListItem.from_spec(
                {"name": name, "value": value, "description": desc})
            for name, value, desc in items
        ]))


def test_humidifier_modes_match_slugified_chinese_names() -> None:
    """Chinese value-list names are slugified to pinyin, the map must match."""
    prop = _mode_prop([
        ("\u6807\u51c6", 0, "Standard"),
        ("\u7761\u7720", 1, "Sleep"),
        ("\u81ea\u52a8", 2, "Auto"),
    ])
    entity = Humidifier(
        miot_device=_mock_miot_device(),
        entity_data=_mock_service_entity_data("dehumidifier", [prop]))

    assert entity._mode_map == {0: MODE_NORMAL, 1: MODE_SLEEP, 2: MODE_AUTO}
    # Dehumidifiers use platform "dehumidifier" but live in the humidifier
    # domain
    assert entity.entity_id.startswith("humidifier.")


@pytest.mark.asyncio
async def test_humidifier_mode_collision_and_legacy_names() -> None:
    """Values must stay selectable, also by their legacy description."""
    prop = _mode_prop([
        ("none", 0, "None"),
        ("constant_speed", 1, "Constant Speed"),
    ])
    entity = Humidifier(
        miot_device=_mock_miot_device(),
        entity_data=_mock_service_entity_data("humidifier", [prop]))

    # The second item would also map to MODE_NORMAL; it keeps its description
    assert entity._mode_map == {0: MODE_NORMAL, 1: "Constant Speed"}
    assert entity.available_modes == [MODE_NORMAL, "Constant Speed"]

    sent: list = []

    async def fake_set_property_async(prop, value, **kwargs):
        # pylint: disable=unused-argument
        sent.append(value)

    entity.set_property_async = fake_set_property_async
    await entity.async_set_mode(MODE_NORMAL)
    await entity.async_set_mode("Constant Speed")
    # Pre-0.5.0 automations used the description of the first item
    await entity.async_set_mode("None")
    assert sent == [0, 1, 0]


def test_binary_property_shown_as_sensor_uses_sensor_domain() -> None:
    """A binary_sensor property added to the sensor platform needs sensor.*."""
    instance = MIoTSpecInstance.load({
        "urn":
            "urn:miot-spec-v2:device:sensor:0000A000:test-s1:1",
        "name":
            "sensor",
        "description":
            "Sensor",
        "description_trans":
            "Sensor",
        "services": [{
            "iid": 2,
            "type": "urn:miot-spec-v2:service:contact:00007800:test-s1:1",
            "description": "Contact",
            "description_trans": "Contact",
            "properties": [{
                "iid":
                    1,
                "type":
                    "urn:miot-spec-v2:property:contact-state:0000007C:test-s1:1",
                "description":
                    "Contact State",
                "description_trans":
                    "Contact State",
                "format":
                    "bool",
                "access": ["read", "notify"],
                "unit":
                    None,
                "value_range":
                    None,
                "value_list": [
                    {
                        "value": False,
                        "description": "Open"
                    },
                    {
                        "value": True,
                        "description": "Closed"
                    },
                ],
            }],
            "events": [],
            "actions": [],
        }],
    })
    prop = instance.services[0].properties[0]
    prop.platform = "binary_sensor"

    entity = Sensor(miot_device=_mock_miot_device(), spec=prop)
    assert entity.entity_id == "sensor.xiaomi_test_contact_contact_state"


def test_temperature_api_matches_running_core() -> None:
    """Old cores get the legacy names, 2026.11+ the native_* names."""
    native = hasattr(ClimateEntity, "native_current_temperature")
    assert climate._NATIVE_TEMP_API is native
    assert water_heater._NATIVE_TEMP_API is hasattr(
        WaterHeaterEntity, "native_current_temperature")

    name = "native_current_temperature" if native else "current_temperature"
    assert name in climate.FeatureTemperature.__dict__
    assert name in water_heater.WaterHeater.__dict__


def test_doorbell_event_offers_and_fires_ring() -> None:
    """Doorbell event entities must use the standard ring event type."""
    instance = MIoTSpecInstance.load({
        "urn":
            "urn:miot-spec-v2:device:doorbell:0000A0A0:test-d1:1",
        "name":
            "doorbell",
        "description":
            "Doorbell",
        "description_trans":
            "Doorbell",
        "services": [{
            "iid": 2,
            "type": "urn:miot-spec-v2:service:doorbell:00007810:test-d1:1",
            "description": "Doorbell",
            "description_trans": "Doorbell",
            "properties": [],
            "events": [{
                "iid":
                    1,
                "type":
                    "urn:miot-spec-v2:event:doorbell-ring:00005032:test-d1:1",
                "description":
                    "Doorbell Ring",
                "description_trans":
                    "Doorbell Ring",
                "argument": [],
            }],
            "actions": [],
        }],
    })
    spec = instance.services[0].events[0]
    spec.platform = "event"
    spec.device_class = EventDeviceClass.DOORBELL

    entity = Event(miot_device=_mock_miot_device(), spec=spec)
    assert entity.event_types == [DoorbellEventType.RING]

    fired: list = []
    entity._trigger_event = (
        lambda event_type, event_attributes: fired.append(event_type))
    entity.on_event_occurred("Doorbell Ring", None)
    assert fired == [DoorbellEventType.RING]


@pytest.mark.asyncio
@pytest.mark.parametrize("body", [
    "not json access_token=SECRET",
    '{"code": 1, "access_token": "SECRET"}',
    '{"code": 0, "result": {"access_token": "SECRET"}}',
])
async def test_oauth_token_errors_hide_response(body: str) -> None:
    """Token responses carry credentials and must not reach error text."""
    async def text() -> str:
        return body

    async def get(**kwargs):  # pylint: disable=unused-argument
        return SimpleNamespace(status=200, text=text)

    client = MIoTOauthClient.__new__(MIoTOauthClient)
    client._session = SimpleNamespace(get=get)
    client._oauth_host = "example.invalid"

    with pytest.raises(MIoTOauthError) as err:
        await client._MIoTOauthClient__get_token_async(data={})
    assert "SECRET" not in str(err.value)


@pytest.mark.parametrize("entity_cls", [Sensor, Text])
def test_long_string_value_kept_in_unrecorded_attribute(entity_cls) -> None:
    """The state is cut at 255 characters, the attribute keeps it all."""
    entity = entity_cls.__new__(entity_cls)
    long_value = "{" + "x" * 400 + "}"
    entity._value = long_value
    assert entity.extra_state_attributes == {"value": long_value}
    entity._value = "short"
    assert entity.extra_state_attributes is None
    # Large and frequently changing, keep it out of the recorder database
    assert "value" in entity_cls._Entity__combined_unrecorded_attributes


_ENTITY_PLATFORMS = (
    "binary_sensor", "button", "climate", "cover", "device_tracker", "event",
    "fan", "humidifier", "light", "media_player", "notify", "number",
    "select", "sensor", "switch", "text", "vacuum", "water_heater")
_ADD_REMOVE_METHODS = (
    "async_prepare_to_add_to_hass", "async_added_to_hass",
    "async_will_remove_from_hass")


def _integration_entity_classes() -> list[type]:
    for platform in _ENTITY_PLATFORMS:
        importlib.import_module(f"custom_components.xiaomi_home.{platform}")
    found, todo = set(), list(Entity.__subclasses__())
    while todo:
        cls = todo.pop()
        if cls in found:
            continue
        found.add(cls)
        todo.extend(cls.__subclasses__())
    return [cls for cls in found
            if cls.__module__.startswith("custom_components.xiaomi_home")]


def test_entity_classes_opt_in_to_in_place_entity_id_change() -> None:
    """Every entity must take the HA 2026.11 in-place entity_id change.

    Mirrors core's _entity_class_requires_readd: a class of ours that
    defines an add or remove hook is only covered when it, or a subclass of
    it, also defines async_entity_id_changed. Otherwise core removes and
    re-adds the entity on rename (deprecated, removed in 2027.11).
    """
    classes = _integration_entity_classes()
    assert len(classes) > 30
    for entity_cls in classes:
        mro = [cls for cls in entity_cls.__mro__
               if not cls.__module__.startswith("homeassistant.")]
        owners = [cls for cls in mro
                  if "async_entity_id_changed" in cls.__dict__]
        for cls in mro:
            if any(method in cls.__dict__ for method in _ADD_REMOVE_METHODS):
                assert any(issubclass(owner, cls) for owner in owners), (
                    f"{entity_cls.__name__}: {cls.__name__} defines an add "
                    "or remove hook without async_entity_id_changed")


@pytest.mark.parametrize("entity_cls, base_cls", [
    (Light, MIoTServiceEntity), (Sensor, MIoTPropertyEntity),
    (Event, MIoTEventEntity), (Button, MIoTActionEntity)])
def test_entity_id_changed_calls_base_class(entity_cls, base_cls) -> None:
    """The opt-in passes the call on, core moves its own bookkeeping there."""
    assert "async_entity_id_changed" in base_cls.__dict__
    entity = entity_cls.__new__(entity_cls)
    with patch.object(
            Entity, "async_entity_id_changed", create=True) as base_hook:
        entity.async_entity_id_changed("sensor.old_id")
    base_hook.assert_called_once_with("sensor.old_id")
