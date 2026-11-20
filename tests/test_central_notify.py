"""Central hub gateway connection notifications (XiaoMi/ha_xiaomi_home#1868)."""
# pylint: disable=protected-access
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from custom_components.xiaomi_home.miot import miot_client as client_module
from custom_components.xiaomi_home.miot.miot_client import MIoTClient


def _client():
    with patch.object(MIoTClient, "__init__", lambda self, *a, **k: None):
        client = MIoTClient()  # pylint: disable=no-value-for-parameter
    client._uid, client._cloud_server = "u1", "cn"
    client._entry_data = {"nick_name": "nick"}
    client._i18n = SimpleNamespace(
        translate_str=lambda key, replace=None: key)
    client._persistence_notify = MagicMock()
    client._central_disconnect_timers = {}
    client._central_disconnect_notified = set()
    client._mips_local = {}
    timers = []

    def call_later(delay, callback, *args):
        timer = MagicMock()
        timers.append((delay, callback, args, timer))
        return timer

    client._main_loop = SimpleNamespace(call_later=call_later)
    return client, timers


def _changed(client, group: str, connected: bool) -> None:
    client._MIoTClient__on_central_state_changed(group, connected)


def _shown(client) -> list:
    """Notifications created (a title), as opposed to dismissed (None)."""
    return [c for c in client._persistence_notify.call_args_list
            if c.args[1] is not None]


def test_brief_reconnect_shows_nothing() -> None:
    """Each connect and disconnect used to create a persistent notification,
    so a short reconnect left a "Connected" notification behind."""
    client, timers = _client()
    _changed(client, "g1", False)
    assert timers[0][0] == client_module.CENTRAL_DISCONNECT_NOTIFY_DELAY
    _changed(client, "g1", True)

    timers[0][3].cancel.assert_called_once()
    assert not _shown(client)
    client._persistence_notify.assert_called_once()  # the dismissal


def test_lasting_disconnect_is_shown_once_and_dismissed_on_reconnect() -> None:
    client, timers = _client()
    client._mips_local = {"g1": SimpleNamespace(mips_state=False)}
    _changed(client, "g1", False)
    _changed(client, "g1", False)  # repeated callbacks start one timer
    assert len(timers) == 1

    _, callback, args, _ = timers[0]
    callback(*args)
    assert len(_shown(client)) == 1
    _changed(client, "g1", False)  # already shown: no new timer
    assert len(timers) == 1

    _changed(client, "g1", True)
    assert client._persistence_notify.call_args.args[1:] == (None, None)
    assert not client._central_disconnect_notified


def test_gateway_back_when_the_timer_fires_shows_nothing() -> None:
    client, timers = _client()
    client._mips_local = {"g1": SimpleNamespace(mips_state=True)}
    _changed(client, "g1", False)
    _, callback, args, _ = timers[0]
    callback(*args)
    assert not _shown(client)


def test_notification_stays_while_another_gateway_is_down() -> None:
    client, timers = _client()
    client._mips_local = {"g1": SimpleNamespace(mips_state=False)}
    _changed(client, "g1", False)
    _, callback, args, _ = timers[0]
    callback(*args)
    client._persistence_notify.reset_mock()

    _changed(client, "g2", True)
    client._persistence_notify.assert_not_called()
