"""Unit tests for the user certificate checks of MIoTCert."""
import hashlib
import logging
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ed25519
from cryptography.x509.oid import NameOID

from custom_components.xiaomi_home.miot.miot_storage import (
    MIoTCert, MIoTStorage)

_UID = "123456"


def _user_cert(did: str) -> bytes:
    """A user cert as issued for the virtual device did."""
    did_hash = hashlib.sha1(did.encode("utf-8")).hexdigest()
    subject = x509.Name([
        x509.NameAttribute(NameOID.COUNTRY_NAME, "CN"),
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, "Mijia Device"),
        x509.NameAttribute(NameOID.COMMON_NAME, f"mips.{_UID}.{did_hash}.2"),
    ])
    key = ed25519.Ed25519PrivateKey.generate()
    now = datetime.now(timezone.utc)
    cert = (x509.CertificateBuilder()
            .subject_name(subject).issuer_name(subject)
            .public_key(key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now - timedelta(days=1))
            .not_valid_after(now + timedelta(days=30))
            .sign(key, algorithm=None))
    return cert.public_bytes(serialization.Encoding.PEM)


def _cert() -> MIoTCert:
    return MIoTCert(
        storage=MagicMock(spec=MIoTStorage), uid=_UID, cloud_server="cn")


@pytest.mark.asyncio
async def test_matching_user_cert_reports_remaining_time() -> None:
    cert_data = _user_cert("1001")
    remaining = await _cert().user_cert_remaining_time_async(
        cert_data=cert_data, did="1001")
    assert 29 * 86400 < remaining <= 30 * 86400
    # The client checks without a did, only the validity counts then
    assert await _cert().user_cert_remaining_time_async(
        cert_data=cert_data) == remaining


@pytest.mark.asyncio
async def test_cert_of_another_virtual_device_is_renewed_quietly(
        caplog: pytest.LogCaptureFixture) -> None:
    """A new config flow has a new virtual did; renewing is not an error."""
    with caplog.at_level(logging.INFO):
        remaining = await _cert().user_cert_remaining_time_async(
            cert_data=_user_cert("1001"), did="2002")
    assert remaining == 0
    assert not [r for r in caplog.records if r.levelno >= logging.WARNING]
    assert "another virtual device" in caplog.text
