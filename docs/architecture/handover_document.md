# Xiaomi Home (Mod) Project Handover Document

## 1. Project Background & Goals
- **Project Name**: `ha_xiaomi_home` (Home Assistant custom component for Xiaomi MIoT)
- **Refactoring Goals**: Clear technical debt (Tasks A-D) while maintaining `entity_id` stability to protect existing user automations.

## 2. Completed Refactoring Tasks
Removed over 5,200 lines of bloated code and added 1,700 lines of modular code:

- **Task A (I18n Cleanup)**: Streamlined `miot/i18n/` and `translations/` to reduce packaging footprint.
- **Task B (Deconstruct God Objects)**:
  - Deconstructed the 2,100-line monolithic `config_flow.py` into modular `config_flow.py`, `options_flow.py`, `oauth.py`, and `network.py`.
  - Extracted communication logic from `MIoTClient` into `miot_cloud_manager.py` and `miot_lan_manager.py` to achieve separation of concerns.
  - Extracted multilingual spec parsing into `miot_i18n.py`.
- **Task C (Platform Compliance & Entity Naming)**: 
  - Standardized on `has_entity_name = True`, eliminating hardcoded `entity_id` overrides.
  - Leveraged Home Assistant native `unique_id` (with `_p_{siid}_{piid}` suffix) to guarantee entity uniqueness and avoid duplicated `_2` ghost entities.
  - Maintained `async_migrate_unique_ids` migration logic for seamless upgrades.
- **Task D (Exception Handling)**: Replaced over 50 instances of broad silent exception suppresses with explicit traceback logging.

## 3. Hotfix Changelog
- **[r10] Config Flow Loader Fix (`Invalid handler specified`)**:
  - Issue: HA Loader does not recognize directory-based `config_flow/__init__.py`.
  - Fix: Flattened modular flow files to `xiaomi_home/` root and fixed relative imports.
- **[r11] Restored MIoTI18n Class**:
  - Issue: Overwritten `MIoTI18n` class in `miot_i18n.py`.
  - Fix: Restored `MIoTI18n` class with complete type annotations.
- **[r12] Entity Initialization Scope Fix**:
  - Issue: Improper indentation inside `MIoTServiceEntity.__init__`.
  - Fix: Restored correct scoping ensuring proper subscription and timer initialization.
- **[r13] Dynamic Entity Fallback Generation**:
  - Issue: Omission of general fallback conversion when spec properties are missing from `SPEC_PROP_TRANS_MAP`.
  - Fix: Restored general conversion block to dynamically instantiate `sensor`, `switch`, `number`, and `select` entities for unmapped spec properties.

## 4. Current Architectural State
1. **Setup Flow**: `config_flow.py` acts as entry point, delegating advanced settings to `options_flow.py`.
2. **Network Layer**: `MIoTClient` provides unified API, delegating requests dynamically to `miot_cloud_manager.py` (HTTP/Cloud) or `miot_lan_manager.py` (UDP/LAN).
3. **Entity Layer**: Fully compliant with `has_entity_name=True`. Device name provides base identity, while sub-entities dynamically format names according to MIoT Spec definitions.

## 5. Maintenance Recommendations
- **Entity Naming**: Never hardcode `self.entity_id = ...`. Rely on `unique_id` and `has_entity_name=True`.
- **Test Coverage**: Maintain and expand unit tests under `tests/` across cloud and LAN polling managers.
