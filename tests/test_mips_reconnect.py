"""Tests for MQTT reconnect coalescing and connection log levels."""
# pylint: disable=protected-access
import threading
from unittest.mock import MagicMock

import pytest
from paho.mqtt.client import MQTT_ERR_CONN_LOST, MQTT_ERR_KEEPALIVE
from paho.mqtt.packettypes import PacketTypes
from paho.mqtt.reasoncodes import ReasonCode

from custom_components.xiaomi_home.miot.miot_mips import MipsCloudClient


class _Clock:
    """Controllable internal loop clock."""

    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def _client() -> tuple[MipsCloudClient, _Clock, MagicMock]:
    client = MipsCloudClient.__new__(MipsCloudClient)
    clock = _Clock()
    client._internal_loop = MagicMock()
    client._internal_loop.time = clock
    client._internal_loop.call_later = MagicMock(
        side_effect=lambda *args: MagicMock())
    client.main_loop = MagicMock()
    client._logger = MagicMock()
    client._client_id = 'test'
    client._mips_reconnect_tag = True
    client._mips_reconnect_interval = 0
    client._mips_reconnect_timer = None
    client._mips_failure_since = None
    client._mips_failure_warned_at = None
    return client, clock, client._logger


def _retry(client: MipsCloudClient) -> None:
    client._MipsClient__mips_try_reconnect()


def _fire_timer(client: MipsCloudClient) -> None:
    """The scheduled __mips_connect clears the timer before connecting."""
    client._mips_reconnect_timer = None


def test_duplicate_failures_schedule_one_retry() -> None:
    """Two failure callbacks for one attempt must not double the backoff."""
    client, _, _ = _client()
    _retry(client)
    _retry(client)
    assert client._internal_loop.call_later.call_count == 1
    assert client._mips_reconnect_interval == client.MIPS_RECONNECT_INTERVAL_MIN

    _fire_timer(client)
    _retry(client)
    assert client._internal_loop.call_later.call_count == 2
    assert client._mips_reconnect_interval == (
        2 * client.MIPS_RECONNECT_INTERVAL_MIN)


def test_immediate_retry_replaces_pending_timer() -> None:
    """A start or forced reconnect still replaces the pending timer."""
    client, _, _ = _client()
    _retry(client)
    pending = client._mips_reconnect_timer
    client._MipsClient__mips_try_reconnect(immediately=True)
    pending.cancel.assert_called_once()
    assert client._internal_loop.call_later.call_count == 2


def test_lasting_outage_warns_once_then_recovers() -> None:
    """Warn after 120 s of failures, at most every 30 min, then log recovery."""
    client, clock, logger = _client()
    _retry(client)
    assert not logger.warning.called

    clock.now += client.MIPS_FAILURE_WARNING_DELAY
    _fire_timer(client)
    _retry(client)
    assert logger.warning.call_count == 1

    clock.now += 60
    _fire_timer(client)
    _retry(client)
    assert logger.warning.call_count == 1

    clock.now += client.MIPS_FAILURE_WARNING_INTERVAL
    _fire_timer(client)
    _retry(client)
    assert logger.warning.call_count == 2

    client._MipsClient__reset_reconnect_time()
    assert any('recovered' in call.args[0]
               for call in logger.info.call_args_list)
    assert client._mips_failure_since is None
    assert client._mips_reconnect_interval == 0


def _disconnect(rc) -> MagicMock:
    client, _, logger = _client()
    client._mqtt_state = True
    client._mqtt_timer = None
    client._mqtt_fd = -1
    client._mips_sub_pending_timer = None
    client._mips_sub_pending_map = {}
    client._mips_state_sub_map = {}
    client._mips_state_sub_map_lock = threading.Lock()
    client._event_disconnect = MagicMock()
    client._event_connect = MagicMock()
    client._MipsClient__on_disconnect(None, None, rc, None)
    return logger


@pytest.mark.parametrize(('rc', 'level'), [
    (0, 'info'),
    (MQTT_ERR_CONN_LOST, 'debug'),
    (MQTT_ERR_KEEPALIVE, 'debug'),
    (ReasonCode(PacketTypes.DISCONNECT, identifier=135), 'warning'),
    # Broker reason code 4 is not the client's "no connection" error
    (ReasonCode(PacketTypes.DISCONNECT, identifier=4), 'info'),
])
def test_disconnect_log_level(rc, level: str) -> None:
    """Transient losses are quiet, rejected credentials stand out."""
    logger = _disconnect(rc)
    calls = [name for name in ('debug', 'info', 'warning', 'error')
             if any('mips disconnect' in call.args[0]
                    for call in getattr(logger, name).call_args_list)]
    assert calls == [level]
