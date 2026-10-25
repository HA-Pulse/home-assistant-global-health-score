"""Conditional ignore labels: extra ignore labels while a helper entity is "on".

The options name labels and one helper (input_boolean, switch or binary_sensor). While the
helper is exactly "on" the labels count as ignore labels; "off", "unavailable", "unknown"
or a missing (deleted or renamed) helper leave them out. Configuration stays in the
OptionsFlow; automations only switch the helper.
"""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any
from unittest.mock import patch

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import STATE_OFF, STATE_ON, STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import area_registry as ar
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import label_registry as lr
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.haghs.config_flow import HaghsOptionsFlowHandler
from custom_components.haghs.const import CONF_IGNORE_LABELS, CONF_STORAGE_TYPE, DOMAIN
from custom_components.haghs.coordinator import HaghsDataUpdateCoordinator, _PsiData
from tests.factories import make_coordinator, patch_disk, patch_psi

HELPER = "input_boolean.vacation"
LABELS = "conditional_ignore_labels"
ENTITY = "conditional_ignore_entity"
_PSI = _PsiData(cpu=0.5, memory=0.5, io=0.5)


@pytest.fixture(autouse=True)
def _reset_states(hass):
    """No integration was really loaded: avoid fake loaded states at teardown."""
    yield
    for entry in hass.config_entries.async_entries():
        if entry.domain != DOMAIN:
            object.__setattr__(entry, "state", ConfigEntryState.NOT_LOADED)


def _label(hass: HomeAssistant, name: str) -> str:
    label_id = lr.async_get(hass).async_create(name).label_id
    assert label_id != name
    return label_id


def _zombie(hass: HomeAssistant, object_id: str, *, labels: set[str] | None = None) -> str:
    entry = er.async_get(hass).async_get_or_create(
        "sensor", "test_platform", f"uid_{object_id}", suggested_object_id=object_id
    )
    if labels:
        er.async_get(hass).async_update_entity(entry.entity_id, labels=labels)
    _unavailable_for_30_minutes(hass, entry.entity_id)
    return entry.entity_id


def _unavailable_for_30_minutes(hass: HomeAssistant, entity_id: str) -> None:
    """Past the 5-minute zombie grace (make_coordinator backdates the boot by 120 minutes)."""
    hass.states.async_set(entity_id, STATE_UNAVAILABLE)
    hass.states.get(entity_id).last_changed = dt_util.utcnow() - timedelta(minutes=30)


async def _zombies(coord: HaghsDataUpdateCoordinator) -> tuple[int, bool]:
    with patch_psi(cpu=0.0, memory=0.0, io=0.0), patch_disk():
        result = await coord._async_update_data()
    return result["zombie_count"], result["conditional_ignore_active"]


# --- options flow -----------------------------------------------------------------------


async def _submit(hass: HomeAssistant, user_input: dict[str, Any]):
    entry = MockConfigEntry(domain=DOMAIN, data={})
    entry.add_to_hass(hass)
    with patch.object(HaghsDataUpdateCoordinator, "_read_psi_sync", return_value=_PSI):
        flow = HaghsOptionsFlowHandler(entry)
        flow.hass = hass
        return await flow.async_step_init({CONF_STORAGE_TYPE: "sd-card", **user_input})


async def test_options_both_empty_or_both_set_are_accepted(hass) -> None:
    label = _label(hass, "Vacation")
    empty = await _submit(hass, {})
    assert empty["type"] == FlowResultType.CREATE_ENTRY
    assert (empty["data"][LABELS], empty["data"][ENTITY]) == ([], None)
    both = await _submit(hass, {LABELS: [label], ENTITY: HELPER})
    assert both["type"] == FlowResultType.CREATE_ENTRY
    assert (both["data"][LABELS], both["data"][ENTITY]) == ([label], HELPER)


@pytest.mark.parametrize("user_input", [{LABELS: ["vacation"]}, {ENTITY: HELPER}])
async def test_options_only_one_set_is_rejected(hass, user_input) -> None:
    result = await _submit(hass, user_input)
    assert result["type"] == FlowResultType.FORM
    assert result["errors"] == {ENTITY: "conditional_ignore_incomplete"}


async def test_options_offer_only_helper_domains(hass) -> None:
    entry = MockConfigEntry(domain=DOMAIN, data={})
    entry.add_to_hass(hass)
    with patch.object(HaghsDataUpdateCoordinator, "_read_psi_sync", return_value=_PSI):
        form = await hass.config_entries.options.async_init(entry.entry_id)
    config = form["data_schema"].schema[ENTITY].config
    assert config["filter"][0]["domain"] == ["input_boolean", "switch", "binary_sensor"]
    assert form["data_schema"].schema[LABELS].config["multiple"] is True


# --- effective labels -----------------------------------------------------------------


@pytest.mark.parametrize(
    ("helper_state", "expected"),
    [
        (STATE_ON, (0, True)),
        (STATE_OFF, (1, False)),
        (STATE_UNAVAILABLE, (1, False)),
        (STATE_UNKNOWN, (1, False)),
        (None, (1, False)),
    ],
)
async def test_zombie_with_conditional_label_follows_the_helper(
    hass, helper_state, expected
) -> None:
    label = _label(hass, "Vacation")
    _zombie(hass, "away_lamp", labels={label})
    if helper_state is not None:
        hass.states.async_set(HELPER, helper_state)
    coord = make_coordinator(hass, options={LABELS: [label], ENTITY: HELPER})
    coord._registries_ready = True

    assert await _zombies(coord) == expected


async def test_base_ignore_labels_stay_and_are_not_duplicated(hass) -> None:
    base = _label(hass, "Ignore")
    vacation = _label(hass, "Vacation")
    hass.states.async_set(HELPER, STATE_ON)
    coord = make_coordinator(
        hass, options={CONF_IGNORE_LABELS: [base], LABELS: [base, vacation], ENTITY: HELPER}
    )
    coord._apply_conditional_labels()
    assert coord.ignore_labels == [base, vacation]
    hass.states.async_set(HELPER, STATE_OFF)
    coord._apply_conditional_labels()
    assert coord.ignore_labels == [base]


async def test_device_and_area_labels_follow_the_helper(hass) -> None:
    label = _label(hass, "Vacation")
    owner = MockConfigEntry(domain="test_platform", data={})
    owner.add_to_hass(hass)
    device = dr.async_get(hass).async_get_or_create(
        config_entry_id=owner.entry_id, identifiers={("test", "lamp")}, name="Lamp"
    )
    dr.async_get(hass).async_update_device(device.id, labels={label})
    on_device = er.async_get(hass).async_get_or_create(
        "sensor",
        "test_platform",
        "uid_device",
        suggested_object_id="device_lamp",
        device_id=device.id,
    )
    _unavailable_for_30_minutes(hass, on_device.entity_id)
    area = ar.async_get(hass).async_create("Holiday home")
    ar.async_get(hass).async_update(area.id, labels={label})
    in_area = er.async_get(hass).async_get_or_create(
        "sensor", "test_platform", "uid_area", suggested_object_id="area_lamp"
    )
    er.async_get(hass).async_update_entity(in_area.entity_id, area_id=area.id)
    _unavailable_for_30_minutes(hass, in_area.entity_id)
    coord = make_coordinator(hass, options={LABELS: [label], ENTITY: HELPER})
    coord._registries_ready = True

    hass.states.async_set(HELPER, STATE_ON)
    assert await _zombies(coord) == (0, True)
    hass.states.async_set(HELPER, STATE_OFF)
    assert await _zombies(coord) == (2, False)


async def test_not_configured_is_inactive(hass) -> None:
    _zombie(hass, "lamp")
    hass.states.async_set(HELPER, STATE_ON)
    coord = make_coordinator(hass)
    coord._registries_ready = True
    assert await _zombies(coord) == (1, False)
    assert coord.async_track_conditional_entity()() is None


# --- deleted or renamed helper (condition 3) --------------------------------------------


async def test_deleted_or_renamed_helper_counts_as_off_without_warning(hass, caplog) -> None:
    label = _label(hass, "Vacation")
    _zombie(hass, "away_lamp", labels={label})
    helper = er.async_get(hass).async_get_or_create(
        "input_boolean", "input_boolean", "vacation", suggested_object_id="vacation"
    )
    assert helper.entity_id == HELPER
    hass.states.async_set(HELPER, STATE_ON)
    coord = make_coordinator(hass, options={LABELS: [label], ENTITY: HELPER})
    coord._registries_ready = True
    assert await _zombies(coord) == (0, True)

    # Renamed: the old entity id has no state any more.
    er.async_get(hass).async_update_entity(HELPER, new_entity_id="input_boolean.holiday")
    hass.states.async_remove(HELPER)
    hass.states.async_set("input_boolean.holiday", STATE_ON)
    caplog.clear()
    with caplog.at_level(logging.DEBUG):
        assert await _zombies(coord) == (1, False)
    # Deleted: neither registry entry nor state.
    er.async_get(hass).async_remove("input_boolean.holiday")
    hass.states.async_remove("input_boolean.holiday")
    with caplog.at_level(logging.DEBUG):
        assert await _zombies(coord) == (1, False)
    assert not [
        r
        for r in caplog.records
        if r.levelno >= logging.WARNING and r.name.startswith("custom_components.haghs")
    ]
    assert coord.data is None or coord.data.get("update_cycle_failed") is not True

    # A new helper under the old id is followed again.
    hass.states.async_set(HELPER, STATE_ON)
    assert await _zombies(coord) == (0, True)


# --- listener, unload and reload (condition 2) ----------------------------------------


async def test_helper_change_refreshes_once_and_unload_reload_leave_one_listener(hass) -> None:
    label = _label(hass, "Vacation")
    hass.states.async_set(HELPER, STATE_OFF)
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={},
        options={LABELS: [label], ENTITY: HELPER},
        version=3,
        minor_version=4,
    )
    entry.add_to_hass(hass)
    calls: list[str] = []

    async def _count(self) -> None:
        calls.append(self.config_entry.entry_id if self.config_entry else "coordinator")

    async def _fake_psi(_self) -> _PsiData:
        return _PSI

    async def _toggle(state: str) -> int:
        before = len(calls)
        hass.states.async_set(HELPER, state)
        await hass.async_block_till_done()
        return len(calls) - before

    with (
        patch.object(HaghsDataUpdateCoordinator, "_read_psi_sync", return_value=_PSI),
        patch.object(HaghsDataUpdateCoordinator, "_async_read_psi", _fake_psi),
        patch.object(HaghsDataUpdateCoordinator, "async_request_refresh", _count),
        patch_disk(),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        assert await _toggle(STATE_ON) == 1
        assert await _toggle(STATE_ON) == 0  # attribute-only writes keep the same state object

        assert await hass.config_entries.async_unload(entry.entry_id)
        await hass.async_block_till_done()
        assert await _toggle(STATE_OFF) == 0

        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        assert await _toggle(STATE_ON) == 1

        assert await hass.config_entries.async_reload(entry.entry_id)
        await hass.async_block_till_done()
        assert await _toggle(STATE_OFF) == 1

        assert await hass.config_entries.async_unload(entry.entry_id)
        await hass.async_block_till_done()
