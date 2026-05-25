# Xiaomi Home 整合優化：純區域網路控制與客製化輪詢策略

為了滿足進階玩家對於「完全本地化控制 (Local)」與「動態優先級控制」的需求，我們對 `Xiaomi Home` 核心代碼進行了深度的架構修改。

## 1. 總體開關：新增完全 Local 模式 (`CtrlMode.LOCAL`)

我們在 `config_flow.py` (介面設定) 與 `miot_client.py` 中引入了全新的 `CtrlMode.LOCAL` 模式。
- **UI 設定支援**：現在可以在「選項 (Options)」頁面中看到 `純區域網路 (Local)` 的控制模式。
- **絕對隔離**：在下達指令（例如開關燈、調溫度）時，如果選擇了 Local 模式，即使本地中樞網關或是 LAN 直連斷線、發生錯誤，整合也會**拒絕回退 (Fallback)**，直接向 Home Assistant 拋出錯誤。這確保了使用者的控制指令絕對不會將資料外洩或依賴外部網際網路。

## 2. 狀態輪詢策略客製化 (`poll_priority`)

- **新設定選項**：使用者可以在設定介面中調整狀態輪詢的優先順序 (`poll_priority`)。
- **策略選擇**：
  - `Cloud First` (預設)：保留官方原版的安全保護機制，優先向雲端抓取快取，避免本地網關因大量輪詢而發生癱瘓或崩潰。
  - `Local First`：進階玩家專屬。直接依序向 網關 -> LAN 抓取設備資料。
- **智慧覆寫**：如果您將總體模式 (`ctrl_mode`) 設定為強制 `LOCAL` 或是強制 `CLOUD`，系統會自動無視 `poll_priority`，確保符合總體隔離政策。

## 3. 設備屬性 (Attributes) 動態擴展：`control_path`

我們大幅增強了設備資訊的可視性。
- 在 `MIoTServiceEntity.extra_state_attributes` 屬性字典中，動態注入了 `control_path` 參數。
- 整合會即時計算每一台設備目前掛載在 `Gateway`、`LAN` 還是 `Cloud`。
- **成果**：在 Home Assistant 的開發者工具或實體頁面中，展開該設備的屬性（Attributes），即可立即看到它當下的實際控制路徑！例如：`control_path: Gateway`，讓玩家輕鬆驗證自己的設備有沒有真的走本地控制。

---

> [!TIP]
> 這些新功能在您重新啟動 Home Assistant 並重新進入整合的「選項 (Options)」畫面時即可看到。您可以針對不同的家庭與場景自由組合這些設定！
