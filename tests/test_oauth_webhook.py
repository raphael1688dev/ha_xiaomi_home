"""The OAuth callback webhook keeps the code and state out of the log and
the result page (from XiaoMi/ha_xiaomi_home#1873)."""
import asyncio
import logging
from types import SimpleNamespace

import pytest

from custom_components.xiaomi_home.miot.const import DOMAIN
from custom_components.xiaomi_home.oauth import _handle_oauth_webhook

WEBHOOK_ID = "hook"
EXPECTED_STATE = "expected-state-0123456789"


def _hass(i18n=None):
    future = asyncio.get_running_loop().create_future()
    return SimpleNamespace(data={DOMAIN: {WEBHOOK_ID: {
        "oauth_state": EXPECTED_STATE,
        "fut_oauth_code": future,
        "i18n": i18n,
    }}}), future


def _request(**query):
    return SimpleNamespace(query=query)


@pytest.mark.asyncio
async def test_state_mismatch_reveals_neither_state(caplog) -> None:
    """The error named both states. It is logged with its traceback at
    ERROR, and shown on the page when there is no translation. The expected
    state stays valid after a mismatch."""
    hass, future = _hass()
    with caplog.at_level(logging.DEBUG):
        response = await _handle_oauth_webhook(
            hass, WEBHOOK_ID,
            _request(code="the-code", state="<b>attacker-state</b>"))

    page = response.text
    for value in (EXPECTED_STATE, "attacker-state", "the-code"):
        assert value not in caplog.text
        assert value not in page
    assert not future.done()
    # Still waiting for the real callback
    assert hass.data[DOMAIN][WEBHOOK_ID]["oauth_state"] == EXPECTED_STATE


@pytest.mark.asyncio
async def test_valid_callback_delivers_the_code_without_logging_it(
        caplog) -> None:
    hass, future = _hass()
    with caplog.at_level(logging.DEBUG):
        await _handle_oauth_webhook(
            hass, WEBHOOK_ID, _request(code="the-code", state=EXPECTED_STATE))

    assert future.result() == "the-code"
    assert "the-code" not in caplog.text
    assert EXPECTED_STATE not in caplog.text
    assert "oauth_state" not in hass.data[DOMAIN][WEBHOOK_ID]


@pytest.mark.asyncio
async def test_missing_code_does_not_complete_the_flow() -> None:
    hass, future = _hass()
    await _handle_oauth_webhook(
        hass, WEBHOOK_ID, _request(state=EXPECTED_STATE))
    assert not future.done()
