"""Requests in flight when a gateway or LAN connection goes away must end."""
# pylint: disable=protected-access
import asyncio
import json
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.xiaomi_home.miot import miot_lan, miot_mips
from custom_components.xiaomi_home.miot.miot_lan import (
    MIoTLan, _MIoTLanRequestData)
from custom_components.xiaomi_home.miot.miot_mips import (
    MipsLocalClient, _MipsRequest)


def _mips() -> MipsLocalClient:
    with patch.object(MipsLocalClient, "__init__",
                      lambda self, *args, **kwargs: None):
        mips = MipsLocalClient()  # pylint: disable=no-value-for-parameter
    mips.log_debug = MagicMock()
    mips._mips_thread = None  # base disconnect has nothing to stop
    mips.main_loop = MagicMock()
    return mips


def test_gateway_disconnect_answers_pending_requests() -> None:
    """disconnect() used to clear the map without replying: the replies of
    _on_mips_disconnect never ran because the internal loop had stopped."""
    mips = _mips()
    replies = []
    timer = MagicMock()
    mips._request_map = {"7": _MipsRequest(
        mid=7, on_reply=lambda payload, ctx: replies.append((payload, ctx)),
        on_reply_ctx="ctx", timer=timer)}

    mips.disconnect()

    timer.cancel.assert_called_once()
    assert len(replies) == 1
    assert json.loads(replies[0][0])["error"]["code"] == -10001
    assert replies[0][1] == "ctx"
    assert not mips._request_map


@pytest.mark.asyncio
async def test_gateway_request_that_is_never_answered_times_out(
        monkeypatch) -> None:
    mips = _mips()
    mips.main_loop = asyncio.get_running_loop()
    monkeypatch.setattr(miot_mips, "_REQUEST_TIMEOUT_MARGIN", 0.05)
    mips._MipsLocalClient__request_external = MagicMock(return_value=True)

    result = await asyncio.wait_for(
        mips._MipsLocalClient__request_async(
            topic="proxy/get", payload="{}", timeout_ms=10), timeout=2)

    assert result["error"]["code"] == -10006


def _lan() -> MIoTLan:
    with patch.object(MIoTLan, "__init__", lambda self, *a, **k: None):
        lan = MIoTLan()  # pylint: disable=no-value-for-parameter
    return lan


@pytest.mark.asyncio
async def test_lan_call_that_is_never_answered_times_out(monkeypatch) -> None:
    lan = _lan()
    lan._main_loop = asyncio.get_running_loop()
    lan._internal_loop = MagicMock()  # drops the request, like a stopped loop
    monkeypatch.setattr(miot_lan, "_REQUEST_TIMEOUT_MARGIN", 0.05)

    result = await asyncio.wait_for(
        lan._MIoTLan__call_api_async(did="1", msg={}, timeout_ms=10),
        timeout=2)

    assert result["code"] == -10006
    lan._internal_loop.call_soon_threadsafe.assert_called_once()


def test_lan_deinit_answers_pending_requests() -> None:
    lan = _lan()
    lan._scan_timer = None
    lan._lan_devices = {}
    lan._reply_msg_buffer = {}
    lan._broadcast_socks = {}
    lan._internal_loop = MagicMock()
    answers = []
    timer = MagicMock()
    lan._pending_requests = {
        1: _MIoTLanRequestData(
            msg_id=1, handler=lambda msg, ctx: answers.append((msg, ctx)),
            handler_ctx="ctx", timeout=timer),
        2: _MIoTLanRequestData(  # an ack, nothing to answer
            msg_id=2, handler=None, handler_ctx=None, timeout=None)}

    lan._MIoTLan__deinit()

    timer.cancel.assert_called_once()
    assert answers == [({"code": -10006, "error": "lan control stopped"},
                        "ctx")]
    assert not lan._pending_requests
    lan._internal_loop.stop.assert_called_once()


@pytest.mark.asyncio
async def test_refresh_handler_survives_a_raising_refresh_path() -> None:
    """An exception used to leave _refresh_props_timer set for good, so
    request_refresh_prop never scheduled another refresh."""
    from custom_components.xiaomi_home.miot.miot_client import (  # pylint: disable=import-outside-toplevel
        CtrlMode, MIoTClient, REFRESH_PROPS_RETRY_DELAY)
    with patch.object(MIoTClient, "__init__", lambda self, *a, **k: None):
        client = MIoTClient()  # pylint: disable=no-value-for-parameter
    client._refresh_props_list = {"1|2|3": {"did": "1", "siid": 2, "piid": 3}}
    client._ctrl_mode = CtrlMode.LOCAL
    client._entry_data = {}
    client._refresh_props_retry_count = 0
    client._lan_manager = MagicMock()
    client._lan_manager.refresh_props_from_gw = AsyncMock(
        side_effect=RuntimeError("boom"))
    client._lan_manager.refresh_props_from_lan = AsyncMock(return_value=False)
    client._main_loop = MagicMock()
    client._refresh_props_timer = MagicMock()

    await client._MIoTClient__refresh_props_handler()

    client._lan_manager.refresh_props_from_lan.assert_awaited_once()
    assert client._refresh_props_retry_count == 1
    assert client._main_loop.call_later.call_args.args[0] == (
        REFRESH_PROPS_RETRY_DELAY)


@pytest.mark.asyncio
async def test_disconnect_async_does_not_block_the_event_loop() -> None:
    """disconnect() joins the MQTT thread, which can be stuck in a blocking
    connect; called on the loop it froze Home Assistant meanwhile."""
    mips = _mips()
    started = time.monotonic()
    mips.disconnect = lambda: time.sleep(0.3)  # a slow thread join
    ticks = 0

    async def tick() -> None:
        nonlocal ticks
        while time.monotonic() - started < 0.25:
            ticks += 1
            await asyncio.sleep(0.01)

    await asyncio.gather(mips.disconnect_async(), tick())

    assert ticks >= 10


def test_ack_without_handler_is_not_kept_as_pending() -> None:
    """Acks used the device's message id and were never answered: the map
    grew with every push, and a later push with that id was dropped."""
    lan = _lan()
    lan._pending_requests = {}
    lan._internal_loop = MagicMock()
    lan._MIoTLan__sendto = MagicMock()

    lan._MIoTLan__make_request(
        msg_id=42, msg=bytearray(b"ack"), if_name="en0", ip="1.2.3.4",
        handler=None)
    assert not lan._pending_requests
    lan._MIoTLan__sendto.assert_called_once()

    lan._MIoTLan__make_request(
        msg_id=43, msg=bytearray(b"call"), if_name="en0", ip="1.2.3.4",
        handler=lambda msg, ctx: None, timeout_ms=1000)
    assert list(lan._pending_requests) == [43]
