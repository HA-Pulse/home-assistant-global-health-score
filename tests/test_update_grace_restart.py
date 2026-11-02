"""The 7-day update grace survives Home Assistant restarts (doc audit v2.4.0b4, P2).

The first-seen time of every pending update is kept in a Store. A restart is simulated by dropping HAGHS's hass.data
(a new Home Assistant run) while the storage stays.
"""

from __future__ import annotations

import logging
from datetime import timedelta

import pytest
from freezegun.api import FrozenDateTimeFactory
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import async_fire_time_changed

from custom_components.haghs.const import DOMAIN
from tests.factories import make_coordinator

KEY = "haghs.update_first_seen"


def _restart(hass: HomeAssistant) -> None:
    """A new Home Assistant run: in-memory state gone, storage kept."""
    hass.data.pop(DOMAIN, None)


def _stored(seen: dict[str, str]) -> dict:
    return {"version": 1, "minor_version": 1, "key": KEY, "data": seen}


async def _update_count(hass: HomeAssistant) -> int:
    """Number of updates past the grace after one full update cycle (one pending update in these tests)."""
    coordinator = make_coordinator(hass)
    await coordinator.async_refresh()
    return int(coordinator.data["rec_updates_pending"])


async def test_window_is_kept_across_a_restart(
    hass, hass_storage, freezer: FrozenDateTimeFactory
) -> None:
    hass.states.async_set("update.esphome", "on", {"friendly_name": "ESPHome"})
    assert await _update_count(hass) == 0
    freezer.tick(timedelta(seconds=11))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    first = hass_storage[KEY]["data"]["update.esphome"]

    freezer.tick(timedelta(days=4))
    _restart(hass)
    assert await _update_count(hass) == 0  # day 4, still in the window

    freezer.tick(timedelta(days=4))
    _restart(hass)
    assert await _update_count(hass) == 1  # day 8 after first seen, two restarts in between
    assert hass.data[DOMAIN]["_update_first_seen"]["update.esphome"] == dt_util.parse_datetime(
        first
    )


async def test_without_the_store_a_restart_starts_a_new_window(hass, hass_storage) -> None:
    """Control: the same eight days without the stored time count from the restart (behaviour before the fix)."""
    hass.states.async_set("update.esphome", "on")
    hass_storage.pop(KEY, None)
    _restart(hass)
    assert await _update_count(hass) == 0


async def test_stored_time_older_than_the_grace_counts_at_once(hass, hass_storage) -> None:
    eight_days = (dt_util.utcnow() - timedelta(days=8)).isoformat()
    hass_storage[KEY] = _stored({"update.esphome": eight_days})
    hass.states.async_set("update.esphome", "on")
    assert await _update_count(hass) == 1


async def test_installed_update_is_pruned_from_the_store(hass, hass_storage, freezer) -> None:
    hass_storage[KEY] = _stored(
        {"update.esphome": (dt_util.utcnow() - timedelta(days=8)).isoformat()}
    )
    hass.states.async_set("update.esphome", "off")
    assert await _update_count(hass) == 0
    freezer.tick(timedelta(seconds=11))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert hass_storage[KEY]["data"] == {}


async def test_nothing_is_written_without_a_change(hass, hass_storage, freezer) -> None:
    seen = (dt_util.utcnow() - timedelta(days=2)).isoformat()
    hass_storage[KEY] = _stored({"update.esphome": seen})
    hass.states.async_set("update.esphome", "on")
    coordinator = make_coordinator(hass)
    await coordinator._async_load_update_first_seen()
    hass_storage.pop(KEY)  # a write would put it back
    coordinator._calc_updates()
    coordinator._calc_updates()
    freezer.tick(timedelta(seconds=11))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert KEY not in hass_storage


async def test_known_entries_of_this_run_win_and_load_happens_once(hass, hass_storage) -> None:
    hass_storage[KEY] = _stored(
        {"update.esphome": (dt_util.utcnow() - timedelta(days=8)).isoformat()}
    )
    hass.states.async_set("update.esphome", "on")
    coordinator = make_coordinator(hass)
    now = dt_util.utcnow()
    coordinator._update_first_seen["update.esphome"] = now
    await coordinator._async_load_update_first_seen()
    assert coordinator._update_first_seen["update.esphome"] == now
    hass_storage[KEY] = _stored({"update.other": (now - timedelta(days=9)).isoformat()})
    await make_coordinator(hass)._async_load_update_first_seen()  # second entry, same run
    assert "update.other" not in coordinator._update_first_seen


@pytest.mark.parametrize(
    "data",
    [
        ["update.esphome"],
        {"update.esphome": "not a time"},
        {"update.esphome": 5},
        {"sensor.esphome": "2026-01-01T00:00:00+00:00"},
        {"update.esphome": "2026-01-01T00:00:00"},
        {"update.esphome": "2999-01-01T00:00:00+00:00"},
    ],
)
async def test_invalid_stored_data_starts_now_with_one_debug(
    hass, hass_storage, caplog, data
) -> None:
    hass_storage[KEY] = _stored(data)
    hass.states.async_set("update.esphome", "on")
    caplog.set_level(logging.DEBUG, logger="custom_components.haghs.coordinator")
    assert await _update_count(hass) == 0
    seen = hass.data[DOMAIN]["_update_first_seen"]["update.esphome"]
    assert dt_util.utcnow() - seen < timedelta(minutes=1)
    assert len([r for r in caplog.records if "stored update first-seen" in r.getMessage()]) == 1


async def test_unreadable_store_starts_now_with_one_debug(hass, caplog, monkeypatch) -> None:
    hass.states.async_set("update.esphome", "on")
    coordinator = make_coordinator(hass)

    async def broken() -> None:
        raise ValueError("broken json")

    monkeypatch.setattr(coordinator._first_seen_store, "async_load", broken)
    caplog.set_level(logging.DEBUG, logger="custom_components.haghs.coordinator")
    await coordinator._async_load_update_first_seen()
    assert coordinator._calc_updates()[1] == 0
    assert (
        len([r for r in caplog.records if "update first-seen times unreadable" in r.getMessage()])
        == 1
    )


async def test_the_update_cycle_loads_the_store(hass, hass_storage) -> None:
    hass_storage[KEY] = _stored(
        {"update.esphome": (dt_util.utcnow() - timedelta(days=8)).isoformat()}
    )
    hass.states.async_set("update.esphome", "on", {"friendly_name": "ESPHome"})
    coordinator = make_coordinator(hass)
    await coordinator.async_refresh()
    assert coordinator.data["rec_updates_pending"] is True
    assert coordinator.data["pending_updates"] == ["ESPHome"]
