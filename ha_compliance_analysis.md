# Home Assistant Compliance Analysis (2026.5.0)

This document records the non-compliant code patterns and optimization opportunities found in the `ha_xiaomi_home` project, specifically concerning Home Assistant 2026.5.0 best practices.

## 1. `aiohttp.ClientSession` Usage (Resolved)

> [!TIP]
> **Resolution:** 
> Replaced manual instantiation with Home Assistant's managed session via `async_get_clientsession(hass)`. Injected session instances into `MIoTNetwork`, `MIoTHttpClient`, and `MIoTOauthClient` from `config_flow.py` and `miot_client.py`.

**Issue:**
The integration manually instantiates `aiohttp.ClientSession()` in multiple places:
- [miot_cloud.py](file:///Users/raphael/Desktop/ha_xiaomi_home-main/custom_components/xiaomi_home/miot/miot_cloud.py)
- [miot_network.py](file:///Users/raphael/Desktop/ha_xiaomi_home-main/custom_components/xiaomi_home/miot/miot_network.py)
- [common.py](file:///Users/raphael/Desktop/ha_xiaomi_home-main/custom_components/xiaomi_home/miot/common.py)

**Required Fix:**
Replace all instances of `aiohttp.ClientSession()` with Home Assistant's managed session.

## 2. Entity `name` Property Override (Resolved)

> [!TIP]
> **Resolution:** 
> Removed `@property def name(self)` overrides in `vacuum.py`. Set `self._attr_name = None` to leverage HA's native device naming convention alongside `self._attr_has_entity_name = True`. Confirmed `MIoTServiceEntity` is already compliant.

**Issue:**
Files like [vacuum.py](file:///Users/raphael/Desktop/ha_xiaomi_home-main/custom_components/xiaomi_home/vacuum.py) and [miot_device.py](file:///Users/raphael/Desktop/ha_xiaomi_home-main/custom_components/xiaomi_home/miot/miot_device.py) override the `name` property to explicitly return `self._device_name`.

**Required Fix:**
- Remove the `@property def name(self)` methods completely.
- Since `self._attr_has_entity_name = True` is already used, the main entity name should either be defined via `self._attr_name = None` (to inherit the device name) or explicitly set to a string during `__init__`.

## 3. Background Task Tracking (Future Hazard)

> [!WARNING]
> Use `async_create_background_task` instead of `async_create_task` when running background loops tied to a ConfigEntry.

**Issue:**
[config_flow.py](file:///Users/raphael/Desktop/ha_xiaomi_home-main/custom_components/xiaomi_home/config_flow.py) uses `self.hass.async_create_task(...)` for background OAuth processes. 

**Required Fix:**
Migrate to `config_entry.async_create_background_task(...)` so that Home Assistant can automatically track, cancel, and clean up these tasks if the integration is reloaded or removed. *(Note: This specific fix was deferred as it involves ConfigFlow which doesn't always have a `config_entry` yet.)*

## 4. State Map Initialization Optimization (Resolved)

> [!TIP]
> **Resolution:**
> Extracted the static hardcoded word sets into module-level constants (e.g. `VACUUM_STATUS_DOCKED_WORDS`) in `vacuum.py` to prevent repeated memory allocation per entity instantiation.

**Issue:**
In [vacuum.py](file:///Users/raphael/Desktop/ha_xiaomi_home-main/custom_components/xiaomi_home/vacuum.py), the `__init__` method contains hardcoded string sets inside a loop for categorizing device states. 

**Required Fix:**
Extract these static sets (`{'charging', 'charged', ...}`) to module-level constants. This avoids recreating the sets in memory every time a new vacuum entity is instantiated, reducing initialization time and memory overhead.

## 5. Home Assistant 2027 Deprecation Outlook

> [!NOTE]
> Based on the Home Assistant architecture proposals, the primary deprecation scheduled for **Home Assistant 2027.5** is the removal of the **legacy device tracker platform API** (non-config-entry).

**Analysis of `ha_xiaomi_home`:**
- **Legacy Device Tracker API:** We have verified that this integration is already compliant. It utilizes the modern `TrackerEntity` base class (`from homeassistant.components.device_tracker import TrackerEntity`) instead of the deprecated legacy `device_tracker` approach.
- **Next Steps:** No immediate action is required for the device tracker API. However, we have added a permanent rule in `CLAUDE.md` to continuously monitor and anticipate upcoming 2027 deprecation warnings in the Home Assistant logs.
