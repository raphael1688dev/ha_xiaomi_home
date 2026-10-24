# Xiaomi Home Integration (Mod) for Home Assistant

[![GitHub Release](https://img.shields.io/github/v/release/raphael1688dev/ha_xiaomi_home?style=flat-square)](https://github.com/raphael1688dev/ha_xiaomi_home/releases)
[![Home Assistant Compatibility](https://img.shields.io/badge/Home%20Assistant-2026.10%2B-blue?style=flat-square)](https://www.home-assistant.io/)
[![Python Version](https://img.shields.io/badge/Python-3.14%2B-green?style=flat-square)](https://www.python.org/)
[![License](https://img.shields.io/github/license/raphael1688dev/ha_xiaomi_home?style=flat-square)](./LICENSE.md)

An enhanced, high-performance, and production-ready fork of the official Xiaomi Home integration for Home Assistant. Maintained by [@raphael1688dev](https://github.com/raphael1688dev), this custom edition focuses on bulletproof connection stability, seamless local LAN control, rapid state synchronization, zero-disruption entity migrations, and full compliance with modern Home Assistant architectures.

---

## 🚀 Key Mod Features

### 1. Modern Home Assistant (2026.10+) & Python 3.14+ Compatibility
- **Python 3.14 Asyncio Garbage Collection Safety**: Explicitly tracks and retains strong references to all background asyncio tasks (`_background_tasks`), preventing Python 3.14's aggressive cyclic garbage collector from destroying active coroutines before completion.
- **Hassfest & Modern Entity Compliance**: Fully adheres to `has_entity_name = True`, eliminating legacy naming violations and invalid entity IDs. Explicitly defines `CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)`.
- **Modern Sensor Units & State Classes**: Cleanly adopts standard density and ratio units with dynamic fallbacks, deprecation-free across all sensor types.

### 2. Upstream 0.5.0 Fixes & Synchronizations
- **Safe Cloud Batch Future Draining**: Ensures pending property futures are immediately resolved with `None` upon batch request exceptions in `__get_prop_handler`, preventing waiting coroutines from hanging indefinitely (PR #1723).
- **MIoT Spec Value Precision Alignment**: Corrects integer step alignment calculations when `min_ != 0`: `(value - min_) / step * step + min_` (PR #1623).
- **Public Cloud Broker TLS Verification**: Verifies broker hostname for public cloud MQTT endpoints (`tls_insecure_set(False)`) while preserving unverified TLS connections for local hub gateways (PR #1774).
- **Non-UTF-8 MQTT Frame Guard**: Safely intercepts and discards corrupted non-UTF-8 cloud messages to avoid JSON decoder crashes (PR #1750).
- **Humidifier Mode Translations**: Maps MIoT humidifier spec mode strings to standard Home Assistant constants (`MODE_NORMAL`, `MODE_ECO`, etc.) (PR #1658).
- **CO2 Sensor Long-Term Statistics**: Mapped `co2-density` with `SensorDeviceClass.CO2` and `SensorStateClass.MEASUREMENT` (PR #1631).
- **Device Specification Overrides**: Integrated upstream specification fixes for Daikin ACs, Xiaomi ACs, Aupu bath heaters, and relays (PR #1805).

### 3. Bulletproof Network & Disconnect Resilience
- **Fast Disconnect Teardown**: Upon MIPS gateway socket disconnection, all in-flight requests in `_request_map` are immediately aborted and timers cancelled, eliminating cascading 10-second timeout error logs.
- **Queue Flush on Disconnect**: Instantly empties `_get_prop_queue` when connections drop, immediately resolving awaiting futures and preventing integration task stalls.
- **Exponential Backoff Gateway Discovery**: Wraps gateway device synchronization with exponential backoff ($3\text{s} \to 6\text{s} \to 12\text{s} \to 24\text{s} \to 60\text{s}$), eliminating network spam during hub reboots.
- **Clean Logging Levels**: Demotes internal request timeouts to `DEBUG` and routine MQTT reconnect scheduling to `INFO`, keeping the Home Assistant system log clean and readable.

### 4. Zero-Disruption Entity ID Stability & Auto-Migration
- **Domain-less Unique IDs**: Eradicated the legacy technical debt where the official Xiaomi component forced `xiaomi_home.` domain prefixes into entity unique IDs.
- **Multi-Phase Auto-Migration**: Built-in startup migration automatically rewrites legacy registry entries and cleans up orphaned action entities. Existing dashboards, scripts, and automations continue working seamlessly with **zero `_2` duplicate entities**.

### 5. Overseas Server Local LAN Control & Unicast Polling
- **Local Control for Non-CN Servers**: Enables local LAN control for Wi-Fi devices registered on overseas servers (e.g., Singapore, Europe, USA), bypassing the official regional restriction.
- **Active Unicast Polling (Cloud Ban Prevention)**: Implements proactive unicast state polling every 30 seconds for Wi-Fi devices. Replaces unreliable UDP broadcast listeners (which often fail across VLANs) while routing polling traffic locally to avoid cloud rate limits.

### 6. Built-in Diagnostic Sensors
- **Control Path Sensor**: Exposes real-time communication routing (`Cloud`, `LAN`, or `Gateway`).
- **IP Address Sensor**: Displays the active local IP address natively in the device diagnostic panel.

### 7. Security Hardening
- **AST Mathematical Safe Evaluator**: Replaced Python's native `eval()` in `miot_spec.py` with an AST-based mathematical safe evaluator (`safe_eval`), completely neutralizing remote code execution (RCE) vectors.

---

## 📦 Installation

> **System Requirements**:
> - Home Assistant Core $\geq 2026.5.0$ (Fully tested and verified on Home Assistant $2026.10+$)
> - Python $\geq 3.12$ (Tested under Python 3.14.6)

### Method 1: HACS (Recommended)

1. Open **HACS** in your Home Assistant instance.
2. Click the three dots in the upper right corner and select **Custom repositories**.
3. Enter the repository URL:
   ```text
   https://github.com/raphael1688dev/ha_xiaomi_home
   ```
4. Set the Type to **Integration** and click **Add**.
5. Search for **Xiaomi Home(Mod)**, click **Download**, and restart Home Assistant.

### Method 2: Git Clone

```bash
cd config/custom_components
git clone https://github.com/raphael1688dev/ha_xiaomi_home.git temp_xiaomi
cp -r temp_xiaomi/custom_components/xiaomi_home ./xiaomi_home
rm -rf temp_xiaomi
```
Restart Home Assistant after copying.

### Method 3: Manual Download

1. Download `xiaomi_home.zip` from the latest [Release](https://github.com/raphael1688dev/ha_xiaomi_home/releases).
2. Extract the archive into your `config/custom_components/` directory such that `config/custom_components/xiaomi_home/manifest.json` exists.
3. Restart Home Assistant.

---

## ⚙️ Configuration

### 1. Add the Integration
1. Go to **Settings > Devices & Services > Add Integration**.
2. Search for **Xiaomi Home(Mod)**.
3. Select your Xiaomi account region (Mainland China, Europe, Singapore, USA, Russia, or India).
4. Follow the OAuth 2.0 authentication prompt to link your account.

### 2. Device Selection & Control Mode
- Choose the home and devices you wish to synchronize into Home Assistant.
- In **Integration Options**, you can customize:
  - **Control Mode**: Auto, Cloud, or Local Gateway / LAN.
  - **Action Debug Mode**: Generates interactive text inputs for sending raw MIoT action commands.
  - **Cover Dead Zone Width**: Sets positioning dead-zone margins for smart curtains.

---

## 🔄 Architecture & Messaging Principles

### Cloud Control (MQTT Push + HTTP Control)
<div align="center">
<img src="./doc/images/cloud_control.jpg" width="400" alt="Cloud Control Architecture">
</div>

1. The integration subscribes to device events via the MIoT Cloud MQTT broker.
2. Property changes and events trigger immediate upstream notifications to Home Assistant with zero polling delay.
3. Outbound commands are dispatched through the MIoT Cloud HTTP REST API.

### Local Gateway Control (Xiaomi Central Hub Gateway)
<div align="center">
<img src="./doc/images/local_control.jpg" width="400" alt="Local Gateway Architecture">
</div>

1. The Xiaomi Central Hub Gateway hosts a local MQTT broker.
2. Home Assistant discovers and establishes a secure TLS connection with the hub.
3. Subscriptions and commands are routed entirely within your local network, independent of active Internet access.

### Local LAN Wi-Fi Control (Unicast OT Protocol)
- For Wi-Fi devices supporting the MIoT OT protocol, Home Assistant directly communicates over local UDP/TCP unicast.
- Eliminates cloud latency and protects automations from Internet outages.

---

## 📊 MIoT-Spec-V2 Entity Mappings

MIoT Specification Version 2 defines device capabilities using Services, Properties, Events, and Actions. The integration converts them to Home Assistant entities according to the following rules:

### Properties
| Access | Format | Value List | Value Range | Home Assistant Platform |
|---|---|---|---|---|
| Writable | `string` | - | - | **Text** |
| Writable | `bool` | - | - | **Switch** |
| Writable | Numeric | Present | - | **Select** |
| Writable | Numeric | Absent | Present | **Number** |
| Read-only | Any | - | - | **Sensor** / **Binary Sensor** |

### Events & Actions
- **Events**: Mapped to native Home Assistant **Event** entities with parameters exposed in attributes.
- **Actions**: Mapped to **Button** entities (or **Notify** entities when input arguments are required).

---

## 📝 Release History & Changelog

### Version 20261024r36 (v0.5.3 Mod) — Latest
- **Security**: OAuth token refresh no longer logs credentials, and token and user profile errors no longer embed raw responses that could reach logs and diagnostics. Contributed by @Wuty-zju, extended in this fork.
- **Doorbell Events**: Doorbell event entities declare and fire the standard `ring` event type required from Home Assistant 2027.4. Automations matching the old event type name need to use `ring`. Contributed by @reginaldalfret.
- **Device Fixes**: `uwize.plug.yzs01` power consumption is no longer 100 times too high (contributed by @xuilen), and `miaomiaoce.airm.co2` CO2 readings are no longer rounded to 100 ppm (contributed by @Wuty-zju).
- **Setup Text**: The device filter instructions describe the subtraction in the right order. Contributed by @0xSixtos.
- **Code Quality**: CI is fully green; pylint reports no findings.

### Version 20261016r35 (v0.5.2 Mod)
- **Setup Crash Fix**: Robot vacuums, speakers, TVs, air conditioners and other whole-device entities no longer make the integration fail to load (`TypeError` on `frozenset` action sets, `AttributeError` on `MIoTSpecInstance`). Contributed by @theodorx7.
- **MQTT Loop Guard**: Event loop handlers no longer touch a closed socket after a disconnect. Contributed by @theodorx7.
- **Quieter Gateway Logs**: Known unsupported models are skipped before device info validation. Contributed by @theodorx7.

### Version 20261016r34 (v0.5.1 Mod)
- **Home Assistant 2026.10 Compliance**: Fixed entity IDs with mismatched domains (deprecated, rejected from 2027.5), migrated off the deprecated `DeviceRegistry.async_get_device`, and register devices via `DeviceInfo.as_dict()` when available.
- **HA 2026.11 Readiness**: Climate and water heater entities implement `native_*` temperature properties on cores that provide them, keeping the legacy names on older cores.
- **Device Tracker**: Battery level moved to a dedicated battery sensor; dropped the deprecated `location_name` (removed in 2027.7) and fixed latitude/longitude lagging one update.
- **Humidifier Modes**: Chinese mode names now match, duplicate standard modes no longer hide device values, and legacy mode names still work in automations.
- **English Only**: Removed the remaining Chinese translations; existing entries using another language are migrated to English on setup (entity IDs are unchanged).
- **Hidden Crash Fixes**: Fixed `NameError`s in the HTTP helper error path and the OAuth refresh handler, and removed the `cryptography` requirement rejected by hassfest.
- **Housekeeping**: `async_schedule_reload` in the options flow, quieter MQTT/cloud error logs, corrected manifest metadata, and hardened upstream tracker / quality audit CI.

### Version 20261011r33 (v0.5.0 Mod)
- **Cloud Batch Resilience**: Added safe future draining with `None` upon batch request exceptions in `__get_prop_handler` (upstream PR #1723).
- **MIoT Spec Value Precision**: Corrected integer step alignment for non-zero `min_` value ranges: `(value - min_) / step * step + min_` (upstream PR #1623). Added test in `tests/test_miot_spec.py`.
- **MIPS TLS & Unicode Guard**: Enabled public cloud broker hostname verification (`tls_insecure_set(False)`) while maintaining insecure TLS for local hubs, and dropped non-UTF-8 cloud MQTT messages (upstream PR #1750, #1774).
- **Humidifier Mode Translations**: Mapped MIoT humidifier spec mode strings to standard Home Assistant constants (`MODE_NORMAL`, `MODE_ECO`, etc.) using unicode escape sequences (upstream PR #1658).
- **CO2 Sensor Statistics**: Mapped `co2-density` with `SensorDeviceClass.CO2` and `SensorStateClass.MEASUREMENT` (upstream PR #1631).
- **Device Spec Overrides**: Adopted upstream specification overrides for Daikin ACs, Xiaomi ACs, Aupu bath heaters, and relays (upstream PR #1805).
- **Hassfest Compliance**: Defined `CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)` in `__init__.py` and added URL placeholders in config flows and `en.json` (upstream PR #1800).
- **Blood Glucose Unit Escaping**: Escaped Chinese blood glucose unit strings in `miot_device.py`.

### Version 20261011r32 (v0.4.14 Mod)
- **Fast Disconnect Teardown**: Immediately abort in-flight requests in `_request_map` and cancel timers upon MIPS socket disconnection, eliminating cascading 10-second timeout error logs.
- **Queue Flush on Disconnect**: Cleared `_get_prop_queue` upon MIPS disconnect to immediately resolve awaiting futures and prevent task stalls.
- **Log Noise Optimization**: Demoted internal request timeout logs from ERROR to DEBUG, and routine MQTT disconnect / reconnect logs from WARNING to INFO.
- **Error Formatting**: Enhanced error reporting in `MIoTClient` and `MIoTCloudManager` to fall back to exception type names when `str(err)` is empty.

### Version 20261008r31 (v0.4.13 Mod)
- **Python 3.14 Asyncio GC Protection**: Retained strong references in `MIoTClient._background_tasks` to prevent garbage collection of pending asyncio tasks.
- **Coroutine Serialization Fix**: Resolved `TypeError: Type is not JSON serializable: coroutine` in cloud property polling by sanitizing parameter lists down to pure dictionaries.
- **Gateway Refresh Exponential Backoff**: Wrapped `mips.get_dev_list_async` with exponential backoff retry ($3\text{s} \to 60\text{s}$), demoting routine retry attempts to INFO.

### Version 20260730r30 (v0.4.12 Mod)
- **Home Assistant 2026.8 Deprecation Fixes**: Replaced deprecated `CONCENTRATION_*` constants with dynamic fallbacks to `UnitOfDensity` and `UnitOfRatio`.
- **Modern Device Tracker**: Modernized `device_tracker.py` by eliminating overridden property getters and migrating to dynamic `_attr_*` and `extra_state_attributes`.

### Version 20260601r28 (v0.4.10 Mod)
- **Security Hardening**: Implemented AST-based mathematical safe evaluator `safe_eval` in `miot_spec.py` to replace Python's native `eval()`, mitigating remote code execution vectors.
- **Config Flow Modularization**: Decomposed the monolithic 150-line `__check_oauth_async` in `config_flow.py` into 7 single-responsibility private helper methods.

### Version 20260531r26 & r27 (v0.4.9 Mod)
- **Directory Layout & Test Migration**: Relocated the test suite to the repository root under `tests/` with modern pytest fixtures.
- **LAN Capability Refactor**: Introduced `is_lan_capable` property on `MIoTDevice` and cleaned up capability checks.
- **Explicit Network Logging**: Replaced silent exception suppression in `common.py` and `miot_network.py` with explicit network timeout and client error logging.

### Version 20260531r23 – r25 (v0.4.8 Mod)
- **Architecture Refactoring**: Decomposed monolithic spec parsers in `miot_spec.py` into modular property, event, and action parsers. Added comprehensive type annotations across parser modules.
- **Dead Code Cleanup**: Purged unused imports, eliminated dead storage entries, and extracted modular `network.py` helpers to remove circular dependencies.

---

## 📄 License & Attribution

- Based on the official [XiaoMi/ha_xiaomi_home](https://github.com/XiaoMi/ha_xiaomi_home) repository.
- Licensed under the [Apache License 2.0](./LICENSE.md).
- Xiaomi and Mi Home are trademarks of Xiaomi Inc.
