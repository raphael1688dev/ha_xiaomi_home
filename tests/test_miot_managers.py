"""Unit tests for MIoTLanManager and MIoTCloudManager refresh handling."""
import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock
from custom_components.xiaomi_home.miot.const import PROP_MSG_POLLED
from custom_components.xiaomi_home.miot.miot_lan_manager import MIoTLanManager
from custom_components.xiaomi_home.miot.miot_cloud_manager import MIoTCloudManager


@pytest.mark.asyncio
async def test_lan_manager_coroutine_safety() -> None:
    """Test that MIoTLanManager does not leak coroutines on failure."""
    client = MagicMock()
    client.miot_lan.init_done = True
    client.device_list_lan = {"dev1": {"ip": "192.168.1.100"}}
    client.refresh_props_list = {
        "dev1|2|1": {"did": "dev1", "siid": 2, "piid": 1}
    }
    # Mock get_prop_async returning None (simulating failure)
    client.miot_lan.get_prop_async = AsyncMock(return_value=None)

    manager = MIoTLanManager(client)
    success = await manager.refresh_props_from_lan()

    assert success is False
    # Check that failed request was re-queued cleanly without 'fut' coroutine
    # object
    assert "dev1|2|1" in client.refresh_props_list
    requeued = client.refresh_props_list["dev1|2|1"]
    assert "fut" not in requeued
    assert requeued == {"did": "dev1", "siid": 2, "piid": 1}


@pytest.mark.asyncio
async def test_cloud_manager_sanitization_and_coroutine_resilience() -> None:
    """Test that MIoTCloudManager sanitizes dirty items without crashing."""
    client = MagicMock()
    client.miot_network.network_status = True

    # Simulate refresh_props_list having a contaminated item with extra
    # non-serializable fields
    dummy_coro = asyncio.sleep(0.01)
    client.refresh_props_list = {
        "dev1|2|1": {
            "did": "dev1",
            "siid": 2,
            "piid": 1,
            # Coroutine object that previously broke JSON serialization
            "fut": dummy_coro
        }
    }

    # Mock get_props_async
    async def mock_get_props(params: list):
        # Verify params sent to HTTP is clean
        for p in params:
            assert "fut" not in p
            assert set(p.keys()) == {"did", "siid", "piid"}
        return [{"did": "dev1", "siid": 2, "piid": 1, "value": 100}]

    client.miot_http.get_props_async = AsyncMock(side_effect=mock_get_props)

    manager = MIoTCloudManager(client)
    success = await manager.refresh_props()

    assert success is True
    assert client.on_prop_msg.called
    # Await dummy coro to prevent RuntimeWarning
    await dummy_coro


@pytest.mark.asyncio
async def test_cloud_manager_timeout_handling() -> None:
    """Test that MIoTCloudManager re-queues sanitized items on timeout."""
    client = MagicMock()
    client.miot_network.network_status = True
    client.refresh_props_list = {
        "dev1|2|1": {"did": "dev1", "siid": 2, "piid": 1}
    }
    client.miot_http.get_props_async = AsyncMock(
        side_effect=TimeoutError("Request timed out"))

    manager = MIoTCloudManager(client)
    success = await manager.refresh_props()

    assert success is False
    assert "dev1|2|1" in client.refresh_props_list
    assert client.refresh_props_list["dev1|2|1"] == {
        "did": "dev1",
        "siid": 2,
        "piid": 1
    }


def _refresh_client() -> MagicMock:
    client = MagicMock()
    client.miot_lan.init_done = True
    client.miot_network.network_status = True
    client.device_list_lan = {"dev1": {"ip": "192.168.1.100"}}
    client.device_list_gateway = {"dev1": {"group_id": "g1"}}
    client.refresh_props_list = {
        "dev1|2|1": {"did": "dev1", "siid": 2, "piid": 1}}
    return client


@pytest.mark.asyncio
@pytest.mark.parametrize("source", ["cloud", "gateway", "lan"])
async def test_refreshed_values_are_marked_as_polled(source: str) -> None:
    """Entities tell a poll from a device push by this marker."""
    client = _refresh_client()
    if source == "cloud":
        client.miot_http.get_props_async = AsyncMock(return_value=[
            {"did": "dev1", "siid": 2, "piid": 1, "value": 100}])
        assert await MIoTCloudManager(client).refresh_props()
    elif source == "gateway":
        mips_gw = MagicMock()
        mips_gw.get_prop_async = AsyncMock(return_value=100)
        client.mips_local = {"g1": mips_gw}
        assert await MIoTLanManager(client).refresh_props_from_gw()
    else:
        client.miot_lan.get_prop_async = AsyncMock(return_value=100)
        assert await MIoTLanManager(client).refresh_props_from_lan()

    params = client.on_prop_msg.call_args.kwargs["params"]
    assert params == {"did": "dev1", "siid": 2, "piid": 1, "value": 100,
                      PROP_MSG_POLLED: True}
