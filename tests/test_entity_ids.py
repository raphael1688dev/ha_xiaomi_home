"""Entity IDs the integration suggests must be valid entity IDs.

Home Assistant reports an invalid entity_id set by an entity and stops
adding such entities in 2027.2. A few models have an uppercase letter in
their last part (xiaomi.watch.band1A, band1S).
"""
# pylint: disable=protected-access
from types import SimpleNamespace

import pytest
from homeassistant.core import valid_entity_id
from homeassistant.util import slugify

from custom_components.xiaomi_home.miot.common import slugify_name
from custom_components.xiaomi_home.miot.miot_device import MIoTDevice


def _device(model: str, did: str = "123456") -> MIoTDevice:
    device = object.__new__(MIoTDevice)
    device._did = did
    device._model = model
    device._model_strs = model.split(".")
    device.miot_client = SimpleNamespace(cloud_server="cn")
    return device


def _old_entity_id(device: MIoTDevice, domain: str, name) -> str:
    """The formula before the fix."""
    prefix = f"{device.did_tag}_{device._model_strs[-1][:20]}"
    if name:
        suffix = slugify_name(name.replace("* ", ""))
        return f"{domain}.{prefix}_{suffix}"
    return f"{domain}.{prefix}"


@pytest.mark.parametrize("model, did, domain, name", [
    ("yeelink.light.lamp30", "779521713", "light", None),
    ("yeelink.light.lamp30", "779521713", "light", "Light Brightness"),
    ("zhimi.fan.za5", "blt.3.abc", "fan", "* Fan Control"),
    ("dmaker.fan.p39", "12345", "sensor", "Environment Temperature"),
    ("xiaomi.vacuum.b108gl", "group.1", "button", "Vacuum Start Sweep"),
])
def test_valid_ids_do_not_change(model, did, domain, name) -> None:
    """Existing entities keep their IDs: no rename for valid models."""
    device = _device(model, did)
    old = _old_entity_id(device, domain, name)
    assert valid_entity_id(old)
    assert device.gen_entity_id(domain, name) == old


@pytest.mark.parametrize(
    "model", ["xiaomi.watch.band1A", "xiaomi.watch.band1S"])
def test_uppercase_model_gives_the_registry_id(model) -> None:
    """The registry slugified the old suggestion, so the new ID is the one it
    already holds and the startup migration has nothing to rename."""
    device = _device(model)
    old = _old_entity_id(device, "sensor", "Battery Battery Level")
    assert not valid_entity_id(old)
    new = device.gen_entity_id("sensor", "Battery Battery Level")
    assert valid_entity_id(new)
    object_id = old.split(".", 1)[1]
    assert new == f"sensor.{slugify(object_id)}"
    assert valid_entity_id(f"sensor.{device.entity_id_prefix}_control_path")


@pytest.mark.parametrize("model", ["vendor.type.Pro-Max+", "vendor.type.v2_"])
def test_odd_model_parts_give_valid_ids(model) -> None:
    device = _device(model)
    for name in (None, "Switch Status"):
        assert valid_entity_id(device.gen_entity_id("switch", name))


def test_name_without_a_slug_gives_a_valid_id() -> None:
    """A name with nothing to slugify used to leave a trailing "_"."""
    device = _device("yeelink.light.lamp30")
    assert _old_entity_id(device, "sensor", "*").endswith("_")
    assert device.gen_entity_id("sensor", "*") == "sensor.cn_123456_lamp30"
