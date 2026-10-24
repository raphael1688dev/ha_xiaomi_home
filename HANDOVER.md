# Project Handover Document for Claude Code (and Human Teams)

Welcome to the `ha_xiaomi_home` project! This repository has undergone a massive modernization and architectural optimization in May 2026 (Version 20260527r7). 

Whether you are a human maintainer or an AI Agent (like Claude Code) taking over this project, **you must read this document first** to understand the architectural decisions, the performance optimizations, and the strict boundaries we have established.

## 📚 Essential Reading (Artifacts)
We have preserved our architectural research and decision-making history in the `docs/ai_architecture/` directory. AI Agents should index and read these files to understand the "Why" behind the code:
1. `docs/ai_architecture/xiaomi_miot_architectural_comparison.md`: Why we abandoned the Node.js wrapper for a native Python transpilation layer.
2. `docs/ai_architecture/miio_python_native_analysis.md`: The technical analysis of implementing zero-delay MIIO local control.
3. `docs/ai_architecture/miio_integration_analysis.md`: Analysis of how MIIO local control integrates with the existing Home Assistant ecosystem.

## 🚀 Key Architectural Upgrades (What you inherited)

### 1. Native Python MIIO Local Control (Zero-Delay)
We bypassed the legacy Node.js translation layer for 19 core devices (Yeelight lamps and Smartmi/Dmaker fans). These devices are now handled natively via the MIIO protocol, resulting in **zero-delay local execution** without cloud polling. 
**Rule**: Do NOT expand this whitelist arbitrarily. The zero-technical-debt promise relies on restricting this to highly stable, standard models.

### 2. $O(1)$ Data Structure Optimization
All major entity platforms (`climate.py`, `vacuum.py`, `cover.py`, `water_heater.py`, `select.py`, `humidifier.py`) have been heavily optimized:
- **No $O(N)$ scanning in runtime**: We replaced linear array scans with pre-computed $O(1)$ dictionary lookups (e.g., `_mode_reverse_map`, `_fan_level_reverse_map`).
- **List Comprehensions**: Deeply nested component loops in entity initialization (`async_setup_entry`) were flattened using Python List Comprehensions for faster boot times.

### 3. Bulletproof Entity ID Migration
The `async_migrate_unique_ids` script in `custom_components/xiaomi_home/__init__.py` handles the seamless migration of legacy entity IDs (stripping `xiaomi_home.` prefixes and handling `_control_path` / `_ip_address` isolation).
- **Self-Healing**: If HA generates a duplicate `_2` entity due to a dirty registry, this script automatically detects the collision, deletes the `_2` entity, and correctly binds the legacy entity.

## 🚫 STRICT RED LINES (DO NOT CROSS)
To prevent the codebase from regressing into a buggy, laggy state, observe these strict rules when adding features or fixing bugs:

1. **Do NOT blindly clamp sensor values**: In `sensor.py`, if a device reports a value outside its `value_range` (e.g., `temp < min_temp`), you MUST return `None` (Unavailable). Do NOT clamp it to `min_temp` or `max_temp`. Clamping destroys historical graph scaling and masks critical hardware failures.
2. **Do NOT remove the Mutex flags in Fan/Light devices**: We introduced `_is_turning_on` in `fan.py` to prevent race conditions during startup. Xiaomi devices will lag or crash if bombarded with overlapping `on=True` commands. Preserve concurrency safety.
3. **Do NOT merge `mode` and `brightness` into separate entities for Lights**: We unified them into `_effect_map` in `light.py`. Separating them causes mutual state overwrites when HA sends both commands simultaneously.
4. **Do NOT revert to $O(N)$ array searches**: Always use dictionary lookups (`_reverse_map.get(value)`) when converting between HA states and MIoT-Spec numerical values.
5. **Preserve `slugify_description=True`**: When generating unique IDs for services (like `Indicator Light`), ensure they are slugified (`indicator_light`) so they flawlessly match legacy Home Assistant registry entries.

---
*Signed, Raphael & Antigravity (May 2026)*

## October 2026 Update (v0.5.1 to v0.5.5)

Maintenance of the fork was handed over to Claude Code on 2026-10-16. Decisions and conventions since then:

### Decisions
- **English only**: `INTEGRATION_LANGUAGES` contains only `en`; the Chinese translation and i18n files are gone and `bool_trans.yaml` / `multi_lang.json` keep English only. Config entries created with another language are migrated to English in `async_setup_entry` (entity IDs are kept). Do not re-add languages without updating `test/check_rule_format.py::test_miot_lang_integrity`.
- **Upstream PRs**: open upstream pull requests are ported once reviewed here, with the author kept and credited in the changelog and release notes. Upstream has no release after v0.5.0 (2026-09-28); its open fixes up to #1838 are in v0.5.3 and v0.5.4.
- **Entity init loops stay**: the `for prop in entity_data.props` dispatch loops in cover, humidifier, media_player, vacuum, water_heater and device_tracker run once per entity. Replacing them with `get_prop()` would change last-match to first-match for duplicate property names, so they are kept on purpose.
- **Supported cores**: `hacs.json` declares Home Assistant 2026.5.0+. APIs introduced later (for example `async_get_device_by_identifier`, the HA 2026.11 `native_*` temperature properties, the `DeviceInfo` dataclass) are used through feature detection with a fallback, never unconditionally.
- **License wording**: `LICENSE.md` is Xiaomi's own license, which allows use, modification and distribution only for non-commercial use with Home Assistant. Never describe the project as Apache 2.0 or open source (the README did until v0.5.5). Any change to the license or its description needs the owner's confirmation.
- **README**: describes the code as it is on `main` and is checked against the code when it is rewritten. Its release history lists only the current minor series (v0.5.x); older versions live in `CHANGELOG.md`. Each release adds its README entry and moves the `Latest` marker.

### Additional red lines
6. **Never build an `entity_id` from `spec.platform` alone**: entities created on a different platform (dehumidifiers, binary sensors shown as sensors, debug action text entities) must pass `ha_domain`, because HA rejects mismatched domains from 2027.5.
7. **Never use `set.union()` on spec mapping sets**: `SPEC_DEVICE_TRANS_MAP` uses `frozenset`; use the `|` operator. `MIoTSpecInstance` (whole-device entities) has no `iid` / `need_filter` / `proprietary`, so check `isinstance(..., MIoTSpecService)` before touching them.
8. **Do not override `TrackerEntity.location_name` or `battery_level`**: both are removed in HA 2027.7; battery level is a separate sensor.
9. **Never log or embed raw OAuth or profile responses**: token responses carry credentials and reach logs and diagnostics through error messages; report only the response code or the server error description.
10. **Large, frequently changing attributes stay out of the recorder**: list them in `_unrecorded_attributes` (for example the untruncated `value` of long strings).
11. **MQTT disconnect codes**: `rc` is either a paho client error code or a broker `ReasonCode` with overlapping values (4 is "no connection" as a client code). Check `isinstance(rc, ReasonCode)` before comparing values. `_MipsCloudMQTTClient` overrides paho's protected `_filter_wildcard_len_check` and `_create_socket` (the latter tries every broker address, because a node that drops the TLS handshake would otherwise keep the connection down). paho is pinned to 2.1.0 by Home Assistant; when it is bumped, re-check both overrides (`tests/test_mips_failover.py` asserts the paho internals they use).
12. **Failures the integration recovers from on its own are not errors**: log retried connection attempts and subscriptions made while offline (they are replayed on connect) at DEBUG. A lasting outage gets one WARNING that names the last error, and its recovery is logged. Keep ERROR for problems that need the user.

### Workflow
- Quality gate: `python3 scripts/quality_audit.py` (Chinese character policy, compilation, `tests/`, the offline `test/` suite and `test/check_rule_format.py`).
- Branch, commit, fast-forward merge into `main`, push. Contributor PRs are cherry-picked with their authorship kept, then closed with a comment.
- Releases: tag `YYYYMMDDrNN`, title `<tag> (vX.Y.Z Mod)`, notes taken from `CHANGELOG.md`. Publishing a release triggers `release.yaml`, which uploads `xiaomi_home.zip`.
- Repository layout: `tests/` holds this fork's unit tests (run against Home Assistant), `test/` is upstream's suite and stays as is so upstream changes cherry-pick cleanly. Finished plans and analyses from earlier work live in `docs/history/`.
- Cloud MQTT outages: the broker name `<region>-ha.mqtt.io.mi.com` (`cn`, `de`, `i2`, `ru`, `sg`, `us`) resolves to several nodes. To diagnose, resolve it and run a TLS handshake against each address on port 8883 with the broker name as SNI. In October 2026 one `sg` node (`47.236.195.180`) dropped every handshake, which led to the failover in v0.5.5.
- CI is fully green since 2026-10-24 and must stay that way: pylint reports zero findings (deliberate catch-all handlers carry an inline `# pylint: disable=broad-exception-caught`, as upstream does), and the HACS license check is skipped with `ignore: license` because `LICENSE.md` is Xiaomi's custom license without an SPDX identifier.

---
*Updated by Claude Code (October 2026)*
