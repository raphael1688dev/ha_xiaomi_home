"""Unit tests for the default unit of sensors without a spec unit."""
import os
import subprocess
import sys

import pytest
from homeassistant.components.sensor import SensorDeviceClass

from custom_components.xiaomi_home.sensor import _default_unit


@pytest.mark.parametrize("device_class,unit", [
    (SensorDeviceClass.DURATION, "s"),
    (SensorDeviceClass.TEMPERATURE, "°C"),
    (SensorDeviceClass.VOLATILE_ORGANIC_COMPOUNDS, "mg/m³"),
    (SensorDeviceClass.VOLATILE_ORGANIC_COMPOUNDS_PARTS, "ppb"),
    (SensorDeviceClass.MOISTURE, "%"),
    (SensorDeviceClass.AQI, None),
    (None, None),
])
def test_default_unit(device_class, unit) -> None:
    assert _default_unit(device_class) == unit


def test_default_unit_does_not_depend_on_the_hash_seed() -> None:
    """list(set)[0] gave d, h, ms or s for a duration depending on
    PYTHONHASHSEED, so the unit changed between restarts."""
    code = (
        "from homeassistant.components.sensor import SensorDeviceClass as D\n"
        "from custom_components.xiaomi_home.sensor import _default_unit\n"
        "print([_default_unit(d) for d in D])")
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    outputs = {
        subprocess.run(
            [sys.executable, "-c", code], cwd=root, check=True,
            capture_output=True, text=True,
            env={**os.environ, "PYTHONHASHSEED": str(seed),
                 "PYTHONPATH": root}).stdout
        for seed in (1, 2, 3, 4)}
    assert len(outputs) == 1
