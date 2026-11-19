"""The property refresh queue: every queued property reaches a reader.

Rewritten from XiaoMi/ha_xiaomi_home#1862. These drive the client's real
refresh handler with the real cloud and gateway/LAN managers.
"""
# pylint: disable=protected-access
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.xiaomi_home.miot.miot_client import (
    CtrlMode, MIoTClient)
from custom_components.xiaomi_home.miot.miot_cloud_manager import (
    MIoTCloudManager)
from custom_components.xiaomi_home.miot.miot_lan_manager import (
    MIoTLanManager)

DID = "dev1"


def _client(cloud, lan_values: dict, *, local: bool = True,
            ctrl_mode=CtrlMode.AUTO, priority="cloud_first"):
    with patch.object(MIoTClient, "__init__", lambda self, *a, **k: None):
        client = MIoTClient()  # pylint: disable=no-value-for-parameter
    client._refresh_props_list = {}
    client._refresh_props_timer = None
    client._refresh_props_retry_count = 0
    client._refresh_props_attempts = {}
    client._refresh_props_cloud_missed = set()
    client._refresh_props_attempted = False
    client._ctrl_mode = ctrl_mode
    client._entry_data = {"poll_priority": priority}
    client._main_loop = MagicMock()
    client._create_tracked_task = MagicMock()
    client._network = SimpleNamespace(network_status=True)
    client._http = SimpleNamespace(get_props_async=cloud)

    async def lan_get(did, siid, piid, timeout_ms):
        del did, siid, timeout_ms
        return lan_values.get(piid)

    client._miot_lan = SimpleNamespace(
        init_done=True, get_prop_async=AsyncMock(side_effect=lan_get))
    client._device_list_lan = {DID: {}} if local else {}
    client._device_list_gateway = {}
    client._mips_local = {}
    client._device_list_cache = {DID: {}}
    client._cloud_manager = MIoTCloudManager(client)
    client._lan_manager = MIoTLanManager(client)
    client.delivered = []
    client.on_prop_msg = lambda params, ctx: client.delivered.append(
        (params["piid"], params["value"]))
    for piid in range(1, 7):
        client.request_refresh_prop(did=DID, siid=2, piid=piid)
    return client


async def _drain(client, max_cycles: int = 40) -> int:
    handler = client._MIoTClient__refresh_props_handler
    for cycle in range(max_cycles):
        if not client._refresh_props_list:
            return cycle
        await handler()
    raise AssertionError("the refresh queue did not drain")


def _cloud_reply(*results):
    return AsyncMock(return_value=[
        {"did": DID, "siid": 2, **r} for r in results])


@pytest.mark.asyncio
async def test_properties_the_cloud_misses_are_read_locally() -> None:
    """The cloud returned property 1, an error for 2 and nothing for 3-6.
    Only 1 used to be delivered: the rest were dropped, and the handler
    stopped after the cloud's success without asking the LAN."""
    cloud = _cloud_reply({"piid": 1, "value": 10},
                         {"piid": 2, "code": -704010000})
    client = _client(cloud, {p: p * 10 for p in range(2, 7)})
    await _drain(client)

    assert sorted(client.delivered) == [(p, p * 10) for p in range(1, 7)]
    cloud.assert_awaited_once()  # missed ones are not asked for again
    assert not client._refresh_props_attempts
    assert not client._refresh_props_cloud_missed


@pytest.mark.asyncio
async def test_failing_properties_do_not_crowd_out_unread_ones() -> None:
    """Cloud timeout; the LAN reads one property per device per cycle and
    fails on 1-4. The shared retry limit used to clear 5-6 before their
    first read."""
    cloud = AsyncMock(side_effect=TimeoutError())
    client = _client(cloud, {5: 50, 6: 60})
    await _drain(client)

    assert sorted(client.delivered) == [(5, 50), (6, 60)]
    # 1-4 were each read three times by the LAN, then given up
    reads = [c.kwargs["piid"]
             for c in client._miot_lan.get_prop_async.await_args_list]
    assert sorted(reads) == sorted([1, 2, 3, 4] * 3 + [5, 6])


@pytest.mark.asyncio
async def test_cloud_misses_without_a_local_reader_are_dropped() -> None:
    cloud = _cloud_reply({"piid": 1, "value": 10})
    client = _client(cloud, {}, local=False)
    await _drain(client)

    assert client.delivered == [(1, 10)]
    cloud.assert_awaited_once()


@pytest.mark.asyncio
async def test_cloud_control_mode_never_hands_misses_to_the_lan() -> None:
    cloud = _cloud_reply({"piid": 1, "value": 10})
    client = _client(cloud, {p: p for p in range(1, 7)},
                     ctrl_mode=CtrlMode.CLOUD)
    await _drain(client)

    assert client.delivered == [(1, 10)]
    client._miot_lan.get_prop_async.assert_not_awaited()


@pytest.mark.asyncio
async def test_nothing_to_read_with_gives_up_after_three_idle_cycles() -> None:
    """Cloud down and no local reader: retried a few times, then dropped,
    instead of retrying forever."""
    cloud = AsyncMock(side_effect=TimeoutError())
    client = _client(cloud, {}, local=False)
    cycles = await _drain(client)

    assert not client.delivered
    assert cycles == 4
    assert not client._refresh_props_list


@pytest.mark.asyncio
async def test_all_reads_succeeding_is_unchanged() -> None:
    cloud = _cloud_reply(*({"piid": p, "value": p} for p in range(1, 7)))
    client = _client(cloud, {})
    cycles = await _drain(client)

    assert sorted(client.delivered) == [(p, p) for p in range(1, 7)]
    assert cycles == 1
