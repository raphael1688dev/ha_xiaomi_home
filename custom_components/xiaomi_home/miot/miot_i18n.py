# -*- coding: utf-8 -*-
"""
MIoT-Spec-V2 multi language support.
"""
import asyncio
import logging
import os
import traceback
from typing import Optional

from .common import MIoTHttp, load_json_file
from .const import DEFAULT_INTEGRATION_LANGUAGE
from .miot_error import MIoTSpecError
from .miot_storage import MIoTStorage

_LOGGER = logging.getLogger(__name__)


class _MIoTSpecMultiLang:
    """MIoT SPEC multi lang class."""
    _DOMAIN: str = 'miot_specs_multi_lang'
    _MULTI_LANG_FILE = 'specs/multi_lang.json'
    _lang: str
    _storage: MIoTStorage
    _main_loop: asyncio.AbstractEventLoop

    _custom_cache: dict[str, dict]
    _current_data: Optional[dict[str, str]]

    def __init__(self,
                 lang: Optional[str],
                 storage: MIoTStorage,
                 loop: Optional[asyncio.AbstractEventLoop] = None) -> None:
        self._lang = lang or DEFAULT_INTEGRATION_LANGUAGE
        self._storage = storage
        self._main_loop = loop or asyncio.get_running_loop()

        self._custom_cache = {}
        self._current_data = None

    async def set_spec_async(self, urn: str) -> None:
        if urn in self._custom_cache:
            self._current_data = self._custom_cache[urn]
            return

        trans_cache: dict[str, str] = {}
        trans_cloud: dict = {}
        trans_local: dict = {}
        # Get multi lang from cloud
        try:
            trans_cloud = await self.__get_multi_lang_async(urn)
            if self._lang == 'zh-Hans':
                # Simplified Chinese
                trans_cache = trans_cloud.get('zh_cn', {})
            elif self._lang == 'zh-Hant':
                # Traditional Chinese, zh_hk or zh_tw
                trans_cache = trans_cloud.get('zh_hk', {})
                if not trans_cache:
                    trans_cache = trans_cloud.get('zh_tw', {})
            else:
                trans_cache = trans_cloud.get(self._lang, {})
        except Exception as err:
            trans_cloud = {}
            _LOGGER.info('get multi lang from cloud failed, %s, %s\n%s', urn, err, traceback.format_exc())
        # Get multi lang from local
        try:
            trans_local = await self._storage.load_async(domain=self._DOMAIN,
                                                         name=urn,
                                                         type_=dict
                                                        )  # type: ignore
            if (isinstance(trans_local, dict) and self._lang in trans_local):
                trans_cache.update(trans_local[self._lang])
        except Exception as err:
            trans_local = {}
            _LOGGER.info('get multi lang from local failed, %s, %s\n%s', urn, err, traceback.format_exc())
        # Revert: load multi_lang.json
        try:
            trans_local_json = await self._main_loop.run_in_executor(
                None, load_json_file,
                os.path.join(os.path.dirname(os.path.abspath(__file__)),
                             self._MULTI_LANG_FILE))
            urn_strs: list[str] = urn.split(':')
            urn_key: str = ':'.join(urn_strs[:6])
            if (isinstance(trans_local_json, dict) and
                    urn_key in trans_local_json and
                    self._lang in trans_local_json[urn_key]):
                trans_cache.update(trans_local_json[urn_key][self._lang])
                trans_local = trans_local_json[urn_key]
        except Exception as err:
            _LOGGER.error('multi lang, load json file error, %s\n%s', err, traceback.format_exc())
        # Revert end
        # Default language
        if not trans_cache:
            if trans_cloud and DEFAULT_INTEGRATION_LANGUAGE in trans_cloud:
                trans_cache = trans_cloud[DEFAULT_INTEGRATION_LANGUAGE]
            if trans_local and DEFAULT_INTEGRATION_LANGUAGE in trans_local:
                trans_cache.update(trans_local[DEFAULT_INTEGRATION_LANGUAGE])
        trans_data: dict[str, str] = {}
        for tag, value in trans_cache.items():
            if value is None or value.strip() == '':
                continue
            # The dict key is like:
            # 'service:002:property:001:valuelist:000' or
            # 'service:002:property:001' or 'service:002'
            strs: list = tag.split(':')
            strs_len = len(strs)
            if strs_len == 2:
                trans_data[f's:{int(strs[1])}'] = value
            elif strs_len == 4:
                type_ = 'p' if strs[2] == 'property' else (
                    'a' if strs[2] == 'action' else 'e')
                trans_data[f'{type_}:{int(strs[1])}:{int(strs[3])}'] = value
            elif strs_len == 6:
                trans_data[
                    f'v:{int(strs[1])}:{int(strs[3])}:{int(strs[5])}'] = value

        self._custom_cache[urn] = trans_data
        self._current_data = trans_data

    def translate(self, key: str) -> Optional[str]:
        if not self._current_data:
            return None
        return self._current_data.get(key, None)

    async def __get_multi_lang_async(self, urn: str) -> dict:
        res_trans = await MIoTHttp.get_json_async(
            url='https://miot-spec.org/instance/v2/multiLanguage',
            params={'urn': urn})
        if (not isinstance(res_trans, dict) or 'data' not in res_trans or
                not isinstance(res_trans['data'], dict)):
            raise MIoTSpecError('invalid translation data')
        return res_trans['data']
