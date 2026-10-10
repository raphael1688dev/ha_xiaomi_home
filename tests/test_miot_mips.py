"""Unit tests for MIoT MIPS local client error handling and retry resilience."""
import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from custom_components.xiaomi_home.miot.miot_error import MIoTMipsError
from custom_components.xiaomi_home.miot.miot_mips import MipsLocalClient


@pytest.fixture
def mock_mips_local() -> MipsLocalClient:
    """Create a mock MipsLocalClient instance with internal components stubbed."""
    with patch.object(MipsLocalClient, "__init__", lambda self, *args, **kwargs: None):
        mips = MipsLocalClient()
        mips.log_error = MagicMock()
        mips.log_info = MagicMock()
        return mips


@pytest.mark.asyncio
async def test_get_dev_list_async_timeout(mock_mips_local: MipsLocalClient) -> None:
    """Test get_dev_list_async provides clear timeout message on code -10006."""
    mock_mips_local._MipsLocalClient__request_async = AsyncMock(
        return_value={"error": {"code": -10006, "message": "timeout"}}
    )
    with pytest.raises(MIoTMipsError) as exc_info:
        await mock_mips_local.get_dev_list_async(timeout_ms=10000)

    assert "request timeout (10000ms)" in str(exc_info.value)


@pytest.mark.asyncio
async def test_get_dev_list_async_gateway_error(mock_mips_local: MipsLocalClient) -> None:
    """Test get_dev_list_async reports specific gateway error code and message."""
    mock_mips_local._MipsLocalClient__request_async = AsyncMock(
        return_value={"error": {"code": -10001, "message": "service unavailable"}}
    )
    with pytest.raises(MIoTMipsError) as exc_info:
        await mock_mips_local.get_dev_list_async()

    assert "gateway error (-10001): service unavailable" in str(exc_info.value)


@pytest.mark.asyncio
async def test_get_dev_list_async_empty_response(mock_mips_local: MipsLocalClient) -> None:
    """Test get_dev_list_async reports empty response clearly."""
    mock_mips_local._MipsLocalClient__request_async = AsyncMock(return_value=None)
    with pytest.raises(MIoTMipsError) as exc_info:
        await mock_mips_local.get_dev_list_async()

    assert "empty response from gateway" in str(exc_info.value)


@pytest.mark.asyncio
async def test_get_dev_list_async_nested_devlist(mock_mips_local: MipsLocalClient) -> None:
    """Test get_dev_list_async handles nested result.devList structure gracefully."""
    mock_mips_local._MipsLocalClient__request_async = AsyncMock(
        return_value={
            "result": {
                "devList": {
                    "did123": {
                        "name": "Plug",
                        "urn": "urn:miot-spec-v2:device:outlet:0000A002:cuco-v3:1",
                        "model": "cuco.plug.v3",
                        "online": True,
                        "specV2Access": True,
                        "pushAvailable": True,
                    }
                }
            }
        }
    )
    devices = await mock_mips_local.get_dev_list_async()
    assert "did123" in devices
    assert devices["did123"]["online"] is True
    assert devices["did123"]["specv2_access"] is True


@pytest.mark.asyncio
async def test_get_dev_list_async_standard_devlist(mock_mips_local: MipsLocalClient) -> None:
    """Test get_dev_list_async handles standard top-level devList response."""
    mock_mips_local._MipsLocalClient__request_async = AsyncMock(
        return_value={
            "devList": {
                "did456": {
                    "name": "Light",
                    "urn": "urn:miot-spec-v2:device:light:0000A001:yeelink-v1:1",
                    "model": "yeelink.light.v1",
                    "online": False,
                    "specV2Access": True,
                    "pushAvailable": False,
                }
            }
        }
    )
    devices = await mock_mips_local.get_dev_list_async()
    assert "did456" in devices
    assert devices["did456"]["online"] is False
    assert devices["did456"]["push_available"] is False
