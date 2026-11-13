# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Xiaomi Home Integration is an official Home Assistant integration for controlling Xiaomi IoT smart devices. It connects to devices via Xiaomi Cloud (MQTT) or locally through Xiaomi Central Hub Gateway. The integration converts MIoT-Spec-V2 device specifications into Home Assistant entities.

## Development Commands

### Installation & Setup
```bash
# Install to Home Assistant config directory
./install.sh /path/to/config

# Install the upstream suite's test dependencies
pip install pytest pytest-asyncio pytest-dependency zeroconf paho.mqtt psutil cryptography slugify aiohttp
```

### Testing
There are two suites, and the Tests workflow runs both. `test/` is the upstream suite. `tests/` holds the fork's unit tests; they import Home Assistant, so run them locally with the venv `test_env/` (Home Assistant 2026.11.1, the version CI installs).
```bash
# Upstream suite
pytest -v -s -m github ./test/

# Run specific test files
pytest -v -s ./test/test_spec.py
pytest -v -s ./test/test_cloud.py
pytest -v -s ./test/test_lan.py

# Check rule format
pytest -v -s -m github ./test/check_rule_format.py

# Fork unit tests
test_env/bin/python -m pytest tests/

# Local gate: no Chinese characters, py_compile, both test suites, manifest version
test_env/bin/python scripts/quality_audit.py
```

### Code Quality
```bash
# Run pylint (follows Google Python Style Guide)
pylint $(git ls-files '*.py')

# Lint specific files
pylint custom_components/xiaomi_home/*.py
```

### Validation
```bash
# HACS validation (run by GitHub Actions)
# Uses: hacs/action@main

# Hassfest validation (run by GitHub Actions)
# Uses: home-assistant/actions/hassfest@master
```

## Architecture Overview

### Core Components (miot/)

The integration is built around the `miot/` core package:

**miot_client.py**: Top-level client instance representing a logged-in Xiaomi user. Each user login creates one MIoTClient. Manages authentication, device list, and message routing.

**miot_cloud.py**: OAuth 2.0 authentication and HTTP API calls to Xiaomi Cloud. Handles token refresh, user info, device control commands, and spec downloads.

**miot_mips.py**: Message bus (MQTT) for subscribing to device property changes and events. Implements both cloud (MipsCloudClient) and local (MipsLocalClient) message handling.

**miot_device.py**: `MIoTDevice`, one per Xiaomi device, which turns its spec into entity data, and the entity base classes the platforms subclass (`MIoTServiceEntity`, `MIoTPropertyEntity`, `MIoTEventEntity`, `MIoTActionEntity`). Handles property updates, action execution, and event processing.

**miot_spec.py**: MIoT-Spec-V2 parser. Parses device specifications (URN-based type system) from cloud or local cache. Each spec defines services, properties, events, and actions.

**miot_lan.py**: Local LAN control for IP devices in same network. Discovery and control without cloud (optional).

**miot_mdns.py**: mDNS discovery for Xiaomi Central Hub Gateway services.

**miot_storage.py**: File storage for certificates, device specs, translations, and cached data.

**miot_network.py**: Network status monitoring and IP address detection.

**miot_i18n.py**: Translations for entity names and integration messages. This fork ships English only (`INTEGRATION_LANGUAGES` lists only `en`); entries created with another language are migrated to English on setup.

### Entity Conversion (specs/specv2entity.py)

MIoT-Spec-V2 instances are converted to Home Assistant entities using three mapping dictionaries:

- **SPEC_DEVICE_TRANS_MAP**: Whole-device patterns (e.g., vacuum, humidifier, climate)
- **SPEC_SERVICE_TRANS_MAP**: Service-level patterns (e.g., battery, air-purifier)
- **SPEC_PROP_TRANS_MAP**: Property-level patterns (e.g., temperature, humidity)

Conversion priority: Device > Service > Property > General rules

### Spec Customization Files (miot/specs/)

**spec_filter.yaml**: Filters out MIoT-Spec-V2 instances that should NOT be converted to entities. Uses device URN keys and supports wildcard matching for service/property/event/action IIDs.

**spec_modify.yaml**: Modifies spec instances before conversion (e.g., changing value ranges, access modes).

**multi_lang.json**: Local translation overrides with higher priority than cloud translations. Keyed by device URN (without version).

**spec_add.json**: Additional spec definitions for devices not in cloud database.

**bool_trans.yaml**: Boolean value translation mappings.

The YAML spec files are read once per Home Assistant process (`load_yaml_file` in `miot/common.py` is cached), so after editing them, restart Home Assistant, then update the conversion rules from the integration's CONFIGURE page.

### Platform Files (custom_components/xiaomi_home/)

Standard Home Assistant platform files (sensor.py, switch.py, climate.py, etc.) implement entity registration and state management. Each platform imports from miot_device.py and creates entity subclasses.

**config_flow.py**: Configuration flow for OAuth login and device selection.

**__init__.py**: Integration setup, entry management, and data structure initialization.

## MIoT-Spec-V2 Concepts

**URN Format**: `urn:<namespace>:<type>:<name>:<value>[:<vendor-product>:<version>]`
- namespace: miot-spec-v2 (Xiaomi), bluetooth-spec (SIG), or vendor-specific
- type: device, service, property, event, action
- name: human-readable identifier (used for mapping)

**IIDs (Instance IDs)**: Decimal identifiers
- siid: Service Instance ID
- piid: Property Instance ID
- eiid: Event Instance ID
- aiid: Action Instance ID

**Instance Code Format**:
```
service:<siid>                              # service
service:<siid>:property:<piid>              # property
service:<siid>:property:<piid>:valuelist:<index>  # value list item
service:<siid>:event:<eiid>                 # event
service:<siid>:action:<aiid>                # action
```

## Naming Conventions

From CONTRIBUTING.md:

- **Xiaomi**: Always "Xiaomi" in text. Variables: "xiaomi" or "mi"
- **Xiaomi Home**: Always "Xiaomi Home" in text. Variables: "mihome" or "MiHome"
- **Xiaomi IoT**: Always "MIoT" in text. Variables: "miot" or "MIoT"
- **Home Assistant**: Always "Home Assistant" in text. Variables: "hass" or "hass_xxx"

Mixed Chinese/English: Add space between Chinese and English or use Chinese quotation marks.

## Commit Message Format

```
<type>: <subject>

<body>

<footer>
```

Types: feat, fix, docs, style, refactor, perf, test, chore, revert

Subject: Imperative, present tense. Not capitalized. No period.

Body: Detailed description (mandatory except for docs type).

## Code Style

Follow [Google Python Style Guide](https://google.github.io/styleguide/pyguide.html). Use the provided `.pylintrc` for linting.

Code changes follow the rules and best practices of Home Assistant 2026.11, the minimum version in `hacs.json`, and avoid APIs that Home Assistant has announced it will deprecate or remove in 2027.

## Debugging

Enable debug logging in Home Assistant configuration.yaml:
```yaml
logger:
  default: critical
  logs:
    custom_components.xiaomi_home: debug
```

## Control Modes

- **Cloud Control**: MQTT message subscription + HTTP command API
- **Local Control**: Via Xiaomi Central Hub Gateway (firmware 3.3.0_0023+, China region only: `SUPPORT_CENTRAL_GATEWAY_CTRL` in `miot/const.py`) or LAN control (IP devices only, may be unstable)

Central gateway local control takes priority over LAN control when both are available.

## Multi-Region Support

Regions (`CLOUD_SERVERS` in `miot/const.py`): China (cn), Europe (de), India (i2), Russia (ru), Singapore (sg), USA (us)

User data is isolated per region. Integration supports multiple regions in same Home Assistant instance.

## Important Files Location

- Integration source: `custom_components/xiaomi_home/`
- Spec mappings: `custom_components/xiaomi_home/miot/specs/specv2entity.py`
- Spec filters: `custom_components/xiaomi_home/miot/specs/spec_filter.yaml`
- Translations: `custom_components/xiaomi_home/translations/` and `custom_components/xiaomi_home/miot/i18n/`
- Tests: `test/` (upstream suite) and `tests/` (the fork's unit tests)

## Fork-specific behavior to keep

### 1. Native MIIO local control
LAN control translates MIoT property writes into MIIO commands in Python, but only for the models keyed in `miot/miio_specs.py`: Yeelight desk, floor and bedside lamps (`yeelink.light.lamp*`, `yeelink.light.bslamp*`), `dmaker.fan.p5`, and `zhimi.fan.sa1`, `v2`, `v3`, `za1`, `za3` and `za4`. Other fans of the same brands, such as `zhimi.fan.za5`, use standard MIoT control. The translation lambdas in `miot_lan.py` receive the device's current properties (`props`) and the property's maximum (`max_val`), so a translation can depend on state (e.g. `["auto_delay_off", int(props.get("bright", 100)), value]`).

### 2. Entity ID migration
`__init__.py` moves legacy registry entries to the current IDs: it strips the `xiaomi_home.` and platform prefixes from old unique IDs, and when an earlier boot left a duplicate `_2` entity, it removes the duplicate and gives the legacy entity its ID back, so automations keep working. Service unique IDs are lowercase and built with `slugify_description=True` to match existing registry entries (for example `indicator_light`).

### 3. Behavior that fixes depend on
- Local-mode property polling asks the central hub gateway before LAN.
- `remove_device_async` also removes the device from memory, so a deleted device does not come back.
- `miot_device.py` rejects malformed optional services.
- `light.py` keeps modes and brightness levels in one `_effect_map`, so neither overwrites the other.
- `fan.py` uses the `_is_turning_on` flag, so concurrent commands do not send power-on twice.
- `sensor.py` caps dynamic enum options at 64, returns `None` (unavailable) for out-of-range values instead of clamping them, and gives diagnostic sensors unique IDs that include the `entry_id`; they are disabled by default.

### 4. Data structures
- **Single-pass initialization**: Platforms that look up a few known properties use `get_prop()`. Platforms that inspect every property (cover, humidifier, media_player, vacuum, water_heater, device_tracker) keep one `for prop in entity_data.props:` dispatch loop in `__init__`: it runs once per entity, and it keeps the last-match semantics for duplicate property names across services, which `get_prop()` (first match) would change.
- `MIoTEntityData` builds its name lookups (`get_prop()`, `get_event()`, `get_action()`) as dictionaries on first use, and `MIoTSpecValueList` keeps value-to-description and description-to-value dictionaries (`_val_to_desc`, `_desc_to_val`).
