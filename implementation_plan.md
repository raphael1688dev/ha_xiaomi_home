# Add Pure Local Control & Custom Polling Strategies

This plan implements three core features: Pure Local Mode, customizable polling priority, and dynamic device control path display in entity attributes.

## Proposed Changes

### 1. `CtrlMode` Support for Full Local Mode
- **`miot_client.py`**:
  - Add `LOCAL` to the `CtrlMode` enumeration.
  - In `set_prop_async` and `action_async` execution flows, if current mode is `CtrlMode.LOCAL`, strictly reject fallback to Cloud Control upon local (Gateway/LAN) disconnection or failure.
- **`config_flow.py`**:
  - Add `'local'` to the `ctrl_mode` dropdown selector for setup and reconfiguration flows.

### 2. Customizable Polling Priority (`poll_priority`)
- **`config_flow.py`**:
  - Add `poll_priority` options: `cloud_first` (default, avoids local network saturation) and `local_first`.
- **`miot_client.py`**:
  - Apply setting in `get_prop_async`: if `local_first`, poll Gateway -> LAN first and fallback to Cloud; if `cloud_first`, maintain cloud cache fetching first.
  - **Safety Guard**: Global `ctrl_mode` settings (`LOCAL` or `CLOUD`) strictly lock and override polling sequence.

### 3. Real-Time Device "Control Path" Attribute
- **`miot_client.py`**:
  - Implement `get_device_control_path(did) -> str` to dynamically determine active command routes (`"Gateway"`, `"LAN"`, `"Cloud"`, or `"Offline"`).
- **`miot_device.py`**:
  - Inject `control_path` into `MIoTServiceEntity.extra_state_attributes` for real-time visibility in Developer Tools and UI cards.

## Verification Plan

### Manual Verification
- **Setup Flow**: Verify `LOCAL` mode and `poll_priority` selectors appear in Options flow.
- **Offline Resilience**: Verify local operations continue without cloud timeout errors when internet connectivity is disconnected under `LOCAL` mode.
- **Attribute Verification**: Check Developer Tools for `control_path` attribute under entity state attributes.
