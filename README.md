# Xiaomi Home Integration (Mod) for Home Assistant

[![GitHub Release](https://img.shields.io/github/v/release/raphael1688dev/ha_xiaomi_home?style=flat-square)](https://github.com/raphael1688dev/ha_xiaomi_home/releases)
[![Home Assistant](https://img.shields.io/badge/Home%20Assistant-2026.5%2B-blue?style=flat-square)](https://www.home-assistant.io/)
[![HACS](https://img.shields.io/badge/HACS-Custom-orange?style=flat-square)](https://hacs.xyz/)
[![License](https://img.shields.io/badge/License-Xiaomi%20non--commercial-lightgrey?style=flat-square)](./LICENSE.md)

A maintained fork of the official [Xiaomi Home integration](https://github.com/XiaoMi/ha_xiaomi_home) for Home Assistant, by [@raphael1688dev](https://github.com/raphael1688dev). It keeps up with current Home Assistant releases, takes in worthwhile upstream fixes that are still waiting for review there, and adds steadier connections, local control and stable entity IDs.

The official repository has had no release since v0.5.0; this fork has carried on from there. See [what has changed](#-release-history) or the full [CHANGELOG](./CHANGELOG.md).

---

## 🚀 Key Mod Features

### 1. Current Home Assistant Compliance
- **Follows Home Assistant 2026.5+ practice**: entity naming with `has_entity_name`, entity IDs that match their domain (mismatches are rejected from 2027.5), `DeviceInfo`, config entry only setup, and standard event types such as the doorbell `ring`.
- **Ready for announced deprecations**: climate and water heater entities use the `native_*` temperature properties on cores that have them (Home Assistant 2026.11), and the device tracker no longer uses `location_name` (removed in 2027.7).
- **Python 3.14 safe**: background asyncio tasks are kept referenced so they are not garbage collected before they finish.
- **Recorder friendly**: large, frequently changing attributes (such as the full value of long strings) are kept out of the history database.

### 2. Steadier Connections
- **Cloud broker failover**: the cloud MQTT broker name resolves to several nodes. When one of them fails the TLS handshake, the integration moves on to the next address instead of retrying the broken node.
- **Calm reconnects**: one failed attempt schedules one retry with exponential backoff. Short drops stay at DEBUG; if the connection stays down for 2 minutes, a single warning names the cause, and the recovery is logged.
- **Fast disconnect teardown**: when a gateway connection drops, in-flight requests and queued property reads are resolved at once instead of each timing out after 10 seconds.
- **Gateway discovery backoff**: device list sync retries with exponential backoff (3 s up to 60 s) while a hub reboots.

### 3. Local Control
- **LAN control on every region**: Wi-Fi devices registered on overseas servers (Europe, Singapore, USA and others) can be controlled over the LAN, not only China mainland accounts.
- **Unicast probing and polling**: devices are probed by unicast as well as broadcast, so they are found across VLANs where broadcasts are blocked, and LAN-capable entities poll their state locally. In Auto mode, **Polling Priority** chooses whether cloud or local polling comes first.
- **Native MIIO control**: 19 popular devices that do not speak MIoT over the LAN (Yeelight desk, floor and bedside lamps, Smartmi `zhimi.fan.*` and Dmaker `dmaker.fan.p5` fans) are controlled locally through a built-in Python MIIO layer.

### 4. Stable Entity IDs
- **Automatic migration**: unique IDs no longer carry the legacy `xiaomi_home.` prefix. Existing registry entries are rewritten on startup, duplicate `_2` entities from earlier versions are removed, and existing dashboards and automations keep working.

### 5. Diagnostics
- **Control Path** sensor: shows whether a device is reached through the `Cloud`, `LAN` or a `Gateway`.
- **IP Address** sensor: shows the device's local IP address.
- Both are diagnostic entities and are disabled by default.

### 6. Security
- **No `eval()` on spec data**: value expressions from device specs are evaluated by a restricted AST evaluator.
- **No credentials in logs**: OAuth token refreshes and API errors never log tokens or raw account responses.
- **Verified cloud TLS**: the public cloud broker's certificate and hostname are verified.

### 7. English Only
- The integration ships English translations only. Entries created with another language are migrated to English on setup; entity IDs are unchanged.

---

## 📦 Installation

> **Requirements**: Home Assistant 2026.5.0 or later (tested on 2026.10).

### Method 1: HACS (Recommended)

1. Open **HACS** in your Home Assistant instance.
2. Click the three dots in the upper right corner and select **Custom repositories**.
3. Enter the repository URL:
   ```text
   https://github.com/raphael1688dev/ha_xiaomi_home
   ```
4. Set the Type to **Integration** and click **Add**.
5. Search for **Xiaomi Home(Mod)**, click **Download**, and restart Home Assistant.

> The fork uses the `xiaomi_home` domain, like the official integration, so install one or the other, not both.

### Method 2: Manual Download

1. Download `xiaomi_home.zip` from the latest [Release](https://github.com/raphael1688dev/ha_xiaomi_home/releases).
2. Extract the archive into your `config/custom_components/` directory such that `config/custom_components/xiaomi_home/manifest.json` exists.
3. Restart Home Assistant.

### Method 3: Git Clone

```bash
cd config/custom_components
git clone https://github.com/raphael1688dev/ha_xiaomi_home.git temp_xiaomi
cp -r temp_xiaomi/custom_components/xiaomi_home ./xiaomi_home
rm -rf temp_xiaomi
```
Restart Home Assistant after copying. This installs the development version from `main`, which may be ahead of the latest release.

---

## ⚙️ Configuration

### 1. Add the Integration
1. Go to **Settings > Devices & Services > Add Integration**.
2. Search for **Xiaomi Home(Mod)**.
3. Select your Xiaomi account region (China Mainland, Europe, India, Russia, Singapore or United States).
4. Follow the OAuth 2.0 login to link your account.

### 2. Devices & Options
- Choose the homes and devices to add, optionally filtered by room, device type or model.
- **Control Mode**:
  - **Auto**: use a Xiaomi Central Hub Gateway when one is available, then LAN control, and the cloud otherwise.
  - **Cloud**: send every command through the cloud.
  - **Pure Local**: use only the central hub gateway and LAN control, never the cloud.
- **Polling Priority** (Auto mode): **Cloud First** (default) or **Local First** for state polling.
- In the integration's **Configure** page you can also update the device list and entity conversion rules, change the LAN control network interfaces, and set:
  - **Action Debug Mode**: adds a text input entity for each device action, to send raw MIoT action arguments.
  - **Hide Non-Standard Generated Entities**: hides entities whose name starts with `*`.
  - **Binary Sensor Display Mode**: show binary values as text sensors or binary sensors.
  - **Cover Dead Zone Width**: position margin for curtains that stop short of fully open or closed.

---

## 🔄 How It Connects

### Cloud Control (MQTT Push + HTTP Control)
<div align="center">
<img src="./doc/images/cloud_control.jpg" width="400" alt="Cloud Control Architecture">
</div>

1. The integration subscribes to device updates through the Xiaomi cloud MQTT broker for your region.
2. Property changes and events are pushed to Home Assistant as they happen.
3. Commands are sent through the Xiaomi cloud HTTP API.

### Local Gateway Control (Xiaomi Central Hub Gateway)
<div align="center">
<img src="./doc/images/local_control.jpg" width="400" alt="Local Gateway Architecture">
</div>

1. The Xiaomi Central Hub Gateway (firmware 3.3.0_0023 or later) hosts a local MQTT broker.
2. Home Assistant discovers it over mDNS and connects over TLS.
3. Subscriptions and commands stay on your local network.

Central hub gateway control is available for China mainland accounts only; this is a Xiaomi restriction.

### LAN Control (Wi-Fi Devices)
- Wi-Fi devices that support the MIoT OT protocol are controlled directly over UDP on the local network.
- When both are available, the central hub gateway takes priority over LAN control.
- LAN control applies to IP devices only. Some devices made before 2020 do not support it.

---

## 📊 MIoT-Spec-V2 Entity Mappings

MIoT-Spec-V2 describes each device as services with properties, events and actions. Whole devices and services that match a known type (vacuum, air conditioner, humidifier, light and so on) become the matching Home Assistant entity. Everything else is converted per instance:

### Properties
| Access | Format | Value List | Value Range | Home Assistant Platform |
|---|---|---|---|---|
| Writable | `string` | - | - | **Text** |
| Writable | `bool` | - | - | **Switch** |
| Writable | Numeric | Present | - | **Select** |
| Writable | Numeric | Absent | Present | **Number** |
| Read-only | Any | - | - | **Sensor** / **Binary Sensor** |

### Events & Actions
- **Events**: become **Event** entities, with the event arguments as attributes.
- **Actions**: become **Button** entities, or **Notify** entities when the action takes input arguments.

---

## 🛠️ Troubleshooting

Turn on debug logging in `configuration.yaml`:

```yaml
logger:
  default: warning
  logs:
    custom_components.xiaomi_home: debug
```

- **`mips connection remains unavailable (...)`**: the cloud MQTT connection has been down for over 2 minutes and the integration keeps retrying. The text in brackets is the last error. Recovery is logged at INFO as `mips connection recovered`.
- **Entities missing or wrong after editing spec files**: open the integration's **Configure** page and run **Update entity conversion rules**.

Report problems in the [issue tracker](https://github.com/raphael1688dev/ha_xiaomi_home/issues). Include the device model, your region and a debug log, with account details removed.

---

## 📝 Release History

The most recent releases are listed below. Older versions are in the [CHANGELOG](./CHANGELOG.md) and on the [Releases](https://github.com/raphael1688dev/ha_xiaomi_home/releases) page.

### Version 20261024r38 (v0.5.5 Mod) — Latest
- **Cloud Broker Failover**: When one node behind the cloud MQTT broker name fails the TLS handshake (seen on the Singapore broker as `UNEXPECTED_EOF_WHILE_READING`), the integration connects through the next address instead of staying offline.
- **Clearer Outage Logs**: Connection errors during an outage log at DEBUG, and the single "connection remains unavailable" warning names the last error. Subscribing while disconnected is no longer reported as an error.
- **README**: Rewritten to match the current fork, with troubleshooting tips and a corrected license description.

### Version 20261024r37 (v0.5.4 Mod)
- **Cloud Devices With `#` in Their ID**: These devices can subscribe to property, event and state updates again. Contributed by @Blueve.
- **Steadier MQTT Reconnects**: One failed attempt schedules one retry, transient losses stay at DEBUG, and a lasting outage warns after 120 seconds and logs its recovery. Contributed by @Wuty-zju; disconnect codes are now classified by their actual meaning.
- **Long String Values**: Sensor and text entities keep the full value of strings over 255 characters in a `value` attribute, excluded from the recorder. Contributed by @MGrin.

### Version 20261024r36 (v0.5.3 Mod)
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

---

## 🙏 Credits

Thanks to the people whose fixes were reviewed and merged here, many of them first proposed upstream: @theodorx7, @Wuty-zju, @Blueve, @MGrin, @reginaldalfret, @xuilen and @0xSixtos, and to the Xiaomi team for the original integration.

## 📄 License & Attribution

- Based on the official [XiaoMi/ha_xiaomi_home](https://github.com/XiaoMi/ha_xiaomi_home) repository.
- Distributed under Xiaomi's license, see [LICENSE.md](./LICENSE.md). It allows use, modification and distribution only for your own non-commercial use of Home Assistant.
- Xiaomi and Mi Home are trademarks of Xiaomi Inc. This fork is not affiliated with or endorsed by Xiaomi.
