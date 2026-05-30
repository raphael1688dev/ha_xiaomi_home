# Code Optimization Audit — ha_xiaomi_home(Mod)

**Audit date:** 2026-05-30
**Codebase version:** `20260530r13`
**Scope:** Performance, code volume, and architectural review separate from the bug audits (`logic_flaws_audit.md`, `logic_flaws_audit_v2.md`). Focuses on hot-path runtime cost, startup time, memory churn, DRY violations, and encapsulation smells.
**Method:** Static reading of `common.py`, `miot_device.py`, `miot_spec.py`, `miot_mips.py`, `miot_storage.py`, `miot_client.py`, `miot_lan_manager.py`, `miot_cloud_manager.py`, `__init__.py`, and entity platforms.

This document catalogues **optimization opportunities** — code that works correctly today but pays a needless cost at runtime, startup, or maintenance time.

---

## Categories

- **A. Hot Path / Runtime Performance** — per-message / per-state-change cost paid on every HA tick.
- **B. Startup / Initialization** — paid once per HA restart per ConfigEntry.
- **C. Memory / Allocation** — needless object churn or duplicate caches.
- **D. Code Volume / DRY** — copy-pasted patterns that bloat the codebase and create drift risk.
- **E. Architecture / Encapsulation** — coupling that increases the cost of future refactors.

---

## A. Hot Path / Runtime Performance

### O-001 — `MIoTHttp.get_async` / `post_async` builds a fresh `aiohttp.ClientSession` per call when no session is passed
**File:** `custom_components/xiaomi_home/miot/common.py:147-208`

```python
async def get_async(url, params=None, headers=None, loop=None, session=None):
    if session:
        async with session.get(...) as response:
            ...
    else:
        async with aiohttp.ClientSession(headers=headers) as session_internal:
            async with session_internal.get(...) as response:
                ...
```

No keep-alive, no connection pooling on the fallback path. Contradicts `ha_compliance_analysis.md` §1 ("Resolved" — replace manual instantiation with `async_get_clientsession(hass)`).

**Improvement:** Make the `session` argument mandatory (callers already have HA's managed session), or hold a module-level singleton seeded from `async_setup`. Remove the synchronous `urlopen` siblings while you're there (see O-021).

---

### O-002 — `MIoTDevice.gen_*_unique_id` recomputes the shared prefix on every call
**File:** `custom_components/xiaomi_home/miot/miot_device.py:452-491`

```python
def gen_prop_unique_id(self, spec_name, siid, piid):
    return (
        f'{self._model_strs[0][:9]}_{self.did_tag}_'
        f'{self._model_strs[-1][:20]}_{slugify_name(spec_name)}_p_{siid}_{piid}')
```

The first three fragments are fixed per device but rebuilt on every call (and `did_tag` itself calls `slugify_did(...)` every access). During setup this fires per service / per property / per event / per action — and again during migration.

**Improvement:**
```python
@cached_property
def _uid_prefix(self) -> str:
    return f'{self._model_strs[0][:9]}_{self.did_tag}_{self._model_strs[-1][:20]}'
```
All five `gen_*` methods become one-line concatenations.

---

### O-003 — `MIoTDevice.device_info` allocates a new `DeviceInfo` on every property read
**File:** `custom_components/xiaomi_home/miot/miot_device.py:417-430`

`DeviceInfo(...)` is content-stable for the device's lifetime but HA reads it multiple times across entity lifecycle.

**Improvement:** Build once in `__init__` (or `@cached_property`) and return the same object.

---

### O-004 — `MIoTSpecValueList.descriptions / values / names` rebuild a fresh list per access
**File:** `custom_components/xiaomi_home/miot/miot_spec.py:118-128`

```python
@property
def descriptions(self) -> list[str]:
    return [item.description for item in self.items]
```

`items` is frozen after `load()`. Called by e.g. `sensor.py:85` `self._attr_options = spec.value_list.descriptions`.

**Improvement:** Materialise once in `load()` as `self._descriptions: tuple[str, ...]` and let the property return it directly.

---

### O-005 — `props_dict` build walks every entity × every prop of the device per `set_property_async`
**File:** `custom_components/xiaomi_home/miot/miot_device.py:1010-1014`
*(Performance facet of bug **N-020**; documented separately here because the fix is shared.)*

```python
for e_list in self.miot_device.entity_list.values():
    for e in e_list:
        if isinstance(e, MIoTServiceEntity):
            for p in e.entity_data.props:
                props_dict[p.name] = e.get_prop_value(p)
```

For a 50+-entity device (e.g. air-conditioner), every single property write does O(D×E×P) dictionary writes — purely to feed the MIIO lambda its sibling context.

**Improvement:** Maintain a shared `MIoTDevice._props_cache: dict[str, Any]` updated inside `__on_properties_changed`; `set_property_async` reads it directly. Reduces the cost from O(D×E×P) to O(1).

---

### O-006 — `MIoTDevice.connect_type` / `local_ip` allocate a throwaway `{}` per access
**File:** `custom_components/xiaomi_home/miot/miot_device.py:437-445`

```python
@property
def connect_type(self) -> int:
    return self.miot_client.device_list.get(self.did, {}).get('connect_type', -1)
```

`get(self.did, {})` creates a new empty dict on every miss only to throw it away. Polled by diagnostic sensors.

**Improvement:** Cache `connect_type` on the `MIoTDevice` instance at init; refresh on cloud-device-refresh callback. Or at minimum:
```python
return (self.miot_client.device_list.get(self.did) or {}).get('connect_type', -1)
```

---

### O-007 — `MIoTEntityData.get_prop/get_event/get_action` use `hasattr`-guarded lazy maps
**File:** `custom_components/xiaomi_home/miot/miot_device.py:194-225`

```python
def get_prop(self, prop_name, service_name=None):
    if not hasattr(self, '_props_map'):
        self._props_map = {}
        for prop in self.props:
            ...
```

Three near-identical methods. `hasattr` is `try/except AttributeError` under the hood. Also, the secondary `if prop.name not in self._props_map` silently favours first-seen on name collisions.

**Improvement:** Initialise `_props_map: dict | None = None` in `__init__`; finalise after parsing completes. Or change `props` from `set` to `dict[str, MIoTSpecProperty]` and let `add()` maintain the index naturally.

---

### O-008 — Entity property getters dispatch through `get_prop_value` dict lookup on every read
**Files:** `light.py:168-198`, `fan.py:245-297`, `climate.py`, `vacuum.py`, etc.

```python
@property
def is_on(self) -> Optional[bool]:
    value_on = self.get_prop_value(prop=self._prop_on)
    if value_on is None:
        return None
    return bool(value_on)
```

HA calls `is_on`, `percentage`, `current_temperature`, `effect`, etc. routinely. Each goes through `self._prop_value_map.get(prop)` — fine for cold path but multiplied across every entity, every refresh tick.

**Improvement:** Push the conversion into `__on_properties_changed`: when the device pushes a new value, compute `self._attr_is_on = bool(...)`, `self._attr_percentage = ...`. Property getters then return cached `_attr_*` fields directly. Trades a small write overhead on push for many fewer reads.

---

## B. Startup / Initialization

### O-009 — `_SpecFilter` / `_SpecBoolTranslation` / `_SpecAdd` / `_SpecModify` reload YAML per ConfigEntry setup
**File:** `custom_components/xiaomi_home/miot/miot_spec.py:752, 832, 927, 978`

Each `__init__.py async_setup_entry` constructs a new `MIoTSpecParser`, which constructs all four classes — each running `run_in_executor(load_yaml_file, ...)` on the *same* on-disk file. Multi-region users (CN + EU + IN) pay N× the I/O.

**Improvement:** Lift to `async_setup` (called once per HA boot) and store in `hass.data[DOMAIN]['spec_cache']`. Or wrap loaders with `functools.lru_cache` keyed by absolute path.

---

### O-010 — Spec auxiliary classes init sequentially via individual `await`
**File:** `custom_components/xiaomi_home/miot/miot_spec.py` (parser bootstrap)

The four spec aux classes (`_SpecFilter`, `_SpecAdd`, `_SpecModify`, `_SpecBoolTranslation`) each await `run_in_executor(...)` independently and serially. They're independent — could run in parallel.

**Improvement:**
```python
await asyncio.gather(
    self._spec_filter.init_async(),
    self._spec_add.init_async(),
    self._spec_modify.init_async(),
    self._bool_trans.init_async(),
)
```

---

### O-011 — `__init__.py async_setup_entry` iterates `entity_registry` three times
**File:** `custom_components/xiaomi_home/__init__.py:138, 171, 181`

1. `async_migrate_unique_ids:138` — iterate to migrate.
2. Lines 171-178 — iterate to drop stale `xiaomi_home.*` entries.
3. Line 181 — captured snapshot for `_remove_from_registry_by_uid` closure.

Three full scans where one would suffice.

**Improvement:** Snapshot the registry once at the top of setup; pass the list into both migration and cleanup helpers.

---

### O-012 — `_async_migrate_legacy_entity_ids` does function-local `import re` and `import slugify`
**File:** `custom_components/xiaomi_home/__init__.py:46, 65`

```python
from homeassistant.util import slugify       # inside function
...
import re                                    # inside inner branch
```

Python caches imports, but module-level imports surface intent better and silence linter warnings.

**Improvement:** Move both to the top of `__init__.py`.

---

## C. Memory / Allocation

### O-013 — `MIOT_UNIT_MAP` / `MIOT_ICON_MAP` are mutable dicts at module scope
**File:** `custom_components/xiaomi_home/miot/miot_device.py:74-170`

Frozen by convention but technically mutable. Defensive `MappingProxyType(MIOT_UNIT_MAP)` documents intent and lets `*_MAP.get(...)` stay zero-cost. Marginal.

---

### O-014 — `MIoTSpecValueList` keeps `items: list`, `_val_to_desc: dict`, `_desc_to_val: dict` — three redundant copies
**File:** `custom_components/xiaomi_home/miot/miot_spec.py:108-153`

Triple-storage of the same value mapping. For tiny lists (modes, fan levels) this is negligible; for devices with large enums it adds up. Could keep one canonical `items` list + two `@cached_property` dicts.

---

## D. Code Volume / DRY

### O-015 — `_SpecStdLib` has six near-identical `*_translate` methods
**File:** `custom_components/xiaomi_home/miot/miot_spec.py:203-243`

`device_translate`, `service_translate`, `property_translate`, `event_translate`, `action_translate`, `value_translate` — each ~7 lines, differing only by which dict they consult.

**Refactor:**
```python
def _translate(self, table: dict, key: str) -> Optional[str]:
    entry = table.get(key)
    if not entry:
        return None
    return entry.get(self._lang) or entry.get(DEFAULT_INTEGRATION_LANGUAGE)

def device_translate(self, key):   return self._translate(self._devices, key)
def service_translate(self, key):  return self._translate(self._services, key)
# … etc.
```

Saves ~30 LoC; behaviour identical.

---

### O-016 — `_SpecFilter.filter_*` has four near-identical methods
**File:** `custom_components/xiaomi_home/miot/miot_spec.py:871-906`

Same wildcard-or-exact-match pattern repeated for service/property/event/action.

**Refactor:**
```python
def _filter(self, kind: str, primary: int, secondary: Optional[int] = None) -> bool:
    items = (self._cache or {}).get(kind, ())
    if secondary is None:
        return str(primary) in items or '*' in items
    return f'{primary}.{secondary}' in items or f'{primary}.*' in items

def filter_service(self, siid): return self._filter('services', siid)
def filter_property(self, siid, piid): return self._filter('properties', siid, piid)
# … etc.
```

Saves ~20 LoC.

---

### O-017 — `miot_mips.py` builds the same topic string in `sub_*` and `unsub_*` independently
**File:** `custom_components/xiaomi_home/miot/miot_mips.py:849, 884, 901, 938`

```python
# in sub_prop
topic: str = f'device/{did}/up/properties_changed/{"#" if … else f"{siid}/{piid}"}'

# in unsub_prop — identical template, manually mirrored
topic: str = f'device/{did}/up/properties_changed/{"#" if … else f"{siid}/{piid}"}'
```

Drift risk: the existing typo `event_occured` already has to be kept in sync across two places.

**Refactor:** Extract `_prop_topic(did, siid, piid)` and `_event_topic(did, siid, eiid)` private helpers.

---

### O-018 — `miot_mips.py` repeats the JSON-parse-and-validate closure across all subscriptions
**File:** `custom_components/xiaomi_home/miot/miot_mips.py:855, 907, 955, 1158, 1204, 1521`

Each `sub_*` defines an inner closure that:
1. `json.loads(payload)` with try/except,
2. validates required keys (`siid`, `piid`/`eiid`, `value`/`arguments`, …),
3. invokes the user handler.

The closure form is fine, but the body is duplicated five times.

**Refactor:**
```python
def _parse_msg(self, topic: str, payload: str, required: set[str]) -> Optional[dict]:
    try:
        msg = json.loads(payload)
    except json.JSONDecodeError:
        self.log_error(f'invalid msg, {topic}, {payload}')
        return None
    params = msg.get('params')
    if not isinstance(params, dict) or not required.issubset(params):
        self.log_error(f'invalid msg, {topic}, {payload}')
        return None
    return params
```

Each `sub_*` shrinks to ~3 lines. Saves ~60 LoC and removes drift surface.

---

### O-019 — `__init__.py` repeats the same kept/removed filtering pattern four times
**File:** `custom_components/xiaomi_home/__init__.py:207-253`

Four blocks — entity_list / prop_list / event_list / action_list — each: iterate items, decide keep-or-remove based on `need_filter` / `hide_non_standard_entities` + `proprietary`, regenerate the platform list.

**Refactor:**
```python
def _filter_platform(device, platform, attr, uid_gen, should_keep):
    items = getattr(device, attr).get(platform, [])
    kept = []
    for item in items:
        if should_keep(item):
            kept.append(item)
        else:
            _remove_from_registry_by_uid([uid_gen(item)])
    getattr(device, attr)[platform] = kept
```

Saves ~30 LoC.

---

### O-021 — `MIoTHttp` ships sync and async siblings; only async is reachable in HA
**File:** `custom_components/xiaomi_home/miot/common.py:87-145, 147-222`

`MIoTHttp.get` / `MIoTHttp.post` use `urllib.request.urlopen` synchronously — illegal in HA's event loop. grep confirms no production caller hits them.

**Refactor:** Delete the sync versions. Saves ~60 LoC and removes a misuse footgun.

---

## E. Architecture / Encapsulation

### O-020 — `MIoTLanManager` / `MIoTCloudManager` reach into `client._private`
**Files:** `custom_components/xiaomi_home/miot/miot_lan_manager.py:17,21,25,27,30`, `custom_components/xiaomi_home/miot/miot_cloud_manager.py:20-31`

Each manager exposes one public method (`refresh_props_*`) but reads/writes `client._miot_lan`, `client._mips_local`, `client._refresh_props_list`, `client._network`, `client._http`. Net effect of the Task-B "God Object split": the same coupling, now spread across three files.

**Refactor options:**
- **(a) Fold them back** into `MIoTClient` as private methods; the split adds no testable boundary.
- **(b) Define an internal interface** on `MIoTClient` (`get_pending_refresh_batch()`, `route_to_gateway(did)`, `route_to_lan(did)`) so managers depend on a named surface, not field names. Then rename-refactoring `MIoTClient` won't silently break them.

---

## Impact Summary

| ID | Category | Benefit | LoC delta | Risk |
|----|----------|---------|-----------|------|
| O-001 | A | Restore HA-managed session, reduce socket churn | ~20 | Low |
| O-002 | A | Faster setup, ~N× entity gen_uid speedup | ~10 | Very low |
| O-003 | A | Drop per-access DeviceInfo allocation | ~5 | Very low |
| O-004 | A | Cache value_list properties | ~10 | Very low |
| O-005 | A | O(D×E×P) → O(1) per `set_property_async` | ~30 | Medium (cache coherency) |
| O-006 | A | Drop throwaway `{}` allocs | ~5 | Very low |
| O-007 | A | Remove hasattr lazy guard, simpler lifecycle | ~15 | Low |
| O-008 | A | Push conversion to write-path, faster reads | medium | Medium |
| O-009 | B | Multi-region startup speedup | ~15 | Low |
| O-010 | B | Parallel spec aux init | ~5 | Very low |
| O-011 | B | Avoid 3× registry scan | ~5 | Very low |
| O-012 | B | Cosmetic — move imports up | ~3 | Very low |
| O-013 | C | MappingProxyType, intent documentation | ~3 | Very low |
| O-014 | C | One canonical value_list copy | ~10 | Very low |
| O-015 | D | −30 LoC, identical behaviour | ~30 | Very low |
| O-016 | D | −20 LoC, identical behaviour | ~20 | Very low |
| O-017 | D | Single topic builder, drift-proof | ~10 | Very low |
| O-018 | D | −60 LoC, single msg validator | ~70 | Low |
| O-019 | D | −30 LoC, single platform filter helper | ~30 | Low |
| O-021 | D | −60 LoC, remove sync misuse footgun | ~60 | Very low |
| O-020 | E | Re-encapsulate managers or fold in | medium | Medium |

---

## Recommended Sequencing

1. **Hot path wins** (O-002, O-003, O-004, O-005, O-006): biggest day-to-day runtime impact, ~60 LoC total.
2. **Startup wins** (O-001, O-009, O-010, O-011): perceptible boot speedup, ~45 LoC total.
3. **DRY pass** (O-015, O-016, O-017, O-018, O-019, O-021): ~200 LoC removed, near-zero risk, large readability win.
4. **Architecture pass** (O-020): only after the above settle so changes don't conflict.
5. **Optional / lower-priority** (O-007, O-008, O-012, O-013, O-014): defer unless a specific symptom appears.

---

*Generated by Claude Code optimization audit, 2026-05-30.*
