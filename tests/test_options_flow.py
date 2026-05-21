"""Options flow persistence tests.

Regression coverage for the community-reported bug where clearing an
optional field (db_sensor, cpu/ram fallback, ignore labels/patterns)
silently reverted to the original value after every HA restart because
the missing key in ``user_input`` never reached ``entry.options`` and
the ``{**data, **options}`` merge in the coordinator resurrected the
value from ``entry.data``.
"""

from __future__ import annotations

from unittest.mock import patch

from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.haghs.const import (
    CONF_CPU_SENSOR,
    CONF_DB_SENSOR,
    CONF_IGNORE_LABELS,
    CONF_IGNORE_PATTERNS,
    CONF_RAM_SENSOR,
    CONF_STORAGE_TYPE,
    DOMAIN,
)
from custom_components.haghs.coordinator import _PsiData

_PSI_AVAILABLE = _PsiData(cpu=0.5, memory=0.5, io=0.5)
_PSI_UNAVAILABLE = _PsiData()


def _merged(entry: MockConfigEntry) -> dict:
    """Reproduce the coordinator-side {**data, **options} merge."""
    return {**entry.data, **entry.options}


async def _run_options_flow(
    hass: HomeAssistant,
    entry: MockConfigEntry,
    user_input: dict,
    *,
    psi: _PsiData = _PSI_AVAILABLE,
) -> None:
    """Open the options flow and submit ``user_input``."""
    with patch(
        "custom_components.haghs.coordinator.HaghsDataUpdateCoordinator._read_psi_sync",
        return_value=psi,
    ):
        result = await hass.config_entries.options.async_init(entry.entry_id)
        assert result["type"] == FlowResultType.FORM

        result = await hass.config_entries.options.async_configure(
            result["flow_id"], user_input=user_input
        )
        assert result["type"] == FlowResultType.CREATE_ENTRY


async def test_clearing_db_sensor_persists(hass: HomeAssistant) -> None:
    """A db_sensor cleared in the options dialog must not resurrect after restart."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_STORAGE_TYPE: "sd",
            CONF_DB_SENSOR: "sensor.wrongly_picked_at_install",
        },
        options={},
    )
    entry.add_to_hass(hass)

    await _run_options_flow(hass, entry, {CONF_STORAGE_TYPE: "sd"})

    assert entry.options[CONF_DB_SENSOR] is None
    assert _merged(entry)[CONF_DB_SENSOR] is None


async def test_clearing_ignore_labels_persists(hass: HomeAssistant) -> None:
    """Removing every ignore label must survive a restart-equivalent merge."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_STORAGE_TYPE: "sd",
            CONF_IGNORE_LABELS: ["legacy_label"],
        },
        options={},
    )
    entry.add_to_hass(hass)

    await _run_options_flow(hass, entry, {CONF_STORAGE_TYPE: "sd"})

    assert entry.options[CONF_IGNORE_LABELS] == []
    assert _merged(entry)[CONF_IGNORE_LABELS] == []


async def test_clearing_ignore_patterns_persists(hass: HomeAssistant) -> None:
    """Removing every ignore pattern must survive a restart-equivalent merge."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_STORAGE_TYPE: "sd",
            CONF_IGNORE_PATTERNS: ["sensor.docker_*"],
        },
        options={},
    )
    entry.add_to_hass(hass)

    await _run_options_flow(hass, entry, {CONF_STORAGE_TYPE: "sd"})

    assert entry.options[CONF_IGNORE_PATTERNS] == []
    assert _merged(entry)[CONF_IGNORE_PATTERNS] == []


async def test_clearing_cpu_ram_persists_when_psi_available(hass: HomeAssistant) -> None:
    """Fallback sensors must be clearable when PSI is available."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_STORAGE_TYPE: "sd",
            CONF_CPU_SENSOR: "sensor.old_cpu",
            CONF_RAM_SENSOR: "sensor.old_ram",
        },
        options={},
    )
    entry.add_to_hass(hass)

    await _run_options_flow(hass, entry, {CONF_STORAGE_TYPE: "sd"}, psi=_PSI_AVAILABLE)

    assert entry.options[CONF_CPU_SENSOR] is None
    assert entry.options[CONF_RAM_SENSOR] is None
    merged = _merged(entry)
    assert merged[CONF_CPU_SENSOR] is None
    assert merged[CONF_RAM_SENSOR] is None


async def test_existing_value_kept_when_field_submitted(hass: HomeAssistant) -> None:
    """A non-empty submission overrides the prior value and is not normalized away."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_STORAGE_TYPE: "sd",
            CONF_DB_SENSOR: "sensor.old_db",
        },
        options={},
    )
    entry.add_to_hass(hass)

    await _run_options_flow(
        hass,
        entry,
        {CONF_STORAGE_TYPE: "sd", CONF_DB_SENSOR: "sensor.new_db"},
    )

    assert entry.options[CONF_DB_SENSOR] == "sensor.new_db"
    assert _merged(entry)[CONF_DB_SENSOR] == "sensor.new_db"
