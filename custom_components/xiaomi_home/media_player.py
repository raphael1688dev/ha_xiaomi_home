# -*- coding: utf-8 -*-
"""
Media player entities for Xiaomi Home.
"""
from __future__ import annotations
import logging
from typing import Optional, Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.components.media_player import (MediaPlayerEntity,
                                                   MediaPlayerEntityFeature,
                                                   MediaPlayerDeviceClass,
                                                   MediaPlayerState, MediaType)

from .miot.const import DOMAIN
from .miot.miot_device import MIoTDevice, MIoTServiceEntity, MIoTEntityData
from .miot.miot_spec import MIoTSpecProperty, MIoTSpecAction

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, config_entry: ConfigEntry,
                            async_add_entities: AddEntitiesCallback) -> None:
    """Set up a config entry."""
    device_list: list[MIoTDevice] = hass.data[DOMAIN]['devices'][
        config_entry.entry_id]

    new_entities = []
    for miot_device in device_list:
        for data in miot_device.entity_list.get('wifi-speaker', []):
            data.platform = 'media_player'
            new_entities.append(
                WifiSpeaker(miot_device=miot_device, entity_data=data))
        for data in miot_device.entity_list.get('television', []):
            data.platform = 'media_player'
            new_entities.append(
                Television(miot_device=miot_device, entity_data=data))

    if new_entities:
        async_add_entities(new_entities)


class _FeatureBase(MIoTServiceEntity, MediaPlayerEntity):
    """Base feature class for Media Player"""
    def __init__(self, miot_device: MIoTDevice,
                 entity_data: MIoTEntityData) -> None:
        super().__init__(miot_device=miot_device, entity_data=entity_data)


class FeatureTurnOn(_FeatureBase):
    _prop_on: Optional[MIoTSpecProperty]
    _action_turn_on: Optional[MIoTSpecAction]

    def __init__(self, miot_device: MIoTDevice,
                 entity_data: MIoTEntityData) -> None:
        super().__init__(miot_device=miot_device, entity_data=entity_data)
        self._prop_on = None
        self._action_turn_on = None
        for prop in entity_data.props:
            if prop.name == 'on':
                self._attr_supported_features |= MediaPlayerEntityFeature.TURN_ON
                self._prop_on = prop
                return
        for action in entity_data.actions:
            if action.name == 'turn-on':
                self._attr_supported_features |= MediaPlayerEntityFeature.TURN_ON
                self._action_turn_on = action
                return

    async def async_turn_on(self) -> None:
        if self._prop_on:
            await self.set_property_async(prop=self._prop_on, value=True)
        elif self._action_turn_on:
            await self.action_async(action=self._action_turn_on)


class FeatureTurnOff(_FeatureBase):
    _prop_on: Optional[MIoTSpecProperty]
    _action_turn_off: Optional[MIoTSpecAction]

    def __init__(self, miot_device: MIoTDevice,
                 entity_data: MIoTEntityData) -> None:
        super().__init__(miot_device=miot_device, entity_data=entity_data)
        self._prop_on = None
        self._action_turn_off = None
        for prop in entity_data.props:
            if prop.name == 'on':
                self._attr_supported_features |= MediaPlayerEntityFeature.TURN_OFF
                self._prop_on = prop
                return
        for action in entity_data.actions:
            if action.name == 'turn-off':
                self._attr_supported_features |= MediaPlayerEntityFeature.TURN_OFF
                self._action_turn_off = action
                return

    async def async_turn_off(self) -> None:
        if self._prop_on:
            await self.set_property_async(prop=self._prop_on, value=False)
        elif self._action_turn_off:
            await self.action_async(action=self._action_turn_off)


class FeatureVolumeSet(_FeatureBase):
    _prop_volume: Optional[MIoTSpecProperty]

    def __init__(self, miot_device: MIoTDevice,
                 entity_data: MIoTEntityData) -> None:
        super().__init__(miot_device=miot_device, entity_data=entity_data)
        self._prop_volume = None
        for prop in entity_data.props:
            if prop.name == 'volume':
                self._attr_supported_features |= MediaPlayerEntityFeature.VOLUME_SET
                self._attr_supported_features |= MediaPlayerEntityFeature.VOLUME_STEP
                self._prop_volume = prop
                return

    async def async_set_volume_level(self, volume: float) -> None:
        if not self._prop_volume or not self._prop_volume.value_range:
            return
        await self.set_property_async(
            prop=self._prop_volume,
            value=int(volume * self._prop_volume.value_range.max_))

    @property
    def volume_level(self) -> Optional[float]:
        if not self._prop_volume or not self._prop_volume.value_range:
            return None
        val = self.get_prop_value(prop=self._prop_volume)
        # 優化: 確保轉型為 float 且防範 NoneType 錯誤
        if val is None:
            return None
        return float(val / self._prop_volume.value_range.max_)


class FeatureVolumeMute(_FeatureBase):
    _prop_mute: Optional[MIoTSpecProperty]

    def __init__(self, miot_device: MIoTDevice,
                 entity_data: MIoTEntityData) -> None:
        super().__init__(miot_device=miot_device, entity_data=entity_data)
        self._prop_mute = None
        for prop in entity_data.props:
            if prop.name == 'mute':
                self._attr_supported_features |= MediaPlayerEntityFeature.VOLUME_MUTE
                self._prop_mute = prop
                return

    async def async_mute_volume(self, mute: bool) -> None:
        if not self._prop_mute:
            return
        await self.set_property_async(prop=self._prop_mute, value=mute)

    @property
    def is_volume_muted(self) -> Optional[bool]:
        if not self._prop_mute:
            return None
        val = self.get_prop_value(prop=self._prop_mute)
        # 優化: 嚴格轉換布林值
        return bool(val) if val is not None else None


class FeaturePlay(_FeatureBase):
    _action_play: Optional[MIoTSpecAction]

    def __init__(self, miot_device: MIoTDevice,
                 entity_data: MIoTEntityData) -> None:
        super().__init__(miot_device=miot_device, entity_data=entity_data)
        self._action_play = None
        for action in entity_data.actions:
            if action.name == 'play':
                self._attr_supported_features |= MediaPlayerEntityFeature.PLAY
                self._action_play = action
                return

    async def async_media_play(self) -> None:
        if not self._action_play:
            return
        await self.action_async(action=self._action_play)


class FeaturePause(_FeatureBase):
    _action_pause: Optional[MIoTSpecAction]

    def __init__(self, miot_device: MIoTDevice,
                 entity_data: MIoTEntityData) -> None:
        super().__init__(miot_device=miot_device, entity_data=entity_data)
        self._action_pause = None
        for action in entity_data.actions:
            if action.name == 'pause':
                self._attr_supported_features |= MediaPlayerEntityFeature.PAUSE
                self._action_pause = action
                return

    async def async_media_pause(self) -> None:
        if not self._action_pause:
            return
        await self.action_async(action=self._action_pause)


class FeatureStop(_FeatureBase):
    _action_stop: Optional[MIoTSpecAction]

    def __init__(self, miot_device: MIoTDevice,
                 entity_data: MIoTEntityData) -> None:
        super().__init__(miot_device=miot_device, entity_data=entity_data)
        self._action_stop = None
        for action in entity_data.actions:
            if action.name == 'stop':
                self._attr_supported_features |= MediaPlayerEntityFeature.STOP
                self._action_stop = action
                return

    async def async_media_stop(self) -> None:
        if not self._action_stop:
            return
        await self.action_async(action=self._action_stop)


class FeatureNextTrack(_FeatureBase):
    _action_next: Optional[MIoTSpecAction]

    def __init__(self, miot_device: MIoTDevice,
                 entity_data: MIoTEntityData) -> None:
        super().__init__(miot_device=miot_device, entity_data=entity_data)
        self._action_next = None
        for action in entity_data.actions:
            if action.name == 'next':
                self._attr_supported_features |= MediaPlayerEntityFeature.NEXT_TRACK
                self._action_next = action
                return

    async def async_media_next_track(self) -> None:
        if not self._action_next:
            return
        await self.action_async(action=self._action_next)


class FeaturePreviousTrack(_FeatureBase):
    _action_previous: Optional[MIoTSpecAction]

    def __init__(self, miot_device: MIoTDevice,
                 entity_data: MIoTEntityData) -> None:
        super().__init__(miot_device=miot_device, entity_data=entity_data)
        self._action_previous = None
        for action in entity_data.actions:
            if action.name == 'previous':
                self._attr_supported_features |= MediaPlayerEntityFeature.PREVIOUS_TRACK
                self._action_previous = action
                return

    async def async_media_previous_track(self) -> None:
        if not self._action_previous:
            return
        await self.action_async(action=self._action_previous)


class FeatureSoundMode(_FeatureBase):
    _prop_sound_mode: Optional[MIoTSpecProperty]
    _sound_mode_map: Optional[dict[Any, Any]]
    _sound_mode_reverse_map: dict[Any, Any]

    def __init__(self, miot_device: MIoTDevice,
                 entity_data: MIoTEntityData) -> None:
        super().__init__(miot_device=miot_device, entity_data=entity_data)
        self._prop_sound_mode = None
        self._sound_mode_map = None
        self._sound_mode_reverse_map = {}
        
        for prop in entity_data.props:
            if prop.name != 'mode':
                continue
            if not prop.value_list:
                _LOGGER.error('mode value_list is None, %s', self.entity_id)
                continue
            self._sound_mode_map = prop.value_list.to_map()
            # 優化: 預先建立 O(1) 的反向查詢字典
            self._sound_mode_reverse_map = {v: k for k, v in self._sound_mode_map.items()}
            self._attr_sound_mode_list = list(self._sound_mode_map.values())
            self._attr_supported_features |= MediaPlayerEntityFeature.SELECT_SOUND_MODE
            self._prop_sound_mode = prop

    async def async_select_sound_mode(self, sound_mode: str) -> None:
        if not self._prop_sound_mode:
            return
        # 優化: O(1) 字典查找取代 O(N)
        mode_val = self._sound_mode_reverse_map.get(sound_mode)
        if mode_val is not None:
            await self.set_property_async(prop=self._prop_sound_mode, value=mode_val)

    @property
    def sound_mode(self) -> Optional[str]:
        if not self._prop_sound_mode or not self._sound_mode_map:
            return None
        val = self.get_prop_value(prop=self._prop_sound_mode)
        return self._sound_mode_map.get(val) if val is not None else None


class FeatureSource(_FeatureBase):
    _prop_source: Optional[MIoTSpecProperty]
    _source_map: Optional[dict[Any, Any]]
    _source_reverse_map: dict[Any, Any]

    def __init__(self, miot_device: MIoTDevice,
                 entity_data: MIoTEntityData) -> None:
        super().__init__(miot_device=miot_device, entity_data=entity_data)
        self._prop_source = None
        self._source_map = None
        self._source_reverse_map = {}
        
        for prop in entity_data.props:
            if prop.name != 'input-control':
                continue
            if not prop.value_list:
                _LOGGER.error('input-control value_list is None, %s',
                              self.entity_id)
                continue
            self._source_map = prop.value_list.to_map()
            # 優化: 預先建立 O(1) 的反向查詢字典
            self._source_reverse_map = {v: k for k, v in self._source_map.items()}
            self._attr_source_list = list(self._source_map.values())
            self._attr_supported_features |= MediaPlayerEntityFeature.SELECT_SOURCE
            self._prop_source = prop

    async def async_select_source(self, source: str) -> None:
        if not self._prop_source:
            return
        # 優化: O(1) 字典查找取代 O(N)
        source_val = self._source_reverse_map.get(source)
        if source_val is not None:
            await self.set_property_async(prop=self._prop_source, value=source_val)

    @property
    def source(self) -> Optional[str]:
        if not self._prop_source or not self._source_map:
            return None
        val = self.get_prop_value(prop=self._prop_source)
        return self._source_map.get(val) if val is not None else None


class FeatureState(_FeatureBase):
    _prop_playing_state: Optional[MIoTSpecProperty]
    _playing_state_map: Optional[dict[Any, Any]]

    def __init__(self, miot_device: MIoTDevice,
                 entity_data: MIoTEntityData) -> None:
        super().__init__(miot_device=miot_device, entity_data=entity_data)
        self._prop_playing_state = None
        self._playing_state_map = None
        for prop in entity_data.props:
            if prop.name == 'playing-state':
                if not prop.value_list:
                    _LOGGER.error('playing-state value_list is None, %s',
                                  self.entity_id)
                    continue
                self._playing_state_map = {}
                for item in prop.value_list.items:
                    if item.name in {'playing', 'play'}:
                        self._playing_state_map[item.value] = MediaPlayerState.PLAYING
                    elif item.name in {'pause', 'paused'}:
                        self._playing_state_map[item.value] = MediaPlayerState.PAUSED
                    elif item.name in {'stop', 'stopped'}:
                        self._playing_state_map[item.value] = MediaPlayerState.IDLE
                self._prop_playing_state = prop

    @property
    def state(self) -> Optional[MediaPlayerState]:
        if not self._prop_playing_state or not self._playing_state_map:
            return MediaPlayerState.ON
        val = self.get_prop_value(prop=self._prop_playing_state)
        if val is None:
            return MediaPlayerState.ON
        return self._playing_state_map.get(val, MediaPlayerState.ON)


class WifiSpeaker(FeatureVolumeSet, FeatureVolumeMute, FeaturePlay,
                  FeaturePause, FeatureStop, FeatureNextTrack,
                  FeaturePreviousTrack, FeatureSoundMode, FeatureState):
    """WiFi speaker, aka XiaoAI sound speaker."""

    def __init__(self, miot_device: MIoTDevice,
                 entity_data: MIoTEntityData) -> None:
        """Initialize the device."""
        super().__init__(miot_device=miot_device, entity_data=entity_data)

        self._attr_device_class = MediaPlayerDeviceClass.SPEAKER
        self._attr_media_content_type = MediaType.MUSIC


class Television(FeatureVolumeSet, FeatureVolumeMute, FeaturePlay, FeaturePause,
                 FeatureStop, FeatureNextTrack, FeaturePreviousTrack,
                 FeatureSoundMode, FeatureState, FeatureSource, FeatureTurnOn,
                 FeatureTurnOff):
    """Television"""

    def __init__(self, miot_device: MIoTDevice,
                 entity_data: MIoTEntityData) -> None:
        """Initialize the device."""
        super().__init__(miot_device=miot_device, entity_data=entity_data)

        self._attr_device_class = MediaPlayerDeviceClass.TV
        self._attr_media_content_type = MediaType.VIDEO