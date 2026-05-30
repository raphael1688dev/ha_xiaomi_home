# Logic Flaws Audit v2 — ha_xiaomi_home(Mod)

**Audit date:** 2026-05-30
**Codebase version:** `20260530r13`
**Scope:** Post-`logic_flaws_audit.md` follow-up — verifies prior findings + surfaces new defects introduced by `implementation_plan.md` features (CtrlMode.LOCAL / poll_priority / control_path) and hotfixes r10–r13.
**Method:** Static reading of changed regions in `miot_client.py`, `miot_device.py`, `miot_lan.py`, `miot_lan_manager.py`, `miot_cloud_manager.py`, `__init__.py`, and entity platforms (`fan.py`, `light.py`, `sensor.py`).

This document catalogues **new logical defects** not covered by the v1 audit. Each finding is reproducible by reading the cited file/line.

---

## Status of v1 Audit Findings

| ID | v1 Severity | Status in r13 | Notes |
|----|-------------|---------------|-------|
| F-001 `create_task(await ...)` | Critical | ✅ Fixed | grep clean |
| F-002 `not result and 'devices' not in result` | Critical | ✅ Fixed | `or` at `miot_client.py:1487` |
| F-003 MIIO empty `props` / hardcoded `max_val=100` | Critical | ⚠️ Partial — see **N-019** | props_dict built but contains None values |
| F-004 optional service `continue` skip | High | ✅ Fixed | `skip_service` flag at `miot_device.py:609` |
| F-005 LOCAL refresh LAN-before-Gateway | High | ✅ Fixed | Gateway first at `miot_client.py:1683` |
| F-006 `remove_device_async` missing cache pop | High | ✅ Fixed | Pops all caches at `miot_client.py:930` |
| F-007 `_prop_value_map[prop]` KeyError | High | ✅ Fixed | No bare `[prop]` reads remain |
| F-008 Gateway redundant resub | Medium-High | ✅ Fixed | Dropped second clause at `miot_client.py:1041` |
| F-009 `_attr_options` unbounded growth | Medium | ✅ Fixed | Capped at 64 in `sensor.py:135` |
| F-010 `MIoTSpecAction(in_=…)` dead arg | Low-Med | ✅ Fixed | Constructor no longer takes `in_` |
| F-011 Event positional fallback | Medium | ⚠️ Unfixed | Still marked "Dirty fix", no warning log |
| F-012 cover dead-zone | Low | — | Cosmetic only |
| F-013 MIIO dict reverse linear scan | Low | ⚠️ Unfixed | Still O(N), dead `isdigit` branch retained |

---

## Severity Legend

- **Critical** — Causes crash, data loss, or silent wrong behaviour on the happy path.
- **High** — Triggers under realistic conditions (device offline, fresh boot, registry migration, MIIO setup).
- **Medium** — Subtle inconsistency or edge-case crash; users may hit it but not always.
- **Low** — Cosmetic / dead code / unbounded growth / encapsulation smell.

---

## New Critical / High Bugs

### N-001 — `get_device_control_path` does not verify the `mips_local` route exists
**Severity:** High
**File:** `custom_components/xiaomi_home/miot/miot_client.py:495-511`

```python
def get_device_control_path(self, did: str) -> str:
    if self._ctrl_mode in [CtrlMode.AUTO, CtrlMode.LOCAL]:
        device_gw = self._device_list_gateway.get(did, None)
        if (
            device_gw and device_gw.get('online', False)
            and device_gw.get('specv2_access', False)
            and 'group_id' in device_gw
        ):
            return 'Gateway'   # <-- never checks self._mips_local.get(group_id)
```

**Why it's wrong:** `set_prop_async` (`miot_client.py:651`) applies the same gateway check but then verifies `mips = self._mips_local.get(device_gw['group_id'], None)`. If `mips is None`, it logs an error and falls through to LAN. The control-path display ignores this extra condition, so it can report "Gateway" while the actual write goes via LAN or Cloud.

**Impact:** Breaks the contract of `implementation_plan.md` item 3: "現在下達指令會走哪條連線路徑". Users see a misleading attribute.

**Fix:**
```python
if (device_gw and device_gw.get('online', False)
    and device_gw.get('specv2_access', False)
    and 'group_id' in device_gw
    and self._mips_local.get(device_gw['group_id']) is not None):
    return 'Gateway'
```

---

### N-002 — `_get_from_cloud` uses truthy `if result:` and drops legal `0` / `False` / `""`
**Severity:** Critical
**File:** `custom_components/xiaomi_home/miot/miot_client.py:736-749`

```python
async def _get_from_cloud() -> Any:
    if self._ctrl_mode == CtrlMode.LOCAL:
        return None
    try:
        if self._network.network_status:
            result = await self._http.get_prop_async(...)
            if result:                     # <-- truthy check
                return result
    except Exception as err:
        ...
    return None

async def _get_from_local() -> Any:
    ...
    if res is not None:                    # <-- correct
        return res
```

`http.get_prop_async` (`miot_cloud.py:686-694`) returns `result['value']` — which can legitimately be `0`, `False`, or `""`.

**Impact:** In `cloud_first` mode, a device returning `0` (off, idle, etc.) has its cloud read discarded; the outer caller then tries local. If local is unavailable, the property stays None and HA never updates state.

**Fix:** `if result is not None:` (mirrors the local branch).

---

### N-003 — `action_async` silently returns `[]` in LOCAL mode when local routes fail
**Severity:** High
**File:** `custom_components/xiaomi_home/miot/miot_client.py:794-855`

`set_prop_async` raises `MIoTClientError(...)` at its tail (`:710`) when no path worked. `action_async` instead logs and returns:

```python
_LOGGER.error('client action failed, %s.%d.%d', did, siid, aiid)
return []
```

**Why it's wrong:** `implementation_plan.md` item 1 explicitly states LOCAL mode must "直接拋出異常,拒絕回退到 Cloud Control". `action_async` violates this contract.

**Impact:** When a user in LOCAL mode pushes a ButtonEntity action while the device is unreachable locally, HA sees a successful empty return — no error notification, no automation failure signal.

**Fix:** Replace the final `_LOGGER.error(...); return []` with `raise MIoTClientError(...)` mirroring `set_prop_async:710`.

---

### N-010 — Fan `_is_turning_on` Mutex doesn't cross `await`; `asyncio.gather` reintroduces overlapping `on=True`
**Severity:** High (violates HANDOVER red line #2)
**File:** `custom_components/xiaomi_home/fan.py:166-187`, `:197-220`

```python
async def async_turn_on(self, percentage=None, preset_mode=None, **kwargs):
    if not self.is_on and not self._is_turning_on:
        self._is_turning_on = True
        try:
            await self.set_property_async(prop=self._prop_on, value=True)
        finally:
            self._is_turning_on = False     # <-- released before gather starts

    tasks = []
    if percentage is not None:
        tasks.append(self.async_set_percentage(percentage))  # has its own turn_on path
    if preset_mode is not None:
        tasks.append(self.async_set_preset_mode(preset_mode))
    if tasks:
        await asyncio.gather(*tasks)
```

`async_set_percentage` reads `is_on` and `_is_turning_on` independently. During the gather window:
- `is_on` may still be `False` (no MQTT push back yet)
- `_is_turning_on` is already `False` (released by `finally`)

→ `async_set_percentage` enters its own turn-on block, issues a *second* `on=True`.

**Why it's wrong:** HANDOVER.md red line #2: "Xiaomi devices will lag or crash if bombarded with overlapping `on=True` commands. Preserve concurrency safety." The current mutex only guards a single statement, not the full operation.

**Fix sketch:**
- Keep `_is_turning_on=True` until **after** the gather completes, or
- After a successful `set_property_async(_prop_on, True)`, write `self._prop_value_map[self._prop_on] = True` so `self.is_on` returns True immediately to subsequent coroutines, or
- Drop the inline turn-on in `async_set_percentage` entirely and rely on the outer `async_turn_on` having already ensured power.

---

### N-019 — F-003 regression: `props_dict` may contain `None`, triggering `int(None)` inside MIIO lambdas
**Severity:** High
**Files:** `custom_components/xiaomi_home/miot/miot_device.py:1009-1023`, `custom_components/xiaomi_home/miot/miio_specs.py:93,131,170,227,296,…`

```python
# miot_device.py
props_dict = {}
for e_list in self.miot_device.entity_list.values():
    for e in e_list:
        if isinstance(e, MIoTServiceEntity):
            for p in e.entity_data.props:
                props_dict[p.name] = e.get_prop_value(p)   # may be None

# miio_specs.py (multiple lambdas, same pattern)
"set_template": lambda value, props, max_val:
    ["auto_delay_off", int(props.get("bright", 100)), value],
```

`get_prop_value` returns `self._prop_value_map.get(prop, None)`. When the entity has not yet received a push update, `bright` lands in `props_dict` as `None`.

`dict.get('bright', 100)` returns the default **only** when the key is missing — when the key exists with value `None`, it returns `None`. Then `int(None)` → `TypeError`.

**Impact:** The F-003 fix prevents the original "always 100" bug but introduces a crash path during the device's first set after boot, before any property push has arrived. Affects all MIIO models whose templates reference sibling props (bedside lamp delayed-off and similar).

**Fix:**
```python
val = e.get_prop_value(p)
if val is not None:
    props_dict[p.name] = val
```
or sanitize at the lambda boundary with `lambda value, props, max_val: ["auto_delay_off", int(props.get("bright") or 100), value]`.

---

### N-021 — `refresh_props_from_lan` globally blocks when any gateway exists; LAN-only devices never refresh
**Severity:** High
**File:** `custom_components/xiaomi_home/miot/miot_lan_manager.py:17`

```python
async def refresh_props_from_lan(self) -> bool:
    if not self.client._miot_lan.init_done or len(self.client._mips_local) > 0:
        return False
```

The second clause aborts LAN refresh whenever **any** gateway is connected — even if the device being refreshed has no gateway and is LAN-only.

Compare to `refresh_props_from_gw:62-66` which correctly checks **per-device** (`device_gw = self.client._device_list_gateway.get(did, None); if not device_gw: continue`).

**Impact:** A user with a Central Hub Gateway for some devices plus a Yeelight IP lamp (LAN-only) will see the Yeelight's state never refresh.

**Fix:** Drop the global `len(_mips_local) > 0` guard; rely on the per-device check inside the loop (mirroring the GW handler).

---

## New Medium Bugs

### N-012 — Light declares `ColorMode.BRIGHTNESS` even when brightness uses `value_list`, then crashes on the slider
**Severity:** Medium
**File:** `custom_components/xiaomi_home/light.py:96-104, 159-162, 232-237`

```python
if prop := entity_data.get_prop('brightness'):
    if prop.value_range:
        self._brightness_scale = (...)
        self._prop_brightness = prop
    elif prop.value_list:
        # Populate _effect_map for "Brightness: low/mid/high"
        ...
        self._prop_brightness = prop           # _brightness_scale stays None
        ...

# Later:
if not self._attr_supported_color_modes:
    if self._prop_brightness:                  # True even for value_list case
        self._attr_supported_color_modes.add(ColorMode.BRIGHTNESS)
        self._attr_color_mode = ColorMode.BRIGHTNESS

async def async_turn_on(self, **kwargs):
    if ATTR_BRIGHTNESS in kwargs and self._prop_brightness:
        brightness = brightness_to_value(self._brightness_scale, kwargs[ATTR_BRIGHTNESS])
        # brightness_to_value(None, 128) → TypeError
```

**Impact:** HA UI presents a brightness slider. User drags it → `TypeError`.

**Fix:** Only add `ColorMode.BRIGHTNESS` when `self._brightness_scale is not None`.

---

### N-014 — Light `mode.value_range` uses `range(min, max+step, step)` and may emit values > max
**Severity:** Medium
**File:** `custom_components/xiaomi_home/light.py:143-147`

```python
for value in range(prop.value_range.min_,
                   prop.value_range.max_ + prop.value_range.step,
                   prop.value_range.step):
    mode_list[value] = f'mode {value}'
```

If `(max - min) % step != 0`, the range includes a value above max. Example: min=0, max=10, step=3 → `[0,3,6,9,12]`. Sending `12` to a device that only supports up to 10 risks rejection or undefined behaviour.

**Fix:** Clamp inside the loop or use `range(min_, max_ + 1, step)`.

---

### N-018 — `MIoTControlPathSensor.available` follows `miot_device.online`; users see "Unavailable" instead of `Offline`
**Severity:** Medium
**File:** `custom_components/xiaomi_home/sensor.py:171-179`

```python
@property
def available(self) -> bool:
    return self.miot_device.online
```

`get_device_control_path` already returns the string `'Offline'` when no path is reachable. But the entity itself is marked unavailable when the device is offline, so HA hides the value and shows the generic "unavailable" label — defeating the diagnostic sensor's purpose.

This contradicts `implementation_plan.md` verification step: "拔除網路線後該屬性是否會隨之變化".

**Fix:**
```python
@property
def available(self) -> bool:
    return True
```

---

### N-023 — `MIoTCloudManager.refresh_props` 5xx detection relies on substring matching `', 500,'`
**Severity:** Medium
**File:** `custom_components/xiaomi_home/miot/miot_cloud_manager.py:58-65`

```python
elif any(code in err_str for code in [', 500,', ', 502,', ', 503,', ', 504,']):
```

Brittle. Any upstream error-format change (`[500]`, `:500:`, `Error 500`) silently breaks the 5xx branch. The 401 branch above uses `getattr(err, 'code', None) == MIoTErrorCode.CODE_HTTP_INVALID_ACCESS_TOKEN` — much more robust.

**Fix:** Inspect `err.code` / `err.status_code` if available; treat substring search as last-resort fallback.

---

## New Low / Encapsulation Bugs

### N-006/N-007/N-008 — Registry migration scripts have iteration-during-mutation and naming-collision risk
**Severity:** Low
**File:** `custom_components/xiaomi_home/__init__.py:41-88, 136-167`

- `async_migrate_unique_ids:158-167` removes entities mid-iteration over a registry snapshot; subsequent `async_update_entity` calls on now-stale `entry` objects can throw.
- `_async_migrate_legacy_entity_ids:76` constructs `entity_id = f"{domain}.{slugify(device_name)}_{slugify(entity_name)}"` without de-duplication. Two entities with identical names on the same device collide; the second migration logs a warning and skips.
- The double `.replace(f"{...}.", "", 1)` chain (`:141-145`) makes implicit assumptions about legacy unique_id format that don't always hold for compound prefixes.

Functional today, but every edge case adds a registry warning the user has to ignore.

---

### N-020 — `props_dict` construction is O(D × E × P) per `set_property_async` call
**Severity:** Low (perf)
**File:** `custom_components/xiaomi_home/miot/miot_device.py:1010-1014`

Every property write walks **every** entity of **every** platform of the device, reading **every** property. Aircon-class devices (50+ entities × multiple props) pay this on every command.

**Fix sketch:** Maintain a shared `_props_cache: dict[str, Any]` on `MIoTDevice`, updated inside `__on_properties_changed`, and pass it directly to `client.set_prop_async` without rebuilding.

---

### N-024 — Manager classes bypass encapsulation, directly poke `client._private`
**Severity:** Low (architectural)
**Files:** `custom_components/xiaomi_home/miot/miot_lan_manager.py:17,21,25,27,30`, `custom_components/xiaomi_home/miot/miot_cloud_manager.py:20-31`

The split-out managers reach into `self.client._miot_lan`, `_mips_local`, `_refresh_props_list`, `_network`, `_http`. Task B (God-Object split, per `docs/architecture/handover_document.md`) intended to *separate concerns*, but the result is two new classes tightly coupled to `MIoTClient`'s private internals. Refactoring `MIoTClient` will silently break them.

**Suggested fix:** Expose narrow accessor methods (`client.get_lan_devices()`, `client.consume_refresh_batch()`) so managers depend on an interface rather than field names.

---

## Summary Table

| ID | Severity | File | LoC | Effort |
|----|----------|------|-----|--------|
| N-001 | High | `miot_client.py:495-511` | 1 | Trivial (add mips check) |
| N-002 | Critical | `miot_client.py:736-749` | 2 | Trivial (truthy → `is not None`) |
| N-003 | High | `miot_client.py:794-855` | 1 | Trivial (raise instead of return []) |
| N-010 | High | `fan.py:166-220` | ~10 | Medium (mutex redesign) |
| N-019 | High | `miot_device.py:1009-1023` | ~3 | Trivial (filter None) |
| N-021 | High | `miot_lan_manager.py:17` | 1 | Trivial (drop global guard) |
| N-012 | Medium | `light.py:159-162` | 1 | Trivial (gate on `_brightness_scale`) |
| N-014 | Medium | `light.py:143-147` | 1 | Trivial (clamp range) |
| N-018 | Medium | `sensor.py:171-179` | 3 | Trivial (always available) |
| N-023 | Medium | `miot_cloud_manager.py:58-65` | 5 | Small (use err.code) |
| N-006/7/8 | Low | `__init__.py:41-167` | — | Medium |
| N-020 | Low | `miot_device.py:1010-1014` | — | Medium (cache layer) |
| N-024 | Low | `miot_lan_manager.py`, `miot_cloud_manager.py` | — | Medium (interface) |

**Recommended bundle order:**
1. **Quick wins (1-3 LoC each):** N-001, N-002, N-003, N-019, N-021, N-012, N-014, N-018 — together <30 LoC, all High/Medium severity.
2. **Fan mutex redesign:** N-010 — needs careful concurrency review.
3. **Performance/architecture:** N-020 (shared props cache), N-024 (manager interface).
4. **Migration robustness:** N-006/7/8 — accumulate registry test fixtures first.

---

*Generated by Claude Code audit pass v2, 2026-05-30.*
