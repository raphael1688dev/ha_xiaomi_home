"""Unit tests for MIoT device utility functions and common utilities."""
import pytest
from unittest.mock import MagicMock
from custom_components.xiaomi_home.miot.common import (
    calc_group_id,
    slugify_name,
    slugify_did,
    MIoTMatcher,
)
from custom_components.xiaomi_home.miot.miot_device import MIoTDevice


def test_calc_group_id() -> None:
    """Test group id calculation based on user ID and home ID."""
    uid: str = "123456"
    home_id: str = "7890"
    group_id: str = calc_group_id(uid, home_id)
    assert len(group_id) == 16
    assert isinstance(group_id, str)
    assert group_id == calc_group_id(uid, home_id)  # Deterministic


def test_slugify_name() -> None:
    """Test slugification of a name."""
    assert slugify_name("My Device Name") == "my_device_name"
    assert slugify_name("Hello-World") == "hello_world"
    assert slugify_name("Test_Device") == "test_device"


def test_slugify_did() -> None:
    """Test slugification of a device id."""
    assert slugify_did("cn", "123456") == "cn_123456"
    assert slugify_did("us", "abc-def") == "us_abc_def"


def test_miot_matcher() -> None:
    """Test MIoT matcher pub/sub matching."""
    matcher: MIoTMatcher = MIoTMatcher()
    matcher["device1/p/1/1"] = "handler1"
    matcher["device1/p/1/2"] = "handler2"
    matcher["device2/p/+/1"] = "handler_wildcard"

    assert matcher.get("device1/p/1/1") == "handler1"
    assert matcher.get("device1/p/1/2") == "handler2"
    assert list(matcher.iter_match("device2/p/5/1")) == ["handler_wildcard"]
    assert matcher.get("nonexistent") is None

    # Test iter_all_nodes
    nodes: list[str] = list(matcher.iter_all_nodes())
    assert len(nodes) == 3


def test_unique_id_generation() -> None:
    """Test MIoTDevice unique ID generation functions using a dummy subclass."""
    class DummyDevice(MIoTDevice):
        def __init__(self) -> None:
            self.did_tag = "12345_lamp"
            self._model_strs = ["xiaomi", "lamp", "v1"]
            self._uid_prefix = "12345_lamp_lamp"

        @property
        def entity_id_prefix(self) -> str:
            return "lamp_12345"

    device: DummyDevice = DummyDevice()
    assert device.gen_device_unique_id() == "12345_lamp_lamp"
    
    assert device.gen_service_unique_id(1, "Device Info") == "12345_lamp_lamp_s_1_Device Info"
    assert device.gen_service_unique_id(1, "Device Info", slugify_description=True) == "12345_lamp_lamp_s_1_device_info"
    
    assert device.gen_prop_unique_id("Switch", 2, 1) == "12345_lamp_lamp_switch_p_2_1"
    assert device.gen_event_unique_id("Motion", 3, 1) == "12345_lamp_lamp_motion_e_3_1"
    assert device.gen_action_unique_id("Toggle", 4, 1) == "12345_lamp_lamp_toggle_a_4_1"


def test_device_tracker_extra_state_attributes() -> None:
    """Test DeviceTracker extra_state_attributes and dynamic _attr_* updates without property getter overrides."""
    from custom_components.xiaomi_home.device_tracker import DeviceTracker
    from custom_components.xiaomi_home.miot.miot_spec import MIoTSpecService

    assert "battery_level" not in DeviceTracker.__dict__
    assert "location_name" not in DeviceTracker.__dict__
    assert "latitude" not in DeviceTracker.__dict__
    assert "longitude" not in DeviceTracker.__dict__
    
    mock_miot_device = MagicMock()
    mock_miot_device.miot_client.get_device_control_path.return_value = "LAN"
    mock_miot_device.did = "123456"
    mock_miot_device.online = True
    
    mock_prop_battery = MagicMock()
    mock_prop_battery.name = "battery-level"
    mock_prop_lat = MagicMock()
    mock_prop_lat.name = "latitude"
    mock_prop_lon = MagicMock()
    mock_prop_lon.name = "longitude"
    mock_prop_area = MagicMock()
    mock_prop_area.name = "area-id"
    
    mock_spec = MagicMock(spec=MIoTSpecService)
    mock_spec.name = "device-tracker"
    mock_spec.description = "device_tracker"
    mock_spec.description_trans = "Device Tracker"
    mock_spec.proprietary = False
    mock_spec.entity_category = None
    mock_spec.iid = 1
    
    mock_entity_data = MagicMock()
    mock_entity_data.spec = mock_spec
    mock_entity_data.props = [mock_prop_battery, mock_prop_lat, mock_prop_lon, mock_prop_area]
    mock_entity_data.platform = "device_tracker"
    
    tracker = DeviceTracker(miot_device=mock_miot_device, entity_data=mock_entity_data)
    
    def mock_get_prop_value(prop: MagicMock) -> Any:
        if prop.name == "battery-level":
            return 85
        if prop.name == "latitude":
            return 31.2304
        if prop.name == "longitude":
            return 121.4737
        if prop.name == "area-id":
            return "Home"
        return None

    tracker.get_prop_value = mock_get_prop_value
    
    attrs = tracker.extra_state_attributes
    assert attrs.get("battery_level") == 85
    assert attrs.get("location_name") == "Home"
    assert attrs.get("control_path") == "LAN"
    
    assert tracker.latitude == 31.2304
    assert tracker.longitude == 121.4737
    assert tracker.location_name == "Home"

