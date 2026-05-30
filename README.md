# Xiaomi Home Integration for Home Assistant

[English](./README.md) | [简体中文](./doc/README_zh.md)

Xiaomi Home Integration is an integrated component of Home Assistant supported by Xiaomi official. It allows you to use Xiaomi IoT smart devices in Home Assistant.

## 🚀 Mod Features (raphael1688dev fork)

This custom fork includes several massive enhancements and compliance upgrades over the official version:

- **Home Assistant 2026.5.0 Full Compliance**: 
  - Eradicated legacy Entity Naming violations (removed leading spaces and redundant name properties) to strictly comply with `has_entity_name = True`.
  - Audited and guaranteed 100% compliance with non-blocking I/O, `async_forward_entry_setups`, standard Enums (`SensorDeviceClass`, `EntityCategory`), and deprecated constants cleanup.
- **Entity Registry Seamless Migration**:
  - Cleansed the technical debt of the official Xiaomi integration which forced the `xiaomi_home.` domain into the `unique_id` of all entities.
  - Built-in **Auto-Migration Script**: Seamlessly converts all legacy `xiaomi_home.` unique IDs in the Home Assistant registry on startup. It strictly preserves the original case-sensitivity to guarantee **zero broken automations, Node-RED flows, or dashboards**.
- **Local Control for Non-CN Servers**: Enables local LAN control for Wi-Fi devices even when registered to overseas servers (e.g., Singapore), bypassing the official "Gateway Suicide" restriction.
- **Enhanced Configuration Flow**: Adds an integration option to explicitly set the `CtrlMode` (Auto / Cloud / Local) and poll priorities.
- **New Diagnostic Sensors**:
  - **Control Path Sensor**: Real-time display of the current device control path (Cloud / LAN / Gateway).
  - **IP Address Sensor**: Exposes the local IP address of the device natively in the Device Info diagnostics section.
- **Active State Polling for Wi-Fi Devices (Unicast UDP)**: 
  - Implements proactive state polling for Wi-Fi devices every 30 seconds, bypassing the official integration's reliance on UDP LAN broadcasts which are often blocked by VLANs. Ensures physical control states sync immediately to Home Assistant.
  - **Cloud-Ban Prevention**: The native polling handler has been entirely refactored to respect `CtrlMode` and `Poll Priority` locally, routing polling traffic to the LAN (Unicast) instead of flooding the Xiaomi Cloud API. This prevents account rate-limiting while providing lightning-fast state synchronization.

## Installation

> Home Assistant version requirement:
>
> - Core $\geq$ 2026.5.0
> - Operating System $\geq$ 13.0

### Method 1: Git clone from GitHub

```bash
cd config
git clone https://github.com/XiaoMi/ha_xiaomi_home.git
cd ha_xiaomi_home
./install.sh /config
```

We recommend this installation method, for it is convenient to switch to a tag when updating `xiaomi_home` to a certain version.

For example, update to version v1.0.0

```bash
cd config/ha_xiaomi_home
git fetch
git checkout v1.0.0
./install.sh /config
```

### Method 2: [HACS](https://hacs.xyz/)

One-click installation from HACS:

[![Open your Home Assistant instance and open the Xiaomi Home integration inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=XiaoMi&repository=ha_xiaomi_home&category=integration)

Or, HACS > In the search box, type **Xiaomi Home** > Click **Xiaomi Home**, getting into the detail page > DOWNLOAD

### Method 3: Manually installation via [Samba](https://github.com/home-assistant/addons/tree/master/samba) / [FTPS](https://github.com/hassio-addons/addon-ftp)

Download and copy `custom_components/xiaomi_home` folder to `config/custom_components` folder in your Home Assistant.

## Configuration

### Login

[Settings > Devices & services > ADD INTEGRATION](https://my.home-assistant.io/redirect/brand/?brand=xiaomi_home) > Search `Xiaomi Home` > NEXT > Click here to login > Sign in with Xiaomi account

[![Open your Home Assistant instance and start setting up a new Xiaomi Home integration instance.](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=xiaomi_home)

### Add MIoT Devices

After logging in successfully, a dialog box named "Select Home and Devices" pops up. You can select the home containing the device that you want to import in Home Assistant.

### Multiple User Login

After a Xiaomi account login and its user configuration are completed, you can continue to add other Xiaomi accounts in the configured Xiaomi Home Integration page.

Method: [Settings > Devices & services > Configured > Xiaomi Home](https://my.home-assistant.io/redirect/integration/?domain=xiaomi_home) > ADD HUB > NEXT > Click here to login > Sign in with Xiaomi account

[![Open your Home Assistant instance and show Xiaomi Home integration.](https://my.home-assistant.io/badges/integration.svg)](https://my.home-assistant.io/redirect/integration/?domain=xiaomi_home)

### Update Configurations

You can change the configurations in the "Configuration Options" dialog box, in which you can update your user nickname and the list of the devices importing from Xiaomi Home APP, etc.

Method: [Settings > Devices & services > Configured > Xiaomi Home](https://my.home-assistant.io/redirect/integration/?domain=xiaomi_home) > CONFIGURE > Select the option to update

### Debug Mode for Action

You can manually send Action command message with parameters to the device when the debug mode for action is activated. The user interface for sending the Action command with parameters is shown as a Text entity.

Method: [Settings > Devices & services > Configured > Xiaomi Home](https://my.home-assistant.io/redirect/integration/?domain=xiaomi_home) > CONFIGURE > Debug mode for action

## Security

Xiaomi Home Integration and the affiliated cloud interface is provided by Xiaomi officially. You need to use your Xiaomi account to login to get your device list. Xiaomi Home Integration implements OAuth 2.0 login process, which does not keep your account password in the Home Assistant application. However, due to the limitation of the Home Assistant platform, the user information (including device information, certificates, tokens, etc.) of your Xiaomi account will be saved in the Home Assistant configuration file in clear text after successful login. You need to ensure that your Home Assistant configuration file is properly stored. The exposure of your configuration file may result in others logging in with your identity.

> If you suspect that your OAuth 2.0 token has been leaked, you can revoke the login authorization of your Xiaomi account by the following steps: Xiaomi Home APP -> Profile -> Click your username and get into Xiaomi Account management page -> Basic info: Apps -> Xiaomi Home (Home Assistant Integration) -> Remove

## FAQ

- Does Xiaomi Home Integration support all Xiaomi smart devices?

  Xiaomi Home Integration currently supports most categories of the smart device. Only a few categories are not supported. They are Bluetooth device, infrared device and virtual device.

- Does Xiaomi Home Integration support multiple Xiaomi accounts?

  Yes, it supports multiple Xiaomi accounts. Furthermore, Xiaomi Home Integration allows that devices belonging to different accounts can be added to a same area.

- Why do some older devices (e.g., Yeelight Bedside Lamp 2, old smart plugs) always use Cloud control instead of LAN control?

  The LAN control engine (`miot_lan`) of this integration is built exclusively for the modern **MIoT Spec (OT Protocol)**. Older devices use the legacy **miio Profile** protocol, which uses custom string-based commands (e.g., `set_power`) instead of standardized Service/Property IDs (`siid`/`piid`). 
  Because this integration does not contain the massive translation dictionaries required to convert MIoT Spec payloads into legacy `miio` payloads locally, it explicitly blacklists these old models (defined in `profile_models.yaml`). For these legacy devices, the integration seamlessly falls back to **Cloud Control**, letting the Xiaomi Cloud servers handle the protocol translation.
  If you require 100% local control for these legacy devices, we recommend using Home Assistant's native **Yeelight** or **Xiaomi Miio** integrations alongside this one.

- Does Xiaomi Home Integration support local mode?

  Local mode is implemented by [Xiaomi Central Hub Gateway](https://www.mi.com/shop/buy/detail?product_id=15755&cfrom=search) (firmware version 3.3.0_0023 and above) or Xiaomi smart devices with [built-in central hub gateway](https://github.com/XiaoMi/ha_xiaomi_home/wiki/Central-hub-gateway-device-models) (software version 0.8.9 and above) inside. If you do not have a Xiaomi central hub gateway or other devices having central hub gateway function, all control commands are sent through Xiaomi Cloud. The firmware for Xiaomi central hub gateway including the built-in central hub gateway supporting Home Assistant local mode feature has been released.

  Xiaomi central hub gateway is only available in mainland China. In other regions, it is not available.

  Xiaomi Home Integration can also implement partial local mode by enabling Xiaomi LAN control function. Xiaomi LAN control function can only control IP devices (devices connected to the router via WiFi or ethernet cable) in the same local area network as Home Assistant. It cannot control BLE Mesh, ZigBee, etc. devices. This function may cause some abnormalities. We recommend NOT using this function. Xiaomi LAN control function is enabled by [Settings > Devices & services > Configured > Xiaomi Home](https://my.home-assistant.io/redirect/integration/?domain=xiaomi_home) > CONFIGURE > Update LAN control configuration.

  Xiaomi LAN control function is not restricted by region. It is available in all regions. However, if there is a central gateway in the local area network where Home Assistant is located, even Xiaomi LAN control function is enabled in the integration, it will not take effect.

- In which regions is Xiaomi Home Integration available?

  Xiaomi Home Integration can be used in the mainland of China, Europe, India, Russia, Singapore, and USA. As user data in Xiaomi Cloud of different regions is isolated, you need to choose your region when importing MIoT devices in the configuration process. Xiaomi Home Integration allows you to import devices of different regions to a same area.

## Principle of Messaging

### Control through the Cloud

<div align=center>
<img src="./doc/images/cloud_control.jpg" width=300>

Image 1: Cloud control architecture

 </div>

Xiaomi Home Integration subscribes to the interested device messages on the MQTT Broker in MIoT Cloud. When a device property changes or a device event occurs, the device sends an upstream message to MIoT Cloud, and the MQTT Broker pushes the subscribed device message to Xiaomi Home Integration. Because Xiaomi Home Integration does not need to poll to obtain the current device property value in the cloud, it can immediately receive the notification message when the properties change or the events occur. Thanks to the message subscription mechanism, Xiaomi Home Integration only queries the properties of all devices from the cloud once when the integration configuration is completed, which puts little access pressure on the cloud.

Xiaomi Home Integration sends command messages to the devices via the HTTP interface of MIoT Cloud to control devices. The device reacts and responds after receiving the downstream message sent forward by MIoT Cloud.

### Control locally

<div align=center>
<img src="./doc/images/local_control.jpg" width=300>

Image 2: Local control architecture

</div>

Xiaomi central hub gateway contains a standard MQTT Broker, which implements a complete subscribe-publish mechanism. Xiaomi Home Integration subscribes to the interested device messages through Xiaomi central hub gateway. When a device property changes or a device event occurs, the device sends an upstream message to Xiaomi central hub gateway, and the MQTT Broker pushes the subscribed device message to Xiaomi Home Integration.

When Xiaomi Home Integration needs to control a device, it publishes a device command message to the MQTT Broker, which is then forwarded to the device by Xiaomi central hub gateway. The device reacts and responds after receiving the downstream message from the gateway.

## Mapping Relationship between MIoT-Spec-V2 and Home Assistant Entity

[MIoT-Spec-V2](https://iot.mi.com/v2/new/doc/introduction/knowledge/spec) is the abbreviation for MIoT Specification Version 2, which is an IoT protocol formulated by Xiaomi IoT platform to give a standard functional description of IoT devices. It includes function definition (referred to as data model by other IoT platforms), interaction model, message format, and encoding.

In MIoT-Spec-V2 protocol, a product is defined as a device. A device contains several services. A service may have some properties, events and actions. Xiaomi Home Integration creates Home Assistant entities according to MIoT-Spec-V2. The conversion relationship is as follows.

### General Conversion

- Property

| access       | format                | value-list   | value-range | Entity in Home Assistant |
| ------------ | --------------------- | ------------ | ----------- | ------------------------ |
| writable     | string                | -            | -           | Text                     |
| writable     | bool                  | -            | -           | Switch                   |
| writable     | not string & not bool | existent     | -           | Select                   |
| writable     | not string & not bool | non-existent | existent    | Number                   |
| not writable | -                     | -            | -           | Sensor                   |

- Event

MIoT-Spec-V2 event is transformed to Event entity in Home Assistant. The event's parameters are also passed to entity's `_trigger_event`.

MIoT-Spec-V2 event's arguments field is the list of parameters of the event. The list elements represent the piid of the property in the same service. For example, the [MIoT-Spec-V2](http://poc.miot-spec.srv/miot-spec-v2/instance?type=urn:miot-spec-v2:device:remote-control:0000A021:xiaomi-mcn002:1:0000D057) of the Xiaomi Wireless Double-key Switch contains the siid=2 Switch Sensor service. The eiid=1014 Long Press event of the service is triggered when a button is long pressed. The debug level log will print `Press and hold, attributes: {'Button Type': 1}`. This is an example log that the button type is 1, which means the right button is long pressed.

- Action

| in        | Entity in Home Assistant |
| --------- | ------------------------ |
| empty     | Button                   |
| not empty | Notify                   |

If the debug mode for action is activated, the Text entity will be created when the "in" field in the action spec is not empty.

The "Attribute" item in the entity details page displays the format of the input parameter which is an ordered list, enclosed in square brackets []. The string elements in the list are enclosed in double quotation marks "".

For example, the "Attributes" item in the details page of the Notify entity converted by the "Intelligent Speaker Execute Text Directive" action of xiaomi.wifispeaker.s12 siid=5, aiid=5 instance shows the action params as `[Text Content(str), Silent Execution(bool)]`. A properly formatted input is `["Hello", true]`.

### Specific Conversion

MIoT-Spec-V2 uses URN for defining types. The format is `urn:<namespace>:<type>:<name>:<value>[:<vendor-product>:<version>]`, in which `name` is a human-readable word or phrase describing the instance of device, service, property, event and action. Xiaomi Home Integration first determines whether to convert the MIoT-Spec-V2 instance into a specific Home Assistant entity based on the instance's name. For the instance that does not meet the specific conversion rules, general conversion rules are used for conversion.

`namespace` is the namespace of MIoT-Spec-V2 instance. When its value is miot-spec-v2, it means that the specification is defined by Xiaomi. When its value is bluetooth-spec, it means that the specification is defined by Bluetooth Special Interest Group (SIG). When its value is not miot-spec-v2 or bluetooth-spec, it means that the specification is defined by other vendors. If MIoT-Spec-V2 `namespace` is not miot-spec-v2, a star mark `*` is added in front of the entity's name .

- Device

The conversion follows `SPEC_DEVICE_TRANS_MAP`.

```
{
    '<device instance name>':{
        'required':{
            '<service instance name>':{
                'required':{
                    'properties': {
                        '<property instance name>': set<property access: str>
                    },
                    'events': set<event instance name: str>,
                    'actions': set<action instance name: str>
                },
                'optional':{
                    'properties': set<property instance name: str>,
                    'events': set<event instance name: str>,
                    'actions': set<action instance name: str>
                }
            }
        },
        'optional':{
            '<service instance name>':{
                'required':{
                    'properties': {
                        '<property instance name>': set<property access: str>
                    },
                    'events': set<event instance name: str>,
                    'actions': set<action instance name: str>
                },
                'optional':{
                    'properties': set<property instance name: str>,
                    'events': set<event instance name: str>,
                    'actions': set<action instance name: str>
                }
            }
        },
        'entity': str
    }
}
```

The "required" field under "device instance name" indicates the required services of the device. The "optional" field under "device instance name" indicates the optional services of the device. The "entity" field indicates the Home Assistant entity to be created. The "required" and the "optional" field under "service instance name" are required and optional properties, events and actions of the service respectively. The value of "property instance name" under "required" "properties" field is the access mode of the property. The condition for a successful match is that the value of "property instance name" is a subset of the access mode of the corresponding MIoT-Spec-V2 property instance.

Home Assistant entity will not be created if MIoT-Spec-V2 device instance does not contain all required services, properties, events or actions.

- Service

The conversion follows `SPEC_SERVICE_TRANS_MAP`.

```
{
    '<service instance name>':{
        'required':{
            'properties': {
                '<property instance name>': set<property access: str>
            },
            'events': set<event instance name: str>,
            'actions': set<action instance name: str>
        },
        'optional':{
            'properties': set<property instance name: str>,
            'events': set<event instance name: str>,
            'actions': set<action instance name: str>
        },
        'entity': str
    }
}
```

The "required" field under "service instance name" indicates the required properties, events and actions of the service. The "optional" field indicates the optional properties, events and actions of the service. The "entity" field indicates the Home Assistant entity to be created. The value of "property instance name" under "required" "properties" field is the access mode of the property. The condition for a successful match is that the value of "property instance name" is a subset of the access mode of the corresponding MIoT-Spec-V2 property instance.

Home Assistant entity will not be created if MIoT-Spec-V2 service instance does not contain all required properties, events or actions.

- Property

The conversion follows `SPEC_PROP_TRANS_MAP`.

```
{
    'entities':{
        '<entity name>':{
            'format': set<str>,
            'access': set<str>
        }
    },
    'properties': {
        '<property instance name>':{
            'device_class': str,
            'entity': str
        }
    }
}
```

The "format" field under "entity name" represents the data format of the property, and matching with one value indicates a successful match. The "access" field under "entity name" represents the access mode of the property, and matching with all values is considered a successful match.

The "entity" field under "property instance name", of which value is one of entity name under "entities" field, indicates the Home Assistant entity to be created. The "device_class" field under "property instance name" indicates the Home Assistant entity's `_attr_device_class`.

- Event

The conversion follows `SPEC_EVENT_TRANS_MAP`.

```
{
    '<event instance name>': str
}
```

The value of the event instance name indicates `_attr_device_class` of the Home Assistant entity to be created.

### MIoT-Spec-V2 Filter

`spec_filter.yaml` is used to filter out the MIoT-Spec-V2 instance that will not be converted to Home Assistant entity.

The format of `spec_filter.yaml` is as follows.

```yaml
<MIoT-Spec-V2 device instance urn without the version field>:
    services: list<service_iid: str>
    properties: list<service_iid.property_iid: str>
    events: list<service_iid.event_iid: str>
    actions: list<service_iid.action_iid: str>
```

The key of `spec_filter.yaml` dictionary is the urn excluding the "version" field of the MIoT-Spec-V2 device instance. The firmware of different versions of the same product may be associated with the MIoT-Spec-V2 device instances of different versions. It is required that the MIoT-Spec-V2 instance of a higher version must contain all MIoT-Spec-V2 instances of the lower versions when a vendor defines the MIoT-Spec-V2 of its product on MIoT platform. Thus, the key of `spec_filter.yaml` does not need to specify the version number of MIoT-Spec-V2 device instance.

The value of "services", "properties", "events" or "actions" fields under "device instance" is the instance id (iid) of the service, property, event or action that will be ignored in the conversion process. Wildcard matching is supported.

Example:

```yaml
urn:miot-spec-v2:device:television:0000A010:xiaomi-rmi1:
    services:
    - '*'   # Filter out all services. It is equivalent to completely ignoring the device with such MIoT-Spec-V2.
urn:miot-spec-v2:device:gateway:0000A019:xiaomi-hub1:
    services:
    - '3'   # Filter out the siid=3 service.
    properties:
    - '4.*' # Filter out all properties in the siid=4 service.
    events:
    - '4.1' # Filter out the eiid=1 event in the siid=4 service.
    actions:
    - '4.1' # Filter out the aiid=1 action in the siid=4 service.
```

Device information service (urn:miot-spec-v2:service:device-information:00007801) of all devices will never be converted to Home Assistant entity.

## Multiple Language Support

There are 13 languages available for selection in the config flow language option of Xiaomi Home, including Simplified Chinese, Traditional Chinese, English, Spanish, Russian, French, German, Japanese, Italian, Dutch, Portuguese, Brazilian Portuguese, and Turkish. The config flow page in Simplified Chinese and English has been manually reviewed by the developer. Other languages are translated by machine translation or community contributions. If you want to modify the words and sentences in the config flow page, you need to modify the json file of the certain language in `custom_components/xiaomi_home/translations/` and `custom_components/xiaomi_home/miot/i18n/` directory.

When displaying Home Assistant entity name, Xiaomi Home downloads the multiple language file configured by the device vendor from MIoT Cloud, which contains translations for MIoT-Spec-V2 instances of the device. `multi_lang.json` is a locally maintained multiple language dictionary, which has a higher priority than the multiple language file obtained from the cloud and can be used to supplement or modify the multiple language translation of devices.

The format of `multi_lang.json` is as follows.

```
{
    "<MIoT-Spec-V2 device instance>": {
        "<language code>": {
            "<instance code>": <translation: str>
        }
    }
}
```

The key of `multi_lang.json` dictionary is the urn excluding the "version" field of the MIoT-Spec-V2 device instance.

The language code is zh-Hans, zh-Hant, en, es, ru, fr, de, ja, it, nl, pt, pt-BR, or tr, corresponding to the 13 selectable languages mentioned above.

The instance code is the code of the MIoT-Spec-V2 instance, which is in the format of:

```
service:<siid>                  # service
service:<siid>:property:<piid>  # property
service:<siid>:property:<piid>:valuelist:<index> # The index of a value in the value-list of a property
service:<siid>:event:<eiid>     # event
service:<siid>:action:<aiid>    # action
```

siid, piid, eiid, aiid and value are all decimal three-digit integers.

Example:

```
{
    "urn:miot-spec-v2:device:health-pot:0000A051:chunmi-a1": {
        "zh-Hant": {
            "service:002": "養生壺",
            "service:002:property:001": "工作狀態",
            "service:002:property:001:valuelist:000": "待機中",
            "service:002:action:002": "停止烹飪",
            "service:005:event:001": "烹飪完成"
        }
    }
}
```

> If you edit any files in the `custom_components/xiaomi_home/miot/specs` directory (`spec_filter.yaml`, `spec_modify.yaml`, `multi_lang.json`, etc.) in your Home Assistant, you need to update the entity conversion rule in the integration's CONFIGURE page to take effect. Method: [Settings > Devices & services > Configured > Xiaomi Home](https://my.home-assistant.io/redirect/integration/?domain=xiaomi_home) > CONFIGURE > Update entity conversion rules

## Documents

- [License](./LICENSE.md)
- Contribution Guidelines: [English](./CONTRIBUTING.md) | [简体中文](./doc/CONTRIBUTING_zh.md)
- [ChangeLog](./CHANGELOG.md)
- Development Documents: https://developers.home-assistant.io/docs/creating_component_index
- [FAQ](https://github.com/XiaoMi/ha_xiaomi_home/wiki)

## Directory Structure

- miot: core code.
- miot/miot_client: Adding a login user in the integration needs adding a miot_client instance.
- miot/miot_cloud: Contains functions related to the cloud service, including OAuth login process, HTTP interface functions (to get the user information, to send the device control command, etc.)
- miot/miot_device: Device entity, including device information, processing logic of property, event and action.
- miot/miot_mips: Message bus for subscribing and publishing method.
- miot/miot_spec: Parse MIoT-Spec-V2.
- miot/miot_lan: Device LAN control, including device discovery, device control, etc.
- miot/miot_mdns: Central hub gateway service LAN discovery.
- miot/miot_network: Obtain network status and network information.
- miot/miot_storage: File storage for the integration.
- miot/test: Test scripts.
- config_flow: Config flow.

## New Features & Enhancements (Version 20260527r3)
- **Local Control via MIIO Protocol (Zero-Delay, Zero-Technical-Debt)**: Implemented native Python transpilation for 19 whitelisted MIIO legacy devices (including `yeelink.light.lamp*`, `yeelink.light.bslamp*`, `zhimi.fan.*`, and `dmaker.fan.*`). These devices now enjoy instant, local execution without relying on cloud polling, bypassing the heavy Node.js translation layer.
- **Robust Entity ID Migration Recovery**: Fixed a critical upstream bug in the Home Assistant unique_id migration script that caused legacy entity IDs (e.g., `sensor.*`, `light.*`) to be improperly renamed. 
  - **Case Sensitivity & Slugify Fix**: Enforced strict lowercase mapping and `slugify_description=True` (especially for Service entities like `indicator_light`) for all newly generated `unique_id`s in `miot_device.py` to perfectly match historical HA registry entries. This fully resolves issues where entities like `Indicator Light` (with spaces and capitalization) would crash against legacy `indicator_light` (slugified) entries.
  - **Auto-Recovery**: Enhanced `__init__.py` to automatically detect and delete erroneously created duplicate entities (like `_2`), seamlessly restoring legacy entity IDs and preserving all user automations.
- **Included Models (Strict Whitelist)**: To guarantee the highest performance and zero technical debt, this native transpilation layer is strictly limited to 19 core smart home components from specific reliable brands:
  - **Yeelight (易來)**: Only `yeelink.light.lamp*` (檯燈/落地燈) and `yeelink.light.bslamp*` (床頭燈) series.
  - **Smartmi & Dmaker (智米/造夢者)**: All `zhimi.fan` and `dmaker.fan` series.
  - *(All other appliances, sensors, and brands are explicitly excluded from this local translation layer)*

## New Features & Enhancements (Version 20260527r7)
- **Elimination of 8 Critical Logic Bugs**: Deeply audited and fixed legacy logic errors inherited from the official upstream integration.
- **Light Entity Revival**: Re-architected the effect list by combining `mode` and `brightness` properties into a unified `_effect_map`. This restores full control to lights that support both operating modes and brightness levels simultaneously, and corrects a boundary bug (`range` max exclusion) that hid the highest mode from the UI.
- **Fan Concurrency Safety (Race Condition Fix)**: Implemented strict Mutex flags (`_is_turning_on`) during fan startup sequences. This prevents duplicate `on=True` commands from spamming the device, drastically improving response times and eliminating command drops caused by network congestion.
- **Diagnostic Entity Migration & Clutter Reduction**: 
  - Restructured `unique_id`s for Diagnostic sensors (`Control Path` and `IP Address`) to include `entry_id`, fully resolving clashes in multi-account/multi-gateway setups.
  - Implemented a **seamless zero-downtime migration script** in `__init__.py` that updates the HA registry dynamically during boot, strictly preventing the creation of `_2` duplicate entities and keeping legacy IDs intact.
  - Set diagnostic sensors to be disabled by default to comply with HA UI cleanliness standards.
- **Sensor Data Purity**: Upgraded `sensor.py`'s out-of-bounds checking. Instead of blindly clamping erroneous values (which skews charts and masks hardware failures), sensors now gracefully return `None` (Unavailable) when values violate their `value_range`.

## New Features & Enhancements (Version 20260527r8)
- **Extreme Performance Optimization & Code Diet**:
  - **O(N) Zombie Eradication**: Conducted a deep technical debt sweep and eliminated all hidden $O(N)$ list traversals (`for prop in properties: ...`) across all major Home Assistant entity initializations (`climate`, `fan`, `light`).
  - **O(1) Lazy Cache Architecture**: Re-architected `MIoTEntityData` with an intelligent, lazy-loading dictionary cache (`props_map`). This transforms all property lookups into instantaneous $O(1)$ operations, shrinking thousands of lines of boilerplate code and eliminating all loop overhead during HA entity initialization.
- **Native MIIO Enhancements**:
  - Successfully injected execution context (`props`, `max_val`) into the native Python `miot_lan` MIIO transpilation layer, allowing complex lambda-based local control structures to receive real-time device states rather than hardcoded fallbacks.

## New Features & Enhancements (Version 20260527r9)
- **Deep Logic Flaw Sweep (9 Critical Fixes)**: Resolved all latent bugs identified in the rigorous `logic_flaws_audit.md` pass, severely bolstering integration robustness:
  - **Crash Prevention**: Fixed critical `TypeError`s caused by `create_task(await ...)` and faulty `None` checks during API disconnects.
  - **Local Control Priority**: Corrected a long-standing routing bug where Local-mode properties were incorrectly polling the `LAN` instead of the `Gateway` first, eliminating state de-syncs.
  - **Ghost Device Eradication**: Fixed `remove_device_async` to actively pop devices from the memory cache so deleted entities no longer resurrect on the next Home Assistant restart.
  - **Spec Safety**: Hardened device parsing (`miot_device.py`) to properly reject malformed optional services that declare features they don't have access to.
  - **Enum Memory Leak Protection**: Capped the unbounded dynamic growth of `Sensor._attr_options` at 64 items, protecting Home Assistant from OOM leaks if a buggy device spams undocumented enum values.

## New Features & Enhancements (Version 20260527r10)
- **OAuth Error Handling Optimization**: 
  - Overhauled the Xiaomi Cloud API error handling logic inside `miot_cloud.py`.
  - When the user's refresh token expires (Error 96009), the system now correctly intercepts the error and elegantly logs a `WARNING` message instead of crashing the Options Flow and spamming the Home Assistant log with a massive stack trace (`invalid http response format`). Users can now cleanly re-authenticate via the integration settings.

## New Features & Enhancements (Version 20260528r1)
- **Home Assistant 2026.6 Compatibility (Python 3.14)**:
  - Removed `from __future__ import annotations` across all 19 component files to comply with Home Assistant Core 2026.6's strict Ruff linting rules for Python 3.14.4 compatibility.
  - Ensured maximum safety for entity generation logic (`unique_id`) and platform initialization.

## New Features & Enhancements (Version 20260530r1)
- **Log Spam Eradication**:
  - Implemented precise exception interception in the cloud polling module (`__refresh_props_from_cloud`).
  - The system will no longer spam massive stack traces when the Xiaomi Cloud access token expires (HTTP 401) or when the server is temporarily down (HTTP 5xx). Instead, it gracefully outputs a single, clean `WARNING` message, saving massive amounts of log space and preventing I/O lag.

## New Features & Enhancements (Version 20260530r2)
- **LAN Decrypt Error Fix**:
  - Fixed a critical bug in `miot_lan.py` where a missing network interface (`if_name`) during early UDP packet reception caused the `send2device` ACK to crash.
  - Corrected a misleading `try/except` scope that caused this LAN handling crash to be wrongly logged as a `decrypt packet error`.
  - The system now securely authenticates the device's IP and interface immediately upon successful packet decryption, ensuring rock-solid local network stability.

## New Features & Enhancements (Version 20260530r6)
- **HA 2026.5.0 Naming Modernization**:
  - Removed all `self.entity_id` hardcoding, returning full entity naming authority to Home Assistant core.
  - Simplified and standardized `unique_id` to ensure absolute stability against device renaming.
  - Automated transparent migration of `unique_id` via `async_migrate_unique_ids` which preserves user's old entity IDs to prevent immediate automation breakage. Users can now seamlessly convert all entities to the modern, clean format simply by renaming their device in the HA UI.

## New Features & Enhancements (Version 20260530r5)
- **Hotfix: Duplicate Entities (`_2`) Resolution**:
  - Fixed an issue where the previous legacy ID restore generated IDs in the `xiaomi_home.` domain instead of the actual platform domain (e.g., `fan.`), and omitted the description slug. This mismatch caused HA to conflict with user-renamed entities, resulting in a wave of `_2` duplicate entities.
  - The logic now EXACTLY mirrors the `98fc679` format (e.g., `fan.zhimi_sg_406233287_za5_s_2_fan`) that users' automations originally relied on, preventing any further entity ID duplication.

## New Features & Enhancements (Version 20260530r4)
- **Hotfix: Setup Entry Crash**:
  - Fixed an issue where the integration would fail to start (`Error setting up entry`) due to missing methods in `__init__.py`. The cleanup routine was still calling the deleted `gen_*_unique_id` methods; it has now been correctly mapped back to `gen_*_entity_id`.

## New Features & Enhancements (Version 20260530r3)
- **Legacy Entity ID Backward Compatibility Restore**:
  - Reverted a recent refactor that stopped hardcoding `self.entity_id`, which had inadvertently allowed Home Assistant to auto-generate completely new, localized Pinyin entity IDs (e.g., `fan.feng_shan_chen_bo_rui_...`).
  - By restoring the hardcoded generation of `self.entity_id` and reverting the `unique_id` suffixes, all original device IDs (e.g., `fan.zhimi_sg_406233287_za5_s_2_fan`) are now guaranteed to be perfectly maintained.
  - This absolutely ensures zero disruptions to existing user automations and prevents "unavailable" ghost entities from spawning during updates.

## New Features & Enhancements (Version 20260530r9)
- **Massive Technical Debt & Architecture Refactoring (A-D)**:
  - **God Object Dismantling**: Completely shattered the massive `config_flow.py` (2,100+ lines) into a modular `config_flow/` directory (`options_flow.py`, `oauth.py`, `network.py`), vastly improving UI flow maintainability.
  - **Client Isolation**: Broke down the monolithic `MIoTClient` (2,000+ lines) by extracting polling and communication routines into dedicated `miot_cloud_manager.py` and `miot_lan_manager.py` modules.
  - **Strict Platform Compliance**: Removed all legacy heuristic code that blindly coerced properties into invalid HA platforms (e.g., forcing all booleans to `switch`). Platform generation now strictly adheres to the HA Device Class standards defined in `SPEC_PROP_TRANS_MAP`.
  - **Traceable Exception Handling**: Purged over 50 instances of the dangerous `# pylint: disable=broad-exception-caught` mask. All `Exception` catches now properly format and log stack traces (`traceback.format_exc()`), making silent failures a thing of the past.
  - **Translation Engine Extraction**: Extracted the `_MIoTSpecMultiLang` engine out of the heavy `miot_spec.py` into its own `miot_i18n.py` module, and reduced the integration footprint by deleting all unused translations (retaining only `en`, `zh-Hant`, `zh-Hans`).
