"""Regression tests for device-level entities (whole-device conversion)."""
from unittest.mock import MagicMock

from custom_components.xiaomi_home.miot.miot_device import MIoTDevice
from custom_components.xiaomi_home.miot.miot_spec import MIoTSpecInstance


def _vacuum_spec() -> MIoTSpecInstance:
    """A minimal robot vacuum; its device mapping uses frozenset actions."""
    urn = 'urn:miot-spec-v2:device:vacuum:0000A006:test-v1:1'

    def action(iid: int, name: str, desc: str) -> dict:
        return {
            'iid': iid,
            'type': f'urn:miot-spec-v2:action:{name}:00002801:test-v1:1',
            'name': name,
            'description': desc,
            'description_trans': desc,
            'in': [],
            'out': [],
        }

    return MIoTSpecInstance.load({
        'urn': urn,
        'name': 'vacuum',
        'description': 'Robot Cleaner',
        'description_trans': 'Robot Cleaner',
        'services': [{
            'iid': 2,
            'type': 'urn:miot-spec-v2:service:vacuum:00007810:test-v1:1',
            'name': 'vacuum',
            'description': 'Robot Cleaner',
            'description_trans': 'Robot Cleaner',
            'properties': [],
            'events': [],
            'actions': [
                action(1, 'start-sweep', 'Start Sweep'),
                action(2, 'stop-sweeping', 'Stop Sweeping'),
            ],
        }],
    })


def _device(spec: MIoTSpecInstance) -> MIoTDevice:
    miot_client = MagicMock()
    miot_client.area_name_rule = 'none'
    return MIoTDevice(
        miot_client=miot_client,
        device_info={
            'did': '123456', 'name': 'Vacuum', 'model': 'test.vacuum.v1'},
        spec_instance=spec)


def test_vacuum_device_entity_transform() -> None:
    """frozenset actions in SPEC_DEVICE_TRANS_MAP used to raise TypeError."""
    device = _device(_vacuum_spec())
    device.spec_transform()

    entities = device.entity_list.get('vacuum', [])
    assert len(entities) == 1
    assert isinstance(entities[0].spec, MIoTSpecInstance)
    assert {a.name for a in entities[0].actions} == {
        'start-sweep', 'stop-sweeping'}


def test_expected_entity_ids_skip_device_entity() -> None:
    """MIoTSpecInstance has no iid, the migration mapping must skip it."""
    device = _device(_vacuum_spec())
    device.spec_transform()
    # Used to raise AttributeError: 'MIoTSpecInstance' has no attribute 'iid'
    assert isinstance(device.get_expected_entity_ids(), dict)
