"""Several HAGHS entries keep separate repairs and update first-seen records (#217).

Before, every entry shared the repair id ``fallback_missing`` and one first-seen record: one entry deleted the other
entry's repair, and an ignore label in one entry restarted the 7-day update grace of the other.
"""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any
from unittest.mock import patch

import voluptuous as vol
from homeassistant.components.repairs import ConfirmRepairFlow
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers import label_registry as lr
from homeassistant.setup import async_setup_component
from homeassistant.util import dt as dt_util
from pytest_homeassistant.common import MockConfigEntry, async_fire_time_changed

from custom_components import haghs as haghs_module
from custom_components.haghs.const import (
    CONF_CPU_SENSOR,
    CONF_IGNORE_LABELS,
    CONF_RAM_SENSOR,
    DOMAIN,
    UPDATE_FIRST_SEEN_LEGACY_STORE_KEY,
    UPDATE_GRACE_DAYS,
    IssueIds,
    entry_issue_id,
    entry_store_key,
)
from custom_components.haghs.coordinator import _PsiData
from custom_components.haghs.repairs import async_create_fix_flow
from tests.factories import make_coordinator, patch_disk, patch_psi

_PSI_SYNC_PATH = "custom_components.haghs.coordinator.HaghsDataUpdateCoordinator._read_psi_sync"
_PSI_ASYNC_PATH = "custom_components.haghs.coordinator.HaghsDataUpdateCoordinator._async_read_psi"
SENSORS = {CONF_CPU_SENSOR: "sensor.cpu", CONF_RAM_SENSOR: "sensor.ram"}


def _fallback(hass: HomeAssistant, entry_id: str) -> ir.IssueEntry | None:
    return ir.async_get(hass).async_get_issue(
        DOMAIN, entry_issue_id(IssueIds.FALLBACK_MISSING, entry_id)
    )


def _store(key: str, seen: dict[str, str]) -> dict[str, Any]:
    return {
        "version": 1,
        "minor_version": 1,
        "key": key,
        "data": {entity_id: {"since": since, "version": None} for entity_id, since in seen.items()},
    }


def _legacy_store(seen: dict[str, str]) -> dict[str, Any]:
    return _store(UPDATE_FIRST_SEEN_LEGACY_STORE_KEY, seen)


def _entry_at_3_4(hass: HomeAssistant) -> MockConfigEntry:
    """An entry as HAGHS 2.4 left it (config version 3.4)."""
    entry = MockConfigEntry(domain=DOMAIN, data={}, options={}, version=3, minor_version=4)
    entry.add_to_hass(hass)
    return entry


async def test_one_entry_never_deletes_the_repair_of_another(hass) -> None:
    hass.states.async_set("sensor.cpu", "10")
    hass.states.async_set("sensor.ram", "20")
    unmeasured = make_coordinator(hass)
    measured = make_coordinator(hass, options=SENSORS)
    with patch_psi(), patch_disk():  # no PSI: only the entry without sensors misses CPU and RAM
        await unmeasured.async_refresh()
        await measured.async_refresh()
        await measured.async_refresh()

    repair = _fallback(hass, unmeasured._entry_id)
    assert repair is not None
    assert repair.data == {"entry_id": unmeasured._entry_id}
    assert repair.translation_key == "fallback_missing"
    assert _fallback(hass, measured._entry_id) is None


async def test_the_sensor_dialog_opens_through_the_new_repair_id(hass) -> None:
    """Deniz's condition on HAGHS-20261127-002: the repair id fallback_missing_<entry> opens the sensor form."""
    assert await async_setup_component(hass, "repairs", {})
    hass.config.components.add(DOMAIN)
    hass.states.async_set("sensor.cpu", "10")
    hass.states.async_set("sensor.ram", "20")
    target = MockConfigEntry(domain=DOMAIN, data={}, options={})
    target.add_to_hass(hass)
    other = MockConfigEntry(domain=DOMAIN, data={}, options={})
    other.add_to_hass(hass)
    issue_id = entry_issue_id(IssueIds.FALLBACK_MISSING, target.entry_id)
    ir.async_create_issue(
        hass,
        DOMAIN,
        issue_id,
        data={"entry_id": target.entry_id},
        is_fixable=True,
        severity=ir.IssueSeverity.WARNING,
        translation_key=IssueIds.FALLBACK_MISSING,
    )

    manager = hass.data["repairs"]["flow_manager"]
    form = await manager.async_init(
        DOMAIN, context={"issue_id": issue_id}, data={"issue_id": issue_id}
    )
    assert form["type"] == FlowResultType.FORM
    assert form["step_id"] == "confirm"
    assert {str(key): type(key) for key in form["data_schema"].schema} == {
        CONF_CPU_SENSOR: vol.Optional,
        CONF_RAM_SENSOR: vol.Optional,
    }
    with patch.object(hass.config_entries, "async_schedule_reload") as reload:
        done = await manager.async_configure(form["flow_id"], dict(SENSORS))
    assert done["type"] == FlowResultType.CREATE_ENTRY
    assert {key: target.options[key] for key in SENSORS} == SENSORS
    assert dict(other.options) == {}
    reload.assert_called_once_with(target.entry_id)


async def test_old_shared_id_still_opens_the_form_and_unknown_ids_confirm(hass) -> None:
    entry = MockConfigEntry(domain=DOMAIN, data={}, options={})
    entry.add_to_hass(hass)
    old = await async_create_fix_flow(hass, "fallback_missing", {"entry_id": entry.entry_id})
    new = await async_create_fix_flow(
        hass,
        entry_issue_id(IssueIds.FALLBACK_MISSING, entry.entry_id),
        {"entry_id": entry.entry_id},
    )
    assert not isinstance(old, ConfirmRepairFlow)
    assert type(old) is type(new)
    assert isinstance(
        await async_create_fix_flow(hass, "fallback_missingx", None), ConfirmRepairFlow
    )


async def test_an_ignore_label_in_one_entry_keeps_the_grace_of_the_other(
    hass, hass_storage, freezer
) -> None:
    freezer.move_to("2026-11-27T10:00:00+00:00")
    label = lr.async_get(hass).async_create("Not here")
    assert label.label_id != label.name
    entry = er.async_get(hass).async_get_or_create(
        "update", "test_platform", "router_fw", suggested_object_id="router_fw"
    )
    er.async_get(hass).async_update_entity(entry.entity_id, labels={label.label_id})
    hass.states.async_set(entry.entity_id, "on", {"friendly_name": "Router firmware"})
    eight_days = (dt_util.utcnow() - timedelta(days=UPDATE_GRACE_DAYS + 1)).isoformat()
    for entry_id in ("counts", "ignores"):  # both entries saw the update 8 days ago
        key = entry_store_key(entry_id)
        hass_storage[key] = _store(key, {entry.entity_id: eight_days})

    counts = make_coordinator(hass, entry_id="counts")
    ignores = make_coordinator(
        hass, entry_id="ignores", options={CONF_IGNORE_LABELS: [label.label_id]}
    )
    with patch_psi(cpu=1.0, memory=1.0, io=1.0), patch_disk():
        await counts.async_refresh()
        await ignores.async_refresh()  # prunes the update from its own record only
        await counts.async_refresh()
    assert counts.data["rec_updates_pending"] is True
    assert counts._update_first_seen[entry.entity_id] == dt_util.parse_datetime(eight_days)
    assert entry.entity_id not in ignores._update_first_seen

    freezer.tick(timedelta(seconds=11))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert set(hass_storage[entry_store_key(counts._entry_id)]["data"]) == {entry.entity_id}
    assert hass_storage[entry_store_key(ignores._entry_id)]["data"] == {}


async def test_migration_copies_the_shared_store_once_and_leaves_it_untouched(
    hass, hass_storage
) -> None:
    seen = (dt_util.utcnow() - timedelta(days=5)).isoformat()
    hass_storage[UPDATE_FIRST_SEEN_LEGACY_STORE_KEY] = _legacy_store({"update.router": seen})
    shared_before = dict(hass_storage[UPDATE_FIRST_SEEN_LEGACY_STORE_KEY])
    entry = _entry_at_3_4(hass)

    assert await haghs_module.async_migrate_entry(hass, entry) is True
    await hass.async_block_till_done()
    assert (entry.version, entry.minor_version) == (3, 5)
    assert hass_storage[entry_store_key(entry.entry_id)]["data"] == shared_before["data"]
    assert hass_storage[UPDATE_FIRST_SEEN_LEGACY_STORE_KEY] == shared_before

    coordinator = make_coordinator(hass, entry_id=entry.entry_id)
    await coordinator._async_load_update_first_seen()
    assert coordinator._update_first_seen == {"update.router": dt_util.parse_datetime(seen)}


async def test_migration_keeps_an_existing_own_store(hass, hass_storage) -> None:
    seen = (dt_util.utcnow() - timedelta(days=2)).isoformat()
    hass_storage[UPDATE_FIRST_SEEN_LEGACY_STORE_KEY] = _legacy_store({"update.legacy": seen})
    entry = _entry_at_3_4(hass)
    key = entry_store_key(entry.entry_id)
    hass_storage[key] = _store(key, {"update.own": seen})

    assert await haghs_module.async_migrate_entry(hass, entry) is True
    await hass.async_block_till_done()
    assert set(hass_storage[key]["data"]) == {"update.own"}


async def test_a_new_entry_never_reads_the_shared_store(hass, hass_storage) -> None:
    """An entry created after the update starts empty, even if the HAGHS 2.4 file is still there."""
    months_ago = (dt_util.utcnow() - timedelta(days=90)).isoformat()
    hass_storage[UPDATE_FIRST_SEEN_LEGACY_STORE_KEY] = _legacy_store({"update.router": months_ago})
    new = make_coordinator(hass)
    await new._async_load_update_first_seen()
    assert new._update_first_seen == {}


async def test_an_unreadable_shared_store_is_reported_and_the_migration_goes_on(
    hass, hass_storage, caplog
) -> None:
    hass_storage[UPDATE_FIRST_SEEN_LEGACY_STORE_KEY] = {
        "version": 9,
        "minor_version": 1,
        "key": UPDATE_FIRST_SEEN_LEGACY_STORE_KEY,
        "data": {},
    }
    entry = _entry_at_3_4(hass)
    caplog.set_level(logging.WARNING, logger="custom_components.haghs.coordinator")

    assert await haghs_module.async_migrate_entry(hass, entry) is True
    assert (entry.version, entry.minor_version) == (3, 5)
    warnings = [r for r in caplog.records if "update first-seen times unreadable" in r.getMessage()]
    assert len(warnings) == 1
    assert warnings[0].exc_info is not None
    repair = ir.async_get(hass).async_get_issue(
        DOMAIN, entry_issue_id(IssueIds.UPDATE_FIRST_SEEN_UNREADABLE, entry.entry_id)
    )
    assert repair is not None
    assert repair.translation_key in (
        "update_first_seen_unreadable",
        "update_first_seen_unreadable_no_backup",
    )
    assert entry_store_key(entry.entry_id) not in hass_storage


async def test_setup_drops_the_old_shared_repair_and_removal_only_the_entrys_own(hass) -> None:
    for issue_id, data in (
        ("fallback_missing", {"entry_id": "someone"}),
        (entry_issue_id(IssueIds.FALLBACK_MISSING, "keep_me"), {"entry_id": "keep_me"}),
        (entry_issue_id(IssueIds.UPDATE_FIRST_SEEN_UNREADABLE, "keep_me"), None),
    ):
        ir.async_create_issue(
            hass,
            DOMAIN,
            issue_id,
            data=data,
            is_fixable=True,
            severity=ir.IssueSeverity.WARNING,
            translation_key="fallback_missing",
        )
    entry = MockConfigEntry(
        domain=DOMAIN, data={}, options=dict(SENSORS), version=3, minor_version=4
    )
    entry.add_to_hass(hass)
    hass.states.async_set("sensor.cpu", "10")
    hass.states.async_set("sensor.ram", "20")
    psi = _PsiData(cpu=None, memory=None, io=None)

    async def _fake_async_read(_self: Any) -> _PsiData:
        return psi

    with (
        patch(_PSI_SYNC_PATH, return_value=psi),
        patch(_PSI_ASYNC_PATH, _fake_async_read),
        patch_disk(),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
    assert entry.state is ConfigEntryState.LOADED
    issues = ir.async_get(hass)
    assert issues.async_get_issue(DOMAIN, "fallback_missing") is None

    for issue in IssueIds:
        ir.async_create_issue(
            hass,
            DOMAIN,
            entry_issue_id(issue, entry.entry_id),
            is_fixable=True,
            severity=ir.IssueSeverity.WARNING,
            translation_key=str(issue),
        )
    await haghs_module.async_remove_entry(hass, entry)
    assert {key[1] for key in issues.issues if key[0] == DOMAIN} == {
        entry_issue_id(IssueIds.FALLBACK_MISSING, "keep_me"),
        entry_issue_id(IssueIds.UPDATE_FIRST_SEEN_UNREADABLE, "keep_me"),
    }
    await hass.config_entries.async_unload(entry.entry_id)


async def test_migration_never_copies_over_an_unreadable_own_store(
    hass, hass_storage, caplog
) -> None:
    """The coordinator reports the unreadable own store; the migration only skips the copy."""
    seen = (dt_util.utcnow() - timedelta(days=2)).isoformat()
    hass_storage[UPDATE_FIRST_SEEN_LEGACY_STORE_KEY] = _legacy_store({"update.legacy": seen})
    entry = _entry_at_3_4(hass)
    key = entry_store_key(entry.entry_id)
    unreadable = {"version": 9, "minor_version": 1, "key": key, "data": {}}
    hass_storage[key] = dict(unreadable)
    caplog.set_level(logging.DEBUG, logger="custom_components.haghs")

    assert await haghs_module.async_migrate_entry(hass, entry) is True
    await hass.async_block_till_done()
    assert (entry.version, entry.minor_version) == (3, 5)
    assert hass_storage[key] == unreadable
    assert [r.levelno for r in caplog.records if "nothing copied" in r.getMessage()] == [
        logging.DEBUG
    ]


async def test_a_failed_copy_warns_and_the_migration_goes_on(hass, hass_storage, caplog) -> None:
    """Writing .storage failed: one WARNING with traceback; the entry still loads (accepted case, plan r4)."""
    seen = (dt_util.utcnow() - timedelta(days=2)).isoformat()
    hass_storage[UPDATE_FIRST_SEEN_LEGACY_STORE_KEY] = _legacy_store({"update.legacy": seen})
    entry = _entry_at_3_4(hass)
    caplog.set_level(logging.WARNING, logger="custom_components.haghs")

    with patch("homeassistant.helpers.storage.Store.async_save", side_effect=OSError("disk full")):
        assert await haghs_module.async_migrate_entry(hass, entry) is True
    assert (entry.version, entry.minor_version) == (3, 5)
    warnings = [r for r in caplog.records if "Could not copy the stored update" in r.getMessage()]
    assert len(warnings) == 1
    assert warnings[0].exc_info is not None
    assert entry_store_key(entry.entry_id) not in hass_storage
