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
