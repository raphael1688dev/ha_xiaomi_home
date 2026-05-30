# Xiaomi Home (Mod) 專案交接文件

## 1. 專案背景與目標 (Project Background & Goals)
- **專案名稱**: `ha_xiaomi_home` (Home Assistant custom component for Xiaomi MIoT)
- **重構目標**: 進行深度「破壞性重構」以清除龐大的技術債 (Tasks A-D)，同時**絕對遵守** `entity_id` 的穩定性，確保使用者的現有自動化不會因為升級而斷掉。

## 2. 已完成的重構任務 (Completed Refactoring Tasks)
本次重構成功移除了超過 5,200 行臃腫程式碼，並新增了 1,700 行模組化程式碼，核心任務包含：

- **Task A (多語系清理)**: 移除了 `miot/i18n/` 與 `translations/` 目錄下所有非必要的翻譯檔案，僅保留英文 (`en`)、繁體中文 (`zh-Hant`)、簡體中文 (`zh-Hans`)，大幅縮減專案體積。
- **Task B (God Objects 拆解)**:
  - 將超過 2,100 行的巨獸級 `config_flow.py` 拆解為模組化的 `config_flow.py`、`options_flow.py`、`oauth.py`、`network.py`。
  - 將包攬所有網路通訊的 `MIoTClient` 拆分為 `miot_cloud_manager.py` 與 `miot_lan_manager.py`，實現關注點分離。
  - 將規格多語系解析類別 `_MIoTSpecMultiLang` 從 `miot_spec.py` 獨立至 `miot_i18n.py`。
- **Task C (平台合規與實體命名)**: 
  - 全面導入 `has_entity_name = True` 規範，停止在程式碼中硬刻 (hardcode) `entity_id`。
  - 利用 Home Assistant 原生的 `unique_id` (帶有 `_p_{siid}_{piid}` 後綴) 來確保實體唯一性，徹底解決了以往因為重複而產生 `_2` 幽靈實體的問題。
  - 保留了 `async_migrate_unique_ids` 邏輯，確保舊版升級上來的用戶不會丟失實體。
- **Task D (異常處理優化)**: 全面掃蕩程式碼中超過 50 處的 `pylint: disable=broad-exception-caught`，改為匯入 `traceback.format_exc()`，讓以前被「靜默吃掉」的錯誤無所遁形。

## 3. 歷次熱修復紀錄 (Hotfix Changelog)
重構合併至 `main` 分支後，我們遭遇並迅速排除了 4 個隱蔽的連鎖問題，版本號推進至 `20260530r13`：

- **[r10] Config Flow 載入器崩潰 (`Invalid handler specified`)**:
  - **問題**: Home Assistant 的底層 Loader 不支援將 Config Flow 寫成資料夾 (`config_flow/__init__.py`)。
  - **修復**: 將拆分出來的流程模組攤平 (Flatten) 回 `xiaomi_home/` 根目錄，並修正所有內部相對路徑 (`from .miot...`)。
- **[r11] 遺失 MIoTI18n 類別 (`cannot import name 'MIoTI18n'`)**:
  - **問題**: 子代理在萃取 `_MIoTSpecMultiLang` 時，意外覆蓋了原本存在於 `miot_i18n.py` 提供給設定介面使用的 `MIoTI18n` 類別。
  - **修復**: 從 Git 歷史紀錄中還原 `MIoTI18n` 類別並補齊所需的 `Union`, `Any` 型別定義。
- **[r12] 實體初始化崩潰 (`AttributeError: 'Fan' object has no attribute '_pending_write_ha_state_timer'`)**:
  - **問題**: 移除不合規命名屬性時，錯將 `@property name` 放進了 `MIoTServiceEntity.__init__` 內部，導致縮排錯誤，使後方所有訂閱與計時器變數變成 Unreachable Code。
  - **修復**: 刪除錯位的 `@property`，恢復正確的 `__init__` 作用域，保證所有實體能安全獲取狀態訂閱。
- **[r13] 大量實體與特規功能消失 (動態屬性生成失效)**:
  - **問題**: 為了追求合規，不慎移除了 `miot_device.py` 內沒有定義在 `SPEC_PROP_TRANS_MAP` 時的「通用自動降級轉換」邏輯。這導致小米龐大的特規屬性（如：特規感測器、電扇擺頭、漸變時間）被拋棄。
  - **修復**: 完整補回 `General conversion` 區塊，恢復對未知 MIoT 屬性的動態 `sensor`, `switch`, `number`, `select` 生成機制。

## 4. 核心架構現況 (Current Architectural State)
1. **設定流程 (Setup Flow)**: 由 `config_flow.py` 作為進入點，將進階設定轉交 `options_flow.py`。
2. **通訊層 (Network Layer)**: `MIoTClient` 為統一介面，內部會智能切換委派給 `miot_cloud_manager.py` (HTTP/雲端) 或 `miot_lan_manager.py` (UDP/區域網路)。
3. **實體層 (Entity Layer)**: 嚴格遵守 `has_entity_name=True`。主設備使用 `name`，子屬性依照 MIoT Spec 的描述檔動態生成名稱，Home Assistant 會自動將其拼接。

## 5. 未來維護建議 (Future Maintenance & TODOs)
- **實體命名原則**: 未來新增任何平台支援時，**嚴禁**使用 `self.entity_id = ...` 強制覆蓋 ID。請繼續依靠 `unique_id` 與 `has_entity_name=True` 讓 HA 處理命名。
- **測試覆蓋率**: 目前已建立 `tests/test_miot_spec.py` 作為基礎，未來在修改 `MIoTClient` 的封包邏輯時，強烈建議補齊對 Cloud/LAN 管理器的 Mock 單元測試。
- **環境清理**: 專案根目錄下有幾支重構期間產生的暫時腳本（如 `fix_exceptions.py`、`fix_exceptions2.py`），如果確認系統運作無誤，可以在未來的 Commit 中將其刪除。
