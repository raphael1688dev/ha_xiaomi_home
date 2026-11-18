"""Pet feeder manual feed button (ported from XiaoMi/ha_xiaomi_home#1858)."""
from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.xiaomi_home.button import Button
from custom_components.xiaomi_home.notify import Notify
from custom_components.xiaomi_home.miot.miot_device import MIoTDevice
from custom_components.xiaomi_home.miot.miot_spec import MIoTSpecInstance


def _feeder_spec(action_name: str = 'pet-food-out') -> MIoTSpecInstance:
    return MIoTSpecInstance.load({
        'urn': 'urn:miot-spec-v2:device:feeder:0000A06E:xiaomi-iv2001:1',
        'name': 'feeder',
        'description': 'Pet Feeder',
        'description_trans': 'Pet Feeder',
        'services': [{
            'iid': 2,
            'type': 'urn:miot-spec-v2:service:pet-feeder:00007888:'
                    'xiaomi-iv2001:1',
            'name': 'pet-feeder',
            'description': 'Pet Feeder',
            'description_trans': 'Pet Feeder',
            'properties': [{
                'iid': 7,
                'type': 'urn:miot-spec-v2:property:feeding-measure:0000014F:'
                        'xiaomi-iv2001:1',
                'name': 'feeding-measure',
                'description': 'Feeding Measure',
                'description_trans': 'Feeding Measure',
                'format': 'uint8', 'access': ['write'], 'unit': 'none',
                'value_range': [1, 30, 1], 'value_list': None,
            }],
            'events': [],
            'actions': [{
                'iid': 1,
                'type': f'urn:miot-spec-v2:action:{action_name}:00002857:'
                        'xiaomi-iv2001:1',
                'name': action_name,
                'description': 'Pet Food Out',
                'description_trans': 'Pet Food Out',
                'in': [7], 'out': [],
            }],
        }],
    })


def _device(spec: MIoTSpecInstance) -> MIoTDevice:
    miot_client = MagicMock()
    miot_client.area_name_rule = 'none'
    miot_client.cloud_server = 'sg'
    device = MIoTDevice(
        miot_client=miot_client,
        device_info={'did': '123456', 'name': 'Feeder',
                     'model': 'xiaomi.feeder.iv2001'},
        spec_instance=spec)
    device.spec_transform()
    return device


def test_feed_action_gets_a_button_besides_the_notify_entity() -> None:
    device = _device(_feeder_spec())
    notify = device.action_list.get('notify', [])
    button = device.action_list.get('button', [])
    assert [a.name for a in notify] == ['pet-food-out']
    assert [a.name for a in button] == ['pet-food-out']
    assert notify[0] is not button[0]
    assert notify[0].platform == 'notify'


def test_other_actions_with_inputs_stay_notify_only() -> None:
    device = _device(_feeder_spec(action_name='play-sound'))
    assert [a.name for a in device.action_list.get('notify', [])] == [
        'play-sound']
    assert not device.action_list.get('button')


def test_startup_migration_does_not_rename_either_entity() -> None:
    """Both entities share the action's unique ID on different platforms,
    so the migration map holds one target for it. The migration swaps in
    the registry entry's own domain, which must give each entity its
    current ID back."""
    device = _device(_feeder_spec())
    action = device.action_list['notify'][0]
    uid = device.gen_action_unique_id(
        spec_name=action.name, siid=action.service.iid, aiid=action.iid)
    object_id = device.get_expected_entity_ids()[uid].split('.', 1)[1]
    device.miot_client.action_async = AsyncMock(return_value=[])
    for entity in (
            Button(miot_device=device, spec=device.action_list['button'][0]),
            Notify(miot_device=device, spec=action)):
        domain = entity.entity_id.split('.', 1)[0]
        assert entity.entity_id == f'{domain}.{object_id}'


@pytest.mark.asyncio
async def test_feed_button_dispenses_one_portion() -> None:
    device = _device(_feeder_spec())
    device.miot_client.action_async = AsyncMock(return_value=[])
    button = Button(miot_device=device,
                    spec=device.action_list['button'][0])
    await button.async_press()
    device.miot_client.action_async.assert_awaited_once_with(
        did='123456', siid=2, aiid=1, in_list=[{'piid': 7, 'value': 1}])
