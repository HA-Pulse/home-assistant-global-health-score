"""Every missing score point must be explained (issue #92).

The parametrization doubles as the acceptance list: each entry is one point
source. A source without a recommendation text and without a rec_* flag fails
the test, so future pillars cannot silently reappear (see #92, #97).
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import STATE_UNAVAILABLE
from homeassistant.core import CoreState
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import issue_registry as ir
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.haghs.coordinator import (
    _ApplicationResult,
    _HardwareResult,
    _RecorderInfo,
    _StaleResult,
)
from tests.factories import make_coordinator, patch_disk, patch_psi


@pytest.mark.parametrize(
    "app",
    [
        pytest.param(_ApplicationResult(p_zombie=5, zombie_count=1, app_score=95), id="zombie"),
        pytest.param(
            _ApplicationResult(stale=_StaleResult(watch_count=1, penalty=5), app_score=95),
            id="stale",
        ),
        pytest.param(_ApplicationResult(p_backup=30, app_score=70), id="backup_stale"),
        pytest.param(_ApplicationResult(update_count=1, app_score=95), id="updates"),
        pytest.param(_ApplicationResult(p_core_lag=20, app_score=80), id="core_lag"),
        pytest.param(
            _ApplicationResult(db_mb=5000.0, db_limit_mb=1000.0, app_score=90),
            id="db_over_limit",
        ),
        pytest.param(
            _ApplicationResult(integration_unhealthy_count=2, app_score=90),
            id="integration_health",
        ),
        pytest.param(_ApplicationResult(config_bonus=0, app_score=90), id="config_audit"),
        pytest.param(
            _ApplicationResult(p_repairs=5, repair_count=1, app_score=95),
            id="repairs",
        ),
    ],
)
async def test_every_missing_point_is_explained(hass, app) -> None:
    coord = make_coordinator(hass)
    with patch_psi(cpu=1.0, memory=1.0, io=1.0), patch_disk():
        hw = await coord._async_calc_hardware()

    advice = coord._build_recommendations(hw, app)
    flags = coord._build_rec_flags(hw, app)

    assert app.app_score < 100, "testaufbau: Punkt fehlt"
    assert advice, f"app_score {app.app_score} ohne jeden Hinweistext"
    assert any(flags.values()), "kein rec_* Flag gesetzt, obwohl Punkte fehlen"


@pytest.mark.parametrize(
    "app",
    [
        pytest.param(_ApplicationResult(config_bonus=10, app_score=100), id="alles_verdient"),
    ],
)
async def test_no_advice_when_nothing_is_missing(hass, app) -> None:
    """Gegenprobe: ohne fehlende Punkte darf kein Hinweis erscheinen."""
    coord = make_coordinator(hass)
    with patch_psi(cpu=1.0, memory=1.0, io=1.0), patch_disk():
        hw = await coord._async_calc_hardware()
    assert coord._build_recommendations(hw, app) == []
    assert not any(coord._build_rec_flags(hw, app).values())


async def test_result_and_neutral_result_have_the_same_keys(hass) -> None:
    """Structural guard: the sensor reads every key from both result dicts."""
    coord = make_coordinator(hass)
    built = coord._build_result(_HardwareResult(), _ApplicationResult())
    neutral = coord._neutral_result()
    assert set(built) == set(neutral)


@pytest.mark.parametrize("excluded_count", [0, 1, 2])
async def test_exclusions_keep_count_score_recommendation_and_flag_consistent(
    hass, excluded_count, monkeypatch
) -> None:
    entries = [MockConfigEntry(domain="androidtv", title="Fire TV", data={}) for _ in range(2)]
    for entry in entries:
        entry.add_to_hass(hass)
        object.__setattr__(entry, "state", ConfigEntryState.SETUP_RETRY)
    coord = make_coordinator(
        hass,
        options={"ignored_integration_entries": [e.entry_id for e in entries[:excluded_count]]},
    )
    # Count calls at the real filter, not at a replacement scoring implementation.
    count_calls = []
    original_count = coord._count_unhealthy_integrations

    def count_once() -> int:
        count_calls.append(True)
        return original_count()

    monkeypatch.setattr(coord, "_count_unhealthy_integrations", count_once)
    app = await coord._async_calc_application()
    assert count_calls == [True]
    remaining = 2 - excluded_count
    assert app.config_bonus == 0
    assert app.app_score == 100 - 5 * remaining
    result = coord._build_result(_HardwareResult(), app)
    assert result["integration_unhealthy_count"] == remaining
    assert result["application_score"] == app.app_score
    assert result["rec_integration_health"] is (remaining > 0)
    advice = coord._build_recommendations(_HardwareResult(), app)
    template = coord._rec("rec_integration_health")
    if remaining:
        assert template.format(count=remaining) in advice
        assert template.format(count=remaining) in result["recommendations"]
    else:
        assert not any(line.startswith(template.split("{")[0]) for line in advice)


async def test_entry_exclusion_does_not_change_zombies_devices_repairs_or_caps(hass) -> None:
    hass.set_state(CoreState.running)
    entry = MockConfigEntry(domain="androidtv", data={})
    entry.add_to_hass(hass)
    object.__setattr__(entry, "state", ConfigEntryState.SETUP_ERROR)
    device = dr.async_get(hass).async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={("androidtv", "exclusion_probe")},
        name="Exclusion probe",
    )
    entity = er.async_get(hass).async_get_or_create(
        "media_player",
        "androidtv",
        "exclusion_probe",
        config_entry=entry,
        device_id=device.id,
    )
    hass.states.async_set(entity.entity_id, STATE_UNAVAILABLE)
    hass.states.get(entity.entity_id).last_changed = dt_util.utcnow() - timedelta(minutes=30)
    ir.async_create_issue(
        hass,
        "androidtv",
        "exclusion_probe",
        is_fixable=False,
        is_persistent=True,
        severity=ir.IssueSeverity.WARNING,
        translation_key="test",
    )
    results = []
    for selection in [[], [entry.entry_id]]:
        coord = make_coordinator(hass, options={"ignored_integration_entries": selection})
        app = await coord._async_calc_application()
        assert app.zombie_count == 1
        assert app.zombie_list == [entity.entity_id]
        assert app.dead_device_count == 1
        assert app.dead_device_list == ["Exclusion probe"]
        assert app.p_zombie == 20
        assert app.repair_count == 1
        assert app.repair_list == ["androidtv/exclusion_probe"]
        assert app.p_repairs == 5
        results.append((app.zombie_count, app.p_zombie, app.dead_device_list, app.repair_list))
        # Both existing caps remain effective even when Integration Health is excluded.
        coord.recorder_info = _RecorderInfo(keep_days=10, entity_filter_active=True, available=True)
        coord._zombie_grace_seconds = 240 * 60
        capped = await coord._async_calc_application()
        assert capped.zombie_count == 0
        assert capped.app_score == 99
        ir.async_get(hass).async_ignore("androidtv", "exclusion_probe", True)
        coord._zombie_grace_seconds = 5 * 60
        capped = await coord._async_calc_application()
        assert capped.repair_count == 0
        # Enough healthy entities dilute the zombie penalty, leaving the zombie hard cap.
        for index in range(200):
            hass.states.async_set(f"sensor.healthy_{index}", "1")
        capped = await coord._async_calc_application()
        assert capped.zombie_count == 1
        assert capped.app_score == 99
        ir.async_get(hass).async_ignore("androidtv", "exclusion_probe", False)
        for index in range(200):
            hass.states.async_remove(f"sensor.healthy_{index}")
    assert results[0] == results[1]


def test_entity_and_device_ignore_labels_do_not_exclude_config_entries(hass) -> None:
    entry = MockConfigEntry(domain="androidtv", data={})
    entry.add_to_hass(hass)
    object.__setattr__(entry, "state", ConfigEntryState.SETUP_ERROR)
    device = dr.async_get(hass).async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={("androidtv", "label_probe")},
    )
    dr.async_get(hass).async_update_device(device.id, labels={"custom_ignore_id"})
    entity = er.async_get(hass).async_get_or_create(
        "media_player", "androidtv", "label_probe", config_entry=entry, device_id=device.id
    )
    er.async_get(hass).async_update_entity(entity.entity_id, labels={"custom_ignore_id"})
    coord = make_coordinator(hass, options={"ignore_labels": ["custom_ignore_id"]})
    assert (
        coord._is_ignored(entity.entity_id, er.async_get(hass).async_get(entity.entity_id)) is True
    )
    assert coord._count_unhealthy_integrations() == 1
    assert coord._calc_integration_health() == 5
