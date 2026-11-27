"""HAGHS's own repairs never stop the update cycle (#217).

The CPU/RAM repair is synced in every cycle. If Home Assistant's issue registry fails there, HAGHS logs one WARNING per
failure streak, calculates score and attributes as usual and tries the sync again in the next cycle. The same holds for
the repair about unreadable stored update times.
"""

from __future__ import annotations

import logging
from unittest.mock import patch

from homeassistant.helpers import issue_registry as ir

from custom_components.haghs import coordinator as coordinator_module
from custom_components.haghs.const import DOMAIN, IssueIds, entry_issue_id
from tests.factories import make_coordinator, patch_disk, patch_psi

LOGGER = "custom_components.haghs.coordinator"
SYNC_MESSAGE = "Could not update its CPU/RAM repair"
UNREADABLE_MESSAGE = "Could not raise the repair for the unreadable update first-seen times"


def _warnings(caplog, message: str) -> list[logging.LogRecord]:
    return [r for r in caplog.records if r.levelno == logging.WARNING and message in r.getMessage()]


def _repair(hass, coordinator):
    return ir.async_get(hass).async_get_issue(
        DOMAIN, entry_issue_id(IssueIds.FALLBACK_MISSING, coordinator._entry_id)
    )


async def test_failing_repair_create_keeps_the_cycle_warns_once_and_retries(
    hass, caplog, freezer
) -> None:
    freezer.move_to("2026-11-27T10:00:00+00:00")
    clean = make_coordinator(hass)
    with patch_psi(), patch_disk():  # no PSI and no sensor: CPU and RAM are not measured
        await clean.async_refresh()
    expected = dict(clean.data)
    assert _repair(hass, clean) is not None

    broken = make_coordinator(hass)
    caplog.set_level(logging.DEBUG, logger=LOGGER)
    failing = patch.object(
        coordinator_module.ir, "async_create_issue", side_effect=RuntimeError("registry down")
    )
    with patch_psi(), patch_disk(), failing:
        await broken.async_refresh()
        assert broken.last_update_success is True
        assert broken.data == expected
        await broken.async_refresh()  # still failing: no second WARNING
        assert broken.last_update_success is True
    assert len(_warnings(caplog, SYNC_MESSAGE)) == 1
    assert _repair(hass, broken) is None

    with patch_psi(), patch_disk():
        await broken.async_refresh()  # registry works again: the sync is retried
    assert _repair(hass, broken) is not None
    assert len(_warnings(caplog, SYNC_MESSAGE)) == 1


async def test_failing_repair_delete_keeps_the_cycle_and_retries(hass, caplog) -> None:
    coordinator = make_coordinator(hass)
    with patch_psi(), patch_disk():
        await coordinator.async_refresh()
    assert _repair(hass, coordinator) is not None

    caplog.set_level(logging.WARNING, logger=LOGGER)
    failing = patch.object(
        coordinator_module.ir, "async_delete_issue", side_effect=RuntimeError("registry down")
    )
    with (
        patch_psi(cpu=1.0, memory=1.0, io=1.0),
        patch_disk(),
        failing,
    ):  # PSI back: CPU/RAM measured
        await coordinator.async_refresh()
    assert coordinator.last_update_success is True
    assert coordinator.data["rec_cpu_ram_unmeasured"] is False
    assert len(_warnings(caplog, SYNC_MESSAGE)) == 1
    assert _repair(hass, coordinator) is not None

    with patch_psi(cpu=1.0, memory=1.0, io=1.0), patch_disk():
        await coordinator.async_refresh()
    assert _repair(hass, coordinator) is None


async def test_failing_unreadable_store_repair_keeps_the_cycle(hass, caplog, monkeypatch) -> None:
    coordinator = make_coordinator(hass)

    async def broken() -> None:
        raise OSError("permission denied")

    monkeypatch.setattr(coordinator._first_seen_store, "async_load", broken)
    caplog.set_level(logging.WARNING, logger=LOGGER)
    with (
        patch_psi(cpu=1.0, memory=1.0, io=1.0),
        patch_disk(),
        patch.object(
            coordinator_module.ir, "async_create_issue", side_effect=RuntimeError("registry down")
        ),
    ):
        await coordinator.async_refresh()
    assert coordinator.last_update_success is True
    assert "global_score" in coordinator.data
    assert len(_warnings(caplog, UNREADABLE_MESSAGE)) == 1


async def test_a_new_failure_after_a_quiet_cycle_warns_again(hass, caplog) -> None:
    """A streak ends when there is nothing to sync; the next failure is a new streak with a WARNING."""
    coordinator = make_coordinator(hass)
    with patch_psi(cpu=1.0, memory=1.0, io=1.0), patch_disk():  # measured: no repair
        await coordinator.async_refresh()
    caplog.set_level(logging.DEBUG, logger=LOGGER)
    failing = patch.object(
        coordinator_module.ir, "async_create_issue", side_effect=RuntimeError("registry down")
    )
    with patch_psi(), patch_disk(), failing:  # unmeasured: the create fails
        await coordinator.async_refresh()
    with patch_psi(cpu=1.0, memory=1.0, io=1.0), patch_disk():  # measured again: nothing to sync
        await coordinator.async_refresh()
    with patch_psi(), patch_disk(), failing:  # unmeasured again: a new failure
        await coordinator.async_refresh()
    assert coordinator.last_update_success is True
    assert len(_warnings(caplog, SYNC_MESSAGE)) == 2
