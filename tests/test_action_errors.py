"""Failed actions reach the caller as Home Assistant errors."""
# pylint: disable=protected-access
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, PropertyMock, patch

import pytest
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError

from custom_components.xiaomi_home.miot.miot_error import MIoTClientError
from custom_components.xiaomi_home.notify import Notify


def _notify() -> Notify:
    entity = object.__new__(Notify)
    entity.spec = SimpleNamespace(in_=[SimpleNamespace(
        iid=1, format_=str, description_trans="Text")])
    entity.entity_id = "notify.speaker_play_text"
    entity.action_async = AsyncMock()
    return entity


@pytest.mark.asyncio
@pytest.mark.parametrize("message", [
    "[unclosed", "just text", "['a', 'b']"])
async def test_notify_reports_bad_input(message: str) -> None:
    """It used to log and return, so the call looked successful."""
    entity = _notify()
    with patch.object(Notify, "name", new_callable=PropertyMock,
                      return_value="Speaker"), \
            pytest.raises(ServiceValidationError):
        await entity.async_send_message(message)
    entity.action_async.assert_not_awaited()


@pytest.mark.asyncio
async def test_notify_sends_valid_input() -> None:
    entity = _notify()
    await entity.async_send_message("['hello']")
    entity.action_async.assert_awaited_once_with(
        in_list=[{"piid": 1, "value": "hello"}])


@pytest.mark.asyncio
async def test_failed_device_write_is_a_home_assistant_error() -> None:
    """RuntimeError showed "Unknown error" and a stack trace in the log."""
    from .test_entity_poll import _lan_device, _switch  # pylint: disable=import-outside-toplevel
    miot_device, _ = _lan_device()
    miot_device.miot_client.set_prop_async = AsyncMock(
        side_effect=MIoTClientError("device offline"))
    entity = _switch(miot_device)
    entity.async_write_ha_state = MagicMock()
    with pytest.raises(HomeAssistantError, match="device offline"):
        await entity.async_turn_on()
