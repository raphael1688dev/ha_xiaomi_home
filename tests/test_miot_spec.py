"""Test for MIoT Spec parser."""
import pytest
from custom_components.xiaomi_home.miot.miot_spec import (
    MIoTSpecInstance, _SpecModify, safe_eval)


def test_miot_spec_instance_loading():
    """Test loading a basic MIoT Spec instance."""
    raw_spec = {
        "urn":
            "urn:miot-spec-v2:device:humidifier:0000A00E:zhimi-ca4:1",
        "name":
            "humidifier",
        "description":
            "Humidifier",
        "description_trans":
            "Humidifier",
        "services": [{
            "iid":
                1,
            "type":
                "urn:miot-spec-v2:service:device-information:00007801:zhimi-ca4:1",
            "description":
                "Device Information",
            "description_trans":
                "Device Information",
            "properties": [],
            "events": [],
            "actions": []
        }]
    }

    instance = MIoTSpecInstance.load(raw_spec)
    assert instance.name == "humidifier"
    assert len(instance.services) == 1
    assert instance.services[0].iid == 1


def test_safe_eval():
    """Test AST safe evaluator on various MIoT Spec expressions."""
    assert safe_eval("(src_value*6)", 5) == 30
    assert safe_eval("(src_value!=1)", 1) is False
    assert safe_eval("(src_value!=1)", 2) is True
    assert safe_eval("round(src_value/100, 2)", 123.456) == 1.23
    assert safe_eval("round(src_value*0.83)", 10) == 8
    assert safe_eval("(100-src_value)", 15) == 85
    assert safe_eval("src_value", "hello") == "hello"

    # Verify RCE and malicious nodes are blocked
    with pytest.raises(ValueError):
        safe_eval("__import__('os').system('ls')", 5)
    with pytest.raises(ValueError):
        safe_eval("open('/tmp/foo')", 5)


def test_value_precision():
    """Test MIoTSpecProperty value_precision with a non-zero min offset."""
    raw_spec = {
        "urn":
            "urn:miot-spec-v2:device:heater:0000A01A:test-h1:1",
        "name":
            "heater",
        "description":
            "Heater",
        "description_trans":
            "Heater",
        "services": [{
            "iid": 1,
            "type": "urn:miot-spec-v2:service:heater:0000782E:test-h1:1",
            "description": "Heater Service",
            "description_trans": "Heater Service",
            "properties": [{
                "iid":
                    1,
                "type":
                    "urn:miot-spec-v2:property:target-temperature:00000021:test-h1:1",
                "description":
                    "Target Temperature",
                "description_trans":
                    "Target Temperature",
                "format":
                    "int8",
                "access": ["read", "write"],
                "unit":
                    "celsius",
                "value_range": [15, 35, 2],
                "value_list":
                    None
            }],
            "events": [],
            "actions": []
        }]
    }
    instance = MIoTSpecInstance.load(raw_spec)
    prop = instance.services[0].properties[0]
    # For min=15, step=2: valid steps are 15, 17, 19, 21, 23...
    # 22.2 should round to 23 (offset (22.2-15)/2 = 3.6 -> 4 * 2 + 15 = 23)
    assert prop.value_precision(22.2) == 23
    assert prop.value_precision(15) == 15
    assert prop.value_precision(16.1) == 17
    assert prop.value_precision(None) is None


@pytest.mark.asyncio
@pytest.mark.parametrize("siid, piid, raw, expected", [
    (3, 1, 12345, 123.45),  # power consumption, kWh
    (3, 2, 523, 5.23),  # electric current, A
    (3, 3, 2201, 220.1),  # voltage, V
])
async def test_chint_valve_power_values_are_scaled(
        siid: int, piid: int, raw: int, expected: float) -> None:
    """chint1.valve.lcd reports these values without their decimal point."""
    modify = _SpecModify()
    await modify.init_async()
    await modify.set_spec_async(
        urn="urn:miot-spec-v2:device:electronic-valve:0000A0A7:chint1-lcd:1")

    assert modify.get_prop_format(siid=siid, piid=piid) == "float"
    assert safe_eval(
        modify.get_prop_expr(siid=siid, piid=piid), raw) == expected
    # Sensors check the range after the expression; the largest raw value
    # of the original integer format must stay in range
    low, high, _ = modify.get_prop_value_range(siid=siid, piid=piid)
    max_raw = 999999999 if piid == 1 else 65535
    assert low <= safe_eval(
        modify.get_prop_expr(siid=siid, piid=piid), max_raw) <= high
