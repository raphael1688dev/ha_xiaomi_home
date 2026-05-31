# -*- coding: utf-8 -*-
"""
Config flow for Xiaomi Home.
"""
import asyncio
import hashlib
import ipaddress
import json
import secrets
import traceback
from typing import Optional, Set, Tuple
from urllib.parse import urlparse
from aiohttp import web
from aiohttp.hdrs import METH_GET
import voluptuous as vol
import logging

from homeassistant import config_entries
from homeassistant.components import zeroconf
from homeassistant.components.zeroconf import HaAsyncZeroconf
from homeassistant.components.webhook import (
    async_register as webhook_async_register,
    async_unregister as webhook_async_unregister,
    async_generate_path as webhook_async_generate_path
)
from homeassistant.core import callback
from homeassistant.data_entry_flow import AbortFlow
from homeassistant.helpers.instance_id import async_get
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .miot.const import (
    DEFAULT_CLOUD_SERVER,
    DEFAULT_CTRL_MODE,
    DEFAULT_INTEGRATION_LANGUAGE,
    DEFAULT_COVER_DEAD_ZONE_WIDTH,
    MIN_COVER_DEAD_ZONE_WIDTH,
    MAX_COVER_DEAD_ZONE_WIDTH,
    DEFAULT_NICK_NAME,
    DEFAULT_OAUTH2_API_HOST,
    DEFAULT_CLOUD_BROKER_HOST,
    DOMAIN,
    OAUTH2_AUTH_URL,
    OAUTH2_CLIENT_ID,
    CLOUD_SERVERS,
    OAUTH_REDIRECT_URL,
    INTEGRATION_LANGUAGES,
    SUPPORT_CENTRAL_GATEWAY_CTRL,
    NETWORK_REFRESH_INTERVAL,
    MIHOME_CERT_EXPIRE_MARGIN
)
from .miot.miot_cloud import MIoTHttpClient, MIoTOauthClient
from .miot.miot_storage import MIoTStorage, MIoTCert
from .miot.miot_mdns import MipsService
from .miot.web_pages import oauth_redirect_page
from .miot.miot_error import (
    MIoTConfigError, MIoTError, MIoTErrorCode, MIoTOauthError)
from .miot.miot_i18n import MIoTI18n
from .miot.miot_network import MIoTNetwork
from .miot.miot_client import MIoTClient, get_miot_instance_async
from .miot.miot_spec import MIoTSpecParser
from .miot.miot_lan import MIoTLan

_LOGGER = logging.getLogger(__name__)


def _handle_network_detect_addr(
    addr_str: str
) -> Tuple[list[str], list[str], list[str]]:
    ip_list: list[str] = []
    url_list: list[str] = []
    invalid_list: list[str] = []
    if addr_str:
        for addr in addr_str.split(','):
            addr = addr.strip()
            if not addr:
                continue
            
            try:
                ipaddress.ip_address(addr)
                ip_list.append(addr)
                continue
            except ValueError:
                pass
            try:
                result = urlparse(addr)
                if (
                    result.netloc
                    and result.scheme.startswith('http')
                ):
                    url_list.append(addr)
                    continue
            except ValueError:
                pass
            invalid_list.append(addr)
    return ip_list, url_list, invalid_list


def _handle_devices_filter(
    devices: dict, logic_or: bool, item_in: dict, item_ex: dict
) -> dict:
    """Filter a device list by include/exclude rules.

    Args:
        devices: Mapping of did -> device info dict.
        logic_or: If True use OR logic for multiple filter keys; else AND.
        item_in: Include filters keyed by device info field name.
        item_ex: Exclude filters keyed by device info field name.

    Returns:
        Filtered dict of did -> device info.
    """
    include_set: Set = set([])
    if not item_in:
        include_set = set(devices.keys())
    else:
        filter_item: list[set] = []
        for key, value in item_in.items():
            filter_item.append(set([
                did for did, info in devices.items()
                if str(info[key]) in value]))
        include_set = (
            set.union(*filter_item)
            if logic_or else set.intersection(*filter_item))
    if not include_set:
        return {}
    if item_ex:
        filter_item: list[set] = []
        for key, value in item_ex.items():
            filter_item.append(set([
                did for did, info in devices.items()
                if str(info[key]) in value]))
        exclude_set: Set = (
            set.union(*filter_item)
            if logic_or else set.intersection(*filter_item))
        if exclude_set:
            include_set = include_set-exclude_set
    if not include_set:
        return {}
    return {
        did: info for did, info in devices.items() if did in include_set}
