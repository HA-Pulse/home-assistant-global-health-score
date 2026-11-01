"""Setup without PSI and without CPU/RAM sensors (issue #123).

The persisted CPU/RAM fields count as missing when their value is empty (None), not only when the keys are
absent: the options flow stores cleared fields as explicit None. Since the #123 follow-up (plan HAGHS-20261101-001)
a missing field never blocks the setup: the entry loads, the value is left out of the hardware pillar and a
non-blocking WARNING repair names it.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

from homeassistant.config_entries import ConfigEntry, ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.helpers import issue_registry as ir
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.haghs.const import (
    CONF_CPU_SENSOR,
    CONF_RAM_SENSOR,
    CONF_STORAGE_TYPE,
    DOMAIN,
    IssueIds,
)
from custom_components.haghs.coordinator import _PsiData
from tests.factories import patch_disk

_PSI_SYNC_PATH = "custom_components.haghs.coordinator.HaghsDataUpdateCoordinator._read_psi_sync"
_PSI_ASYNC_PATH = "custom_components.haghs.coordinator.HaghsDataUpdateCoordinator._async_read_psi"

_PSI_NONE = _PsiData(cpu=None, memory=None, io=None)
_PSI_AVAILABLE = _PsiData(cpu=1.0, memory=1.0, io=1.0)


async def _setup_entry(
    hass: HomeAssistant,
    *,
    data: dict[str, Any],
    psi: _PsiData,
    options: dict[str, Any] | None = None,
) -> ConfigEntry:
    """Run the real config entry setup against a patched PSI source."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data=data,
        options=options or {},
        version=3,
        minor_version=4,
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


def _fallback_issue_present(hass: HomeAssistant) -> bool:
    return (DOMAIN, IssueIds.FALLBACK_MISSING) in ir.async_get(hass).issues


def _fallback_issue(hass: HomeAssistant) -> ir.IssueEntry:
    return ir.async_get(hass).issues[(DOMAIN, IssueIds.FALLBACK_MISSING)]


async def test_setup_proceeds_when_psi_missing_and_both_fields_empty(
    hass: HomeAssistant,
) -> None:
    """Both cleared fields (explicit None) and no PSI: setup proceeds with a WARNING repair (was SETUP_ERROR)."""
    entry = await _setup_entry(
        hass,
        data={
            CONF_STORAGE_TYPE: "sd-card",
            CONF_CPU_SENSOR: "sensor.old_cpu",
            CONF_RAM_SENSOR: "sensor.old_ram",
        },
        options={CONF_CPU_SENSOR: None, CONF_RAM_SENSOR: None},
        psi=_PSI_NONE,
    )

    assert entry.state is ConfigEntryState.LOADED
    issue = _fallback_issue(hass)
    assert (issue.severity, issue.is_fixable, issue.is_persistent) == (
        ir.IssueSeverity.WARNING,
        True,
        False,
    )
    assert issue.data == {"entry_id": entry.entry_id}
    attributes = hass.states.get("sensor.system_ha_global_health_score").attributes
    assert (attributes["cpu_ram_source"], attributes["rec_cpu_ram_unmeasured"]) == ("none", True)


async def test_setup_proceeds_when_psi_missing_and_one_field_empty(
    hass: HomeAssistant,
) -> None:
    """Only the CPU sensor stays configured, RAM cleared, no PSI: setup proceeds with a WARNING repair."""
    hass.states.async_set("sensor.old_cpu", "30")
    entry = await _setup_entry(
        hass,
        data={
            CONF_STORAGE_TYPE: "sd-card",
            CONF_CPU_SENSOR: "sensor.old_cpu",
            CONF_RAM_SENSOR: "sensor.old_ram",
        },
        options={CONF_RAM_SENSOR: None},
        psi=_PSI_NONE,
    )

    assert entry.state is ConfigEntryState.LOADED
    assert _fallback_issue(hass).severity is ir.IssueSeverity.WARNING
    attributes = hass.states.get("sensor.system_ha_global_health_score").attributes
    assert (attributes["cpu_ram_source"], attributes["rec_cpu_ram_unmeasured"]) == ("partial", True)


async def test_setup_proceeds_when_psi_missing_and_sensors_configured(
    hass: HomeAssistant,
) -> None:
    """Both sensors configured and no PSI: setup proceeds, no issue."""
    hass.states.async_set("sensor.old_cpu", "30")
    hass.states.async_set("sensor.old_ram", "75")
    entry = await _setup_entry(
        hass,
        data={
            CONF_STORAGE_TYPE: "sd-card",
            CONF_CPU_SENSOR: "sensor.old_cpu",
            CONF_RAM_SENSOR: "sensor.old_ram",
        },
        psi=_PSI_NONE,
    )

    assert entry.state is ConfigEntryState.LOADED
    assert not _fallback_issue_present(hass)


async def test_setup_proceeds_with_psi_and_cleared_fields(
    hass: HomeAssistant,
) -> None:
    """PSI available with both fields cleared stays allowed (see #49)."""
    entry = await _setup_entry(
        hass,
        data={
            CONF_STORAGE_TYPE: "sd-card",
            CONF_CPU_SENSOR: None,
            CONF_RAM_SENSOR: None,
        },
        psi=_PSI_AVAILABLE,
    )

    assert entry.state is ConfigEntryState.LOADED
    assert not _fallback_issue_present(hass)
