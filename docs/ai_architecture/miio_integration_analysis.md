# 舊世代 miio 協議本地化整合可行性分析

為了解答「是否能將舊世代 miio 控制協議整合進官方的 `ha_xiaomi_home` 專案中」這個問題，我們需要從底層架構、網路層與 payload 轉換層進行深度的技術剖析。

## 1. 網路加密層 (Network Layer) : 高度相似
首先，好消息是：不論是新世代的 **MIoT Spec (OT Protocol)** 還是舊世代的 **Legacy miio**，它們在局域網內都是走 UDP Port `54321`，且封包的加密方式（32-byte Header + Token 加密的 AES-128-CBC payload）幾乎是一模一樣的。
這代表我們目前的 `MIoTLanDevice` 底層 socket 連線庫，理論上具備與舊設備通訊的能力。

## 2. 封包邏輯層 (Payload Layer) : 根本性分歧
壞消息在於通訊格式。小米在設計 `ha_xiaomi_home` 時，是完全建立在 **「MIoT Spec V2 語義模型」** 之上的：
- **新世代 (MIoT Spec)**：所有控制皆基於 `siid` (Service ID) 與 `piid` (Property ID)。
  - 例：開燈 `{"method":"set_properties", "params":[{"siid":2, "piid":1, "value":True}]}`
- **舊世代 (Legacy miio)**：所有控制皆基於各家廠商自定義的**字串指令**。
  - 例：開燈 `{"method":"set_power", "params":["on"]}`
  - 例：調光 `{"method":"set_bright", "params":[50]}`

## 3. 整合的痛點與挑戰：翻譯矩陣 (Translation Matrix)
如果我們要在這套系統內支援局域網控制 `yeelink.light.bslamp2` 這種舊設備，我們就會遇到一道「翻譯高牆」。

因為 `ha_xiaomi_home` 內部所有的實體 (Entity) 都是根據 `siid` 跟 `piid` 生成的。若要轉向本地控制，我們必須在 `miot_lan.py` 中寫入一個**翻譯引擎**：
1. 攔截系統發出的 `siid=2, piid=1` 開燈請求。
2. 判斷目前的設備 `model` 是不是舊型號。
3. 查閱一個**龐大的翻譯對照表**，將 `siid=2, piid=1` 翻譯成該設備專用的字串指令（例如 `set_power` 或 `set_pwr`，每一台舊設備的寫法都不同！）。

這個「翻譯對照表」的維護成本極其龐大，包含了數千款歷史設備的指令集映射。這就是為什麼官方會直接寫死一個 `profile_models.yaml` 黑名單，因為官方不打算把這套龐大的歷史包袱寫進這個全新架構的開源專案中。小米的做法是：**把這層繁重的「翻譯工作」留在小米雲端伺服器上處理**。

## 4. 可行解決方案評估

### 方案 A：自建輕量級翻譯層 (Hardcore Translation)
- **做法**：在 `miot_lan.py` 內建一個攔截器，只針對您常用的幾款舊設備（如床頭燈 2）寫死轉換邏輯。
- **優點**：可以在這套整合內實現本地秒控。
- **缺點**：擴展性極差，每買一台舊設備就要改一次底層源碼。且無法與上游官方開源庫保持乾淨的合併。

### 方案 B：維持雲端控制 (Cloud Proxy)
- **做法**：維持現狀。
- **優點**：讓小米雲端的超級伺服器去處理複雜的 `MIoT Spec` 轉 `miio Profile` 的翻譯，我們只管發送標準的 MIoT 指令。穩定且零維護成本。

### 方案 C：使用 HA 專屬原生整合 (Native HA Component)
- **做法**：將新舊設備分流。新世代設備交由我們現在改裝得極其完美的 `ha_xiaomi_home` 處理；舊世代設備（如 Yeelight 燈具、舊版小米插座）直接使用 Home Assistant 內建的 `Yeelight` 或 `Xiaomi Miio` 整合接入。
- **優點**：這是開源社群最推薦的做法。這些原生整合已經內建了龐大的舊設備字串指令表，100% 走區網控制，且不依賴任何雲端。

## 結論
要在架構如此現代化的 `ha_xiaomi_home` 中強行塞入舊世代的協議翻譯機，**技術上可行，但架構上極度不優雅且難以維護**。
這猶如在特斯拉的電動車系統裡硬生生裝進一個能吃汽油的化油器。最乾淨俐落的做法是採用**方案 B（交由雲端翻譯）**或**方案 C（讓專業的舊整合處理舊設備）**。
