"""Options flow persistence tests.

Regression coverage for the community-reported bug where clearing an
optional field (db_sensor, cpu/ram fallback, ignore labels/patterns)
silently reverted to the original value after every HA restart because
the missing key in ``user_input`` never reached ``entry.options`` and
the ``{**data, **options}`` merge in the coordinator resurrected the
value from ``entry.data``.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import pytest
from homeassistant.config_entries import ConfigEntryState
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
from custom_components.haghs.coordinator import HaghsDataUpdateCoordinator, _PsiData

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
            CONF_STORAGE_TYPE: "sd-card",
            CONF_DB_SENSOR: "sensor.wrongly_picked_at_install",
        },
        options={},
    )
    entry.add_to_hass(hass)

    await _run_options_flow(hass, entry, {CONF_STORAGE_TYPE: "sd-card"})

    assert entry.options[CONF_DB_SENSOR] is None
    assert _merged(entry)[CONF_DB_SENSOR] is None


async def test_clearing_ignore_labels_persists(hass: HomeAssistant) -> None:
    """Removing every ignore label must survive a restart-equivalent merge."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_STORAGE_TYPE: "sd-card",
            CONF_IGNORE_LABELS: ["legacy_label"],
        },
        options={},
    )
    entry.add_to_hass(hass)

    await _run_options_flow(hass, entry, {CONF_STORAGE_TYPE: "sd-card"})

    assert entry.options[CONF_IGNORE_LABELS] == []
    assert _merged(entry)[CONF_IGNORE_LABELS] == []


async def test_clearing_ignore_patterns_persists(hass: HomeAssistant) -> None:
    """Removing every ignore pattern must survive a restart-equivalent merge."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_STORAGE_TYPE: "sd-card",
            CONF_IGNORE_PATTERNS: ["sensor.docker_*"],
        },
        options={},
    )
    entry.add_to_hass(hass)

    await _run_options_flow(hass, entry, {CONF_STORAGE_TYPE: "sd-card"})

    assert entry.options[CONF_IGNORE_PATTERNS] == []
    assert _merged(entry)[CONF_IGNORE_PATTERNS] == []


async def test_clearing_cpu_ram_persists_when_psi_available(hass: HomeAssistant) -> None:
    """Fallback sensors must be clearable when PSI is available."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_STORAGE_TYPE: "sd-card",
            CONF_CPU_SENSOR: "sensor.old_cpu",
            CONF_RAM_SENSOR: "sensor.old_ram",
        },
        options={},
    )
    entry.add_to_hass(hass)

    await _run_options_flow(hass, entry, {CONF_STORAGE_TYPE: "sd-card"}, psi=_PSI_AVAILABLE)

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
            CONF_STORAGE_TYPE: "sd-card",
            CONF_DB_SENSOR: "sensor.old_db",
        },
        options={},
    )
    entry.add_to_hass(hass)

    await _run_options_flow(
        hass,
        entry,
        {CONF_STORAGE_TYPE: "sd-card", CONF_DB_SENSOR: "sensor.new_db"},
    )

    assert entry.options[CONF_DB_SENSOR] == "sensor.new_db"
    assert _merged(entry)[CONF_DB_SENSOR] == "sensor.new_db"


async def test_entry_exclusion_selector_includes_failed_duplicate_entries(hass) -> None:
    """Selection uses entry IDs, even when no devices or entities exist."""
    entries = [MockConfigEntry(domain="androidtv", title="Fire TV", data={}) for _ in range(2)]
    for other in entries:
        other.add_to_hass(hass)
        object.__setattr__(other, "state", ConfigEntryState.SETUP_RETRY)
    entry = MockConfigEntry(domain=DOMAIN, data={CONF_STORAGE_TYPE: "sd-card"})
    entry.add_to_hass(hass)
    with patch(
        "custom_components.haghs.coordinator.HaghsDataUpdateCoordinator._read_psi_sync",
        return_value=_PSI_AVAILABLE,
    ):
        result = await hass.config_entries.options.async_init(entry.entry_id)
    schema = result["data_schema"].schema
    assert "ignored_integration_entries" in schema
    config = schema["ignored_integration_entries"].config
    assert config["multiple"] is True
    assert config["custom_value"] is False
    choices = {option["value"]: option["label"] for option in config["options"]}
    for other in entries:
        assert choices[other.entry_id] == f"Fire TV (androidtv, {other.entry_id})"
    assert len({choices[other.entry_id] for other in entries}) == 2


async def _open_exclusion_options(hass, entry) -> dict:
    with patch(
        "custom_components.haghs.coordinator.HaghsDataUpdateCoordinator._read_psi_sync",
        return_value=_PSI_AVAILABLE,
    ):
        return await hass.config_entries.options.async_init(entry.entry_id)


@pytest.mark.parametrize("omitted", [False, True])
async def test_entry_exclusions_set_remove_clear_and_reopen(hass, omitted) -> None:
    key = "ignored_integration_entries"
    entries = [MockConfigEntry(domain="androidtv", data={}) for _ in range(2)]
    for other in entries:
        other.add_to_hass(hass)
        object.__setattr__(other, "state", ConfigEntryState.SETUP_ERROR)
    ids = [other.entry_id for other in entries]
    entry = MockConfigEntry(domain=DOMAIN, data={CONF_STORAGE_TYPE: "sd-card", key: ids})
    entry.add_to_hass(hass)
    for selection, expected_count in [(ids, 0), (ids[1:], 1), ([], 2)]:
        user_input = {CONF_STORAGE_TYPE: "sd-card", key: selection}
        if omitted and not selection:
            user_input.pop(key)
        await _run_options_flow(hass, entry, user_input)
        assert entry.options[key] == selection
        # Rebuild the real coordinator; options override the legacy data value.
        coord = HaghsDataUpdateCoordinator(hass, entry)
        assert coord._count_unhealthy_integrations() == expected_count
        reopened = await _open_exclusion_options(hass, entry)
        marker = next(field for field in reopened["data_schema"].schema if field == key)
        assert marker.description["suggested_value"] == selection


async def test_stale_entry_exclusions_are_not_suggested_or_saved(hass) -> None:
    key = "ignored_integration_entries"
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_STORAGE_TYPE: "sd-card"},
        options={key: ["removed-entry"]},
    )
    entry.add_to_hass(hass)
    result = await _open_exclusion_options(hass, entry)
    marker = next(field for field in result["data_schema"].schema if field == key)
    assert marker.description["suggested_value"] == []
    assert entry.options[key] == ["removed-entry"], "Opening must not change stored options"
    # The direct handler also filters unknown IDs instead of persisting them.
    from custom_components.haghs.config_flow import HaghsOptionsFlowHandler

    flow = HaghsOptionsFlowHandler(entry)
    flow.hass = hass
    saved = await flow.async_step_init({CONF_STORAGE_TYPE: "sd-card", key: ["removed-entry"]})
    assert saved["data"][key] == []


async def test_entry_removed_while_options_open_does_not_exclude_replacement(hass) -> None:
    key = "ignored_integration_entries"
    removed = MockConfigEntry(domain="androidtv", title="Fire TV", data={})
    removed.add_to_hass(hass)
    entry = MockConfigEntry(domain=DOMAIN, data={CONF_STORAGE_TYPE: "sd-card"})
    entry.add_to_hass(hass)
    opened = await _open_exclusion_options(hass, entry)
    with patch(
        "homeassistant.loader.Integration.async_get_component", return_value=SimpleNamespace()
    ):
        removed_result = await hass.config_entries.async_remove(removed.entry_id)
        assert removed_result["require_restart"] is False
    replacement = MockConfigEntry(domain="androidtv", title="Fire TV", data={})
    replacement.add_to_hass(hass)
    object.__setattr__(replacement, "state", ConfigEntryState.SETUP_RETRY)
    result = await hass.config_entries.options.async_configure(
        opened["flow_id"],
        user_input={CONF_STORAGE_TYPE: "sd-card", key: [removed.entry_id]},
    )
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert entry.options[key] == []
    assert HaghsDataUpdateCoordinator(hass, entry)._count_unhealthy_integrations() == 1


async def test_entry_selector_sorted_with_domain_fallback_for_empty_title(hass) -> None:
    others = [
        MockConfigEntry(domain="androidtv", title=title, data={}) for title in ["Z", "", "A", "A"]
    ]
    for other in others:
        other.add_to_hass(hass)
    entry = MockConfigEntry(domain=DOMAIN, data={CONF_STORAGE_TYPE: "sd-card"})
    entry.add_to_hass(hass)
    result = await _open_exclusion_options(hass, entry)
    options = result["data_schema"].schema["ignored_integration_entries"].config["options"]
    expected = sorted(
        hass.config_entries.async_entries(),
        key=lambda item: (item.title, item.domain, item.entry_id),
    )
    assert [option["value"] for option in options] == [item.entry_id for item in expected]
    fallback = next(option for option in options if option["value"] == others[1].entry_id)
    assert fallback["label"] == f"androidtv (androidtv, {others[1].entry_id})"
