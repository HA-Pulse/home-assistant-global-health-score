"""#123 follow-up: the update from v2.3.0 never ends in "Action required".

Entries as v2.3.0 saves them (config entry 3.4, options from its own dialog, CPU/RAM fields empty because PSI was
available when they were set up), real registry entries for System Monitor. Three cases: PSI present, no PSI with
System Monitor, no PSI without. In all three the entry loads and the score sensor is available.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

import pytest
import voluptuous as vol
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import issue_registry as ir
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.haghs.const import CONF_CPU_SENSOR, CONF_RAM_SENSOR, DOMAIN, IssueIds
from custom_components.haghs.coordinator import _PsiData
from custom_components.haghs.repairs import MissingFallbackSensorRepairFlow
from tests.factories import patch_disk

_PSI_SYNC_PATH = "custom_components.haghs.coordinator.HaghsDataUpdateCoordinator._read_psi_sync"
_PSI_ASYNC_PATH = "custom_components.haghs.coordinator.HaghsDataUpdateCoordinator._async_read_psi"
V230_DATA = {
    "cpu_sensor": None,
    "ram_sensor": None,
    "storage_type": "ssd",
    "ignore_labels": [],
    "ignore_patterns": [],
}
V230_OPTIONS = {
    "cpu_sensor": None,
    "ram_sensor": None,
    "storage_type": "ssd",
    "ignore_labels": [],
    "ignore_patterns": [],
    "update_interval": 90,
    "zombie_grace_minutes": 15,
    "battery_grace_minutes": 30,
}
PSI = {
    "present": _PsiData(cpu=1.0, memory=1.0, io=1.0),
    "absent": _PsiData(cpu=None, memory=None, io=None),
}


def _system_monitor(hass: HomeAssistant) -> dict[str, str]:
    registry = er.async_get(hass)
    sm_entry = MockConfigEntry(domain="systemmonitor")
    sm_entry.add_to_hass(hass)
    found = {}
    for option, unique_id in (
        (CONF_CPU_SENSOR, "processor_use"),
        (CONF_RAM_SENSOR, "memory_use_percent"),
    ):
        entity = registry.async_get_or_create(
            "sensor",
            "systemmonitor",
            unique_id,
            config_entry=sm_entry,
            suggested_object_id=unique_id,
        )
        found[option] = entity.entity_id
    return found


async def _update(hass: HomeAssistant, psi: _PsiData) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN, data=V230_DATA, options=V230_OPTIONS, version=3, minor_version=4
    )
    entry.add_to_hass(hass)

    async def _fake_async_read(_self: Any) -> _PsiData:
        return psi

    with (
        patch(_PSI_SYNC_PATH, return_value=psi),
        patch(_PSI_ASYNC_PATH, _fake_async_read),
        patch_disk(),
    ):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    return entry


def _suggested(result: dict) -> dict[str, Any]:
    return {
        str(key): (key.description or {}).get("suggested_value")
        for key in result["data_schema"].schema
        if isinstance(key, vol.Marker)
    }


@pytest.mark.parametrize(
    ("case", "system_monitor", "source", "issue"),
    [
        ("present", False, "psi", False),
        ("absent", True, "none", True),
        ("absent", False, "none", True),
    ],
)
async def test_update_from_v230_loads_in_every_case(
    hass, case, system_monitor, source, issue
) -> None:
    monitor = _system_monitor(hass) if system_monitor else {}
    entry = await _update(hass, PSI[case])
    assert entry.state is ConfigEntryState.LOADED
    assert dict(entry.options) == V230_OPTIONS  # nothing written by HAGHS itself
    state = hass.states.get("sensor.system_ha_global_health_score")
    assert state is not None
    assert state.state not in ("unavailable", "unknown")
    assert (state.attributes["cpu_ram_source"], state.attributes["rec_cpu_ram_unmeasured"]) == (
        source,
        issue,
    )
    found = ir.async_get(hass).async_get_issue(DOMAIN, IssueIds.FALLBACK_MISSING)
    assert (found is not None) is issue
    if issue:
        assert found.severity is ir.IssueSeverity.WARNING
        flow = MissingFallbackSensorRepairFlow(entry.entry_id)
        flow.hass = hass
        form = await flow.async_step_init()
        assert form["type"] == "form"
        assert _suggested(form) == {
            CONF_CPU_SENSOR: monitor.get(CONF_CPU_SENSOR),
            CONF_RAM_SENSOR: monitor.get(CONF_RAM_SENSOR),
        }
        assert dict(entry.options) == V230_OPTIONS  # opening the form writes nothing


async def test_repair_submit_writes_the_sensors_and_the_repair_goes(hass: HomeAssistant) -> None:
    monitor = _system_monitor(hass)
    hass.states.async_set(monitor[CONF_CPU_SENSOR], "12")
    hass.states.async_set(monitor[CONF_RAM_SENSOR], "40")
    entry = await _update(hass, PSI["absent"])
    flow = MissingFallbackSensorRepairFlow(entry.entry_id)
    flow.hass = hass
    with (
        patch(_PSI_SYNC_PATH, return_value=PSI["absent"]),
        patch(_PSI_ASYNC_PATH, lambda _self: _async(PSI["absent"])),
        patch_disk(),
    ):
        done = await flow.async_step_confirm(dict(monitor))
        await hass.async_block_till_done()
    assert done["type"] == "create_entry"
    assert entry.options[CONF_CPU_SENSOR] == monitor[CONF_CPU_SENSOR]
    assert entry.options[CONF_RAM_SENSOR] == monitor[CONF_RAM_SENSOR]
    assert entry.state is ConfigEntryState.LOADED
    assert ir.async_get(hass).async_get_issue(DOMAIN, IssueIds.FALLBACK_MISSING) is None
    attributes = hass.states.get("sensor.system_ha_global_health_score").attributes
    assert (attributes["cpu_ram_source"], attributes["rec_cpu_ram_unmeasured"]) == (
        "sensors",
        False,
    )


async def _async(value):
    return value


async def test_a_disabled_system_monitor_entity_is_not_suggested(hass: HomeAssistant) -> None:
    monitor = _system_monitor(hass)
    er.async_get(hass).async_update_entity(
        monitor[CONF_CPU_SENSOR], disabled_by=er.RegistryEntryDisabler.USER
    )
    entry = await _update(hass, PSI["absent"])
    flow = MissingFallbackSensorRepairFlow(entry.entry_id)
    flow.hass = hass
    form = await flow.async_step_init()
    assert _suggested(form) == {CONF_CPU_SENSOR: None, CONF_RAM_SENSOR: monitor[CONF_RAM_SENSOR]}
