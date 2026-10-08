"""Unit tests for MIoTLanManager and MIoTCloudManager refresh handling."""
import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock
from custom_components.xiaomi_home.miot.miot_lan_manager import MIoTLanManager
from custom_components.xiaomi_home.miot.miot_cloud_manager import MIoTCloudManager


@pytest.mark.asyncio
async def test_lan_manager_coroutine_safety() -> None:
    """Test that MIoTLanManager does not leak coroutines into refresh_props_list on failure."""
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
    # Check that failed request was re-queued cleanly without 'fut' coroutine object
    assert "dev1|2|1" in client.refresh_props_list
    requeued = client.refresh_props_list["dev1|2|1"]
    assert "fut" not in requeued
    assert requeued == {"did": "dev1", "siid": 2, "piid": 1}


@pytest.mark.asyncio
async def test_cloud_manager_sanitization_and_coroutine_resilience() -> None:
    """Test that MIoTCloudManager sanitizes dirty dictionary items and doesn't crash."""
    client = MagicMock()
    client.miot_network.network_status = True

    # Simulate refresh_props_list having a contaminated item with extra non-serializable fields
    dummy_coro = asyncio.sleep(0.01)
    client.refresh_props_list = {
        "dev1|2|1": {
            "did": "dev1",
            "siid": 2,
            "piid": 1,
            "fut": dummy_coro  # Coroutine object that previously broke JSON serialization
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
    """Test that MIoTCloudManager handles TimeoutError gracefully and re-queues sanitized items."""
    client = MagicMock()
    client.miot_network.network_status = True
    client.refresh_props_list = {
        "dev1|2|1": {"did": "dev1", "siid": 2, "piid": 1}
    }
    client.miot_http.get_props_async = AsyncMock(side_effect=TimeoutError("Request timed out"))

    manager = MIoTCloudManager(client)
    success = await manager.refresh_props()

    assert success is False
    assert "dev1|2|1" in client.refresh_props_list
    assert client.refresh_props_list["dev1|2|1"] == {"did": "dev1", "siid": 2, "piid": 1}
