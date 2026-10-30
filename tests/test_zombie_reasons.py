"""Why each zombie is reported (#154): `zombie_count_per_reason` and `zombie_reasons`."""

from __future__ import annotations

import json
from datetime import timedelta
from pathlib import Path

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import label_registry as lr
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.haghs.const import (
    CONF_IGNORE_LABELS,
    DOMAIN,
    ZOMBIE_LIST_CAP,
    ZOMBIE_REASONS,
)
from custom_components.haghs.sensor import HaghsSensor
from tests.factories import make_coordinator, patch_disk, patch_psi

NEW_KEYS = {"zombie_count_per_reason", "zombie_reasons"}
# Added after #154-d by later plans (#134, #93, conditional ignore labels); compared exactly below.
ADDED_LATER = {
    "integration_unhealthy_entries",
    "empty_device_count",
    "empty_devices",
    "rec_empty_devices",
    "conditional_ignore_active",
}
FROZEN = "2026-10-24T08:00:00+00:00"  # clock of the dev capture
# Complete results of the same scenarios on dev 1a6de2c before this change, captured on a
# clean checkout of that commit without PR code, clock frozen at FROZEN: 8 zombies (one per
# case), and 113 zombies (list capped). Score, every existing attribute (zombie_since values
# included) and every rec_* flag must stay as they were.
DEV_RESULTS = {
    extra: json.loads(
        (Path(__file__).parent / "data" / f"zombie_reasons_dev_{extra}.json").read_text()
    )
    for extra in (0, 105)
}
# Reworded after the capture (plan HAGHS-20261025-001): the count is config entries, not integrations.
OLD_INTEGRATION_LINE = "🧩 Integrations: 2 integration(s) failed to set up."
NEW_INTEGRATION_LINE = "🧩 Integrations: 2 integration entry(ies) failed to set up."


def _expected(extra: int) -> dict:
    """The pinned dev result with exactly the reworded recommendation line replaced."""
    expected = dict(DEV_RESULTS[extra])
    lines = expected["recommendations"].split("\n")
    assert lines.count(OLD_INTEGRATION_LINE) == 1
    expected["recommendations"] = "\n".join(
        NEW_INTEGRATION_LINE if line == OLD_INTEGRATION_LINE else line for line in lines
    )
    return expected


EXPECTED_REASONS = {
    "sensor.orphan": "config_entry_missing",
    "sensor.broken": "integration_not_loaded",
    "sensor.retrying": "integration_not_loaded",
    "sensor.unloaded": "integration_not_loaded",
    "sensor.renamed": "not_provided",
    "sensor.offline": "unavailable",
    "sensor.yaml_restored": "not_provided",
    "sensor.yaml_offline": "unavailable",
}


async def _scenario_result(hass, monkeypatch, extra=0, *, long_ids=False):
    """One real case per reason; extra adds capped-case zombies on a loaded integration.

    long_ids gives the extra zombies long entity ids (worst case for attribute size); the
    pinned dev scenarios use the short ids.
    """
    coord = make_coordinator(hass)
    coord._registries_ready = True
    devices = dr.async_get(hass)
    registry = er.async_get(hass)
    now = dt_util.utcnow()

    def integration(domain, state):
        entry = MockConfigEntry(domain=domain, title=domain, data={})
        entry.add_to_hass(hass)
        object.__setattr__(entry, "state", state)
        return entry

    def registered(entry, object_id, *, state=STATE_UNAVAILABLE, restored=False, domain="sensor"):
        device_id = None
        if entry is not None:  # real registry entries: device first, entity with device_id
            device_id = devices.async_get_or_create(
                config_entry_id=entry.entry_id,
                identifiers={(entry.domain, object_id)},
                name=object_id,
            ).id
        created = registry.async_get_or_create(
            domain,
            entry.domain if entry is not None else "template",
            f"uid_{object_id}",
            suggested_object_id=object_id,
            config_entry=entry,
            device_id=device_id,
        )
        hass.states.async_set(created.entity_id, state, {"restored": True} if restored else {})
        hass.states.get(created.entity_id).last_changed = now - timedelta(minutes=30)
        return created.entity_id

    removed = integration("oldbridge", ConfigEntryState.LOADED)
    broken = integration("brokenint", ConfigEntryState.SETUP_ERROR)
    retry = integration("retryint", ConfigEntryState.SETUP_RETRY)
    unloaded = integration("unloadedint", ConfigEntryState.NOT_LOADED)
    live = integration("liveint", ConfigEntryState.LOADED)
    registered(removed, "orphan", restored=True)  # missing entry beats restored
    registered(broken, "broken", restored=True)  # not loaded beats restored
    registered(retry, "retrying")
    registered(unloaded, "unloaded", state=STATE_UNKNOWN)
    registered(live, "renamed", restored=True)
    registered(live, "offline")
    registered(None, "yaml_restored", restored=True)
    registered(None, "yaml_offline")
    prefix = (
        "living_room_ceiling_rgbww_led_strip_segment_with_a_very_long_name_"
        if long_ids
        else "segment_"
    )
    for index in range(extra):  # capped case
        registered(live, f"{prefix}{index:03d}", domain="light")
    original = hass.config_entries.async_get_entry
    monkeypatch.setattr(
        hass.config_entries,
        "async_get_entry",
        lambda entry_id: None if entry_id == removed.entry_id else original(entry_id),
    )
    hass.states.async_set("sensor.healthy", "21")
    with patch_psi(cpu=1.0, memory=1.0, io=1.0), patch_disk():
        hw = await coord._async_calc_hardware()
        app = await coord._async_calc_application()
    result = coord._build_result(hw, app)
    for entry in (removed, broken, retry, unloaded, live):  # nothing to unload at teardown
        object.__setattr__(entry, "state", ConfigEntryState.NOT_LOADED)
    return coord, result


@pytest.mark.parametrize("extra", [0, 105])
async def test_score_and_existing_attributes_are_unchanged(
    hass: HomeAssistant, monkeypatch: pytest.MonkeyPatch, freezer, extra: int
) -> None:
    """Only the two reason keys are added; every other value equals the pinned dev result.

    The clock is frozen at the capture time, so zombie_since values are compared exactly too.
    The pins are stored with sorted keys, so its order is checked against zombie_entities.
    """
    freezer.move_to(FROZEN)
    _, result = await _scenario_result(hass, monkeypatch, extra)
    assert set(result) == set(DEV_RESULTS[extra]) | NEW_KEYS | ADDED_LATER
    added = NEW_KEYS | ADDED_LATER
    assert {key: value for key, value in result.items() if key not in added} == _expected(extra)
    # The SETUP_ERROR and SETUP_RETRY entries; NOT_LOADED and LOADED entries are not counted.
    assert result["integration_unhealthy_entries"] == ["brokenint: brokenint", "retryint: retryint"]
    assert (result["empty_device_count"], result["empty_devices"]) == (0, [])
    assert result["rec_empty_devices"] is False
    assert result["conditional_ignore_active"] is False
    assert list(result["zombie_since"]) == result["zombie_entities"]


async def test_every_reason_from_home_assistant_facts(
    hass: HomeAssistant, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, result = await _scenario_result(hass, monkeypatch)
    assert result["zombie_reasons"] == {e: EXPECTED_REASONS[e] for e in result["zombie_entities"]}
    assert set(result["zombie_reasons"]) == set(EXPECTED_REASONS)
    assert result["zombie_count_per_reason"] == {
        "config_entry_missing": 1,
        "integration_not_loaded": 3,
        "not_provided": 2,
        "unavailable": 2,
    }
    assert sum(result["zombie_count_per_reason"].values()) == result["zombie_count"]


def test_ranking_is_fixed_and_documented() -> None:
    assert ZOMBIE_REASONS == (
        "config_entry_missing",
        "integration_not_loaded",
        "not_provided",
        "unavailable",
    )


@pytest.mark.parametrize(
    ("entry_state", "restored", "expected"),
    [
        ("missing", True, "config_entry_missing"),  # rank 1 beats rank 3
        ("missing", False, "config_entry_missing"),
        (ConfigEntryState.SETUP_ERROR, True, "integration_not_loaded"),  # rank 2 beats rank 3
        (ConfigEntryState.SETUP_RETRY, False, "integration_not_loaded"),
        (ConfigEntryState.NOT_LOADED, False, "integration_not_loaded"),
        (ConfigEntryState.FAILED_UNLOAD, True, "integration_not_loaded"),
        (ConfigEntryState.LOADED, True, "not_provided"),  # rank 3 beats rank 4
        (ConfigEntryState.LOADED, False, "unavailable"),
        (None, True, "not_provided"),  # no config entry: only rank 3 or 4 apply
        (None, False, "unavailable"),
    ],
)
async def test_highest_applicable_rank_wins(
    hass: HomeAssistant, monkeypatch: pytest.MonkeyPatch, entry_state, restored, expected
) -> None:
    coord = make_coordinator(hass)
    entry = None
    if entry_state is not None:
        entry = MockConfigEntry(domain="someint", data={})
        entry.add_to_hass(hass)
        object.__setattr__(
            entry, "state", ConfigEntryState.LOADED if entry_state == "missing" else entry_state
        )
    entity = er.async_get(hass).async_get_or_create(
        "sensor", "someint", "uid_x", suggested_object_id="x", config_entry=entry
    )
    hass.states.async_set(
        entity.entity_id, STATE_UNAVAILABLE, {"restored": True} if restored else {}
    )
    if entry_state == "missing":
        monkeypatch.setattr(hass.config_entries, "async_get_entry", lambda entry_id: None)
    assert coord._zombie_reason(hass.states.get(entity.entity_id), entity) == expected
    if entry is not None:
        object.__setattr__(entry, "state", ConfigEntryState.NOT_LOADED)


async def test_counts_follow_the_ranking_and_list_only_occurring_reasons(
    hass: HomeAssistant, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, result = await _scenario_result(hass, monkeypatch)
    # All four reasons occur here, so the keys are exactly the ranking.
    assert list(result["zombie_count_per_reason"]) == list(ZOMBIE_REASONS)


async def test_only_occurring_reasons_in_ranking_order(hass: HomeAssistant) -> None:
    """Discovery order unavailable-then-restored still yields the ranking order."""
    coord = make_coordinator(hass)
    coord._registries_ready = True
    registry = er.async_get(hass)
    now = dt_util.utcnow()
    for object_id, restored in (("a_offline", False), ("b_restored", True)):
        entity = registry.async_get_or_create(
            "sensor", "template", f"uid_{object_id}", suggested_object_id=object_id
        )
        hass.states.async_set(
            entity.entity_id, STATE_UNAVAILABLE, {"restored": True} if restored else {}
        )
        hass.states.get(entity.entity_id).last_changed = now - timedelta(minutes=30)
    per_reason = coord._calc_zombies()[9]
    assert list(per_reason) == ["not_provided", "unavailable"]
    assert per_reason == {"not_provided": 1, "unavailable": 1}


async def test_capped_with_the_entity_list_and_counts_stay_full(
    hass: HomeAssistant, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, result = await _scenario_result(hass, monkeypatch, extra=105)
    assert result["zombie_count"] == 113
    assert list(result["zombie_reasons"]) == result["zombie_entities"]
    assert len(result["zombie_reasons"]) == ZOMBIE_LIST_CAP
    assert sum(result["zombie_count_per_reason"].values()) == 113
    assert result["zombie_count_per_reason"]["unavailable"] == 2 + 105


async def test_ignored_disabled_and_unregistered_get_no_reason(
    hass: HomeAssistant, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Excluded entities are absent from zombie_reasons and not counted in zombie_count_per_reason."""
    label = lr.async_get(hass).async_create("Vacation")
    coord = make_coordinator(hass, options={CONF_IGNORE_LABELS: [label.label_id]})
    coord._registries_ready = True
    entry = MockConfigEntry(domain="liveint", data={})
    entry.add_to_hass(hass)
    object.__setattr__(entry, "state", ConfigEntryState.LOADED)
    devices = dr.async_get(hass)
    registry = er.async_get(hass)
    now = dt_util.utcnow()

    def registered(object_id):
        device = devices.async_get_or_create(
            config_entry_id=entry.entry_id, identifiers={("liveint", object_id)}, name=object_id
        )
        created = registry.async_get_or_create(
            "sensor",
            "liveint",
            f"uid_{object_id}",
            suggested_object_id=object_id,
            config_entry=entry,
            device_id=device.id,
        )
        hass.states.async_set(created.entity_id, STATE_UNAVAILABLE)
        hass.states.get(created.entity_id).last_changed = now - timedelta(minutes=30)
        return created.entity_id

    kept = registered("kept")
    labelled = registered("labelled")
    disabled = registered("disabled")
    registry.async_update_entity(labelled, labels={label.label_id})
    registry.async_update_entity(disabled, disabled_by=er.RegistryEntryDisabler.USER)
    hass.states.async_set("sensor.yaml_template", STATE_UNAVAILABLE)
    hass.states.get("sensor.yaml_template").last_changed = now - timedelta(minutes=30)
    result = coord._calc_zombies()
    assert result[10] == {kept: "unavailable"}
    assert result[9] == {"unavailable": 1}
    assert result[5] == 1  # the unregistered entity is reported separately
    object.__setattr__(entry, "state", ConfigEntryState.NOT_LOADED)


async def test_empty_cases_and_sensor(hass: HomeAssistant) -> None:
    coord = make_coordinator(hass)
    coord._registries_ready = True
    assert coord._calc_zombies()[9:] == ({}, {})
    coord._registries_ready = False
    assert coord._calc_zombies()[9:] == ({}, {})
    neutral = coord._neutral_result()
    assert (neutral["zombie_count_per_reason"], neutral["zombie_reasons"]) == ({}, {})
    coord.data = dict(
        neutral,
        zombie_count=1,
        zombie_entities=["sensor.plug"],
        zombie_count_per_reason={"unavailable": 1},
        zombie_reasons={"sensor.plug": "unavailable"},
    )
    attrs = HaghsSensor(coord, hass.config_entries.async_entries(DOMAIN)[0]).extra_state_attributes
    assert attrs["zombie_count_per_reason"] == {"unavailable": 1}
    assert attrs["zombie_reasons"] == {"sensor.plug": "unavailable"}
    assert "zombie_reasons" in HaghsSensor._unrecorded_attributes
    assert "zombie_count_per_reason" not in HaghsSensor._unrecorded_attributes
