"""Every missing score point must be explained (issue #92).

The parametrization doubles as the acceptance list: each entry is one point
source. A source without a recommendation text and without a rec_* flag fails
the test, so future pillars cannot silently reappear (see #92, #97).
"""

from __future__ import annotations

import pytest

from custom_components.haghs.coordinator import _ApplicationResult, _HardwareResult
from tests.factories import make_coordinator, patch_disk, patch_psi


@pytest.mark.parametrize(
    "app",
    [
        pytest.param(_ApplicationResult(p_zombie=5, zombie_count=1, app_score=95), id="zombie"),
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
