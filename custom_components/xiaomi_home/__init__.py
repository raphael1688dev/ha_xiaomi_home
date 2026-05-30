# -*- coding: utf-8 -*-
"""
The Xiaomi Home integration Init File.
"""
import logging
from typing import Optional

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.components import persistent_notification
from homeassistant.helpers import device_registry, entity_registry
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.util import slugify
import re

from .miot.common import slugify_did, MIoTHttp
from .miot.miot_storage import (
    DeviceManufacturer, MIoTStorage, MIoTCert)
from .miot.miot_spec import (
    MIoTSpecInstance, MIoTSpecParser, MIoTSpecService)
from .miot.const import (
    DEFAULT_INTEGRATION_LANGUAGE, DOMAIN, SUPPORTED_PLATFORMS)
from .miot.miot_error import MIoTOauthError
from .miot.miot_device import MIoTDevice
from .miot.miot_client import MIoTClient, get_miot_instance_async

_LOGGER = logging.getLogger(__name__)


async def async_setup(hass: HomeAssistant, hass_config: dict) -> bool:
    # pylint: disable=unused-argument
    hass.data.setdefault(DOMAIN, {})
    # {[entry_id:str]: MIoTClient}, miot client instance
    hass.data[DOMAIN].setdefault('miot_clients', {})
    # {[entry_id:str]: list[MIoTDevice]}
    hass.data[DOMAIN].setdefault('devices', {})
    # {[entry_id:str]: entities}
    hass.data[DOMAIN].setdefault('entities', {})
    for platform in SUPPORTED_PLATFORMS:
        hass.data[DOMAIN]['entities'][platform] = []
    MIoTHttp.set_shared_session(async_get_clientsession(hass))
    return True


async def _async_migrate_legacy_entity_ids(hass: HomeAssistant, entry_id: str) -> None:
    """Migrate legacy entity IDs that fell back to unique_id format back to standard naming."""
    er = entity_registry.async_get(hass)
    dr = device_registry.async_get(hass)
    
    from homeassistant.util import slugify
    
    for entry in entity_registry.async_entries_for_config_entry(er, entry_id):
        # The fallback entity ID looks exactly like `domain.unique_id`
        expected_fallback_id = f"{entry.domain}.{entry.unique_id}"
        
        # We only force rename if the entity ID exactly matches the legacy fallback
        # This protects users who have manually renamed their entity IDs in the UI!
        if entry.entity_id == expected_fallback_id:
            # We need the device name to generate the new entity ID
            if entry.device_id:
                device = dr.async_get(entry.device_id)
                if device:
                    device_name = device.name_by_user or device.name
                    # original_name contains the string from `_attr_name` (e.g. "Environment Relative Humidity")
                    entity_name = entry.original_name
                    
                    # If original_name is None, extract from unique_id
                    if not entity_name:
                        import re
                        match = re.search(r'_([pae])_\d+_\d+$', entry.unique_id)
                        if match:
                            prefix = entry.unique_id[:match.start()]
                            # Extract the part after the did_tag and model suffix
                            parts = prefix.split('_')
                            if len(parts) > 3:
                                # The last part is usually the slugified entity name
                                entity_name = parts[-1]
                    
                    if device_name and entity_name:
                        new_entity_id = f"{entry.domain}.{slugify(device_name)}_{slugify(entity_name)}"
                        if new_entity_id != entry.entity_id:
                            try:
                                er.async_update_entity(entry.entity_id, new_entity_id=new_entity_id)
                                _LOGGER.info(
                                    "Forcibly migrated fallback entity %s to modern HA format %s", 
                                    entry.entity_id, new_entity_id
                                )
                            except ValueError as err:
                                _LOGGER.warning(
                                    "Failed to force migrate fallback entity %s to %s: %s", 
                                    entry.entity_id, new_entity_id, err
                                )


async def async_setup_entry(
    hass: HomeAssistant, config_entry: ConfigEntry
) -> bool:
    """Set up an entry."""
    def ha_persistent_notify(
        notify_id: str, title: Optional[str] = None,
        message: Optional[str] = None
    ) -> None:
        """Send messages in Notifications dialog box."""
        if title:
            persistent_notification.async_create(
                hass=hass,  message=message or '',
                title=title, notification_id=notify_id)
        else:
            persistent_notification.async_dismiss(
                hass=hass, notification_id=notify_id)

    entry_id = config_entry.entry_id
    entry_data = dict(config_entry.data)

    ha_persistent_notify(
        notify_id=f'{entry_id}.oauth_error', title=None, message=None)

    try:
        miot_client: MIoTClient = await get_miot_instance_async(
            hass=hass, entry_id=entry_id,
            entry_data=entry_data,
            persistent_notify=ha_persistent_notify)
        # Spec parser
        spec_parser = MIoTSpecParser(
            lang=entry_data.get(
                'integration_language', DEFAULT_INTEGRATION_LANGUAGE),
            storage=miot_client.miot_storage,
            loop=miot_client.main_loop
        )
        await spec_parser.init_async()
        # Manufacturer
        manufacturer: DeviceManufacturer = DeviceManufacturer(
            storage=miot_client.miot_storage,
            loop=miot_client.main_loop)
        await manufacturer.init_async()
        miot_devices: list[MIoTDevice] = []
        er = entity_registry.async_get(hass=hass)
        er_entries = list(entity_registry.async_entries_for_config_entry(er, entry_id))
        
        # Register a migration script
        await _async_migrate_legacy_entity_ids(hass, entry_id)

        entries_to_remove = entity_registry.async_entries_for_config_entry(er, entry_id)
        if not isinstance(entries_to_remove, list):
            entries_to_remove = list(entries_to_remove)
            
        for entry in entries_to_remove:
            if (
                entry.entity_id.startswith(f'{DOMAIN}.')
                or entry.entity_id.split('.', 1)[0] not in SUPPORTED_PLATFORMS
            ):
                er.async_remove(entity_id=entry.entity_id)
        
        # Remove entities from HA entity registry
        def _remove_from_registry_by_uid(unique_ids: list[str]) -> None:
            for uid in unique_ids:
                for entry in er_entries:
                    if entry.unique_id == uid:
                        er.async_remove(entry.entity_id)
                        er_entries.remove(entry)
                        break

        for did, info in miot_client.device_list.items():
            spec_instance = await spec_parser.parse(urn=info['urn'])
            if not isinstance(spec_instance, MIoTSpecInstance):
                _LOGGER.error('spec content is None, %s, %s', did, info)
                continue
            device: MIoTDevice = MIoTDevice(
                miot_client=miot_client,
                device_info={
                    **info, 'manufacturer': manufacturer.get_name(
                        info.get('manufacturer', ''))},
                spec_instance=spec_instance)
            miot_devices.append(device)
            device.spec_transform()
            
            # Remove filter entities and non-standard entities using helper function
            def _filter_platform(platform_dict: dict, item_type: str, uid_gen_func, has_description=False):
                if platform not in platform_dict:
                    return
                kept_items = []
                for item in platform_dict[platform]:
                    spec_item = item.spec if item_type == 'service' else item
                    if spec_item.need_filter or (miot_client.hide_non_standard_entities and spec_item.proprietary):
                        uids_to_remove = []
                        if has_description:
                            uids_to_remove.append(uid_gen_func(siid=spec_item.iid, description=spec_item.description, slugify_description=False))
                            uids_to_remove.append(uid_gen_func(siid=spec_item.iid, description=spec_item.description))
                        elif item_type == 'property':
                            uids_to_remove.append(uid_gen_func(spec_name=spec_item.name, siid=spec_item.service.iid, piid=spec_item.iid))
                        elif item_type == 'event':
                            uids_to_remove.append(uid_gen_func(spec_name=spec_item.name, siid=spec_item.service.iid, eiid=spec_item.iid))
                        elif item_type == 'action':
                            uids_to_remove.append(uid_gen_func(spec_name=spec_item.name, siid=spec_item.service.iid, aiid=spec_item.iid))
                        _remove_from_registry_by_uid(uids_to_remove)
                    else:
                        kept_items.append(item)
                platform_dict[platform] = kept_items

            for platform in SUPPORTED_PLATFORMS:
                _filter_platform(device.entity_list, 'service', device.gen_service_unique_id, True)
                _filter_platform(device.prop_list, 'property', device.gen_prop_unique_id, False)
                _filter_platform(device.event_list, 'event', device.gen_event_unique_id, False)
                _filter_platform(device.action_list, 'action', device.gen_action_unique_id, False)

            # Action debug
            if not miot_client.action_debug:
                for action in device.action_list.get('notify', []):
                    _remove_from_registry_by_uid([
                        device.gen_action_unique_id(spec_name=action.name, siid=action.service.iid, aiid=action.iid)
                    ])
                    
            # Binary sensor display
            if not miot_client.display_binary_bool:
                for prop in device.prop_list.get('binary_sensor', []):
                    _remove_from_registry_by_uid([
                        device.gen_prop_unique_id(spec_name=prop.name, siid=prop.service.iid, piid=prop.iid)
                    ], platform='binary_sensor')
            if not miot_client.display_binary_text:
                for prop in device.prop_list.get('binary_sensor', []):
                    _remove_from_registry_by_uid([
                        device.gen_prop_unique_id(spec_name=prop.name, siid=prop.service.iid, piid=prop.iid)
                    ], platform='sensor')

        hass.data[DOMAIN]['devices'][entry_id] = miot_devices
        
        # Pre-register devices in the device registry.
        # This prevents a race condition where HA generates entity_ids for sub-entities
        # before the device is fully registered, causing it to fall back to unique_id.
        dr = device_registry.async_get(hass)
        for device in miot_devices:
            if device.device_info:
                dr.async_get_or_create(
                    config_entry_id=entry_id,
                    **device.device_info
                )
                
        # Register a migration script to fix any existing fallback entity_ids
        # generated in previous sessions due to the race condition.
        await _async_migrate_legacy_entity_ids(hass, entry_id)

        await hass.config_entries.async_forward_entry_setups(
            config_entry, SUPPORTED_PLATFORMS)

        # Remove the deleted devices
        devices_remove = (await miot_client.miot_storage.load_user_config_async(
            uid=entry_data['uid'],
            cloud_server=entry_data['cloud_server'],
            keys=['devices_remove'])).get('devices_remove', [])
            
        if isinstance(devices_remove, list) and devices_remove:
            dr = device_registry.async_get(hass)
            for did in devices_remove:
                device_entry = dr.async_get_device(
                    identifiers={(
                        DOMAIN,
                        slugify_did(
                            cloud_server=entry_data['cloud_server'],
                            did=did))},
                    connections=None)
                if not device_entry:
                    _LOGGER.error('remove device not found, %s', did)
                    continue
                dr.async_remove_device(device_id=device_entry.id)
                _LOGGER.info(
                    'delete device entry, %s, %s', did, device_entry.id)
            await miot_client.miot_storage.update_user_config_async(
                uid=entry_data['uid'],
                cloud_server=entry_data['cloud_server'],
                config={'devices_remove': []})

        await spec_parser.deinit_async()
        await manufacturer.deinit_async()

    except MIoTOauthError as oauth_error:
        ha_persistent_notify(
            notify_id=f'{entry_id}.oauth_error',
            title='Xiaomi Home Oauth Error',
            message=f'Please re-add.\r\nerror: {oauth_error}'
        )
    except Exception as err:
        miot_client: MIoTClient = hass.data[DOMAIN].get('miot_clients', {}).pop(
            entry_id, None)
        if miot_client:
            await miot_client.deinit_async()
        raise err

    return True


async def async_unload_entry(
    hass: HomeAssistant, config_entry: ConfigEntry
) -> bool:
    """Unload the entry."""
    entry_id = config_entry.entry_id
    # Unload the platform
    unload_ok = await hass.config_entries.async_unload_platforms(
        config_entry, SUPPORTED_PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN]['entities'].pop(entry_id, None)
        hass.data[DOMAIN]['devices'].pop(entry_id, None)
    # Remove integration data
    miot_client: MIoTClient = hass.data[DOMAIN]['miot_clients'].pop(
        entry_id, None)
    if miot_client:
        await miot_client.deinit_async()
    del miot_client
    return True


async def async_remove_entry(
    hass: HomeAssistant, config_entry: ConfigEntry
) -> bool:
    """Remove the entry."""
    entry_data = dict(config_entry.data)
    uid: str = entry_data['uid']
    cloud_server: str = entry_data['cloud_server']
    miot_storage: MIoTStorage = hass.data[DOMAIN]['miot_storage']
    miot_cert: MIoTCert = MIoTCert(
        storage=miot_storage, uid=uid, cloud_server=cloud_server)

    # Clean device list
    await miot_storage.remove_async(
        domain='miot_devices', name=f'{uid}_{cloud_server}', type_=dict)
    # Clean user configuration
    await miot_storage.update_user_config_async(
        uid=uid, cloud_server=cloud_server, config=None)
    # Clean cert file
    await miot_cert.remove_user_cert_async()
    await miot_cert.remove_user_key_async()
    return True


async def async_remove_config_entry_device(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    device_entry: device_registry.DeviceEntry
) -> bool:
    """Remove the device."""
    miot_client: MIoTClient = await get_miot_instance_async(
        hass=hass, entry_id=config_entry.entry_id)

    if len(device_entry.identifiers) != 1:
        _LOGGER.error(
            'remove device failed, invalid identifiers, %s, %s',
            device_entry.id, device_entry.identifiers)
        return False
    identifiers = list(device_entry.identifiers)[0]
    if identifiers[0] != DOMAIN:
        _LOGGER.error(
            'remove device failed, invalid domain, %s, %s',
            device_entry.id, device_entry.identifiers)
        return False

    # Remove device
    await miot_client.remove_device2_async(did_tag=identifiers[1])
    device_registry.async_get(hass).async_remove_device(device_entry.id)
    _LOGGER.info(
        'remove device, %s, %s', identifiers[1], device_entry.id)
    return True