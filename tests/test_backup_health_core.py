"""Backup Health from Home Assistant's built-in backup integration, next to the add-on (#218).

The built-in integration's sensors are found in the entity registry by platform ``backup`` and their unique ids,
so translated or renamed entity ids still work. A scheduled automatic backup is stale when the last successful one
is older than 8 days. No schedule, no successful automatic backup known, or unavailable sensors: a recommendation
only (not in the first 15 minutes after a start). Stale from either source costs 30 points once. Disabled or
ignored backup sensors are not read.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import label_registry as lr
from homeassistant.util import dt as dt_util

from custom_components.haghs.const import (
    BACKUP_ADDON_ENTITY,
    REC_BACKUP_NO_SCHEDULE,
    REC_BACKUP_STALE,
    REC_BACKUP_UNKNOWN,
)
from custom_components.haghs.coordinator import _HardwareResult
from custom_components.haghs.sensor import HaghsSensor
from tests.factories import make_coordinator, patch_disk, patch_psi

NOW = "2026-11-27T12:00:00+00:00"
# Translated and renamed entity ids on purpose: HAGHS must find them by unique id.
ENTITY_IDS = {
    "last_successful_automatic_backup": "sensor.letzte_erfolgreiche_automatische_sicherung",
    "next_scheduled_automatic_backup": "sensor.naechste_geplante_sicherung",
}
WEEK = 7 * 24


def _core(hass: HomeAssistant, success, next_run) -> None:
    """Register the built-in backup sensors.

    A number is hours relative to now, a string is the raw state, ``None`` leaves the
    registered entity without a state (a disabled entity).
    """
    registry = er.async_get(hass)
    now = dt_util.utcnow()
    for (key, entity_id), value in zip(ENTITY_IDS.items(), (success, next_run), strict=True):
        entry = registry.async_get_or_create(
            "sensor", "backup", key, suggested_object_id=entity_id.split(".", 1)[1]
        )
        assert entry.entity_id == entity_id
        if isinstance(value, (int, float)):
            hass.states.async_set(entity_id, (now + timedelta(hours=value)).isoformat())
        elif isinstance(value, str):
            hass.states.async_set(entity_id, value)
        else:
            hass.states.async_remove(entity_id)


def _backup(hass: HomeAssistant, boot_age_minutes: int = 120):
    return make_coordinator(hass, boot_age_minutes=boot_age_minutes)._calc_backup()


def _summary(result) -> tuple:
    return (result.p_backup, result.source, result.status, result.unverified)


@pytest.fixture(autouse=True)
def _frozen(freezer) -> None:
    freezer.move_to(NOW)


async def test_scheduled_backup_is_stale_after_eight_days(hass) -> None:
    _core(hass, success=-191, next_run=WEEK - 1)
    ok = _backup(hass)
    assert _summary(ok) == (0, "core", "ok", False)
    assert (ok.age_hours, ok.max_age_hours) == (191, 192)
    _core(hass, success=-193, next_run=WEEK - 1)
    stale = _backup(hass)
    assert _summary(stale) == (30, "core", "stale", False)
    assert stale.age_hours == 193
    assert stale.last_success == (dt_util.utcnow() - timedelta(hours=193)).isoformat()


async def test_a_daily_schedule_uses_the_same_eight_days(hass) -> None:
    _core(hass, success=-100, next_run=4)  # four missed daily runs, still within 8 days
    assert _summary(_backup(hass)) == (0, "core", "ok", False)


async def test_no_schedule_is_a_recommendation_without_deduction(hass) -> None:
    _core(hass, success=-900, next_run="unknown")  # HA's schedule "never"
    result = _backup(hass)
    assert _summary(result) == (0, "core", "not_configured", True)
    assert (result.age_hours, result.max_age_hours) == (900, 192)


@pytest.mark.parametrize(
    ("success", "next_run"),
    [
        ("unknown", 21),  # scheduled, no successful automatic backup yet
        ("unavailable", 21),  # integration not loaded
        ("unavailable", "unavailable"),  # both still loading or failed
        ("2026-11-01T00:00:00", 21),  # a time without time zone is not trusted
    ],
)
async def test_unknown_is_a_recommendation_without_deduction(hass, success, next_run) -> None:
    _core(hass, success=success, next_run=next_run)
    result = _backup(hass)
    assert _summary(result) == (0, "core", "unknown", True)
    assert (result.last_success is None) is (not isinstance(success, int))


async def test_no_recommendation_in_the_first_15_minutes_after_a_start(hass) -> None:
    _core(hass, success="unavailable", next_run="unknown")
    assert _summary(_backup(hass, boot_age_minutes=14)) == (0, "core", "not_configured", False)
    assert _summary(_backup(hass, boot_age_minutes=16)) == (0, "core", "not_configured", True)


async def test_both_backup_sensors_disabled_means_no_source(hass) -> None:
    _core(hass, success=None, next_run=None)
    assert _summary(_backup(hass)) == (0, "none", "no_source", False)


@pytest.mark.parametrize(
    ("success", "next_run", "expected"),
    [
        (None, 21, (0, "core", "unknown", True)),  # last-success sensor disabled: not checked, hint
        (-10, None, (0, "core", "ok", False)),  # next-run sensor disabled: the age still counts
        (
            -10,
            "unavailable",
            (0, "core", "ok", False),
        ),  # schedule sensor unavailable: the age counts
        (-480, None, (30, "core", "stale", False)),
    ],
)
async def test_one_disabled_backup_sensor(hass, success, next_run, expected) -> None:
    _core(hass, success=success, next_run=next_run)
    assert _summary(_backup(hass)) == expected


@pytest.mark.parametrize("target", ["entities", "one"])
async def test_an_ignore_label_switches_the_check_off(hass, target) -> None:
    label = lr.async_get(hass).async_create("Backed up elsewhere")
    assert label.label_id != label.name
    _core(hass, success="unknown", next_run="unknown")
    registry = er.async_get(hass)
    ignored = (
        list(ENTITY_IDS.values())
        if target == "entities"
        else [ENTITY_IDS["next_scheduled_automatic_backup"]]
    )
    for entity_id in ignored:
        registry.async_update_entity(entity_id, labels={label.label_id})
    coordinator = make_coordinator(hass, options={"ignore_labels": [label.label_id]})
    result = coordinator._calc_backup()
    if target == "entities":
        assert _summary(result) == (0, "none", "no_source", False)
    else:  # only the schedule sensor ignored: the last-success sensor is still read
        assert _summary(result) == (0, "core", "unknown", True)


async def test_a_last_success_in_the_future_is_not_trusted(hass) -> None:
    _core(hass, success=72, next_run=24)
    result = _backup(hass)
    assert _summary(result) == (0, "core", "unknown", True)
    assert (result.last_success, result.age_hours) == (None, None)


@pytest.mark.parametrize(
    ("addon", "success", "expected"),
    [
        ("on", -10, (30, "both", "stale", False)),  # add-on stale, core fresh: stale once
        ("off", -200, (30, "both", "stale", False)),  # add-on fresh, core stale: stale once
        ("on", -200, (30, "both", "stale", False)),  # both stale: 30 points, not 60
        ("off", -10, (0, "both", "ok", False)),
    ],
)
async def test_both_sources_cost_the_points_once(hass, addon, success, expected) -> None:
    hass.states.async_set(BACKUP_ADDON_ENTITY, addon)
    _core(hass, success=success, next_run=24)
    assert _summary(_backup(hass)) == expected


@pytest.mark.parametrize(
    ("addon", "expected"),
    [
        ("off", (0, "both", "ok", False)),  # a working add-on covers it
        ("unavailable", (0, "core", "not_configured", True)),  # a broken add-on checks nothing
        ("unknown", (0, "core", "not_configured", True)),
    ],
)
async def test_the_addon_covers_an_instance_without_automatic_backups(
    hass, addon, expected
) -> None:
    hass.states.async_set(BACKUP_ADDON_ENTITY, addon)
    _core(hass, success="unknown", next_run="unknown")
    assert _summary(_backup(hass)) == expected


@pytest.mark.parametrize(
    ("addon", "expected"),
    [
        ("on", (30, "addon", "stale", False)),
        ("off", (0, "addon", "ok", False)),
        ("unavailable", (0, "none", "no_source", False)),
        (None, (0, "none", "no_source", False)),
    ],
)
async def test_addon_alone_costs_the_points_as_before(hass, addon, expected) -> None:
    if addon is not None:
        hass.states.async_set(BACKUP_ADDON_ENTITY, addon)
    result = _backup(hass)
    assert _summary(result) == expected
    assert (result.last_success, result.age_hours, result.max_age_hours) == (None, None, None)


async def test_entity_with_the_right_id_but_another_platform_is_ignored(hass) -> None:
    registry = er.async_get(hass)
    for key in ENTITY_IDS:
        entry = registry.async_get_or_create("sensor", "other", key, suggested_object_id=key)
        hass.states.async_set(entry.entity_id, (dt_util.utcnow() - timedelta(days=30)).isoformat())
    assert _summary(_backup(hass)) == (0, "none", "no_source", False)


@pytest.mark.parametrize(
    ("success", "next_run", "status", "flags", "line"),
    [
        (-200, 24, "stale", (True, False), REC_BACKUP_STALE),
        (-200, "unknown", "not_configured", (False, True), REC_BACKUP_NO_SCHEDULE),
        ("unknown", 24, "unknown", (False, True), REC_BACKUP_UNKNOWN),
        (-10, 24, "ok", (False, False), None),
    ],
)
async def test_cycle_result_attributes_flags_and_lines(
    hass, success, next_run, status, flags, line
) -> None:
    _core(hass, success=success, next_run=next_run)
    coordinator = make_coordinator(hass)
    coordinator._registries_ready = True
    with patch_psi(cpu=1.0, memory=1.0, io=1.0), patch_disk():
        app = await coordinator._async_calc_application()
    result = coordinator._build_result(_HardwareResult(), app)

    assert (result["backup_source"], result["backup_status"]) == ("core", status)
    assert (result["rec_backup_stale"], result["rec_backup_unverified"]) == flags
    texts = (REC_BACKUP_STALE, REC_BACKUP_NO_SCHEDULE, REC_BACKUP_UNKNOWN)
    backup_lines = [text for text in result["recommendations"].splitlines() if text in texts]
    assert backup_lines == ([line] if line else [])
    assert app.p_backup == (30 if status == "stale" else 0)


async def test_backup_points_lower_the_application_score_by_exactly_30(hass) -> None:
    coordinator = make_coordinator(hass)
    coordinator._registries_ready = True
    _core(hass, success=-10, next_run=24)
    with patch_psi(cpu=1.0, memory=1.0, io=1.0), patch_disk():
        fresh = await coordinator._async_calc_application()
    _core(hass, success=-200, next_run=24)
    with patch_psi(cpu=1.0, memory=1.0, io=1.0), patch_disk():
        stale = await coordinator._async_calc_application()
    assert fresh.app_score - stale.app_score == 30


async def test_the_backup_check_runs_once_per_cycle(hass, monkeypatch) -> None:
    coordinator = make_coordinator(hass)
    coordinator._registries_ready = True
    calls: list[int] = []
    real = coordinator._calc_backup

    def counted():
        calls.append(1)
        return real()

    monkeypatch.setattr(coordinator, "_calc_backup", counted)
    with patch_psi(cpu=1.0, memory=1.0, io=1.0), patch_disk():
        await coordinator._async_calc_application()
    assert calls == [1]


def test_time_values_stay_out_of_the_recorder() -> None:
    assert {"backup_last_success", "backup_age_hours"} <= HaghsSensor._unrecorded_attributes
    assert not {"backup_source", "backup_status", "backup_max_age_hours"} & (
        HaghsSensor._unrecorded_attributes
    )
