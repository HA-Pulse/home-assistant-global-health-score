"""Stale reporting uses reports rather than value changes."""

import json
from datetime import timedelta
from time import perf_counter
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from homeassistant.helpers import area_registry as ar
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import label_registry as lr
from homeassistant.util import dt as dt_util

from custom_components.haghs.sensor import HaghsSensor
from tests.factories import make_coordinator, patch_disk, patch_psi


async def test_old_valid_report_is_passive_without_score_change(hass):
    coord = make_coordinator(hass)
    coord._registries_ready = True
    hass.states.async_set("sensor.quiet", "42")
    hass.states.get("sensor.quiet").last_reported = dt_util.utcnow() - timedelta(hours=25)
    with patch_psi(cpu=0, memory=0, io=0), patch_disk():
        result = await coord._async_update_data()
    assert result.get("stale_candidate_count") == 1
    assert result["stale_candidates"] == ["sensor.quiet"]
    assert result["stale_watch_count"] == 0
    assert result["stale_penalty"] == 0
    assert result["application_score"] == 100
    assert result["global_score"] == 100
    assert result["rec_stale"] is False


@pytest.mark.parametrize(
    ("count", "bonus", "score"),
    [(1, 0, 95), (2, 0, 90), (3, 0, 90), (1, 10, 99), (2, 10, 99), (3, 10, 99)],
)
async def test_direct_watch_labels_score_any_domain(hass, count, bonus, score):
    coord = make_coordinator(hass, options={"stale_watch_labels": ["watch_id", "second_id"]})
    coord._registries_ready = True
    registry = er.async_get(hass)
    for index in range(count):
        entry = registry.async_get_or_create("switch", "test", f"watch_{index}")
        registry.async_update_entity(entry.entity_id, labels={"watch_id", "second_id"})
        hass.states.async_set(entry.entity_id, "on")
        hass.states.get(entry.entity_id).last_reported = dt_util.utcnow() - timedelta(hours=25)
    with (
        patch_psi(cpu=0, memory=0, io=0),
        patch_disk(),
        patch.object(coord, "_calc_config_audit", return_value=bonus),
    ):
        result = await coord._async_update_data()
    assert result["stale_watch_count"] == count
    assert result["stale_candidate_count"] == 0
    assert result["stale_penalty"] == min(10, 5 * count)
    assert result["application_score"] == score
    assert result["rec_stale"] is True
    assert result["recommendations"].splitlines()[0] == (
        f"Stale reporting: {count} watched entity/entities have not reported for more than 24 hour(s); "
        f"application penalty {min(10, 5 * count)} point(s) before the configuration bonus."
    )


async def test_sensor_preserves_current_lists_but_not_recorder_history(hass):
    coord = make_coordinator(hass)
    coord.data = coord._neutral_result()
    coord.data["stale_candidates"] = ["sensor.quiet"]
    sensor = HaghsSensor(coord, hass.config_entries.async_entries("haghs")[0])
    assert {"stale_candidates", "stale_watch_entities"} <= sensor._unrecorded_attributes
    assert not {"stale_candidate_count", "stale_watch_count"} & sensor._unrecorded_attributes
    assert sensor.extra_state_attributes["stale_candidates"] == ["sensor.quiet"]
    assert sensor.extra_state_attributes["stale_watch_entities"] == []


@pytest.mark.parametrize(("age", "expected"), [(23, 0), (24, 0), (25, 1), (-1, 0)])
async def test_strict_report_boundary(hass, age, expected):
    coord = make_coordinator(hass)
    coord._registries_ready = True
    now = dt_util.utcnow()
    hass.states.async_set("binary_sensor.quiet", "off")
    state = hass.states.get("binary_sensor.quiet")
    state.last_reported = now - timedelta(hours=age)
    state.last_changed = state.last_updated = now - timedelta(days=10)
    with patch("custom_components.haghs.coordinator.dt_util.utcnow", return_value=now):
        result = coord._calc_stale_entities()
    assert result.candidate_count == expected


@pytest.mark.parametrize("reported", [None, "invalid", 7, dt_util.utcnow().replace(tzinfo=None)])
async def test_invalid_report_timestamp_is_not_failure(hass, reported):
    coord = make_coordinator(hass)
    coord._registries_ready = True
    hass.states.async_set("sensor.quiet", "42")
    hass.states.get("sensor.quiet").last_reported = reported
    assert coord._calc_stale_entities().candidate_count == 0


async def test_missing_timestamp_and_unloaded_registries(hass):
    coord = make_coordinator(hass)
    coord._registries_ready = False
    hass.states.async_set("sensor.quiet", "42")
    hass.states.get("sensor.quiet").last_reported = dt_util.utcnow() - timedelta(hours=25)
    assert coord._calc_stale_entities().candidate_count == 0
    coord._registries_ready = True
    with patch.object(
        type(hass.states),
        "async_all",
        return_value=[SimpleNamespace(entity_id="sensor.quiet", domain="sensor", state="42")],
    ):
        assert coord._calc_stale_entities().candidate_count == 0


async def test_repeated_unchanged_report_and_label_removal_recover(hass):
    coord = make_coordinator(hass, options={"stale_watch_labels": ["watch_id"]})
    coord._registries_ready = True
    registry = er.async_get(hass)
    entry = registry.async_get_or_create("sensor", "test", "recovery")
    registry.async_update_entity(entry.entity_id, labels={"watch_id"})
    hass.states.async_set(entry.entity_id, "42")
    state = hass.states.get(entry.entity_id)
    state.last_reported = state.last_changed = state.last_updated = dt_util.utcnow() - timedelta(
        hours=25
    )
    assert coord._calc_stale_entities().watch_count == 1
    registry.async_update_entity(entry.entity_id, labels=set())
    assert coord._calc_stale_entities().watch_count == 0
    registry.async_update_entity(entry.entity_id, labels={"watch_id"})
    assert coord._calc_stale_entities().watch_count == 1
    hass.states.async_set(entry.entity_id, "42")
    assert hass.states.get(entry.entity_id).last_changed == state.last_changed
    result = coord._calc_stale_entities()
    assert result.watch_count == result.candidate_count == result.penalty == 0


@pytest.mark.parametrize(
    "exclusion",
    [
        "unknown",
        "unavailable",
        "disabled",
        "own",
        "entity_ignore",
        "device_ignore",
        "pattern",
        "hidden",
    ],
)
async def test_exclusions_apply_to_passive_and_watch(hass, exclusion):
    coord = make_coordinator(
        hass,
        options={
            "stale_watch_labels": ["watch_id"],
            "ignore_labels": ["ignore_id"],
            "ignore_patterns": ["sensor.skip_*"],
        },
    )
    coord._registries_ready = True
    registry = er.async_get(hass)
    config_entry = hass.config_entries.async_entries("haghs")[0]
    device = dr.async_get(hass).async_get_or_create(
        config_entry_id=config_entry.entry_id, identifiers={("test", "device")}
    )
    if exclusion == "device_ignore":
        dr.async_get(hass).async_update_device(device.id, labels={"ignore_id"})
    entry = registry.async_get_or_create(
        "sensor",
        "haghs" if exclusion == "own" else "test",
        "excluded",
        device_id=device.id,
        suggested_object_id="skip_me" if exclusion == "pattern" else "tested",
    )
    kwargs = {"labels": {"watch_id", "ignore_id"} if exclusion == "entity_ignore" else {"watch_id"}}
    if exclusion == "disabled":
        kwargs["disabled_by"] = er.RegistryEntryDisabler.USER
    if exclusion == "hidden":
        kwargs["hidden_by"] = er.RegistryEntryHider.USER
    registry.async_update_entity(entry.entity_id, **kwargs)
    hass.states.async_set(
        entry.entity_id, exclusion if exclusion in {"unknown", "unavailable"} else "42"
    )
    hass.states.get(entry.entity_id).last_reported = dt_util.utcnow() - timedelta(hours=25)
    result = coord._calc_stale_entities()
    assert result.candidate_count == result.watch_count == (1 if exclusion == "hidden" else 0)


async def test_device_and_area_watch_do_not_opt_in(hass):
    label = lr.async_get(hass).async_create("Different display name")
    coord = make_coordinator(hass, options={"stale_watch_labels": [label.label_id]})
    coord._registries_ready = True
    config_entry = hass.config_entries.async_entries("haghs")[0]
    area = ar.async_get(hass).async_create("Test room")
    ar.async_get(hass).async_update(area.id, labels={label.label_id})
    device = dr.async_get(hass).async_get_or_create(
        config_entry_id=config_entry.entry_id, identifiers={("test", "device")}
    )
    dr.async_get(hass).async_update_device(device.id, labels={label.label_id}, area_id=area.id)
    registry = er.async_get(hass)
    entry = registry.async_get_or_create("sensor", "test", "device_only", device_id=device.id)
    hass.states.async_set(entry.entity_id, "42")
    hass.states.get(entry.entity_id).last_reported = dt_util.utcnow() - timedelta(hours=25)
    assert coord._calc_stale_entities().candidate_count == 1
    assert coord._calc_stale_entities().watch_count == 0
    registry.async_update_entity(entry.entity_id, labels={label.label_id})
    assert coord._calc_stale_entities().watch_count == 1


async def test_complete_counts_sorted_bounded_lists(hass):
    coord = make_coordinator(hass, options={"stale_watch_labels": ["watch_id"]})
    coord._registries_ready = True
    registry = er.async_get(hass)
    ids = []
    for index in reversed(range(105)):
        entry = registry.async_get_or_create("sensor", "test", f"many_{index:03}")
        registry.async_update_entity(entry.entity_id, labels={"watch_id"})
        hass.states.async_set(entry.entity_id, "42")
        hass.states.get(entry.entity_id).last_reported = dt_util.utcnow() - timedelta(hours=25)
        ids.append(entry.entity_id)
    started = perf_counter()
    result = coord._calc_stale_entities()
    elapsed = perf_counter() - started
    attributes = coord._stale_attributes(result)
    print(
        json.dumps(
            {
                "scenario": "105 overdue entities, both lists at cap",
                "elapsed_seconds": elapsed,
                "attribute_payload_bytes": len(json.dumps(attributes).encode()),
            },
            sort_keys=True,
        )
    )
    assert result.candidate_count == result.watch_count == 105
    assert result.candidates == result.watch_entities == sorted(ids)[:100]
    assert result.penalty == 10


async def test_unwatched_other_domain_and_unregistered_passive(hass):
    coord = make_coordinator(hass, options={"stale_watch_labels": ["watch_id"]})
    coord._registries_ready = True
    for entity_id in ("switch.quiet", "sensor.quiet", "binary_sensor.quiet"):
        hass.states.async_set(entity_id, "on")
        hass.states.get(entity_id).last_reported = dt_util.utcnow() - timedelta(hours=25)
    result = coord._calc_stale_entities()
    assert result.candidates == ["binary_sensor.quiet", "sensor.quiet"]
    assert result.watch_count == result.penalty == 0


async def test_area_ignore_stale_results_preserve_direct_watch_opt_in(hass) -> None:
    """Area/device watch labels never opt in, while area ignore silences both lists."""
    labels = lr.async_get(hass)
    ignore = labels.async_create("Stale area exclusion")
    watch = labels.async_create("Direct stale monitoring")
    assert ignore.label_id != ignore.name
    assert watch.label_id != watch.name
    areas = ar.async_get(hass)
    ignored = areas.async_create("Stale ignored room", labels={ignore.label_id, watch.label_id})
    control = areas.async_create("Stale control room", labels={watch.label_id})
    coord = make_coordinator(
        hass,
        options={"ignore_labels": [ignore.label_id], "stale_watch_labels": [watch.label_id]},
    )
    owner = hass.config_entries.async_entries("haghs")[0]
    device = dr.async_get(hass).async_get_or_create(
        config_entry_id=owner.entry_id, identifiers={("test", "area_stale")}
    )
    dr.async_get(hass).async_update_device(device.id, area_id=ignored.id, labels={watch.label_id})
    registry = er.async_get(hass)
    for object_id in ("area_stale_ignored", "area_stale_control", "area_stale_passive"):
        entry = registry.async_get_or_create(
            "sensor",
            "test",
            object_id,
            suggested_object_id=object_id,
            device_id=device.id,
            original_name=object_id,
        )
        if object_id != "area_stale_passive":
            registry.async_update_entity(entry.entity_id, labels={watch.label_id})
        if object_id != "area_stale_ignored":
            registry.async_update_entity(entry.entity_id, area_id=control.id)
        hass.states.async_set(entry.entity_id, "42")
        hass.states.get(entry.entity_id).last_reported = dt_util.utcnow() - timedelta(hours=25)
    for area_labels, candidates, candidate_count, watched, watch_count, penalty in (
        (
            {ignore.label_id, watch.label_id},
            ["sensor.area_stale_control", "sensor.area_stale_passive"],
            2,
            ["sensor.area_stale_control"],
            1,
            5,
        ),
        (
            {watch.label_id},
            ["sensor.area_stale_control", "sensor.area_stale_ignored", "sensor.area_stale_passive"],
            3,
            ["sensor.area_stale_control", "sensor.area_stale_ignored"],
            2,
            10,
        ),
        (
            {ignore.label_id, watch.label_id},
            ["sensor.area_stale_control", "sensor.area_stale_passive"],
            2,
            ["sensor.area_stale_control"],
            1,
            5,
        ),
    ):
        areas.async_update(ignored.id, labels=area_labels)
        result = coord._calc_stale_entities()
        actual = (
            result.candidates,
            result.candidate_count,
            result.watch_entities,
            result.watch_count,
            result.penalty,
        )
        expected = (candidates, candidate_count, watched, watch_count, penalty)
        assert actual == expected, f"actual={actual}, expected={expected}"
