"""Tests for the recommendation builder, PSI-aware variants (#8)."""

from __future__ import annotations

from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.haghs.const import DOMAIN, REC_ALL_CLEAR, REC_FLAG_KEYS
from custom_components.haghs.coordinator import (
    _GB,
    HaghsDataUpdateCoordinator,
    _ApplicationResult,
    _HardwareResult,
)


def _coordinator(hass: HomeAssistant) -> HaghsDataUpdateCoordinator:
    """Create a bare coordinator suitable for unit-testing helpers."""
    entry = MockConfigEntry(domain=DOMAIN, data={})
    entry.add_to_hass(hass)
    return HaghsDataUpdateCoordinator(hass, entry)


async def test_cpu_psi_text_when_psi_used(hass: HomeAssistant) -> None:
    """When CPU value came from PSI, the PSI-flavoured template is used."""
    coordinator = _coordinator(hass)
    hw = _HardwareResult(cpu=6.5, p_cpu=10, cpu_used_psi=True)
    app = _ApplicationResult()

    advice = coordinator._build_recommendations(hw, app)

    assert any("PSI CPU stall time" in line for line in advice)
    assert any("6.5%" in line for line in advice)


async def test_cpu_classic_text_when_psi_unavailable(hass: HomeAssistant) -> None:
    """When CPU value came from the classic sensor, classic wording is used."""
    coordinator = _coordinator(hass)
    hw = _HardwareResult(cpu=38.0, p_cpu=10, cpu_used_psi=False)
    app = _ApplicationResult()

    advice = coordinator._build_recommendations(hw, app)

    assert any("CPU utilization" in line for line in advice)
    assert not any("PSI" in line for line in advice)


async def test_ram_psi_text_when_psi_used(hass: HomeAssistant) -> None:
    """RAM PSI variant fires when ram_used_psi is True."""
    coordinator = _coordinator(hass)
    hw = _HardwareResult(ram=8.0, p_ram=10, ram_used_psi=True)
    app = _ApplicationResult()

    advice = coordinator._build_recommendations(hw, app)

    assert any("PSI memory stall time" in line for line in advice)


async def test_ram_classic_text_when_psi_unavailable(hass: HomeAssistant) -> None:
    """RAM classic variant fires when ram_used_psi is False."""
    coordinator = _coordinator(hass)
    hw = _HardwareResult(ram=82.0, p_ram=15, ram_used_psi=False)
    app = _ApplicationResult()

    advice = coordinator._build_recommendations(hw, app)

    assert any("Memory utilization" in line for line in advice)


async def test_io_text_unchanged(hass: HomeAssistant) -> None:
    """IO has no classic fallback, so the existing wording stays as-is."""
    coordinator = _coordinator(hass)
    hw = _HardwareResult(io=12.5, p_io=10)
    app = _ApplicationResult()

    advice = coordinator._build_recommendations(hw, app)

    assert any("I/O pressure" in line for line in advice)
    assert any("12.5%" in line for line in advice)


async def test_mixed_psi_and_classic_in_same_run(hass: HomeAssistant) -> None:
    """CPU can use PSI while RAM falls back to classic in the same refresh."""
    coordinator = _coordinator(hass)
    hw = _HardwareResult(
        cpu=8.0,
        p_cpu=10,
        cpu_used_psi=True,
        ram=82.0,
        p_ram=15,
        ram_used_psi=False,
    )
    app = _ApplicationResult()

    advice = coordinator._build_recommendations(hw, app)

    joined = "\n".join(advice)
    assert "PSI CPU stall time" in joined
    assert "Memory utilization" in joined


async def test_no_advice_when_all_clear(hass: HomeAssistant) -> None:
    """Empty hardware/application result produces an empty advice list.

    The coordinator's main update path turns the empty list into REC_ALL_CLEAR
    when populating the recommendations attribute.
    """
    coordinator = _coordinator(hass)
    hw = _HardwareResult()
    app = _ApplicationResult()

    advice = coordinator._build_recommendations(hw, app)

    assert advice == []
    # Smoke check the all-clear constant is still importable + non-empty.
    assert REC_ALL_CLEAR


# ============================================================================
# Boolean recommendation flags (#11)
# ============================================================================


async def test_all_flags_false_for_empty_result(hass: HomeAssistant) -> None:
    """A clean hardware/application result yields every rec_* flag as False."""
    coordinator = _coordinator(hass)
    flags = coordinator._build_rec_flags(_HardwareResult(), _ApplicationResult())

    assert set(flags.keys()) == set(REC_FLAG_KEYS)
    assert all(value is False for value in flags.values())


async def test_flag_keys_match_const(hass: HomeAssistant) -> None:
    """REC_FLAG_KEYS in const.py mirrors the keys produced at runtime."""
    coordinator = _coordinator(hass)
    flags = coordinator._build_rec_flags(_HardwareResult(), _ApplicationResult())

    assert tuple(flags.keys()) == REC_FLAG_KEYS


async def test_hardware_flags_fire_on_penalty(hass: HomeAssistant) -> None:
    """CPU, RAM, IO and power flags are True exactly when their penalty fires."""
    coordinator = _coordinator(hass)
    hw = _HardwareResult(p_cpu=10, p_ram=15, p_io=5, p_power=20)
    flags = coordinator._build_rec_flags(hw, _ApplicationResult())

    assert flags["rec_cpu_load"] is True
    assert flags["rec_ram_pressure"] is True
    assert flags["rec_io_pressure"] is True
    assert flags["rec_power_unstable"] is True


async def test_application_flags_fire_on_penalty(hass: HomeAssistant) -> None:
    """DB, backup, updates, zombie and core-lag flags reflect their conditions."""
    coordinator = _coordinator(hass)
    app = _ApplicationResult(
        db_mb=2000.0,
        db_limit_mb=1500.0,
        p_backup=30,
        update_count=3,
        zombie_count=2,
        p_core_lag=20,
    )
    flags = coordinator._build_rec_flags(_HardwareResult(), app)

    assert flags["rec_db_over_limit"] is True
    assert flags["rec_backup_stale"] is True
    assert flags["rec_updates_pending"] is True
    assert flags["rec_zombie"] is True
    assert flags["rec_core_lag"] is True


async def test_disk_low_flag_sd_card(hass: HomeAssistant) -> None:
    """rec_disk_low fires for SD-card storage with less than 5 GB free."""
    coordinator = _coordinator(hass)
    coordinator._storage_type = "sd-card"
    hw = _HardwareResult(disk_total=64 * _GB, disk_free=3 * _GB)

    flags = coordinator._build_rec_flags(hw, _ApplicationResult())

    assert flags["rec_disk_low"] is True


async def test_disk_low_flag_ssd(hass: HomeAssistant) -> None:
    """rec_disk_low fires for SSD storage with less than 10 % free."""
    coordinator = _coordinator(hass)
    coordinator._storage_type = "ssd"
    hw = _HardwareResult(disk_total=1000 * _GB, disk_free=80 * _GB)

    flags = coordinator._build_rec_flags(hw, _ApplicationResult())

    assert flags["rec_disk_low"] is True


async def test_disk_low_flag_clear_when_plenty_of_space(hass: HomeAssistant) -> None:
    """rec_disk_low stays False when both SD and SSD thresholds are clear."""
    coordinator = _coordinator(hass)
    coordinator._storage_type = "ssd"
    hw = _HardwareResult(disk_total=1000 * _GB, disk_free=500 * _GB)

    flags = coordinator._build_rec_flags(hw, _ApplicationResult())

    assert flags["rec_disk_low"] is False
