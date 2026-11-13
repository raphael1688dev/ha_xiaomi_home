"""Entity names and icons that come from translations/en.json and icons.json."""
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from custom_components.xiaomi_home.sensor import (
    MIoTControlPathSensor, MIoTIPAddressSensor)

ROOT = Path("custom_components/xiaomi_home")


@pytest.mark.parametrize("cls, key", [
    (MIoTControlPathSensor, "control_path"),
    (MIoTIPAddressSensor, "ip_address")])
def test_diagnostic_sensors_use_translation_keys(cls, key) -> None:
    """A set _attr_name or _attr_icon would override the translations."""
    miot_device = SimpleNamespace(did="did1", entity_id_prefix="fan_did1")
    entity = cls(miot_device=miot_device, entry_id="entry1")
    assert entity.translation_key == key
    assert "_attr_name" not in entity.__dict__
    assert "_attr_icon" not in entity.__dict__

    strings = json.loads((ROOT / "translations/en.json").read_text())
    icons = json.loads((ROOT / "icons.json").read_text())
    assert strings["entity"]["sensor"][key]["name"]
    assert icons["entity"]["sensor"][key]["default"].startswith("mdi:")
