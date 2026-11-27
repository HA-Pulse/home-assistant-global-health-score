"""An unreadable update first-seen store stays visible (HAGHS-20261124-001).

HAGHS keeps a timestamped copy of the file before anything can overwrite it, warns once with the traceback and
raises its own repair. Without a copy, saving is paused for the run. HAGHS's own repairs do not count in the score.
"""

from __future__ import annotations

import logging
import re
from datetime import timedelta
from pathlib import Path

import pytest
from freezegun.api import FrozenDateTimeFactory
from homeassistant.components.repairs import ConfirmRepairFlow
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.exceptions import UnsupportedStorageVersionError
from homeassistant.helpers import issue_registry as ir
from homeassistant.setup import async_setup_component
from pytest_homeassistant.common import async_fire_time_changed

from custom_components.haghs import coordinator as coordinator_module
from custom_components.haghs import repairs as repairs_module
from custom_components.haghs.const import DOMAIN, IssueIds, entry_issue_id, entry_store_key
from custom_components.haghs.repairs import async_create_fix_flow
from tests.factories import make_coordinator

# One HAGHS entry with its own store and repair (#217); the translation key stays the shared one.
ENTRY = "haghs_unreadable_entry"
KEY = entry_store_key(ENTRY)
ISSUE = entry_issue_id(IssueIds.UPDATE_FIRST_SEEN_UNREADABLE, ENTRY)
TRANSLATION_KEY = "update_first_seen_unreadable"
ORIGINAL = b'{"version": 9, "minor_version": 1, "key": "haghs.update_first_seen", "data": {}}\n'
MESSAGE = "update first-seen times unreadable"
LOGGER = "custom_components.haghs.coordinator"


def _store_file(hass: HomeAssistant) -> Path:
    path = Path(hass.config.path(".storage", KEY))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(ORIGINAL)
    return path


def _break_load(monkeypatch, coordinator, error: Exception) -> None:
    async def broken() -> None:
        raise error

    monkeypatch.setattr(coordinator._first_seen_store, "async_load", broken)


def _read(path: Path) -> bytes:
    """Read a file (sync helper, kept out of the async tests)."""
    return path.read_bytes()


def _records(caplog) -> list[logging.LogRecord]:
    return [r for r in caplog.records if MESSAGE in r.getMessage()]


@pytest.mark.parametrize(
    "error",
    [OSError("permission denied"), UnsupportedStorageVersionError(KEY, 9, 1)],
    ids=["io", "newer_version"],
)
async def test_unreadable_store_keeps_a_copy_warns_once_and_raises_a_repair(
    hass, caplog, monkeypatch, error
) -> None:
    path = _store_file(hass)
    hass.states.async_set("update.esphome", "on", {"friendly_name": "ESPHome"})
    coordinator = make_coordinator(hass, entry_id=ENTRY)
    _break_load(monkeypatch, coordinator, error)
    caplog.set_level(logging.DEBUG, logger=LOGGER)

    await coordinator.async_refresh()
    await coordinator.async_refresh()  # a second cycle must not warn again

    records = _records(caplog)
    assert len(records) == 1
    assert records[0].levelno == logging.WARNING
    assert records[0].exc_info is not None
    assert records[0].exc_info[1] is error

    issue = ir.async_get(hass).async_get_issue(DOMAIN, ISSUE)
    assert issue is not None
    assert issue.translation_key == TRANSLATION_KEY
    assert issue.severity == ir.IssueSeverity.WARNING
    assert issue.is_fixable is True
    assert issue.is_persistent is True
    backup = Path(issue.translation_placeholders["backup_path"])
    assert backup.parent == path.parent
    assert re.fullmatch(rf"{re.escape(KEY)}\.unreadable\.\d{{8}}T\d{{6}}Z", backup.name)
    assert _read(backup) == ORIGINAL
    assert backup.name in records[0].getMessage()
    assert "_update_first_seen_save_blocked" not in hass.data[DOMAIN]
    assert coordinator.data["update_cycle_failed"] is False


async def test_the_next_save_leaves_the_copy_untouched(
    hass, hass_storage, monkeypatch, freezer: FrozenDateTimeFactory
) -> None:
    _store_file(hass)
    hass.states.async_set("update.esphome", "on", {"friendly_name": "ESPHome"})
    coordinator = make_coordinator(hass, entry_id=ENTRY)
    _break_load(monkeypatch, coordinator, OSError("permission denied"))

    await coordinator.async_refresh()
    freezer.tick(timedelta(seconds=11))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()

    assert "update.esphome" in hass_storage[KEY]["data"]  # saving goes on with the new window
    issue = ir.async_get(hass).async_get_issue(DOMAIN, ISSUE)
    assert _read(Path(issue.translation_placeholders["backup_path"])) == ORIGINAL


async def test_without_a_copy_saving_is_paused_and_the_repair_says_so(
    hass, caplog, monkeypatch, freezer: FrozenDateTimeFactory
) -> None:
    path = _store_file(hass)
    hass.states.async_set("update.esphome", "on", {"friendly_name": "ESPHome"})
    coordinator = make_coordinator(hass, entry_id=ENTRY)
    error = OSError("permission denied")
    _break_load(monkeypatch, coordinator, error)

    copy_error = OSError("read-only file system")

    def no_copy(*_args) -> None:
        raise copy_error

    monkeypatch.setattr(coordinator_module.shutil, "copy2", no_copy)
    saves: list[tuple] = []
    monkeypatch.setattr(
        coordinator._first_seen_store, "async_delay_save", lambda *args: saves.append(args)
    )
    caplog.set_level(logging.DEBUG, logger=LOGGER)

    await coordinator.async_refresh()
    await coordinator.async_refresh()
    freezer.tick(timedelta(seconds=11))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()

    assert saves == []
    assert _read(path) == ORIGINAL
    assert hass.data[DOMAIN]["_update_first_seen_save_blocked"] == {ENTRY}
    records = _records(caplog)
    assert len(records) == 1
    assert records[0].levelno == logging.WARNING
    assert records[0].exc_info is not None
    assert records[0].exc_info[1] is copy_error
    assert records[0].exc_info[1].__context__ is error
    assert "read-only file system" in records[0].getMessage()
    issue = ir.async_get(hass).async_get_issue(DOMAIN, ISSUE)
    assert issue.translation_key == "update_first_seen_unreadable_no_backup"
    assert issue.translation_placeholders == {"store_path": str(path)}
    assert list(path.parent.glob(f"{KEY}.unreadable.*")) == []


async def test_a_missing_file_is_named_as_the_reason_the_copy_failed(
    hass, caplog, monkeypatch
) -> None:
    """A real failed copy (no monkeypatch of shutil): the store file does not exist."""
    path = Path(hass.config.path(".storage", KEY))
    coordinator = make_coordinator(hass, entry_id=ENTRY)
    error = OSError("permission denied")
    _break_load(monkeypatch, coordinator, error)
    caplog.set_level(logging.DEBUG, logger=LOGGER)

    await coordinator.async_refresh()
    await coordinator.async_refresh()

    records = _records(caplog)
    assert len(records) == 1
    assert records[0].levelno == logging.WARNING
    assert isinstance(records[0].exc_info[1], FileNotFoundError)
    assert records[0].exc_info[1].__context__ is error
    assert str(records[0].exc_info[1]) in records[0].getMessage()
    issue = ir.async_get(hass).async_get_issue(DOMAIN, ISSUE)
    assert issue.translation_key == "update_first_seen_unreadable_no_backup"
    assert issue.translation_placeholders == {"store_path": str(path)}
    assert hass.data[DOMAIN]["_update_first_seen_save_blocked"] == {ENTRY}


async def test_the_incident_changes_no_score_or_attribute(
    hass, monkeypatch, freezer: FrozenDateTimeFactory
) -> None:
    """Limit (4): HAGHS's own repair is not counted; every value equals a run without the incident."""
    _store_file(hass)
    hass.states.async_set("update.esphome", "on", {"friendly_name": "ESPHome"})
    hass.states.async_set("sensor.broken", "unavailable")
    clean = make_coordinator(hass, entry_id=ENTRY)

    async def empty() -> None:
        return None

    monkeypatch.setattr(clean._first_seen_store, "async_load", empty)
    await clean.async_refresh()
    expected = dict(clean.data)

    hass.data.pop(DOMAIN)  # a new Home Assistant run, same states and clock
    broken = make_coordinator(hass, entry_id=ENTRY)
    _break_load(monkeypatch, broken, OSError("permission denied"))
    await broken.async_refresh()

    assert ir.async_get(hass).async_get_issue(DOMAIN, ISSUE) is not None
    assert broken.data == expected
    assert f"{DOMAIN}/{ISSUE}" not in broken.data["repairs"]


async def test_confirming_the_repair_removes_it(hass, monkeypatch) -> None:
    """Through Home Assistant's repairs flow manager, with HAGHS's own repairs platform."""
    assert await async_setup_component(hass, "repairs", {})
    hass.config.components.add(DOMAIN)
    _store_file(hass)
    coordinator = make_coordinator(hass, entry_id=ENTRY)
    _break_load(monkeypatch, coordinator, OSError("permission denied"))
    await coordinator.async_refresh()
    assert ir.async_get(hass).async_get_issue(DOMAIN, ISSUE) is not None

    # HAGHS's own repairs platform must create the flow (not Home Assistant's fallback): spy on it.
    calls: list[str] = []

    async def spy(hass_arg, issue_id, data):
        calls.append(issue_id)
        return await async_create_fix_flow(hass_arg, issue_id, data)

    monkeypatch.setattr(repairs_module, "async_create_fix_flow", spy)
    assert isinstance(await async_create_fix_flow(hass, ISSUE, None), ConfirmRepairFlow)

    manager = hass.data["repairs"]["flow_manager"]
    form = await manager.async_init(DOMAIN, context={"issue_id": ISSUE}, data={"issue_id": ISSUE})
    assert form["type"] == FlowResultType.FORM
    assert form["step_id"] == "confirm"
    done = await manager.async_configure(form["flow_id"], {})
    assert done["type"] == FlowResultType.CREATE_ENTRY
    assert ir.async_get(hass).async_get_issue(DOMAIN, ISSUE) is None
    assert calls == [ISSUE]


async def test_the_read_error_is_attached_when_the_copy_error_has_no_context(
    hass, caplog, monkeypatch
) -> None:
    """Called outside an `except`: the copy error gets the read error as its context explicitly."""
    coordinator = make_coordinator(hass, entry_id=ENTRY)
    read_error = OSError("permission denied")
    copy_error = OSError("read-only file system")

    def no_copy(*_args) -> None:
        raise copy_error

    monkeypatch.setattr(coordinator_module.shutil, "copy2", no_copy)
    caplog.set_level(logging.DEBUG, logger=LOGGER)

    await coordinator._async_report_unreadable_first_seen_store(read_error)

    records = _records(caplog)
    assert len(records) == 1
    assert records[0].levelno == logging.WARNING
    assert records[0].exc_info[1] is copy_error
    assert copy_error.__context__ is read_error
    issue = ir.async_get(hass).async_get_issue(DOMAIN, ISSUE)
    assert issue.translation_key == "update_first_seen_unreadable_no_backup"
