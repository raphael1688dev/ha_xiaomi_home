"""Unit tests for Home Assistant 2026.10 compliance fixes."""
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from homeassistant.components.climate import ClimateEntity
from homeassistant.components.humidifier.const import (
    MODE_AUTO, MODE_NORMAL, MODE_SLEEP)
from homeassistant.components.water_heater import WaterHeaterEntity

from custom_components.xiaomi_home.miot.miot_spec import (
    MIoTSpecInstance, MIoTSpecService, MIoTSpecValueListItem)


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
    from custom_components.xiaomi_home.humidifier import Humidifier

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
    from custom_components.xiaomi_home.humidifier import Humidifier

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
        sent.append(value)

    entity.set_property_async = fake_set_property_async
    await entity.async_set_mode(MODE_NORMAL)
    await entity.async_set_mode("Constant Speed")
    # Pre-0.5.0 automations used the description of the first item
    await entity.async_set_mode("None")
    assert sent == [0, 1, 0]


def test_binary_property_shown_as_sensor_uses_sensor_domain() -> None:
    """A binary_sensor property added to the sensor platform needs sensor.*."""
    from custom_components.xiaomi_home.sensor import Sensor

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
    from custom_components.xiaomi_home import climate, water_heater

    native = hasattr(ClimateEntity, "native_current_temperature")
    assert climate._NATIVE_TEMP_API is native
    assert water_heater._NATIVE_TEMP_API is hasattr(
        WaterHeaterEntity, "native_current_temperature")

    name = "native_current_temperature" if native else "current_temperature"
    assert name in climate.FeatureTemperature.__dict__
    assert name in water_heater.WaterHeater.__dict__


def test_doorbell_event_offers_and_fires_ring() -> None:
    """Doorbell event entities must use the standard ring event type."""
    from homeassistant.components.event import (
        DoorbellEventType, EventDeviceClass)
    from custom_components.xiaomi_home.event import Event

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
    from custom_components.xiaomi_home.miot.miot_cloud import MIoTOauthClient
    from custom_components.xiaomi_home.miot.miot_error import MIoTOauthError

    async def text() -> str:
        return body

    async def get(**kwargs):
        return SimpleNamespace(status=200, text=text)

    client = MIoTOauthClient.__new__(MIoTOauthClient)
    client._session = SimpleNamespace(get=get)
    client._oauth_host = "example.invalid"

    with pytest.raises(MIoTOauthError) as err:
        await client._MIoTOauthClient__get_token_async(data={})
    assert "SECRET" not in str(err.value)
