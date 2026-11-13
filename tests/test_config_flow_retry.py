"""A failed login in the config flow can be retried."""
# pylint: disable=protected-access
import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.xiaomi_home.config_flow import XiaomiMihomeConfigFlow


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
