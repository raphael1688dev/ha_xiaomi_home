# In-Depth Protocol Architecture Analysis: hass-xiaomi-miot vs Official ha_xiaomi_home

You have raised a very professional architectural question. We have conducted an in-depth source code breakdown and comparison between the third-party integration `hass-xiaomi-miot` (by al-one) and the official `ha_xiaomi_home` that we are currently tuning.

## 1. Are all products in `miio2miot_specs.py` using the legacy protocol?
**Answer: Yes, 100% of them are Legacy miio products.**

After our analysis of the `miio2miot_specs.py` source code, all the `method` fields in this massive 127KB dictionary file are "custom string commands" like `get_prop`, `get_power`, `set_usb_on`, `set_bright`.

This is exactly the standard characteristic of the "Legacy miio Profile"!
Because Xiaomi did not have a unified standard in the early days, every OEM (like Yeelight, Chuangmi, Lumi) invented their own set of string control commands. The sole purpose of this dictionary file is to act as a "Translation Jelly": brutally translating modern MIoT standard commands sent by Home Assistant (e.g., `siid:2, piid:1`) into the dialects these legacy devices can understand (e.g., `set_power`).

For "New Generation (MIoT Spec)" products, they inherently understand standard commands like `{"method":"set_properties", "params":[{"siid":2, "piid":1}]}`. Therefore, they **absolutely do not need to, and will not appear in, this dictionary file**.

---

## 2. Regarding "New Protocol Products (MIoT Spec)", what are the differences between the two integrations?
If we set aside legacy devices and purely look at how the two systems control your new generation MIoT Spec devices like `dmaker.fan.p10`, their approaches have massive differences:

### 1. Underlying Network Engine
- **`hass-xiaomi-miot` (Third-Party)**:
  Relies on the famous open-source library `python-miio` as the transport layer. It is fundamentally Synchronous, so it needs to be thrown into a background thread via HA's `run_in_executor` to send UDP packets (Port 54321). While mature, this approach incurs a higher performance overhead when facing high-frequency polling of a large number of devices.
- **`ha_xiaomi_home` (Official)**:
  The official team developed a fully Asynchronous network engine named `MIoTLanDevice` (OT Protocol) for this. It does not rely on `python-miio`, but directly uses Python's underlying async Socket (`asyncio`). This is exactly why we can add high-frequency "Unicast UDP second-level polling (Active State Polling)" with almost no noticeable impact on system resources.

### 2. Device Discovery
- **`hass-xiaomi-miot` (Third-Party)**:
  Passively sends a device state request every few tens of seconds. If there's a response, it's considered online.
- **`ha_xiaomi_home` (Official)**:
  Designed extremely rigorous `__fast_ping` and `__keep_alive` mechanisms. It proactively sends mDNS broadcasts and unicast UDP Probes to monitor the network connectivity of the devices (this is why you see the Control Path dynamically and seamlessly switching between Cloud and LAN).

### 3. HA Entity Generation Logic - [The Most Fatal Difference]
- **`hass-xiaomi-miot` (Third-Party)**:
  Adopts **"Greedy Parsing"**. It downloads the device's MIoT URN file and generates HA entities for "all" properties within it. This results in joining a fan and having HA spit out over 30 entities (including motor RPM, error codes, motherboard temperature, which are meaningless hidden properties to the user), making the interface extremely cluttered.
- **`ha_xiaomi_home` (Official)**:
  Adopts **"Strict Mapping"**. The official integration defined a rigorous `SPEC_DEVICE_TRANS_MAP` internally. Only when the device's `siid/piid` combination perfectly matches the standard definition will it accurately generate the corresponding Switch or Fan entity. If the manufacturer wrote non-standard hidden properties, the official integration will directly filter them out. This ensures your Home Assistant dashboard always remains clean and pure.

## Conclusion
`hass-xiaomi-miot` is like a Swiss Army Knife. Through a massive translation dictionary and greedy parsing, it supports as many Xiaomi devices (including legacy ones) on the market as possible, but at the cost of heavier performance and cluttered entities.

On the other hand, the official `ha_xiaomi_home` that we have currently upgraded and modified is like a stripped-down, tuned supercar. It discards the historical baggage of the legacy protocol, focuses on new generation MIoT Spec devices, and uses the lowest-level async Sockets and precise entity generation to deliver unparalleled smoothness and stability.
