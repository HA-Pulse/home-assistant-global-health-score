"""The score sensor has state_class "measurement", so Home Assistant keeps long-term statistics for it.

Only the state class is added: the state value, the unit and every HAGHS attribute stay as they were
(pinned against the dev capture of tests/test_recorder_attribute_size.py).
"""

from __future__ import annotations

import pytest
from homeassistant.components.recorder.statistics import async_list_statistic_ids
from homeassistant.components.sensor import SensorStateClass
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.setup import async_setup_component
from pytest_homeassistant.common import MockEntityPlatform
from pytest_homeassistant.components.recorder.common import async_wait_recording_done

from custom_components.haghs.const import DOMAIN
from custom_components.haghs.sensor import HaghsSensor
from tests import test_recorder_attribute_size as attribute_size
from tests.factories import device_entries, make_coordinator, patch_disk, patch_psi

HA_META = {"friendly_name", "icon", "unit_of_measurement", "state_class"}


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations() -> None:
    """The recorder must start before hass; this module loads no custom integration."""
    return


@pytest.fixture
async def added_sensor(recorder_mock, hass: HomeAssistant):
    """The score sensor added through an entity platform; cleaned up even when a test fails."""
    sensor = await _added_sensor(hass)
    yield sensor
    await _remove(hass, sensor)


async def _added_sensor(hass: HomeAssistant) -> HaghsSensor:
    coordinator = make_coordinator(hass)
    with patch_psi(cpu=1.0, memory=1.0, io=1.0), patch_disk():
        await coordinator.async_refresh()
    entry = hass.config_entries.async_get_entry(coordinator._entry_id)
    assert entry is not None
    sensor = HaghsSensor(coordinator, entry)
    await MockEntityPlatform(hass, domain="sensor", platform_name=DOMAIN).async_add_entities(
        [sensor]
    )
    sensor.async_write_ha_state()
    return sensor


async def _remove(hass: HomeAssistant, sensor: HaghsSensor) -> None:
    entry = hass.config_entries.async_get_entry(sensor.coordinator._entry_id)
    object.__setattr__(entry, "state", ConfigEntryState.NOT_LOADED)
    await sensor.coordinator.async_shutdown()


async def test_score_sensor_has_state_class_measurement(added_sensor, hass: HomeAssistant) -> None:
    sensor = added_sensor
    state = hass.states.get(sensor.entity_id)

    assert sensor.state_class is SensorStateClass.MEASUREMENT
    assert state.attributes["state_class"] == "measurement"
    assert state.attributes["unit_of_measurement"] == "%"
    assert state.state == str(sensor.coordinator.data["global_score"])
    extra = sensor.extra_state_attributes or {}
    assert extra
    assert set(state.attributes) - set(extra) == HA_META
    assert {key: state.attributes[key] for key in extra} == extra


async def test_score_sensor_is_listed_for_long_term_statistics(
    added_sensor, hass: HomeAssistant
) -> None:
    sensor = added_sensor
    assert await async_setup_component(hass, "sensor", {})
    await async_wait_recording_done(hass)

    listed = await async_list_statistic_ids(hass, statistic_type="mean")
    ours = [item for item in listed if item["statistic_id"] == sensor.entity_id]
    assert len(ours) == 1
    assert ours[0]["statistics_unit_of_measurement"] == "%"


async def test_state_attributes_match_the_dev_pins_plus_state_class(
    recorder_mock, hass: HomeAssistant, freezer
) -> None:
    """Pinned: every HAGHS attribute in the state equals the dev capture; only HA's meta attributes come on top."""
    freezer.move_to(attribute_size.FROZEN)
    sensor, entry = await attribute_size._worst_case(hass, length=80)
    await MockEntityPlatform(hass, domain="sensor", platform_name=DOMAIN).async_add_entities(
        [sensor]
    )
    sensor.async_write_ha_state()
    state = hass.states.get(sensor.entity_id)
    by_name = {device.name: device.id for device in device_entries(dr.async_get(hass))}
    expected = {  # the same expectation as test_recorder_attribute_size.test_current_attributes_are_unchanged
        **attribute_size.DEV_ATTRIBUTES,
        "integration_unhealthy_entries": [],
        "empty_device_count": 0,
        "empty_devices": [],
        "rec_empty_devices": False,
        "conditional_ignore_active": False,
        "dead_device_ids": [
            by_name[name] for name in attribute_size.DEV_ATTRIBUTES["dead_devices"]
        ],
        "empty_device_ids": [],
        "cpu_ram_source": "psi",
        "rec_cpu_ram_unmeasured": False,
    }
    assert {key: value for key, value in state.attributes.items() if key not in HA_META} == expected
    assert {key: state.attributes[key] for key in HA_META} == {
        "friendly_name": state.attributes["friendly_name"],
        "icon": "mdi:shield-check",
        "unit_of_measurement": "%",
        "state_class": "measurement",
    }
    object.__setattr__(entry, "state", ConfigEntryState.NOT_LOADED)
    await sensor.coordinator.async_shutdown()
