"""Every error and abort key the flows use has an English string."""
# pylint: disable=protected-access
import json
import re
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from homeassistant.data_entry_flow import AbortFlow

from custom_components.xiaomi_home import config_flow, options_flow

ROOT = Path(__file__).parent.parent / "custom_components/xiaomi_home"
STRINGS = json.loads((ROOT / "translations/en.json").read_text())


def _used_keys(source: str) -> set[str]:
    patterns = [
        r"AbortFlow\(\s*(?:reason=)?'([a-z_]+)'",
        r"'base':\s*'([a-z_]+)'",
        r"MIoTConfigError\('([a-z_]+)'\)",
        r"__show_[a-z_]+_form\(\s*(?:reason=)?'([a-z_]+)'",
    ]
    return {key for pattern in patterns
            for key in re.findall(pattern, source)}


@pytest.mark.parametrize("module,section", [
    (config_flow, "config"), (options_flow, "options")])
def test_flow_keys_have_strings(module, section) -> None:
    """Missing keys showed raw identifiers, e.g. devices_storage_failed."""
    file_name = module.__name__.rsplit(".", 1)[1] + ".py"
    source = (ROOT / file_name).read_text()
    known = (set(STRINGS[section]["error"]) | set(STRINGS[section]["abort"])
             | {"already_configured"})  # translated by Home Assistant
    known_keys = module._OAUTH_ERROR_KEYS | {"oauth_failed"}
    missing = (_used_keys(source) | known_keys) - known
    assert not missing


def test_poll_priority_has_a_label() -> None:
    assert "poll_priority" in (
        STRINGS["config"]["step"]["advanced_options"]["data"])
    assert "poll_priority" in (
        STRINGS["options"]["step"]["homes_select"]["data"])


@pytest.mark.asyncio
@pytest.mark.parametrize("flow_cls", [
    config_flow.XiaomiMihomeConfigFlow, options_flow.OptionsFlowHandler])
async def test_oauth_error_keeps_the_abort_and_maps_free_text(
        flow_cls) -> None:
    """The abort used to be rebuilt from its string, losing the translation
    domain and placeholders; free-text errors showed untranslated."""
    flow = flow_cls.__new__(flow_cls)
    abort = AbortFlow("storage_error", description_placeholders={"error": "x"})
    flow._cc_flow_abort = abort
    flow._cc_config_rc = "Flow aborted: storage_error"
    with pytest.raises(AbortFlow) as raised:
        await flow.async_step_oauth_error()
    assert raised.value is abort

    flow._cc_config_rc = "oauth API error: something new"
    flow.async_show_form = MagicMock(return_value="form")
    assert await flow.async_step_oauth_error() == "form"
    assert flow.async_show_form.call_args.kwargs["errors"] == {
        "base": "oauth_failed"}
