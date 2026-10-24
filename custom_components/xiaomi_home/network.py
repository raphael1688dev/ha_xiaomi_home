# -*- coding: utf-8 -*-
"""
Config flow for Xiaomi Home.
"""
import ipaddress
from typing import Set, Tuple
from urllib.parse import urlparse
import logging



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
