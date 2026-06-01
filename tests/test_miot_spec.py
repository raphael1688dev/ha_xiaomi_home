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
