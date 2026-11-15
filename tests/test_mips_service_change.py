"""Central hub gateway mDNS changes: applied one at a time, without errors."""
# pylint: disable=protected-access
import asyncio
import logging
import threading
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.xiaomi_home.miot import miot_client as client_module
from custom_components.xiaomi_home.miot.miot_client import MIoTClient
from custom_components.xiaomi_home.miot.miot_error import (
    MIoTErrorCode, MIoTMipsError)
from custom_components.xiaomi_home.miot.miot_mips import MipsLocalClient

GROUP = "1efb8f7e07418270"


class _FakeMips:
    """Stands in for MipsLocalClient; the real one opens an MQTT thread."""

    created: list = []

    def __init__(self, **kwargs) -> None:
        self.host = kwargs["host"]
        self.port = kwargs["port"]
        self.client_id = kwargs["did"]
        self.group_id = kwargs["group_id"]
        self.on_dev_list_changed = None
        self.subscribed: dict = {}
        self.disconnects = 0
        _FakeMips.created.append(self)

    def enable_logger(self, logger) -> None:
        del logger

    def sub_mips_state(self, key, handler) -> None:
        self.subscribed[key] = handler

    def unsub_mips_state(self, key) -> None:
        # The old behaviour: raises once the key is gone
        del self.subscribed[key]

    def connect(self) -> None:
        pass

    async def disconnect_async(self) -> None:
        self.disconnects += 1
        await asyncio.sleep(0.01)  # joins the MQTT thread in real life

    async def deinit_async(self) -> None:
        self.subscribed.clear()


def _client(host: str = "10.0.0.1") -> MIoTClient:
    with patch.object(MIoTClient, "__init__", lambda self, *a, **k: None):
        client = MIoTClient()  # pylint: disable=no-value-for-parameter
    client._entry_data = {"virtual_did": "vd", "home_selected": {}}
    client._cert = SimpleNamespace(ca_file="ca", cert_file="c", key_file="k")
    client._main_loop = asyncio.get_running_loop()
    client._mips_service_change_locks = {}
    _FakeMips.created = []
    old = _FakeMips(did="vd", group_id=GROUP, host=host, port=8883)
    old.subscribed[GROUP] = object()
    client._mips_local = {GROUP: old}
    return client


def _data(*addresses: str) -> dict:
    return {"addresses": list(addresses), "port": 8883, "group_id": GROUP}


@pytest.mark.asyncio
async def test_close_changes_are_applied_one_after_the_other() -> None:
    """Two announcements close together each replaced the same old client;
    the second failed with KeyError and its newer address was lost."""
    client = _client()
    change = client._MIoTClient__on_mips_service_state_change
    with patch.object(client_module, "MipsLocalClient", _FakeMips):
        await asyncio.gather(
            change(GROUP, None, _data("10.0.0.2")),
            change(GROUP, None, _data("10.0.0.3")))

    assert client._mips_local[GROUP].host == "10.0.0.3"
    created = _FakeMips.created
    assert len(created) == 3  # the old client and one per change
    assert [mips.disconnects for mips in created] == [1, 1, 0]


@pytest.mark.asyncio
async def test_reordered_addresses_keep_the_connection() -> None:
    client = _client(host="10.0.0.1")
    change = client._MIoTClient__on_mips_service_state_change
    with patch.object(client_module, "MipsLocalClient", _FakeMips):
        await change(GROUP, None, _data("10.0.0.9", "10.0.0.1"))

    old = _FakeMips.created[0]
    assert client._mips_local[GROUP] is old
    assert old.disconnects == 0


def test_unsubscribing_twice_does_not_raise() -> None:
    mips = object.__new__(MipsLocalClient)
    mips._mips_state_sub_map = {}
    mips._mips_state_sub_map_lock = threading.Lock()
    mips._logger = None
    mips._client_id = "vd"
    assert mips.unsub_mips_state(GROUP)


@pytest.mark.asyncio
async def test_disconnect_reply_is_reported_as_unavailable() -> None:
    mips = object.__new__(MipsLocalClient)
    mips._MipsLocalClient__request_async = AsyncMock(return_value={
        "error": {"code": -10001, "message": "mips disconnected"}})
    with pytest.raises(MIoTMipsError) as err:
        await mips.get_dev_list_async()
    assert err.value.code == MIoTErrorCode.CODE_UNAVAILABLE


@pytest.mark.asyncio
async def test_device_list_interrupted_by_a_disconnect_is_not_a_warning(
        caplog) -> None:
    """The gateway devices are fetched again when it reconnects."""
    client = _client()
    mips = MagicMock(group_id=GROUP)
    mips.get_dev_list_async = AsyncMock(side_effect=MIoTMipsError(
        "gateway error (-10001): mips disconnected",
        MIoTErrorCode.CODE_UNAVAILABLE))
    with caplog.at_level(logging.DEBUG):
        await client._MIoTClient__on_gw_device_list_changed(mips, ["1"])
    assert not [r for r in caplog.records if r.levelno >= logging.WARNING]

    mips.get_dev_list_async = AsyncMock(side_effect=MIoTMipsError(
        "request timeout (10000ms)"))
    with caplog.at_level(logging.DEBUG):
        await client._MIoTClient__on_gw_device_list_changed(mips, ["1"])
    assert [r for r in caplog.records if r.levelno == logging.WARNING]
