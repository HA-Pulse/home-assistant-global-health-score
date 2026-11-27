"""Backup Health from Home Assistant's built-in backup integration, next to the add-on (#218).

The built-in integration's sensors are found in the entity registry by platform ``backup`` and their unique ids,
so translated or renamed entity ids still work. A scheduled automatic backup is stale when the last successful one
is older than its schedule interval (next run minus last attempt, 24 to 168 hours) plus 26 hours, at most 192 hours.
No schedule, or no successful automatic backup known: a recommendation only. Stale from either source costs 30
points once.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util

from custom_components.haghs.const import (
    BACKUP_ADDON_ENTITY,
    REC_BACKUP_NOT_CONFIGURED,
    REC_BACKUP_STALE,
)
from custom_components.haghs.coordinator import _HardwareResult
from custom_components.haghs.sensor import HaghsSensor
from tests.factories import make_coordinator, patch_disk, patch_psi

NOW = "2026-11-27T12:00:00+00:00"
# Translated and renamed entity ids on purpose: HAGHS must find them by unique id.
ENTITY_IDS = {
    "last_successful_automatic_backup": "sensor.letzte_erfolgreiche_automatische_sicherung",
    "last_attempted_automatic_backup": "sensor.mein_letzter_versuch",
    "next_scheduled_automatic_backup": "sensor.naechste_geplante_sicherung",
}


def _core(hass: HomeAssistant, **hours_from_now: float | str | None) -> None:
    """Register the built-in backup sensors; values are hours relative to now, a string, or None (unknown)."""
    registry = er.async_get(hass)
    now = dt_util.utcnow()
    for key, entity_id in ENTITY_IDS.items():
        object_id = entity_id.split(".", 1)[1]
        entry = registry.async_get_or_create("sensor", "backup", key, suggested_object_id=object_id)
        assert entry.entity_id == entity_id
        value = hours_from_now.get(key.split("_automatic")[0])
        if isinstance(value, (int, float)):
            state = (now + timedelta(hours=value)).isoformat()
        elif isinstance(value, str):
            state = value
        else:
            state = "unknown"
        hass.states.async_set(entity_id, state, {"device_class": "timestamp"})


def _backup(hass: HomeAssistant):
    return make_coordinator(hass)._calc_backup()


def _summary(result) -> tuple:
    return (result.p_backup, result.source, result.status, result.max_age_hours)


@pytest.fixture(autouse=True)
def _frozen(freezer) -> None:
    freezer.move_to(NOW)


async def test_daily_schedule_stale_after_two_missed_runs(hass) -> None:
    # Daily: last attempt 10 h ago, next run in 14 h -> interval 24 h, stale after 50 h.
    # One failed run (48 h at the next run) stays ok while the next run finishes.
    _core(hass, last_successful=-49, last_attempted=-10, next_scheduled=14)
    assert _summary(_backup(hass)) == (0, "core", "ok", 50)
    _core(hass, last_successful=-51, last_attempted=-10, next_scheduled=14)
    result = _backup(hass)
    assert _summary(result) == (30, "core", "stale", 50)
    assert result.age_hours == 51
    assert result.last_success == (dt_util.utcnow() - timedelta(hours=51)).isoformat()


async def test_weekly_schedule_stale_after_eight_days(hass) -> None:
    _core(hass, last_successful=-191, last_attempted=-24, next_scheduled=144)
    assert _summary(_backup(hass)) == (0, "core", "ok", 192)
    _core(hass, last_successful=-193, last_attempted=-24, next_scheduled=144)
    assert _summary(_backup(hass)) == (30, "core", "stale", 192)


@pytest.mark.parametrize(
    ("attempted", "next_run", "max_age"),
    [
        (-2, 70, 98),  # custom days three days apart: 72 h + 26 h
        (-1, 2, 50),  # shorter than a day: at least 24 h + 26 h
        (-1, 400, 192),  # longer than a week: capped at 192 h
        (None, 30, 192),  # no last attempt known (HA before 2025.6): one week, capped
        (5, 3, 192),  # next run not after the last attempt: one week, capped
    ],
)
async def test_interval_from_the_schedule_is_bounded(hass, attempted, next_run, max_age) -> None:
    _core(hass, last_successful=-1, last_attempted=attempted, next_scheduled=next_run)
    assert _summary(_backup(hass)) == (0, "core", "ok", max_age)


async def test_no_schedule_is_a_recommendation_without_deduction(hass) -> None:
    _core(hass, last_successful=-900, last_attempted=-900, next_scheduled=None)
    result = _backup(hass)
    assert _summary(result) == (0, "core", "not_configured", None)
    assert result.age_hours == 900


async def test_scheduled_without_a_successful_backup_is_unknown(hass) -> None:
    _core(hass, last_successful=None, last_attempted=-3, next_scheduled=21)
    result = _backup(hass)
    assert _summary(result) == (0, "core", "unknown", None)
    assert (result.last_success, result.age_hours) == (None, None)


async def test_a_timestamp_without_time_zone_counts_as_unknown(hass) -> None:
    _core(hass, last_successful="2026-11-01T00:00:00", last_attempted=-3, next_scheduled=21)
    assert _summary(_backup(hass)) == (0, "core", "unknown", None)


async def test_unavailable_core_sensor_counts_as_unknown(hass) -> None:
    _core(hass, last_successful=-1, last_attempted=-1, next_scheduled=23)
    hass.states.async_set(ENTITY_IDS["last_successful_automatic_backup"], "unavailable")
    assert _summary(_backup(hass)) == (0, "core", "unknown", None)


@pytest.mark.parametrize(
    ("addon", "core_success", "expected"),
    [
        ("on", -10, (30, "both", "stale", 50)),  # add-on stale, core fresh: stale once
        ("off", -60, (30, "both", "stale", 50)),  # add-on fresh, core stale: stale once
        ("on", -60, (30, "both", "stale", 50)),  # both stale: 30 points, not 60
        ("off", -10, (0, "both", "ok", 50)),
    ],
)
async def test_both_sources_cost_the_points_once(hass, addon, core_success, expected) -> None:
    hass.states.async_set(BACKUP_ADDON_ENTITY, addon)
    _core(hass, last_successful=core_success, last_attempted=-10, next_scheduled=14)
    assert _summary(_backup(hass)) == expected


async def test_the_addon_covers_an_instance_without_automatic_backups(hass) -> None:
    hass.states.async_set(BACKUP_ADDON_ENTITY, "off")
    _core(hass, last_successful=None, last_attempted=None, next_scheduled=None)
    assert _summary(_backup(hass)) == (0, "both", "ok", None)


@pytest.mark.parametrize(
    ("addon", "expected"),
    [
        ("on", (30, "addon", "stale", None)),
        ("off", (0, "addon", "ok", None)),
        ("unavailable", (0, "none", "no_source", None)),
        (None, (0, "none", "no_source", None)),
    ],
)
async def test_addon_alone_behaves_as_before(hass, addon, expected) -> None:
    if addon is not None:
        hass.states.async_set(BACKUP_ADDON_ENTITY, addon)
    assert _summary(_backup(hass)) == expected


async def test_entity_with_the_right_id_but_another_platform_is_ignored(hass) -> None:
    registry = er.async_get(hass)
    entry = registry.async_get_or_create(
        "sensor", "other", "last_successful_automatic_backup", suggested_object_id="fake"
    )
    hass.states.async_set(entry.entity_id, (dt_util.utcnow() - timedelta(days=30)).isoformat())
    assert _summary(_backup(hass)) == (0, "none", "no_source", None)


@pytest.mark.parametrize(
    ("core", "status", "flag_stale", "flag_not_configured", "line"),
    [
        (
            {"last_successful": -60, "last_attempted": -10, "next_scheduled": 14},
            "stale",
            True,
            False,
            REC_BACKUP_STALE,
        ),
        (
            {"last_successful": None, "last_attempted": None, "next_scheduled": None},
            "not_configured",
            False,
            True,
            REC_BACKUP_NOT_CONFIGURED,
        ),
        (
            {"last_successful": None, "last_attempted": -3, "next_scheduled": 21},
            "unknown",
            False,
            True,
            REC_BACKUP_NOT_CONFIGURED,
        ),
        (
            {"last_successful": -10, "last_attempted": -10, "next_scheduled": 14},
            "ok",
            False,
            False,
            None,
        ),
    ],
)
async def test_cycle_result_attributes_flags_and_points(
    hass, core, status, flag_stale, flag_not_configured, line
) -> None:
    _core(hass, **core)
    coordinator = make_coordinator(hass)
    coordinator._registries_ready = True
    with patch_psi(cpu=1.0, memory=1.0, io=1.0), patch_disk():
        app = await coordinator._async_calc_application()
    result = coordinator._build_result(_HardwareResult(), app)

    assert result["backup_status"] == status
    assert result["backup_source"] == "core"
    assert (result["rec_backup_stale"], result["rec_backup_not_configured"]) == (
        flag_stale,
        flag_not_configured,
    )
    lines = result["recommendations"].splitlines()
    assert (REC_BACKUP_STALE in lines) is flag_stale
    assert (REC_BACKUP_NOT_CONFIGURED in lines) is flag_not_configured
    if line is not None:
        assert line in lines
    assert app.p_backup == (30 if status == "stale" else 0)


async def test_backup_points_lower_the_application_score_by_exactly_30(hass) -> None:
    coordinator = make_coordinator(hass)
    coordinator._registries_ready = True
    _core(hass, last_successful=-10, last_attempted=-10, next_scheduled=14)
    with patch_psi(cpu=1.0, memory=1.0, io=1.0), patch_disk():
        fresh = await coordinator._async_calc_application()
    _core(hass, last_successful=-60, last_attempted=-10, next_scheduled=14)
    with patch_psi(cpu=1.0, memory=1.0, io=1.0), patch_disk():
        stale = await coordinator._async_calc_application()
    assert fresh.app_score - stale.app_score == 30


def test_time_values_stay_out_of_the_recorder() -> None:
    assert {"backup_last_success", "backup_age_hours"} <= HaghsSensor._unrecorded_attributes
    assert not {"backup_source", "backup_status", "backup_max_age_hours"} & (
        HaghsSensor._unrecorded_attributes
    )
