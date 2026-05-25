# 新增純區域網路控制與客製化輪詢策略 (Add Pure Local Control & Custom Polling Strategies)

本計畫將實作您要求的三項功能：完全 Local 模式、客製化的查詢優先級，以及在設備屬性中動態顯示目前的控制路徑。

## Open Questions

> [!IMPORTANT]
> **翻譯字串 (Translation Strings) 確認**
> 為了讓使用者在 Home Assistant UI 設定時能夠看到友善的名稱，我預計會將 `ctrl_mode` 的選項中多加入一個 `local`，以及加入一個新的設定項目 `poll_priority` (`cloud_first` / `local_first`)。我們是否需要一併更新所有的 `.json` 翻譯檔案？(這可能會涉及多個語系)。或是以英文設定為優先即可？

## Proposed Changes

### 1. `CtrlMode` 支援完全 Local 模式
- **`miot_client.py`**:
  - 在 `CtrlMode` 列舉 (Enum) 中加入 `LOCAL`。
  - 在 `set_prop_async` 與 `action_async` 的指令執行流程中，如果當前為 `CtrlMode.LOCAL`，則即使 Local (Gateway/LAN) 無法連接或執行失敗，也會直接拋出異常，**拒絕回退 (Fallback) 到 Cloud Control**。
- **`config_flow.py`**:
  - 將 `'local'` 加入控制模式 (`ctrl_mode`) 的下拉式設定選項中，允許使用者在安裝或重新設定時選取。

### 2. 客製化輪詢優先順序 (`poll_priority`)
- **`config_flow.py`**:
  - 新增 `poll_priority` 設定選項，提供兩個選項：`cloud_first`（預設，避免轟炸區網）與 `local_first`。
- **`miot_client.py`**:
  - 在 `get_prop_async` 方法中套用此設定：若為 `local_first`，則先嘗試從網關或 LAN 抓取資料，若失敗再調用雲端；若為 `cloud_first`，則保持現有設計。
  - **安全防護機制**：若總體控制模式 (`ctrl_mode`) 已經被設為 `LOCAL` 或 `CLOUD`，則會強制覆寫並鎖死此優先順序。

### 3. 動態產生設備目前的「控制路徑」資訊
- **`miot_client.py`**:
  - 實作一個新方法 `get_device_control_path(did) -> str`，它會根據設備目前是否存在於 `_device_list_gateway`, `_device_list_lan` 或 `_device_list_cloud`，以及目前的 `ctrl_mode` 狀態，動態計算出**現在下達指令會走哪條連線路徑**（回傳 `"Gateway"`, `"LAN"`, `"Cloud"` 或 `"Offline"`）。
- **`miot_device.py`**:
  - 為了不影響既有結構，將針對 `MIoTServiceEntity` 動態附加該資訊。
  - 在原先的 `extra_state_attributes` 擴展欄位中，自動注入 `control_path` 屬性。這樣一來，使用者只要點開 Home Assistant 上的任何設備實體（不論是開關、冷氣還是感測器），都能在屬性中清楚看到 `control_path: Gateway/LAN/Cloud`。

## Verification Plan

### Manual Verification
- **安裝測試**：重新執行整合安裝，驗證設定流程中是否出現了 `LOCAL` 模式與 `poll_priority` 選項。
- **執行測試**：將模式設定為 `LOCAL` 並切斷網際網路，驗證設備控制是否依舊正常且不出現連線雲端超時的錯誤。
- **狀態顯示測試**：在開發者工具中，檢查任意實體的 `extra_state_attributes` 是否多出了 `control_path` 資訊，且拔除網路線後該屬性是否會隨之變化。
