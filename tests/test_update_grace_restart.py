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
from pytest_homeassistant.common import async_fire_time_changed

from custom_components.haghs.const import DOMAIN
from tests.factories import make_coordinator

KEY = "haghs.update_first_seen"


def _restart(hass: HomeAssistant) -> None:
    """A new Home Assistant run: in-memory state gone, storage kept."""
    hass.data.pop(DOMAIN, None)


def _stored(seen, *, raw: bool = False) -> dict:
    """Store content; plain ISO strings become entries without an offered version."""
    data = (
        seen
        if raw
        else {
            k: v if isinstance(v, dict) else {"since": v, "version": None} for k, v in seen.items()
        }
    )
    return {"version": 1, "minor_version": 1, "key": KEY, "data": data}


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
    first = hass_storage[KEY]["data"]["update.esphome"]["since"]

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
    """Control: without a stored time a pending update counts from now (first start after updating HAGHS)."""
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
        {"update.esphome": "2026-01-01T00:00:00+00:00"},
        {"update.esphome": {"since": "not a time", "version": None}},
        {"update.esphome": {"since": 5, "version": None}},
        {"sensor.esphome": {"since": "2026-01-01T00:00:00+00:00", "version": None}},
        {"update.esphome": {"since": "2026-01-01T00:00:00", "version": None}},
        {"update.esphome": {"since": "2999-01-01T00:00:00+00:00", "version": None}},
        {"update.esphome": {"since": "2026-01-01T00:00:00+00:00", "version": 7}},
    ],
)
async def test_invalid_stored_data_starts_now_with_one_debug(
    hass, hass_storage, caplog, data
) -> None:
    hass_storage[KEY] = _stored(data, raw=True)
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


async def test_a_newer_offered_version_starts_a_new_window(hass, hass_storage) -> None:
    eight_days = (dt_util.utcnow() - timedelta(days=8)).isoformat()
    hass_storage[KEY] = _stored({"update.esphome": {"since": eight_days, "version": "2026.10.0"}})
    hass.states.async_set("update.esphome", "on", {"latest_version": "2026.11.0"})
    assert await _update_count(hass) == 0
    assert hass.data[DOMAIN]["_update_seen_version"]["update.esphome"] == "2026.11.0"


async def test_the_same_offered_version_keeps_its_window_across_a_restart(
    hass, hass_storage, freezer
) -> None:
    hass.states.async_set("update.esphome", "on", {"latest_version": "2026.10.0"})
    assert await _update_count(hass) == 0
    freezer.tick(timedelta(days=8))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert hass_storage[KEY]["data"]["update.esphome"]["version"] == "2026.10.0"
    _restart(hass)
    assert await _update_count(hass) == 1
    hass.states.async_set("update.esphome", "on", {"latest_version": "2026.11.0"})
    _restart(hass)
    assert await _update_count(hass) == 0  # the newer release starts its own 7 days


async def test_first_start_after_updating_haghs_counts_from_now(hass, hass_storage) -> None:
    """No store yet: an update HA has offered for weeks costs nothing on the first start."""
    hass_storage.pop(KEY, None)
    hass.states.async_set("update.esphome", "on", {"latest_version": "2026.1.0"})
    assert await _update_count(hass) == 0


async def test_vanished_update_entities_leave_the_store(hass, hass_storage, freezer) -> None:
    seen = (dt_util.utcnow() - timedelta(days=2)).isoformat()
    hass_storage[KEY] = _stored({"update.gone": seen, "update.esphome": seen})
    hass.states.async_set("update.esphome", "on")
    assert await _update_count(hass) == 0
    freezer.tick(timedelta(seconds=11))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert set(hass_storage[KEY]["data"]) == {"update.esphome"}


async def test_an_update_entity_that_appears_after_the_first_refresh_keeps_its_window(
    hass, hass_storage, freezer
) -> None:
    """Right after a restart the update entity is registered but has no state yet; its stored time must survive."""
    from homeassistant.helpers import entity_registry as er

    eight_days = (dt_util.utcnow() - timedelta(days=8)).isoformat()
    hass_storage[KEY] = _stored({"update.esphome": eight_days, "update.router": eight_days})
    er.async_get(hass).async_get_or_create(
        "update", "esphome", "uid_esphome", suggested_object_id="esphome"
    )
    hass.states.async_set("update.router", "unavailable")  # integration still starting
    assert await _update_count(hass) == 0  # nothing pending yet
    freezer.tick(timedelta(seconds=11))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert set(hass_storage.get(KEY, _stored({}))["data"]) <= {"update.esphome", "update.router"}
    hass.states.async_set("update.esphome", "on")
    hass.states.async_set("update.router", "on")
    coordinator = make_coordinator(hass)
    assert coordinator._calc_updates()[1] == 2  # both keep their eight days


async def test_an_installed_update_is_pruned_but_a_vanished_unregistered_one_too(
    hass, hass_storage
) -> None:
    seen = (dt_util.utcnow() - timedelta(days=2)).isoformat()
    hass_storage[KEY] = _stored({"update.done": seen, "update.gone": seen})
    hass.states.async_set("update.done", "off")
    coordinator = make_coordinator(hass)
    await coordinator.async_refresh()
    assert set(coordinator._update_first_seen) == set()


async def test_first_start_after_updating_haghs_sets_now_for_every_pending_update(
    hass, hass_storage
) -> None:
    """r2 point 3: no store yet, several updates HA has offered for a long time: all start now, no penalty."""
    hass_storage.pop(KEY, None)
    for name in ("esphome", "router", "core"):
        hass.states.async_set(f"update.{name}", "on", {"latest_version": "1.0"})
    coordinator = make_coordinator(hass)
    await coordinator.async_refresh()
    assert coordinator.data["rec_updates_pending"] is False
    seen = hass.data[DOMAIN]["_update_first_seen"]
    assert set(seen) == {"update.esphome", "update.router", "update.core"}
    assert all(dt_util.utcnow() - value < timedelta(minutes=1) for value in seen.values())


async def test_an_entity_removed_from_the_registry_leaves_the_store(hass, hass_storage) -> None:
    from homeassistant.helpers import entity_registry as er

    registry = er.async_get(hass)
    entry = registry.async_get_or_create(
        "update", "esphome", "uid_removed", suggested_object_id="removed"
    )
    hass_storage[KEY] = _stored(
        {entry.entity_id: (dt_util.utcnow() - timedelta(days=3)).isoformat()}
    )
    coordinator = make_coordinator(hass)
    await coordinator.async_refresh()
    assert (
        entry.entity_id in coordinator._update_first_seen
    )  # registered, no state: kept (not ready)
    registry.async_remove(entry.entity_id)
    coordinator._calc_updates()
    assert entry.entity_id not in coordinator._update_first_seen


async def test_a_disabled_update_entity_leaves_the_store(hass, hass_storage) -> None:
    from homeassistant.helpers import entity_registry as er

    entry = er.async_get(hass).async_get_or_create(
        "update",
        "esphome",
        "uid_disabled",
        suggested_object_id="disabled",
        disabled_by=er.RegistryEntryDisabler.USER,
    )
    hass_storage[KEY] = _stored(
        {entry.entity_id: (dt_util.utcnow() - timedelta(days=3)).isoformat()}
    )
    coordinator = make_coordinator(hass)
    await coordinator.async_refresh()
    assert entry.entity_id not in coordinator._update_first_seen


async def test_an_ignored_update_without_a_state_leaves_the_store(hass, hass_storage) -> None:
    from homeassistant.helpers import entity_registry as er
    from pytest_homeassistant.common import MockConfigEntry

    from custom_components.haghs.const import CONF_IGNORE_PATTERNS
    from custom_components.haghs.coordinator import HaghsDataUpdateCoordinator

    entry = er.async_get(hass).async_get_or_create(
        "update", "esphome", "uid_iot", suggested_object_id="iot_bulb"
    )
    hass_storage[KEY] = _stored(
        {entry.entity_id: (dt_util.utcnow() - timedelta(days=3)).isoformat()}
    )
    config = MockConfigEntry(domain=DOMAIN, data={CONF_IGNORE_PATTERNS: ["update.iot_*"]})
    config.add_to_hass(hass)
    coordinator = HaghsDataUpdateCoordinator(hass, config)
    await coordinator.async_refresh()
    assert entry.entity_id not in coordinator._update_first_seen


async def test_two_config_entries_share_one_load(hass, hass_storage) -> None:
    """The second coordinator must not compute before the stored times are merged (several config entries)."""
    import asyncio

    eight_days = (dt_util.utcnow() - timedelta(days=8)).isoformat()
    hass_storage[KEY] = _stored({"update.esphome": eight_days})
    hass.states.async_set("update.esphome", "on")
    first, second = make_coordinator(hass), make_coordinator(hass)
    await asyncio.gather(first.async_refresh(), second.async_refresh())
    assert first.data["rec_updates_pending"] is True
    assert second.data["rec_updates_pending"] is True
    assert hass.data[DOMAIN]["_update_first_seen"]["update.esphome"] == dt_util.parse_datetime(
        eight_days
    )
