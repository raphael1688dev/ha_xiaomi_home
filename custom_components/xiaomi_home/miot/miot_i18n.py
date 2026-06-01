# -*- coding: utf-8 -*-
"""
MIoT-Spec-V2 multi language support.
"""
import asyncio
import logging
import os
import traceback
from typing import Optional, Union, Any

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
        except (OSError, ValueError) as err:
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

class MIoTI18n:
    """MIoT Internationalization Translation.
    Translate by Copilot, which does not guarantee the accuracy of the 
    translation. If there is a problem with the translation, please submit 
    the ISSUE feedback. After the review, we will modify it as soon as possible.
    """
    _main_loop: asyncio.AbstractEventLoop
    _lang: str
    _data: dict

    def __init__(
        self, lang: str, loop: Optional[asyncio.AbstractEventLoop] = None
    ) -> None:
        # 優化: 使用現代的 get_running_loop() 避免 Python 3.10+ 的 DeprecationWarning
        self._main_loop = loop or asyncio.get_running_loop()
        self._lang = lang
        self._data = {}

    async def init_async(self) -> None:
        if self._data:
            return
        data = None
        try:
            data = await self._main_loop.run_in_executor(
                None, load_json_file,
                os.path.join(
                    os.path.dirname(os.path.abspath(__file__)),
                    f'i18n/{self._lang}.json'))
        except (OSError, ValueError) as err:
            _LOGGER.error('load i18n file error, %s\n%s', err, traceback.format_exc())

            return
            
        # Check if the file is a valid JSON file
        if not isinstance(data, dict):
            # 優化: 修正原本筆誤的錯誤日誌 (原本寫 valid file)
            _LOGGER.error('invalid i18n json file format, %s', data)
            return
            
        self._data = data

    async def deinit_async(self) -> None:
        # 優化: 使用 clear() 讓底層直接清空字典，提升記憶體回收效率
        self._data.clear()

    def translate(
        self, key: str, replace: Optional[dict[str, Any]] = None
    ) -> Union[str, dict, None]:
        result: Any = self._data
        
        # 優化: 嚴格判斷 result 是否為字典，防護字串提早出現造成的 TypeError 系統崩潰
        for item in key.split('.'):
            if not isinstance(result, dict) or item not in result:
                return None
            result = result[item]
            
        if isinstance(result, str) and replace:
            for k, v in replace.items():
                # 優化: 改用 f-string 提升字串拼接效能與可讀性
                result = result.replace(f'{{{k}}}', str(v))
                
        return result or None

    def translate_str(
        self, key: str, replace: Optional[dict[str, Any]] = None
    ) -> Optional[str]:
        """Translate key and expect a string, otherwise return None."""
        result = self.translate(key, replace)
        if isinstance(result, str):
            return result
        return None

