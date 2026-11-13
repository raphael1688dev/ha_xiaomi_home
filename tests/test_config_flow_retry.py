"""A failed login in the config flow can be retried."""
# pylint: disable=protected-access
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.xiaomi_home.config_flow import XiaomiMihomeConfigFlow
from custom_components.xiaomi_home.miot.const import DOMAIN
from custom_components.xiaomi_home.options_flow import OptionsFlowHandler


async def _failed_task() -> asyncio.Task:
    async def fail() -> None:
        raise RuntimeError("oauth_code_error")
    task = asyncio.get_running_loop().create_task(fail())
    with pytest.raises(RuntimeError):
        await task
    return task


@pytest.mark.asyncio
async def test_failed_login_starts_the_next_attempt_over() -> None:
    """The failed task and OAuth client were kept, so "next" on the error
    form found the same failed task and showed the same error again."""
    flow = XiaomiMihomeConfigFlow()
    flow.hass = MagicMock()
    flow._cc_task_oauth = await _failed_task()
    oauth = MagicMock()
    oauth.deinit_async = AsyncMock()
    flow._miot_oauth = oauth
    flow.async_show_progress_done = MagicMock(return_value="done")

    assert await flow.async_step_oauth() == "done"

    flow.async_show_progress_done.assert_called_once_with(
        next_step_id="oauth_error")
    assert flow._cc_config_rc == "oauth_code_error"
    assert flow._cc_task_oauth is None
    assert flow._miot_oauth is None
    oauth.deinit_async.assert_awaited_once()


@pytest.mark.asyncio
async def test_setup_error_sets_the_error_text() -> None:
    """Without it, oauth_error called the oauth step again, in a loop."""
    flow = XiaomiMihomeConfigFlow()
    flow.hass = MagicMock()
    flow.hass.data = {}  # the virtual device's data is missing: KeyError
    flow._miot_oauth = None
    flow._virtual_did = "123"
    flow.async_show_progress_done = MagicMock(return_value="done")

    await flow.async_step_oauth()

    assert flow._cc_config_rc


@pytest.mark.parametrize("flow_cls", [
    XiaomiMihomeConfigFlow, OptionsFlowHandler])
def test_ended_flow_unregisters_its_webhook(flow_cls) -> None:
    """A flow that was closed or aborted left the OAuth webhook registered
    and its data, with a pending future, in hass.data."""
    flow = object.__new__(flow_cls)
    flow._virtual_did = "4242"
    flow.hass = MagicMock()
    fut = MagicMock()
    fut.done.return_value = False
    flow.hass.data = {DOMAIN: {"4242": {"fut_oauth_code": fut},
                               "other": {}}}
    with patch(f"{flow_cls.__module__}.webhook_async_unregister") as unreg:
        flow.async_remove()

    unreg.assert_called_once_with(flow.hass, webhook_id="4242")
    assert flow.hass.data[DOMAIN] == {"other": {}}
    fut.cancel.assert_called_once()


def test_flow_without_virtual_device_has_nothing_to_remove() -> None:
    flow = object.__new__(XiaomiMihomeConfigFlow)
    flow._virtual_did = ""
    flow.hass = MagicMock()
    with patch("custom_components.xiaomi_home.config_flow."
               "webhook_async_unregister") as unreg:
        flow.async_remove()
    unreg.assert_not_called()
