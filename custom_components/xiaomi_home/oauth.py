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


async def _handle_oauth_webhook(hass, webhook_id, request):
    """Webhook to handle oauth2 callback."""
    # pylint: disable=inconsistent-quotes
    i18n: MIoTI18n = hass.data[DOMAIN][webhook_id].get('i18n', None)
    try:
        data = dict(request.query)
        if data.get('code', None) is None or data.get('state', None) is None:
            raise MIoTConfigError(
                'invalid oauth code or state',
                MIoTErrorCode.CODE_CONFIG_INVALID_INPUT)

        if data['state'] != hass.data[DOMAIN][webhook_id]['oauth_state']:
            raise MIoTConfigError(
                f'inconsistent state, '
                f'{hass.data[DOMAIN][webhook_id]["oauth_state"]}!='
                f'{data["state"]}', MIoTErrorCode.CODE_CONFIG_INVALID_STATE)

        fut_oauth_code: asyncio.Future = hass.data[DOMAIN][webhook_id].pop(
            'fut_oauth_code', None)
        fut_oauth_code.set_result(data['code'])
        _LOGGER.info('webhook code: %s', data['code'])

        success_trans: dict = {}
        if i18n:
            trans = i18n.translate('oauth2.success')
            if isinstance(trans, dict):
                success_trans = trans
        # Delete
        del hass.data[DOMAIN][webhook_id]['oauth_state']
        del hass.data[DOMAIN][webhook_id]['i18n']
        return web.Response(
            body=await oauth_redirect_page(
                title=success_trans.get('title', 'Success'),
                content=success_trans.get(
                    'content', (
                        'Please close this page and return to the account '
                        'authentication page to click NEXT')),
                button=success_trans.get('button', 'Close Page'),
                success=True,
            ), content_type='text/html')

    except Exception as err:
        _LOGGER.error("oauth webhook error: %s", traceback.format_exc())  
        fail_trans: dict = {}
        err_msg: str = str(err)
        if i18n:
            if isinstance(err, MIoTConfigError):
                err_msg = i18n.translate_str(
                    f'oauth2.error_msg.{err.code.value}'
                ) or err.message
            trans = i18n.translate('oauth2.fail')
            if isinstance(trans, dict):
                fail_trans = trans
        return web.Response(
            body=await oauth_redirect_page(
                title=fail_trans.get('title', 'Authentication Failed'),
                content=str(fail_trans.get('content', (
                    '{error_msg}, Please close this page and return to the '
                    'account authentication page to click the authentication '
                    'link again.'))).replace('{error_msg}', err_msg),
                button=fail_trans.get('button', 'Close Page'),
                success=False),
            content_type='text/html')

