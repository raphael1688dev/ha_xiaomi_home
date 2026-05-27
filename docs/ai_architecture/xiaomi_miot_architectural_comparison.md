# 協議架構深度分析：hass-xiaomi-miot 與官方 ha_xiaomi_home 的差異

您提出了非常專業的架構問題。我們針對第三方整合 `hass-xiaomi-miot` (作者 al-one) 與我們目前調校的官方 `ha_xiaomi_home` 進行了深度的原始碼拆解比對。

## 一、確認 `miio2miot_specs.py` 是否皆為舊協議產品？
**答案：是的，100% 都是舊協議 (Legacy miio) 產品。**

經過我們針對 `miio2miot_specs.py` 原始碼的分析，這份 127KB 的龐大字典檔中，所有的 `method` 欄位都是類似 `get_prop`, `get_power`, `set_usb_on`, `set_bright` 這樣的「自定義字串指令」。

這正是「舊世代 miio Profile」的標準特徵！
因為小米早期並沒有統一標準，導致每家代工廠 (例如 Yeelight, 創米, 綠米) 都有自己發明的一套字串控制指令。這份字典檔存在的唯一目的，就是充當「翻譯蒟蒻」：把 Home Assistant 發出的現代化 MIoT 標準指令 (例如 `siid:2, piid:1`)，硬生生翻譯成這些舊設備聽得懂的方言 (例如 `set_power`)。

對於「新世代 (MIoT Spec)」的產品，它們天生就聽得懂 `{"method":"set_properties", "params":[{"siid":2, "piid":1}]}` 這種標準指令，因此**完全不需要、也不會出現在這份字典檔中**。

---

## 二、針對「新協議產品 (MIoT Spec)」，兩套整合的做法有何差異？
如果我們撇開舊設備不談，單純看兩套系統是如何控制您的 `dmaker.fan.p10` 這種新世代 MIoT Spec 設備，它們的作法有著極大的差異：

### 1. 網路底層傳輸 (Network Engine)
- **`hass-xiaomi-miot` (第三方)**：
  依賴著名的開源函式庫 `python-miio` 作為傳輸底層。它本質上是同步 (Synchronous) 的，因此需要透過 HA 的 `run_in_executor` 丟到背景執行緒去發送 UDP 封包 (Port 54321)。這種做法雖然成熟，但在面對大量設備高頻率輪詢時，效能開銷較大。
- **`ha_xiaomi_home` (官方版)**：
  官方為此開發了一套名為 `MIoTLanDevice` (OT Protocol) 的全異步 (Asynchronous) 網路引擎。它不依賴 `python-miio`，而是直接使用 Python 底層非同步 Socket (asyncio)。這也就是為什麼我們能加入高頻率的「單播 UDP 秒級輪詢 (Active State Polling)」而系統資源幾乎無感的原因。

### 2. 設備上線偵測 (Device Discovery)
- **`hass-xiaomi-miot` (第三方)**：
  被動地每幾十秒發送一次設備狀態請求，如果有回應就當作上線。
- **`ha_xiaomi_home` (官方版)**：
  設計了極度嚴謹的 `__fast_ping` 與 `__keep_alive` 機制。會主動發送 mDNS 廣播與單播 UDP 探針 (Probes) 去監控設備的網路連通性 (這也就是為什麼您會看到 Control Path 會在 Cloud 與 LAN 之間動態無縫切換的原因)。

### 3. HA 實體生成邏輯 (Entity Generation) - 【最致命的差異】
- **`hass-xiaomi-miot` (第三方)**：
  採用**「貪婪生成 (Greedy Parsing)」**。它會把設備的 MIoT URN 文件下載下來，然後把裡面「所有」的屬性全部生成 HA 的實體。這導致您加入一台電風扇，HA 裡可能會噴出 30 幾個實體（包含馬達轉速、錯誤碼、主機板溫度等對使用者毫無意義的隱藏屬性），介面極度雜亂。
- **`ha_xiaomi_home` (官方版)**：
  採用**「嚴格匹配 (Strict Mapping)」**。官方在代碼內部定義了嚴謹的 `SPEC_DEVICE_TRANS_MAP`。只有當設備的 `siid/piid` 組合完全符合標準定義時，才會精準地生成對應的 Switch 或 Fan 實體。如果廠商寫了不標準的隱藏屬性，官方整合會直接過濾掉。這確保了您的 Home Assistant 儀表板永遠保持乾淨、純粹。

## 總結
`hass-xiaomi-miot` 就像是一把瑞士刀，透過龐大的翻譯字典與貪婪的解析，盡可能支援了市面上所有的（包含舊的）小米設備，但代價是效能較重、實體雜亂。

而我們目前升級改造過的官方 `ha_xiaomi_home`，則是一台經過輕量化改裝的超跑。它捨棄了舊協議的歷史包袱，專注於新世代 MIoT Spec 設備，用最底層的異步 Socket 與精準的實體生成，帶來了無可比擬的流暢度與穩定性。
