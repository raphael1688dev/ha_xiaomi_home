"""The MQTT callbacks driven by paho's own dispatch (callback API v2).

A fake MQTT v5 broker on a local socket pair sends CONNACK and DISCONNECT
packets, so paho decodes them and calls our callbacks with the arguments
callback API v2 really passes. What the Xiaomi cloud and the central hub
gateway send in practice can only be seen on a real installation.
"""
# pylint: disable=protected-access
import socket
import threading
import warnings
from unittest.mock import MagicMock

import pytest
from paho.mqtt.client import CallbackAPIVersion, MQTTv5

from custom_components.xiaomi_home.miot.miot_mips import (
    MipsCloudClient, _MipsCloudMQTTClient)

from .test_mips_reconnect import _client

CONNACK_OK = bytes([0x20, 0x03, 0x00, 0x00, 0x00])
CONNACK_NOT_AUTHORIZED = bytes([0x20, 0x03, 0x00, 0x87, 0x00])
# paho 2.1 reads the reason code of a DISCONNECT only when properties
# follow it; the property here is a reason string "bye"
DISCONNECT_NOT_AUTHORIZED = bytes(
    [0xE0, 0x08, 0x87, 0x06, 0x1F, 0x00, 0x03]) + b'bye'


class _Broker:
    """The broker end of a socket pair handed to paho as its connection."""

    def __init__(self) -> None:
        self.server, self.client_sock = socket.socketpair()
        self.server.settimeout(2)

    def send(self, packet: bytes) -> None:
        self.server.sendall(packet)

    def close(self) -> None:
        self.server.close()


def _mips_with_paho() -> tuple[MipsCloudClient, _MipsCloudMQTTClient,
                               _Broker, MagicMock]:
    """Our client wired to a paho client exactly as __mips_loop_thread does,
    with the TCP/TLS socket replaced by the fake broker."""
    mips, _, logger = _client()
    mips._mqtt_state = False
    mips._mqtt_timer = None
    mips._mqtt_fd = -1
    mips._mips_sub_pending_timer = None
    mips._mips_sub_pending_map = {}
    mips._mips_state_sub_map = {}
    mips._mips_state_sub_map_lock = threading.Lock()
    mips._event_connect = MagicMock()
    mips._event_disconnect = MagicMock()
    broker = _Broker()

    with warnings.catch_warnings():
        warnings.simplefilter('error', DeprecationWarning)
        mqtt = _MipsCloudMQTTClient(
            callback_api_version=CallbackAPIVersion.VERSION2,
            client_id='test', protocol=MQTTv5)
    mqtt._create_socket = lambda: broker.client_sock
    mqtt.on_connect = mips._MipsClient__on_connect
    mqtt.on_connect_fail = mips._MipsClient__on_connect_failed
    mqtt.on_disconnect = mips._MipsClient__on_disconnect
    mqtt.on_message = mips._MipsClient__on_message
    mqtt.suppress_exceptions = False  # a wrong signature fails the test
    mips._mqtt = mqtt
    assert mqtt.connect('broker.test', 1883) == 0
    assert broker.server.recv(1024)[0] == 0x10  # CONNECT
    return mips, mqtt, broker, logger


def _logged(logger: MagicMock, level: str, text: str) -> bool:
    return any(text in str(call.args[0])
               for call in getattr(logger, level).call_args_list)


@pytest.fixture(name='connected')
def fixture_connected():
    mips, mqtt, broker, logger = _mips_with_paho()
    broker.send(CONNACK_OK)
    mqtt.loop_read()
    yield mips, mqtt, broker, logger
    broker.close()


def test_connect_through_paho(connected) -> None:
    mips, mqtt, _, logger = connected
    assert mqtt.is_connected()
    assert mips._mqtt_state is True
    assert _logged(logger, 'info', 'mips connect')
    mips._internal_loop.call_soon.assert_called()  # _on_mips_connect


def test_broker_rejects_the_login() -> None:
    """A refused CONNACK is not an error log any more; its reason is kept
    for the warning about a lasting outage, and a retry is scheduled."""
    mips, mqtt, broker, logger = _mips_with_paho()
    broker.send(CONNACK_NOT_AUTHORIZED)
    mqtt.loop_read()

    assert mips._mqtt_state is False
    assert mips._mips_failure_reason == 'Not authorized'
    assert not logger.error.called
    assert mips._mips_reconnect_timer is not None
    broker.close()


def test_broker_disconnects_a_rejected_session(connected) -> None:
    mips, mqtt, broker, logger = connected
    broker.send(DISCONNECT_NOT_AUTHORIZED)
    mqtt.loop_read()

    assert mips._mqtt_state is False
    assert _logged(logger, 'warning', 'mips disconnect, Not authorized')
    assert mips._mips_failure_reason == 'Not authorized'
    assert mips._mips_reconnect_timer is not None


def test_lost_connection_is_quiet(connected) -> None:
    """paho reports a dropped socket as "Unspecified error" from the
    client side; it is retried with a debug log only."""
    mips, mqtt, broker, logger = connected
    broker.close()
    mqtt.loop_read()

    assert mips._mqtt_state is False
    assert _logged(logger, 'debug', 'mips disconnect, Unspecified error')
    assert not _logged(logger, 'info', 'mips disconnect')
    assert mips._mips_failure_reason is None
    assert mips._mips_reconnect_timer is not None


def test_own_disconnect_is_logged_as_info(connected) -> None:
    mips, mqtt, _, logger = connected
    mqtt.disconnect()
    mqtt.loop_write()  # paho reports it once the packet is sent

    assert mips._mqtt_state is False
    assert _logged(logger, 'info', 'mips disconnect, Normal disconnection')
