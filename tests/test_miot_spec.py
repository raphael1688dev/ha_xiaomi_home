"""Test for MIoT Spec parser."""
import pytest
from custom_components.xiaomi_home.miot.miot_spec import MIoTSpecInstance, MIoTSpecService, MIoTSpecProperty

def test_miot_spec_instance_loading():
    """Test loading a basic MIoT Spec instance."""
    raw_spec = {
        "urn": "urn:miot-spec-v2:device:humidifier:0000A00E:zhimi-ca4:1",
        "name": "humidifier",
        "description": "Humidifier",
        "description_trans": "Humidifier",
        "services": [
            {
                "iid": 1,
                "type": "urn:miot-spec-v2:service:device-information:00007801:zhimi-ca4:1",
                "description": "Device Information",
                "description_trans": "Device Information",
                "properties": [],
                "events": [],
                "actions": []
            }
        ]
    }
    
    instance = MIoTSpecInstance.load(raw_spec)
    assert instance.name == "humidifier"
    assert len(instance.services) == 1
    assert instance.services[0].iid == 1


def test_safe_eval():
    """Test AST safe evaluator on various MIoT Spec expressions."""
    from custom_components.xiaomi_home.miot.miot_spec import safe_eval
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

