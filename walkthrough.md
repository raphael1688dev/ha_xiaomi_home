# Xiaomi Home Optimization: Local-Only Control & Customized Polling Strategies

To satisfy advanced user requirements for full local control and dynamic priority policies, significant architectural enhancements were applied to the `Xiaomi Home` core integration.

## 1. Master Mode: Dedicated Local-Only Mode (`CtrlMode.LOCAL`)

Introduced the dedicated `CtrlMode.LOCAL` mode across `options_flow.py`, `config_flow.py`, and `miot_client.py`.
- **UI Configuration Support**: Select `Local Only` control mode within the integration Options menu.
- **Strict Network Isolation**: When issuing commands (e.g. toggle lights, set temperature), if Local mode is chosen, the integration strictly refrains from falling back to cloud servers even if local gateways or direct LAN connections disconnect or experience errors. This guarantees that control commands never leak externally or depend on external Internet connectivity.

## 2. Customizable Polling Priority (`poll_priority`)

- **Configurable Options**: Users can adjust device state polling order (`poll_priority`) in the Options flow.
- **Strategy Selection**:
  - `Cloud First` (Default): Preserves upstream protection mechanisms, fetching from cloud cache first to prevent local gateway overload from aggressive polling.
  - `Local First`: Tailored for local enthusiasts, directly polling via Gateway -> LAN in prioritized sequence.
- **Strict Override**: Setting the global control mode (`ctrl_mode`) to strict `LOCAL` or `CLOUD` automatically takes precedence over `poll_priority` to honor global network isolation policies.

## 3. Dynamic Attribute Exposure: `control_path`

Significantly enhanced device route visibility.
- Dynamically injects `control_path` into `MIoTServiceEntity.extra_state_attributes`.
- The integration calculates real-time active control routes (`Gateway`, `LAN`, or `Cloud`).
- **Result**: View `control_path: Gateway` or `control_path: LAN` in Developer Tools or entity attribute cards to verify local communication paths.

---

> [!TIP]
> These settings can be configured via Home Assistant > Settings > Devices & Services > Xiaomi Home > Configure / Options.
