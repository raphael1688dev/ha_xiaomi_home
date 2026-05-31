"""Unit tests for the entity ID migration logic."""
import pytest
from unittest.mock import MagicMock, patch
from custom_components.xiaomi_home import _async_migrate_legacy_entity_ids


@pytest.mark.asyncio
async def test_migration_legacy_action_orphans():
    """Test that Phase 1 removes action orphans with unique_id == entity_id."""
    hass_mock = MagicMock()
    entry_id = "test_entry"
    
    # Mock entity registry
    er_mock = MagicMock()
    
    # Mock entities:
    # 1. An action orphan (button domain, unique_id == entity_id)
    orphan_entry = MagicMock()
    orphan_entry.domain = "button"
    orphan_entry.unique_id = "button.my_action"
    orphan_entry.entity_id = "button.my_action"
    
    # 2. A normal entity (domain sensor, unique_id != entity_id)
    normal_entry = MagicMock()
    normal_entry.domain = "sensor"
    normal_entry.unique_id = "unique_123"
    normal_entry.entity_id = "sensor.my_sensor"

    # Set up entries return for config entry
    entries_list = [orphan_entry, normal_entry]

    with patch("custom_components.xiaomi_home.entity_registry.async_get", return_value=er_mock), \
         patch("custom_components.xiaomi_home.entity_registry.async_entries_for_config_entry", return_value=entries_list):
        
        await _async_migrate_legacy_entity_ids(hass_mock, entry_id, [])
        
        # Phase 1 should remove the orphan_entry by its entity_id
        er_mock.async_remove.assert_any_call("button.my_action")
        # Should not remove the normal entry
        for call in er_mock.async_remove.call_args_list:
            assert call[0][0] != "sensor.my_sensor"


@pytest.mark.asyncio
async def test_migration_stable_format():
    """Test that Phase 2 migrates entities to stable formats based on expected map."""
    hass_mock = MagicMock()
    entry_id = "test_entry"
    
    # Mock entity registry
    er_mock = MagicMock()
    
    # Mock device
    device_mock = MagicMock()
    device_mock.get_expected_entity_ids.return_value = {
        "12345_switch_p_2_1": "switch.device_switch"
    }
    device_mock.gen_device_unique_id.return_value = "12345_lamp_lamp"
    device_mock.entity_id_prefix = "device_lamp"
    device_mock.did = "12345"

    # Mock entity to migrate:
    # unique_id is in expected mapping, but entity_id is old format
    entity_to_migrate = MagicMock()
    entity_to_migrate.domain = "switch"
    entity_to_migrate.unique_id = "12345_switch_p_2_1"
    entity_to_migrate.entity_id = "switch.old_entity_name"

    entries_list = [entity_to_migrate]

    with patch("custom_components.xiaomi_home.entity_registry.async_get", return_value=er_mock), \
         patch("custom_components.xiaomi_home.entity_registry.async_entries_for_config_entry", return_value=entries_list):
        
        await _async_migrate_legacy_entity_ids(hass_mock, entry_id, [device_mock])
        
        # Verify it updated the entity to the expected new target ID
        er_mock.async_update_entity.assert_called_once_with(
            "switch.old_entity_name", new_entity_id="switch.device_switch"
        )
