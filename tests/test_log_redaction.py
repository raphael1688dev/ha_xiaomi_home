"""Secrets must not reach the log."""
import logging
import pathlib

from custom_components.xiaomi_home.miot.common import redact_secrets
from custom_components.xiaomi_home.miot.miot_lan import MIoTLan


def test_redact_secrets_hides_tokens_at_any_depth() -> None:
    record = {
        "uid": "1", "devices": {"did1": {
            "did": "did1", "token": "abcdef0123456789", "local_ip": "x"}},
        "auth": [{"access_token": "a", "refresh_token": "r"}],
        "empty_token": {"token": ""}}

    redacted = redact_secrets(record)

    text = repr(redacted)
    for secret in ("abcdef0123456789", "'a'", "'r'"):
        assert secret not in text
    assert redacted["devices"]["did1"]["did"] == "did1"
    assert redacted["empty_token"] == {"token": ""}
    # The original is untouched, it is still used afterwards
    assert record["devices"]["did1"]["token"] == "abcdef0123456789"


def test_lan_device_sync_logs_no_token(caplog) -> None:
    """update_devices ran on every device list sync and logged every
    device's token at INFO."""
    lan = MIoTLan.__new__(MIoTLan)
    lan._init_done = False  # pylint: disable=protected-access
    with caplog.at_level(logging.INFO):
        lan.update_devices({"did1": {"token": "abcdef0123456789",
                                     "model": "m", "ip": "1.2.3.4"}})
    assert "abcdef0123456789" not in caplog.text
    assert "did1" in caplog.text


def test_no_known_secret_logging_left() -> None:
    """The log calls that printed device records, codes or certs."""
    root = pathlib.Path(__file__).parent.parent / "custom_components/xiaomi_home"
    source = {p.name: p.read_text() for p in root.rglob("*.py")}
    assert "'webhook code: %s', data['code']" not in source["oauth.py"]
    assert "'update_user_cert_async, %s', crt_str" not in source[
        "miot_client.py"]
    assert "'get_homeinfos response: %s', self._cc_home_info)" not in source[
        "config_flow.py"]
