# -*- coding: utf-8 -*-
"""
Config flow for Xiaomi Home.
"""
import asyncio
import traceback
from aiohttp import web
import logging


from .miot.const import (
    DOMAIN
)
from .miot.web_pages import oauth_redirect_page
from .miot.miot_error import (
    MIoTConfigError, MIoTErrorCode)
from .miot.miot_i18n import MIoTI18n

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

    except Exception as err:  # pylint: disable=broad-exception-caught
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
