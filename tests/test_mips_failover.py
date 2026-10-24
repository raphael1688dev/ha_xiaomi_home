"""Tests for cloud broker address failover and connect error reporting."""
# pylint: disable=protected-access
import socket
import ssl
from unittest.mock import MagicMock

import pytest
from paho.mqtt.client import Client, MQTTv5

from custom_components.xiaomi_home.miot import miot_mips
from custom_components.xiaomi_home.miot.miot_mips import (
    MipsCloudClient, _MipsCloudMQTTClient)

from .test_mips_reconnect import _client, _fire_timer, _retry

_ADDRS = ['192.0.2.1', '192.0.2.2', '192.0.2.3']


def test_paho_private_api_is_present() -> None:
    """The override relies on these paho internals (paho-mqtt 2.1)."""
    client = Client(client_id='test', protocol=MQTTv5)
    for name in ('_create_socket', '_ssl_wrap_socket', '_get_proxy'):
        assert callable(getattr(client, name))
    for name in ('_transport', '_ssl', '_host', '_port', '_connect_timeout',
                 '_bind_address', '_bind_port'):
        assert hasattr(client, name)


def _mqtt(monkeypatch, bad: set[str]) -> tuple[_MipsCloudMQTTClient, list]:
    """A client whose TLS handshake fails on the addresses in bad."""
    mqtt = _MipsCloudMQTTClient(client_id='test', protocol=MQTTv5)
    mqtt.tls_set(tls_version=ssl.PROTOCOL_TLS_CLIENT)
    mqtt._host = 'broker.test'
    mqtt._port = 8883
    tried: list[str] = []
    monkeypatch.setattr(mqtt, '_get_proxy', lambda: None)
    monkeypatch.setattr(miot_mips.socket, 'getaddrinfo', lambda *args, **kw: [
        (socket.AF_INET, socket.SOCK_STREAM, 6, '', (addr, 8883))
        for addr in _ADDRS + _ADDRS[:1]])

    def create_connection(address, **_):
        tried.append(address[0])
        sock = MagicMock()
        sock.addr = address[0]
        return sock

    def wrap(sock):
        if sock.addr in bad:
            raise ssl.SSLEOFError(8, 'EOF occurred in violation of protocol')
        return f'tls:{sock.addr}'

    monkeypatch.setattr(miot_mips.socket, 'create_connection',
                        create_connection)
    monkeypatch.setattr(mqtt, '_ssl_wrap_socket', wrap)
    return mqtt, tried


def test_tls_failure_moves_to_next_address(monkeypatch) -> None:
    """A node that drops the TLS handshake is skipped, then tried last."""
    mqtt, tried = _mqtt(monkeypatch, bad={_ADDRS[0]})
    assert mqtt._create_socket() == f'tls:{_ADDRS[1]}'
    assert tried == _ADDRS[:2]

    tried.clear()
    assert mqtt._create_socket() == f'tls:{_ADDRS[1]}'
    assert tried == [_ADDRS[1]]


def test_all_addresses_failing_raises_last_error(monkeypatch) -> None:
    """Every address is tried once before the error reaches the caller."""
    mqtt, tried = _mqtt(monkeypatch, bad=set(_ADDRS))
    with pytest.raises(ssl.SSLEOFError):
        mqtt._create_socket()
    assert tried == _ADDRS


def test_cloud_client_uses_failover_client() -> None:
    """Only the cloud broker has several addresses behind one name."""
    assert MipsCloudClient._mqtt_client_class is _MipsCloudMQTTClient


def test_outage_warning_names_the_reason() -> None:
    """The single outage warning carries the last connect error."""
    client, clock, logger = _client()
    client._mips_failure_reason = 'TLS handshake failed'
    _retry(client)
    clock.now += client.MIPS_FAILURE_WARNING_DELAY
    _fire_timer(client)
    _retry(client)
    assert logger.warning.call_count == 1
    assert logger.warning.call_args.args[1] == ' (TLS handshake failed)'


def test_sub_before_connect_is_not_an_error() -> None:
    """Topics registered while offline are subscribed on connect."""
    client, _, logger = _client()
    client._mqtt = MagicMock()
    client._mqtt.is_connected.return_value = False
    client._MipsClient__thread_check = MagicMock()
    client._mips_sub_internal('device/1/up/properties_changed/#')
    assert not logger.error.called
    assert logger.debug.called
