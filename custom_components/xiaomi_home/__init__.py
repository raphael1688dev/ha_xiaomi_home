# -*- coding: utf-8 -*-
"""
The Xiaomi Home integration Init File.
"""
from __future__ import annotations
import logging
from typing import Optional

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.components import persistent_notification
from homeassistant.helpers import device_registry, entity_registry

from .miot.common import slugify_did
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
    return True


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
        
        # Migrate old unique_ids to standard format without DOMAIN prefix
        @callback
        def async_migrate_unique_ids() -> None:
            for entry in entity_registry.async_entries_for_config_entry(er, entry_id):
                old_unique_id = entry.unique_id
                new_unique_id = old_unique_id
                if new_unique_id.startswith(f"{DOMAIN}."):
                    new_unique_id = new_unique_id.replace(f"{DOMAIN}.", "", 1)
                # Old unique_ids were exactly the entity_ids, so they started with the platform domain
                if new_unique_id.startswith(f"{entry.domain}."):
                    new_unique_id = new_unique_id.replace(f"{entry.domain}.", "", 1)
                    
                if new_unique_id != old_unique_id:
                    try:
                        er.async_update_entity(entry.entity_id, new_unique_id=new_unique_id)
                        _LOGGER.info("Successfully migrated unique_id from %s to %s", old_unique_id, new_unique_id)
                    except ValueError:
                        # Recovery: New unique ID already exists because a previous boot failed to migrate properly.
                        # We must delete the erroneously created new entity to restore the legacy entity_id.
                        existing_entity_id = er.async_get_entity_id(entry.domain, DOMAIN, new_unique_id)
                        if existing_entity_id and existing_entity_id != entry.entity_id:
                            er.async_remove(existing_entity_id)
                            try:
                                er.async_update_entity(entry.entity_id, new_unique_id=new_unique_id)
                                _LOGGER.info("Recovered legacy entity %s by deleting duplicate %s", entry.entity_id, existing_entity_id)
                            except ValueError as err:
                                _LOGGER.warning("Failed to recover entity %s: %s", entry.entity_id, err)
        
        async_migrate_unique_ids()

        for entry in entity_registry.async_entries_for_config_entry(
            er, entry_id
        ):
            if (
                entry.entity_id.startswith(f'{DOMAIN}.')
                or entry.entity_id.split('.', 1)[0] not in SUPPORTED_PLATFORMS
            ):
                er.async_remove(entity_id=entry.entity_id)
                
        # Helper function for DRY registry cleanup using unique_id
        config_entries_entities = entity_registry.async_entries_for_config_entry(er, entry_id)
        def _remove_from_registry_by_uid(unique_ids: list[str]):
            uids_to_check = set(unique_ids)
            for entry in config_entries_entities:
                if entry.unique_id in uids_to_check:
                    # check if still exists before remove
                    if er.async_get(entry.entity_id):
                        er.async_remove(entity_id=entry.entity_id)

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
            
            # Remove filter entities and non-standard entities using list reconstruction
            for platform in SUPPORTED_PLATFORMS:
                if platform in device.entity_list:
                    kept_entities = []
                    for entity in device.entity_list[platform]:
                        if isinstance(entity.spec, MIoTSpecService) and (
                            entity.spec.need_filter or (miot_client.hide_non_standard_entities and entity.spec.proprietary)
                        ):
                            _remove_from_registry_by_uid([
                                device.gen_service_unique_id(siid=entity.spec.iid, description=entity.spec.description, slugify_description=False),
                                device.gen_service_unique_id(siid=entity.spec.iid, description=entity.spec.description)
                            ])
                        else:
                            kept_entities.append(entity)
                    device.entity_list[platform] = kept_entities

                if platform in device.prop_list:
                    kept_props = []
                    for prop in device.prop_list[platform]:
                        if prop.need_filter or (miot_client.hide_non_standard_entities and prop.proprietary):
                            _remove_from_registry_by_uid([
                                device.gen_prop_unique_id(spec_name=prop.name, siid=prop.service.iid, piid=prop.iid)
                            ])
                        else:
                            kept_props.append(prop)
                    device.prop_list[platform] = kept_props

                if platform in device.event_list:
                    kept_events = []
                    for event in device.event_list[platform]:
                        if event.need_filter or (miot_client.hide_non_standard_entities and event.proprietary):
                            _remove_from_registry_by_uid([
                                device.gen_event_unique_id(spec_name=event.name, siid=event.service.iid, eiid=event.iid)
                            ])
                        else:
                            kept_events.append(event)
                    device.event_list[platform] = kept_events

                if platform in device.action_list:
                    kept_actions = []
                    for action in device.action_list[platform]:
                        if action.need_filter or (miot_client.hide_non_standard_entities and action.proprietary):
                            _remove_from_registry_by_uid([
                                device.gen_action_unique_id(spec_name=action.name, siid=action.service.iid, aiid=action.iid)
                            ])
                            if platform == 'notify':
                                _remove_from_registry_by_uid([
                                    device.gen_action_unique_id(spec_name=action.name, siid=action.service.iid, aiid=action.iid)
                                ])
                        else:
                            kept_actions.append(action)
                    device.action_list[platform] = kept_actions

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
                    ])
            if not miot_client.display_binary_text:
                for prop in device.prop_list.get('binary_sensor', []):
                    _remove_from_registry_by_uid([
                        device.gen_prop_unique_id(spec_name=prop.name, siid=prop.service.iid, piid=prop.iid)
                    ])

        hass.data[DOMAIN]['devices'][entry_id] = miot_devices
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