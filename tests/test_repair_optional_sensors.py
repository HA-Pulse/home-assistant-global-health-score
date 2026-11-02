"""The CPU/RAM repair asks only for what is missing: both fields optional, empty fields keep the option (P4)."""

from __future__ import annotations

from unittest.mock import patch

import voluptuous as vol
from homeassistant.core import HomeAssistant
from homeassistant.helpers import issue_registry as ir

from custom_components.haghs.const import CONF_CPU_SENSOR, CONF_RAM_SENSOR, DOMAIN, IssueIds
from custom_components.haghs.coordinator import _PsiData
from custom_components.haghs.repairs import MissingFallbackSensorRepairFlow
from tests.factories import patch_disk
from tests.test_cpu_ram_source_update import (
    _PSI_ASYNC_PATH,
    _PSI_SYNC_PATH,
    V230_OPTIONS,
    _system_monitor,
    _update,
)

CPU_ONLY = _PsiData(cpu=1.0, memory=None, io=None)  # memory not measured: partial


async def _submit(hass: HomeAssistant, entry, user_input: dict):
    flow = MissingFallbackSensorRepairFlow(entry.entry_id)
    flow.hass = hass

    async def _read(_self):
        return CPU_ONLY

    with patch(_PSI_SYNC_PATH, return_value=CPU_ONLY), patch(_PSI_ASYNC_PATH, _read), patch_disk():
        done = await flow.async_step_confirm(user_input)
        await hass.async_block_till_done()
    return done


async def test_both_fields_are_optional(hass: HomeAssistant) -> None:
    entry = await _update(hass, CPU_ONLY)
    flow = MissingFallbackSensorRepairFlow(entry.entry_id)
    flow.hass = hass
    form = await flow.async_step_init()
    markers = {str(key): type(key) for key in form["data_schema"].schema}
    assert markers == {CONF_CPU_SENSOR: vol.Optional, CONF_RAM_SENSOR: vol.Optional}


async def test_only_the_missing_ram_sensor_is_submitted(hass: HomeAssistant) -> None:
    monitor = _system_monitor(hass)
    hass.states.async_set(monitor[CONF_RAM_SENSOR], "40")
    entry = await _update(hass, CPU_ONLY)
    assert ir.async_get(hass).async_get_issue(DOMAIN, IssueIds.FALLBACK_MISSING) is not None
    done = await _submit(hass, entry, {CONF_RAM_SENSOR: monitor[CONF_RAM_SENSOR]})
    assert done["type"] == "create_entry"
    assert entry.options[CONF_RAM_SENSOR] == monitor[CONF_RAM_SENSOR]
    assert entry.options[CONF_CPU_SENSOR] is None  # untouched; CPU is measured by PSI
    assert ir.async_get(hass).async_get_issue(DOMAIN, IssueIds.FALLBACK_MISSING) is None
    attributes = hass.states.get("sensor.system_ha_global_health_score").attributes
    assert attributes["cpu_ram_source"] == "sensors"


async def test_an_empty_submit_writes_nothing_and_the_repair_stays(hass: HomeAssistant) -> None:
    entry = await _update(hass, CPU_ONLY)
    with patch.object(
        hass.config_entries,
        "async_schedule_reload",
        wraps=hass.config_entries.async_schedule_reload,
    ) as reload:
        done = await _submit(hass, entry, {CONF_CPU_SENSOR: "", CONF_RAM_SENSOR: None})
    reload.assert_called_once_with(entry.entry_id)
    assert done["type"] == "create_entry"
    assert dict(entry.options) == V230_OPTIONS
    assert ir.async_get(hass).async_get_issue(DOMAIN, IssueIds.FALLBACK_MISSING) is not None


async def test_after_an_empty_submit_the_next_cycle_keeps_the_repair(hass: HomeAssistant) -> None:
    """Nothing picked and CPU/RAM still not measured: the repair stays open after the reload and the next cycle."""
    entry = await _update(hass, CPU_ONLY)
    await _submit(hass, entry, {})
    registry = ir.async_get(hass)
    assert registry.async_get_issue(DOMAIN, IssueIds.FALLBACK_MISSING) is not None
    coordinator = hass.data[DOMAIN][entry.entry_id]

    async def _read(_self):
        return CPU_ONLY

    with patch(_PSI_SYNC_PATH, return_value=CPU_ONLY), patch(_PSI_ASYNC_PATH, _read), patch_disk():
        await coordinator.async_refresh()
        await hass.async_block_till_done()
    assert registry.async_get_issue(DOMAIN, IssueIds.FALLBACK_MISSING) is not None
    assert coordinator.data["cpu_ram_source"] == "partial"
