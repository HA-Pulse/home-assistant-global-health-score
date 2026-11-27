"""The score sensor has state_class "measurement", so Home Assistant keeps long-term statistics for it.

Only the state class is added: the state value, the unit and every HAGHS attribute stay as they were
(the exact attribute pins live in tests/test_recorder_attribute_size.py).
"""

from __future__ import annotations

import pytest
from homeassistant.components.recorder.statistics import async_list_statistic_ids
from homeassistant.components.sensor import SensorStateClass
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.setup import async_setup_component
from pytest_homeassistant.common import MockEntityPlatform
from pytest_homeassistant.components.recorder.common import async_wait_recording_done

from custom_components.haghs.const import DOMAIN
from custom_components.haghs.sensor import HaghsSensor
from tests.factories import make_coordinator, patch_disk, patch_psi

HA_META = {"friendly_name", "icon", "unit_of_measurement", "state_class"}


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations() -> None:
    """The recorder must start before hass; this module loads no custom integration."""
    return


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


async def test_score_sensor_has_state_class_measurement(recorder_mock, hass: HomeAssistant) -> None:
    sensor = await _added_sensor(hass)
    state = hass.states.get(sensor.entity_id)

    assert sensor.state_class is SensorStateClass.MEASUREMENT
    assert state.attributes["state_class"] == "measurement"
    assert state.attributes["unit_of_measurement"] == "%"
    assert state.state == str(sensor.coordinator.data["global_score"])
    extra = sensor.extra_state_attributes or {}
    assert extra
    assert set(state.attributes) - set(extra) == HA_META
    assert {key: state.attributes[key] for key in extra} == extra
    await _remove(hass, sensor)


async def test_score_sensor_is_listed_for_long_term_statistics(
    recorder_mock, hass: HomeAssistant
) -> None:
    assert await async_setup_component(hass, "sensor", {})
    sensor = await _added_sensor(hass)
    await async_wait_recording_done(hass)

    listed = await async_list_statistic_ids(hass, statistic_type="mean")
    ours = [item for item in listed if item["statistic_id"] == sensor.entity_id]
    assert len(ours) == 1
    assert ours[0]["statistics_unit_of_measurement"] == "%"
    await _remove(hass, sensor)
