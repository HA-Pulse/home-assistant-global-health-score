"""Every recommendation branch and rec_* flag.

The coordination logic lives in _build_recommendations / _build_rec_flags and
takes the two pillar results as input, so the tests construct _HardwareResult
and _ApplicationResult directly instead of driving the whole update cycle.
"""

from __future__ import annotations

from custom_components.haghs.const import (
    REC_BACKUP_STALE,
    REC_CORE_LAG,
    REC_DB_OVER_LIMIT,
    REC_DISK_SD_LOW,
    REC_DISK_SSD_LOW,
    REC_FLAG_KEYS,
    REC_UPDATES_PENDING,
    REC_ZOMBIES,
)
from custom_components.haghs.coordinator import _ApplicationResult, _HardwareResult
from tests.factories import GB, make_coordinator


def _prefix(template: str) -> str:
    """Return the static text in front of the first placeholder."""
    return template.split("{")[0].strip()


async def test_sd_disk_advice_and_flag(hass) -> None:
    coord = make_coordinator(hass, options={"storage_type": "sd-card"})
    hw = _HardwareResult(disk_free=4 * GB, disk_total=500 * GB)
    advice = coord._build_recommendations(hw, _ApplicationResult())
    assert any(_prefix(REC_DISK_SD_LOW) in line for line in advice)
    assert coord._build_rec_flags(hw, _ApplicationResult())["rec_disk_low"] is True


async def test_ssd_disk_advice_and_flag(hass) -> None:
    coord = make_coordinator(hass, options={"storage_type": "ssd"})
    hw = _HardwareResult(disk_free=5 * GB, disk_total=100 * GB)
    advice = coord._build_recommendations(hw, _ApplicationResult())
    assert _prefix(REC_DISK_SSD_LOW) in advice[0]
    assert coord._build_rec_flags(hw, _ApplicationResult())["rec_disk_low"] is True


async def test_application_advice_branches(hass) -> None:
    coord = make_coordinator(hass)
    hw = _HardwareResult()
    app = _ApplicationResult(
        db_mb=5000.0,
        db_limit_mb=1000.0,
        p_backup=30,
        update_count=2,
        p_zombie=5,
        zombie_count=1,
        p_core_lag=20,
        app_score=60,
    )
    advice = " ".join(coord._build_recommendations(hw, app))
    assert _prefix(REC_DB_OVER_LIMIT) in advice
    assert REC_BACKUP_STALE in advice
    assert _prefix(REC_UPDATES_PENDING) in advice
    assert _prefix(REC_ZOMBIES) in advice
    assert REC_CORE_LAG in advice

    flags = coord._build_rec_flags(hw, app)
    assert flags["rec_db_over_limit"] is True
    assert flags["rec_backup_stale"] is True
    assert flags["rec_updates_pending"] is True
    assert flags["rec_zombie"] is True
    assert flags["rec_core_lag"] is True


async def test_hardware_advice_branches(hass) -> None:
    coord = make_coordinator(hass)
    hw = _HardwareResult(
        p_cpu=10,
        p_ram=25,
        p_io=10,
        p_power=20,
        cpu=30.0,
        ram=80.0,
        io=10.0,
    )
    advice = " ".join(coord._build_recommendations(hw, _ApplicationResult()))
    assert "CPU" in advice
    assert "Memory" in advice
    assert "I/O" in advice
    assert "Power" in advice

    flags = coord._build_rec_flags(hw, _ApplicationResult())
    assert flags["rec_cpu_load"] is True
    assert flags["rec_ram_pressure"] is True
    assert flags["rec_io_pressure"] is True
    assert flags["rec_power_unstable"] is True


async def test_all_clear_has_no_flags(hass) -> None:
    coord = make_coordinator(hass)
    hw = _HardwareResult()
    app = _ApplicationResult()
    assert coord._build_recommendations(hw, app) == []
    assert set(coord._build_rec_flags(hw, app)) == set(REC_FLAG_KEYS)
    assert not any(coord._build_rec_flags(hw, app).values())
