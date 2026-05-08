# -*- coding: utf-8 -*-
"""
MIoT internationalization translation.
"""
import asyncio
import logging
import os
from typing import Optional, Union, Any

# pylint: disable=relative-beyond-top-level
from .common import load_json_file

_LOGGER = logging.getLogger(__name__)


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
        except Exception as err:  # pylint: disable=broad-exception-caught
            _LOGGER.error('load i18n file error, %s', err)
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
