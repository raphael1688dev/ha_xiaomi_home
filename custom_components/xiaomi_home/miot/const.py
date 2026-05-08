# -*- coding: utf-8 -*-

from types import MappingProxyType

DOMAIN: str = 'xiaomi_home'
DEFAULT_NAME: str = 'Xiaomi Home'

DEFAULT_NICK_NAME: str = 'Xiaomi'

MIHOME_HTTP_API_TIMEOUT: int = 30
MIHOME_MQTT_KEEPALIVE: int = 60
# seconds, 3 days
MIHOME_CERT_EXPIRE_MARGIN: int = 3600*24*3

NETWORK_REFRESH_INTERVAL: int = 30

OAUTH2_CLIENT_ID: str = '2882303761520251711'
OAUTH2_AUTH_URL: str = 'https://account.xiaomi.com/oauth2/authorize'
DEFAULT_OAUTH2_API_HOST: str = 'ha.api.io.mi.com'
DEFAULT_CLOUD_BROKER_HOST: str = 'ha.mqtt.io.mi.com'

# seconds, 14 days
SPEC_STD_LIB_EFFECTIVE_TIME = 3600*24*14
# seconds, 14 days
MANUFACTURER_EFFECTIVE_TIME = 3600*24*14

# 使用 tuple 確保全域常數的不可變性 (Immutable)
SUPPORTED_PLATFORMS: tuple[str, ...] = (
    'binary_sensor',
    'button',
    'climate',
    'cover',
    'device_tracker',
    'event',
    'fan',
    'humidifier',
    'light',
    'media_player',
    'notify',
    'number',
    'select',
    'sensor',
    'switch',
    'text',
    'vacuum',
    'water_heater',
)

# 使用 set 提升 `in` 運算子的查詢效能至 O(1)，並保持不可變性
UNSUPPORTED_MODELS: frozenset[str] = frozenset({
    'chuangmi.ir.v2',
    'era.airp.cwb03',
    'hmpace.motion.v6nfc',
    'k0918.toothbrush.t700'
})

DEFAULT_CLOUD_SERVER: str = 'cn'

# 使用 MappingProxyType 設定為唯讀字典，防止執行期被意外竄改
CLOUD_SERVERS = MappingProxyType({
    'cn': '中国大陆',
    'de': 'Europe',
    'i2': 'India',
    'ru': 'Russia',
    'sg': 'Singapore',
    'us': 'United States'
})

SUPPORT_CENTRAL_GATEWAY_CTRL: tuple[str, ...] = ('cn',)

DEFAULT_INTEGRATION_LANGUAGE: str = 'en'
INTEGRATION_LANGUAGES = MappingProxyType({
    'de': 'Deutsch',
    'en': 'English',
    'es': 'Español',
    'fr': 'Français',
    'it': 'Italiano',
    'ja': '日本語',
    'nl': 'Nederlands',
    'pt': 'Português',
    'pt-BR': 'Português (Brasil)',
    'ru': 'Русский',
    'tr': 'Türkçe',
    'zh-Hans': '简体中文',
    'zh-Hant': '繁體中文'
})

DEFAULT_COVER_DEAD_ZONE_WIDTH: int = 0
MIN_COVER_DEAD_ZONE_WIDTH: int = 0
MAX_COVER_DEAD_ZONE_WIDTH: int = 5

DEFAULT_CTRL_MODE: str = 'auto'

# Registered in Xiaomi OAuth 2.0 Service
# DO NOT CHANGE UNLESS YOU HAVE AN ADMINISTRATOR PERMISSION
OAUTH_REDIRECT_URL: str = 'http://homeassistant.local:8123'

# 憑證字串格式維持原樣，以避免改變字串造成 SHA256 驗證失敗
MIHOME_CA_CERT_STR: str = '-----BEGIN CERTIFICATE-----\n' \
    'MIIBazCCAQ+gAwIBAgIEA/UKYDAMBggqhkjOPQQDAgUAMCIxEzARBgNVBAoTCk1p\n' \
    'amlhIFJvb3QxCzAJBgNVBAYTAkNOMCAXDTE2MTEyMzAxMzk0NVoYDzIwNjYxMTEx\n' \
    'MDEzOTQ1WjAiMRMwEQYDVQQKEwpNaWppYSBSb290MQswCQYDVQQGEwJDTjBZMBMG\n' \
    'ByqGSM49AgEGCCqGSM49AwEHA0IABL71iwLa4//4VBqgRI+6xE23xpovqPCxtv96\n' \
    '2VHbZij61/Ag6jmi7oZ/3Xg/3C+whglcwoUEE6KALGJ9vccV9PmjLzAtMAwGA1Ud\n' \
    'EwQFMAMBAf8wHQYDVR0OBBYEFJa3onw5sblmM6n40QmyAGDI5sURMAwGCCqGSM49\n' \
    'BAMCBQADSAAwRQIgchciK9h6tZmfrP8Ka6KziQ4Lv3hKfrHtAZXMHPda4IYCIQCG\n' \
    'az93ggFcbrG9u2wixjx1HKW4DUA5NXZG0wWQTpJTbQ==\n' \
    '-----END CERTIFICATE-----\n' \
    '-----BEGIN CERTIFICATE-----\n' \
    'MIIBjzCCATWgAwIBAgIBATAKBggqhkjOPQQDAjAiMRMwEQYDVQQKEwpNaWppYSBS\n' \
    'b290MQswCQYDVQQGEwJDTjAgFw0yMjA2MDkxNDE0MThaGA8yMDcyMDUyNzE0MTQx\n' \
    'OFowLDELMAkGA1UEBhMCQ04xHTAbBgNVBAoMFE1JT1QgQ0VOVFJBTCBHQVRFV0FZ\n' \
    'MFkwEwYHKoZIzj0CAQYIKoZIzj0DAQcDQgAEdYrzbnp/0x/cZLZnuEDXTFf8mhj4\n' \
    'CVpZPwgj9e9Ve5r3K7zvu8Jjj7JF1JjQYvEC6yhp1SzBgglnK4L8xQzdiqNQME4w\n' \
    'HQYDVR0OBBYEFCf9+YBU7pXDs6K6CAQPRhlGJ+cuMB8GA1UdIwQYMBaAFJa3onw5\n' \
    'sblmM6n40QmyAGDI5sURMAwGA1UdEwQFMAMBAf8wCgYIKoZIzj0EAwIDSAAwRQIh\n' \
    'AKUv+c8v98vypkGMTzMwckGjjVqTef8xodsy6PhcSCq+AiA/n9mDs62hAo5zXyJy\n' \
    'Bs1s7mqXPf1XgieoxIvs1MqyiA==\n' \
    '-----END CERTIFICATE-----\n'

MIHOME_CA_CERT_SHA256: str = \
    '8b7bf306be3632e08b0ead308249e5f2b2520dc921ad143872d5fcc7c68d6759'
