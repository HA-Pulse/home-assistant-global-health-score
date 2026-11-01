"""#123 follow-up: without PSI an unselected CPU or RAM sensor is left out of the hardware pillar, not 0 %."""

from __future__ import annotations

import pytest
from homeassistant.core import HomeAssistant

from custom_components.haghs.const import (
    CONF_CPU_SENSOR,
    CONF_RAM_SENSOR,
    CONF_STORAGE_TYPE,
    REC_CPU_RAM_UNMEASURED,
)
from tests.factories import GB, make_coordinator, patch_disk, patch_psi


async def _result(
    hass: HomeAssistant, *, cpu: str | None, ram: str | None, psi: dict | None = None
):
    data = {
        CONF_STORAGE_TYPE: "ssd",
        CONF_CPU_SENSOR: cpu and "sensor.cpu",
        CONF_RAM_SENSOR: ram and "sensor.ram",
    }
    coord = make_coordinator(hass, data=data)
    if cpu:
        hass.states.async_set("sensor.cpu", cpu)
    if ram:
        hass.states.async_set("sensor.ram", ram)
    # SSD with 8 % free: disk score 80.
    with patch_psi(**(psi or {})), patch_disk(total=100 * GB, free=8 * GB, percent=92.0):
        hw = await coord._async_calc_hardware()
        app = await coord._async_calc_application()
    coord._rec_translations = await coord._async_load_rec_translations()
    return hw, coord._build_result(hw, app)


async def test_neither_measured_leaves_both_out(hass: HomeAssistant) -> None:
    """Disk alone: 80 (dev counted both as 0 % load: (100 + 100 + 80) / 3 = 93)."""
    hw, result = await _result(hass, cpu=None, ram=None)
    assert hw.hardware_score == pytest.approx(80.0)
    assert (hw.p_cpu, hw.p_ram, hw.cpu, hw.ram) == (0, 0, 0.0, 0.0)
    assert (
        result["hardware_score"],
        result["cpu_ram_source"],
        result["rec_cpu_ram_unmeasured"],
    ) == (
        80,
        "none",
        True,
    )
    assert REC_CPU_RAM_UNMEASURED in result["recommendations"].split("\n")


@pytest.mark.parametrize(("cpu", "ram", "expected"), [("30", None, 85.0), (None, "30", 90.0)])
async def test_one_measured_averages_the_measured_components(hass, cpu, ram, expected) -> None:
    """CPU at 30 % costs 10 points: (90 + 80) / 2 = 85; RAM at 30 % costs none: (100 + 80) / 2 = 90."""
    hw, result = await _result(hass, cpu=cpu, ram=ram)
    assert hw.hardware_score == pytest.approx(expected)
    assert (result["cpu_ram_source"], result["rec_cpu_ram_unmeasured"]) == ("partial", True)


async def test_io_pressure_still_counts_when_cpu_and_ram_are_unmeasured(
    hass: HomeAssistant,
) -> None:
    hw, result = await _result(hass, cpu=None, ram=None, psi=dict(io=0.0))
    assert hw.hardware_score == pytest.approx((100.0 + 80.0) / 2)
    assert result["cpu_ram_source"] == "none"


async def test_both_measured_has_no_flag_and_no_line(hass: HomeAssistant) -> None:
    hw, result = await _result(hass, cpu="30", ram="30")
    assert hw.hardware_score == pytest.approx((90.0 + 100.0 + 80.0) / 3)
    assert (result["cpu_ram_source"], result["rec_cpu_ram_unmeasured"]) == ("sensors", False)
    assert REC_CPU_RAM_UNMEASURED not in result["recommendations"]


async def test_psi_for_one_and_a_sensor_for_the_other_counts_as_sensors(
    hass: HomeAssistant,
) -> None:
    _, result = await _result(hass, cpu=None, ram="30", psi=dict(cpu=1.0))
    assert (result["cpu_ram_source"], result["rec_cpu_ram_unmeasured"]) == ("sensors", False)


async def test_neutral_and_fallback_results_have_no_source(hass: HomeAssistant) -> None:
    coord = make_coordinator(hass)
    neutral = coord._neutral_result()
    assert (neutral["cpu_ram_source"], neutral["rec_cpu_ram_unmeasured"]) == (None, False)
    coord._pillar_fallbacks = {"hardware"}
    from custom_components.haghs.coordinator import _ApplicationResult, _HardwareResult

    result = coord._build_result(_HardwareResult(cpu_ram_source="none"), _ApplicationResult())
    assert result["rec_cpu_ram_unmeasured"] is False  # the pillar fallback has its own warning


async def test_repair_is_touched_only_when_the_state_changes(hass: HomeAssistant) -> None:
    from unittest.mock import patch as mock_patch

    from custom_components.haghs.coordinator import _HardwareResult, ir

    coord = make_coordinator(hass)
    coord._pillar_fallbacks = set()
    with (
        mock_patch.object(ir, "async_create_issue") as create,
        mock_patch.object(ir, "async_delete_issue") as delete,
    ):
        for source in ("none", "partial", "none", "sensors", "psi", "none"):
            coord._sync_cpu_ram_issue(_HardwareResult(cpu_ram_source=source))
        coord._pillar_fallbacks = {"hardware"}
        coord._sync_cpu_ram_issue(_HardwareResult(cpu_ram_source="sensors"))  # fallback: no change
    assert (create.call_count, delete.call_count) == (2, 1)
    assert create.call_args.kwargs["severity"] is ir.IssueSeverity.WARNING
