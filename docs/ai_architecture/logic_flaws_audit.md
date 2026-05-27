# Logic Flaws Audit — ha_xiaomi_home(Mod)

**Audit date:** 2026-05-27
**Codebase version:** `20260527r7`
**Scope:** `custom_components/xiaomi_home/` (entry, miot/, entity platforms)
**Method:** Static reading of all 17,500+ Python LOC + cross-reference with `HANDOVER.md` red lines.

This document catalogues **logical bugs** (incorrect behaviour, latent crashes, contract violations) — not style issues or optimization opportunities. Each finding is reproducible by reading the cited file/line.

---

## Severity Legend

- **Critical** — Causes crash, data loss, or silent wrong behaviour on the happy path.
- **High** — Triggers under realistic conditions (device offline, fresh boot, registry migration).
- **Medium** — Subtle inconsistency or edge-case crash; users may hit it but not always.
- **Low** — Cosmetic / dead code / unbounded growth that takes a long time to manifest.

---

## Critical Bugs

### F-001 — `create_task(await ...)` double-await crashes offline-handling path
**Severity:** Critical
**Files:** `custom_components/xiaomi_home/miot/miot_client.py:685`, `:830`

```python
# Line 685 (inside set_prop_async error branch)
if rc in [-704010000, -704042011]:
    _LOGGER.error('device may be removed or offline, %s', did)
    self._main_loop.create_task(
        await self.__refresh_cloud_device_with_dids_async(  # <-- await
            dids=[did]))                                    # <-- create_task wraps None
raise MIoTClientError(...)
```

**Why it's wrong:** `await coro()` evaluates the coroutine and returns its result (`None` here). `create_task(None)` then raises `TypeError: a coroutine was expected, got None`.

**Impact:** Whenever Xiaomi cloud reports a device as removed/offline (`rc == -704010000` or `-704042011`) during `set_prop_async` or `action_async`, the integration raises `TypeError` *before* reaching the proper `raise MIoTClientError`. User sees a noisy stack trace instead of a clean error notification.

**Fix:** Drop the `await`:
```python
self._main_loop.create_task(
    self.__refresh_cloud_device_with_dids_async(dids=[did]))
```

---

### F-002 — `__refresh_cloud_devices_async` cloud-error guard crashes on `result is None`
**Severity:** Critical
**File:** `custom_components/xiaomi_home/miot/miot_client.py:1465`

```python
if not result and 'devices' not in result:
    self.__show_client_error_notify(...)
    return
```

**Why it's wrong:** When `result is None`, `not result` is `True`, then Python evaluates `'devices' not in None` — which raises `TypeError: argument of type 'NoneType' is not iterable`.

**Impact:** Any time the cloud HTTP call returns `None` (transient network failure, timeout), the refresh handler crashes instead of showing the user-facing notification. The retry timer is never re-scheduled because the function never returns cleanly.

**Fix:** Replace `and` with `or` so the second clause short-circuits:
```python
if not result or 'devices' not in result:
```

---

### F-003 — MIIO `set_template` lambdas always receive empty `props` and hard-coded `max_val=100`
**Severity:** Critical
**File:** `custom_components/xiaomi_home/miot/miot_lan.py:906`

```python
new_params = prop_cfg['set_template'](value, {}, 100)
# passing empty props and default max 100 for now
```

**Why it's wrong:** Lambdas in `miio_specs.py` are designed to read the device's other current properties via `props.get('bright', 100)`. Passing `{}` makes every reference to `props.get(...)` fall through to the default value.

**Concrete victim:**
```python
# yeelink.light.bslamp1, prop.2.102
"set_template": lambda value, props, max_val:
    ["auto_delay_off", int(props.get("bright", 100)), value],
```
This is supposed to schedule a delayed-off at the *current* brightness. With `props={}`, it always schedules at brightness=100, regardless of the user's actual setting.

**Impact:** Silent wrong behaviour on at least the `yeelink.light.bslamp*` delayed-off feature. Other MIIO models may be similarly affected — any lambda that references `props` is currently broken.

**Fix sketch:** Cache the last-known properties on `_MIoTLanDevice` (updated on every successful `get_prop`/property change push), then pass that cache instead of `{}`. The `max_val` should come from the MIoT spec's value-range, not be hard-coded.

---

### F-004 — `parse_miot_device_entity` lets non-conforming optional services slip through
**Severity:** High (Critical for spec correctness)
**File:** `custom_components/xiaomi_home/miot/miot_device.py:579-583`

```python
elif service.name in optional_services:
    # ... required-properties / required-actions superset checks (use `continue` to skip service) ...
    for prop in service.properties:
        if prop.name in required_properties:
            if not set(prop.access).issuperset(required_properties[prop.name]):
                continue  # <-- skips this prop only, NOT the service
```

**Why it's wrong:** The matching block for **required services** (lines 549-553) uses `return None` to reject the whole device when a required property lacks the required access. The **optional service** mirror block uses `continue`, which exits only the inner `for prop` loop. The service is then still appended to the entity.

**Impact:** Optional services with incomplete access fields are accepted as if they satisfied the spec. The resulting entity may attempt to read/write properties the device refuses, producing runtime errors instead of being filtered at parse time.

**Fix:** Track rejection with a flag and apply it after the inner loop:
```python
elif service.name in optional_services:
    # ...
    skip_service = False
    for prop in service.properties:
        if prop.name in required_properties:
            if not set(prop.access).issuperset(required_properties[prop.name]):
                skip_service = True
                break
    if skip_service:
        continue  # now skips the outer `for service` loop
```

---

## High-Severity Bugs

### F-005 — LOCAL-mode property refresh tries LAN before Gateway, contradicting all other code paths
**Severity:** High
**File:** `custom_components/xiaomi_home/miot/miot_client.py:1788-1796`

```python
if self._ctrl_mode == CtrlMode.LOCAL:
    handlers = [self.__refresh_props_from_lan, self.__refresh_props_from_gw]
elif self._ctrl_mode == CtrlMode.CLOUD:
    handlers = [self.__refresh_props_from_cloud]
else:  # AUTO
    if self._entry_data.get('poll_priority', 'cloud_first') == 'local_first':
        handlers = [self.__refresh_props_from_lan, self.__refresh_props_from_gw, ...]
```

**Why it's wrong:**
- `get_device_control_path()` (line 487): Gateway → LAN → Cloud
- `set_prop_async()` (line 626): Gateway → LAN → Cloud
- `get_prop_async()` local branch (line 736): Gateway → LAN
- `HANDOVER.md` & `CLAUDE.md`: "Central gateway local control takes priority over LAN control"

But `__refresh_props_handler` LOCAL mode puts LAN **first**. Same for AUTO/`local_first`.

**Impact:** When the user has both a Central Hub Gateway and a LAN-capable device, reads via `request_refresh_prop` go to LAN while reads/writes via `get_prop_async`/`set_prop_async` go to Gateway. State updates may lag or disagree with set commands.

**Fix:** Swap the order so Gateway is tried first:
```python
if self._ctrl_mode == CtrlMode.LOCAL:
    handlers = [self.__refresh_props_from_gw, self.__refresh_props_from_lan]
# AUTO local_first:
handlers = [self.__refresh_props_from_gw, self.__refresh_props_from_lan, self.__refresh_props_from_cloud]
```

---

### F-006 — `remove_device_async` does not actually remove the device from cache
**Severity:** High
**File:** `custom_components/xiaomi_home/miot/miot_client.py:909-922`

```python
async def remove_device_async(self, did: str) -> None:
    if did not in self._device_list_cache:
        return
    sub_from = self._sub_source_list.pop(did, None)
    if sub_from:
        self.__unsub_from(sub_from, did)
    # Storage
    await self._storage.save_async(
        domain='miot_devices',
        name=f'{self._uid}_{self._cloud_server}',
        data=self._device_list_cache)  # <-- writes back including the "removed" device
    self.__request_show_devices_changed_notify()
```

**Why it's wrong:** The function name and call-site (`async_remove_config_entry_device` in `__init__.py:334`) imply removal. But it only unsubscribes — the device stays in `_device_list_cache` and is persisted again to storage. On next HA restart, the device reappears.

**Impact:** Users who delete a device through HA's UI find it returns after restart. The subscription is cancelled mid-session, but the cache resurrects it.

**Fix:** Pop from cache before saving:
```python
self._device_list_cache.pop(did, None)
self._device_list_cloud.pop(did, None)
self._device_list_gateway.pop(did, None)
self._device_list_lan.pop(did, None)
await self._storage.save_async(...)
```

---

### F-007 — `MIoTServiceEntity.get_property_async` raises `KeyError` on first read
**Severity:** High
**File:** `custom_components/xiaomi_home/miot/miot_device.py:1013`

```python
async def get_property_async(self, prop: MIoTSpecProperty) -> Any:
    ...
    value: Any = prop.value_format(
        await self.miot_device.miot_client.get_prop_async(
            did=self.miot_device.did, siid=prop.service.iid, piid=prop.iid))
    value = prop.eval_expr(value)
    result = prop.value_precision(value)
    if result != self._prop_value_map[prop]:  # <-- KeyError if first access
        self._prop_value_map[prop] = result
        self.async_write_ha_state()
    return result
```

**Why it's wrong:** `_prop_value_map` is populated lazily — either by `__on_properties_changed` (push notification) or `set_property_async`. If a caller invokes `get_property_async` before either fires (e.g., on a freshly-added entity that hasn't received its first MQTT update), `self._prop_value_map[prop]` raises `KeyError`.

**Impact:** Any feature that calls `get_property_async` before a push notification has arrived crashes. This is rare in the production hot path (HA mostly relies on push) but breaks the API contract — `get_property_async` should always work for readable properties.

**Fix:**
```python
if result != self._prop_value_map.get(prop):
    self._prop_value_map[prop] = result
    self.async_write_ha_state()
```

---

### F-008 — `__update_device_msg_sub` re-subscribes gateway sources unnecessarily
**Severity:** Medium-High
**File:** `custom_components/xiaomi_home/miot/miot_client.py:1021`

```python
if (from_new == from_old) and (from_new == 'cloud' or from_new == 'lan'):
    return
```

**Why it's wrong:** The intent is "no need to update if source hasn't changed." But the second clause restricts the short-circuit to `cloud` and `lan`. When `from_new == from_old == <gateway-group-id>`, the function falls through to `__unsub_from` then `__sub_from` on the *same* gateway, doing redundant work.

**Impact:** Every device-state notification on a gateway-routed device triggers an unsubscribe/resubscribe cycle to the same gateway. Wastes CPU and MQTT round-trips; may temporarily lose messages between unsub and re-sub.

**Fix:** Drop the source filter:
```python
if from_new == from_old:
    return
```
(Unless the gateway re-subscription is intentional — in which case it deserves a comment explaining why.)

---

## Medium-Severity Bugs

### F-009 — `Sensor._attr_options` grows unboundedly on undocumented device values
**Severity:** Medium
**File:** `custom_components/xiaomi_home/sensor.py:134-141`

```python
_opts = self._attr_options or []
if str_val not in _opts:
    self._attr_options = list(_opts) + [str_val]
    _LOGGER.debug(...)
```

**Why it's wrong:** Every time the device reports a value outside its `value_list`, `_attr_options` grows by one. A misbehaving device (flapping firmware, transient garbage) can balloon this list, slowing HA's enum validation and bloating state attributes.

**Impact:** Memory leak with a long tail. Each Sensor instance keeps its own list, so a fleet of misbehaving devices multiplies the cost.

**Fix:** Either cap the list (`if len(_opts) > 64: ...`) or keep a `set` of "seen extras" and only add to `_attr_options` if not already present (current `not in` check is O(N); a `set` would also fix that).

---

### F-010 — `MIoTSpecAction.__init__` `in_` parameter is dead — always overwritten
**Severity:** Low-Medium (cosmetic but confusing)
**Files:** `custom_components/xiaomi_home/miot/miot_spec.py:712`, `:1513`

```python
spec_action = MIoTSpecAction(spec=action,
                             service=spec_service,
                             in_=action['in'])         # <-- piid list
spec_action.in_ = [prop_map[piid] for piid in action['in'] if piid in prop_map]
                                                      # <-- overwritten with MIoTSpecProperty list
```

**Why it's wrong:** Constructor receives `list[int]` (piids from raw spec), then the very next line replaces it with `list[MIoTSpecProperty]`. The type passed in doesn't match the declared `Optional[list[MIoTSpecProperty]]` parameter, but it doesn't matter because it never survives.

**Impact:** Dead code. Reader confusion. Same pattern appears in both `MIoTSpecInstance.load` (cached path) and `MIoTSpecParser.__parse` (fresh parse path).

**Fix:** Don't pass `in_` to the constructor:
```python
spec_action = MIoTSpecAction(spec=action, service=spec_service)
spec_action.in_ = [prop_map[piid] for piid in action['in'] if piid in prop_map]
```

---

### F-011 — Event multi-argument fallback assumes positional order matches `spec.argument`
**Severity:** Medium
**File:** `custom_components/xiaomi_home/miot/miot_device.py:1346-1355`

```python
elif (
    isinstance(item['value'], list)
    and len(item['value']) == len(self.spec.argument)
):
    # Dirty fix for cloud multi-arguments
    trans_arg = {
        prop.description_trans: item['value'][index]
        for index, prop in enumerate(self.spec.argument)
    }
    break
```

**Why it's wrong:** When the cloud delivers event arguments without `piid` keys, the code falls back to positional matching. There is no guarantee the cloud's array order matches `self.spec.argument`'s order — the latter comes from the device spec, the former from whatever the cloud serialises.

**Impact:** Event attributes may be associated with the wrong names when this fallback triggers. Severity depends on whether the affected events are actually used for automation.

**Mitigation:** Author flagged this as "Dirty fix" — at minimum, log a warning so users can detect mismatches. A real fix needs spec-level documentation of the cloud's serialisation order.

---

## Low-Severity / Cosmetic

### F-012 — `cover.py` dead-zone snap boundaries inclusive both sides
**Severity:** Low
**File:** `custom_components/xiaomi_home/cover.py:249-252`

```python
if pos <= self._cover_dead_zone_width:
    pos = 0
elif pos >= (100 - self._cover_dead_zone_width):
    pos = 100
```

**Observation:** With `dead_zone_width = 0`, the condition `pos <= 0` snaps to 0 and `pos >= 100` snaps to 100 — correct boundary behaviour but reads as if `width=0` still has a snap zone. Pure readability.

**Suggested fix:** None required. Could add a comment clarifying that `<=` / `>=` are intentional.

---

### F-013 — MIIO get-prop dict reverse mapping does linear scan + dead `isdigit()` branch
**Severity:** Low
**File:** `custom_components/xiaomi_home/miot/miot_lan.py:866-874`

```python
if 'dict' in prop_cfg:
    for k, v in prop_cfg['dict'].items():
        if str(v) == str(val):
            if k.isdigit():
                val = int(k)
            else:
                val = k
            break
```

**Observation:** Every read scans the `dict` linearly. Also, `k.isdigit()` checks if the *key* is numeric — but in the current `miio_specs.py` whitelist, all keys are descriptive names (`'nature'`, `'normal'`). Branch is unreachable until/unless a new model is added with numeric keys.

**Suggested fix:** Pre-build a reverse map at module load. Drop the `isdigit` branch unless future models require it.

---

## Summary Table

| ID | Severity | File | LoC | Effort |
|----|----------|------|-----|--------|
| F-001 | Critical | `miot_client.py:685, :830` | 2 | Trivial (remove `await`) |
| F-002 | Critical | `miot_client.py:1465` | 1 | Trivial (`and` → `or`) |
| F-003 | Critical | `miot_lan.py:906` | ~30 | Medium (add props cache) |
| F-004 | High | `miot_device.py:579-583` | ~5 | Small (track skip flag) |
| F-005 | High | `miot_client.py:1788-1796` | 4 | Trivial (reorder list) |
| F-006 | High | `miot_client.py:909-922` | 4 | Small (add `.pop`) |
| F-007 | High | `miot_device.py:1013` | 1 | Trivial (`[]` → `.get()`) |
| F-008 | Medium-High | `miot_client.py:1021` | 1 | Trivial (drop second clause) |
| F-009 | Medium | `sensor.py:134-141` | ~5 | Small (cap + set) |
| F-010 | Low-Medium | `miot_spec.py:712, 1513` | 2 | Trivial (drop arg) |
| F-011 | Medium | `miot_device.py:1346-1355` | — | Needs spec investigation |
| F-012 | Low | `cover.py:249-252` | 0 | Comment only |
| F-013 | Low | `miot_lan.py:866-874` | ~5 | Small (precompute) |

**Recommended next action:** Bundle F-001, F-002, F-007, F-008 into a single low-risk fix commit (5 lines changed). F-003, F-004, F-005, F-006 each warrant a dedicated commit with regression tests.

---

*Generated by Claude Code audit pass, 2026-05-27.*
