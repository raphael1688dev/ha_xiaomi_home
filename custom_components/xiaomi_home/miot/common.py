# -*- coding: utf-8 -*-

import asyncio
import json
from os import path
import random
from typing import Any, Optional
import hashlib
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from urllib.error import URLError

import aiohttp
from paho.mqtt.matcher import MQTTMatcher
import yaml
from slugify import slugify

MIOT_ROOT_PATH: str = path.dirname(path.abspath(__file__))


def gen_absolute_path(relative_path: str) -> str:
    """Generate an absolute path."""
    return path.join(MIOT_ROOT_PATH, relative_path)


def calc_group_id(uid: str, home_id: str) -> str:
    """Calculate the group ID based on a user ID and a home ID."""
    return hashlib.sha1(
        f'{uid}central_service{home_id}'.encode('utf-8')).hexdigest()[:16]


def load_json_file(json_file: str) -> dict:
    """Load a JSON file."""
    with open(json_file, 'r', encoding='utf-8') as f:
        return json.load(f)


def load_yaml_file(yaml_file: str) -> dict:
    """Load a YAML file."""
    with open(yaml_file, 'r', encoding='utf-8') as f:
        return yaml.load(f, Loader=yaml.FullLoader)


def randomize_int(value: int, ratio: float) -> int:
    """Randomize an integer value."""
    return int(value * (1 - ratio + random.random()*2*ratio))


def randomize_float(value: float, ratio: float) -> float:
    """Randomize a float value."""
    return value * (1 - ratio + random.random()*2*ratio)


def slugify_name(name: str, separator: str = '_') -> str:
    """Slugify a name."""
    return slugify(name, separator=separator)


def slugify_did(cloud_server: str, did: str) -> str:
    """Slugify a device id."""
    return slugify(f'{cloud_server}_{did}', separator='_')


class MIoTMatcher(MQTTMatcher):
    """MIoT Pub/Sub topic matcher."""

    def iter_all_nodes(self) -> Any:
        """Return an iterator on all nodes with their paths and contents."""
        def rec(node, path_):
            # pylint: disable=protected-access
            if node._content:
                yield ('/'.join(path_), node._content)
            for part, child in node._children.items():
                yield from rec(child, path_ + [part])
        return rec(self._root, [])

    def get(self, topic: str) -> Optional[Any]:
        try:
            return self[topic]
        except KeyError:
            return None


class MIoTHttp:
    """MIoT Common HTTP API."""
    
    @staticmethod
    def get(
        url: str, params: Optional[dict] = None, headers: Optional[dict] = None
    ) -> Optional[str]:
        full_url = url
        if params:
            encoded_params = urlencode(params)
            full_url = f'{url}?{encoded_params}'
        request = Request(full_url, method='GET', headers=headers or {})
        try:
            with urlopen(request, timeout=10) as response:
                content = response.read()
            return str(content, 'utf-8') if content else None
        except URLError:
            return None

    @staticmethod
    def get_json(
        url: str, params: Optional[dict] = None, headers: Optional[dict] = None
    ) -> Optional[dict]:
        response = MIoTHttp.get(url, params, headers)
        if not response:
            return None
        try:
            return json.loads(response)
        except json.JSONDecodeError:
            return None

    @staticmethod
    def post(
        url: str, data: Optional[dict] = None, headers: Optional[dict] = None
    ) -> Optional[str]:
        req_headers = headers or {}
        data_bytes = None
        
        if data is not None:
            data_bytes = json.dumps(data).encode('utf-8')
            if 'Content-Type' not in req_headers:
                req_headers['Content-Type'] = 'application/json'
                
        request = Request(url, data=data_bytes, method='POST', headers=req_headers)
        try:
            with urlopen(request, timeout=10) as response:
                content = response.read()
            return str(content, 'utf-8') if content else None
        except URLError:
            return None

    @staticmethod
    def post_json(
        url: str, data: Optional[dict] = None, headers: Optional[dict] = None
    ) -> Optional[dict]:
        response = MIoTHttp.post(url, data, headers)
        if not response:
            return None
        try:
            return json.loads(response)
        except json.JSONDecodeError:
            return None

    @staticmethod
    async def get_async(
        url: str, params: Optional[dict] = None, headers: Optional[dict] = None,
        loop: Optional[asyncio.AbstractEventLoop] = None
    ) -> Optional[str]:
        """Async GET utilizing aiohttp for Home Assistant optimization."""
        try:
            async with aiohttp.ClientSession(headers=headers) as session:
                async with session.get(url, params=params, timeout=10) as response:
                    if response.status == 200:
                        return await response.text()
                    return None
        except Exception:
            return None

    @staticmethod
    async def get_json_async(
        url: str, params: Optional[dict] = None, headers: Optional[dict] = None,
        loop: Optional[asyncio.AbstractEventLoop] = None
    ) -> Optional[dict]:
        response = await MIoTHttp.get_async(url, params, headers, loop)
        if not response:
            return None
        try:
            return json.loads(response)
        except json.JSONDecodeError:
            return None

    @staticmethod
    async def post_async(
        url: str, data: Optional[dict] = None, headers: Optional[dict] = None,
        loop: Optional[asyncio.AbstractEventLoop] = None
    ) -> Optional[str]:
        """Async POST utilizing aiohttp for Home Assistant optimization."""
        req_headers = headers or {}
        if data and 'Content-Type' not in req_headers:
            req_headers['Content-Type'] = 'application/json'
            
        try:
            async with aiohttp.ClientSession(headers=req_headers) as session:
                # If json parameter is used, aiohttp automatically sets Content-Type
                async with session.post(url, json=data, timeout=10) as response:
                    if response.status == 200:
                        return await response.text()
                    return None
        except Exception:
            return None
            
    @staticmethod
    async def post_json_async(
        url: str, data: Optional[dict] = None, headers: Optional[dict] = None,
        loop: Optional[asyncio.AbstractEventLoop] = None
    ) -> Optional[dict]:
        """Helper to return JSON directly from async POST."""
        response = await MIoTHttp.post_async(url, data, headers, loop)
        if not response:
            return None
        try:
            return json.loads(response)
        except json.JSONDecodeError:
            return None