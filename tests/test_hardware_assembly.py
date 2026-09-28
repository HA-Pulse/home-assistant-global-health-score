"""Hardware pillar assembly: PSI vs classic fallback, 3 vs 4 components.

Averages under test (coordinator._async_calc_hardware):
  4 components when I/O PSI is available: (cpu + ram + io + disk) / 4
  3 components otherwise:                  (cpu + ram + disk) / 3
  the under-voltage penalty is a flat deduction after averaging.
"""

from __future__ import annotations

import logging

import pytest

from tests.factories import make_coordinator, patch_disk, patch_psi


async def test_psi_values_are_used_when_available(hass) -> None:
    coord = make_coordinator(hass)
    with patch_psi(cpu=1.0, memory=1.0, io=1.0), patch_disk():
        result = await coord._async_calc_hardware()
    assert result.psi_available is True
    assert result.cpu == 1.0
    assert result.ram == 1.0
    assert result.hardware_score == pytest.approx(100.0)


async def test_three_component_average_without_io_psi(hass) -> None:
    coord = make_coordinator(hass)
    with patch_psi(cpu=1.0, memory=1.0, io=None), patch_disk():
        result = await coord._async_calc_hardware()
    assert result.psi_available is True
    assert result.p_io == 0
    assert result.hardware_score == pytest.approx(100.0)


async def test_classic_sensors_are_used_without_psi(hass) -> None:
    coord = make_coordinator(
        hass,
        data={"cpu_sensor": "sensor.cpu", "ram_sensor": "sensor.ram"},
    )
    hass.states.async_set("sensor.cpu", "30")
    hass.states.async_set("sensor.ram", "75")
    with patch_psi(), patch_disk():
        result = await coord._async_calc_hardware()
    assert result.psi_available is False
    assert result.p_cpu == 10
    assert result.p_ram == 16
    assert result.hardware_score == pytest.approx(91.33, abs=0.01)


async def test_no_psi_and_no_sensors_is_neutral(hass) -> None:
    coord = make_coordinator(hass)
    with patch_psi(), patch_disk():
        result = await coord._async_calc_hardware()
    assert result.psi_available is False
    assert result.p_cpu == 0
    assert result.p_ram == 0
    assert result.hardware_score == pytest.approx(100.0)


async def test_cpu_sensor_above_100_is_clamped_and_logged(hass, caplog) -> None:
    coord = make_coordinator(hass, data={"cpu_sensor": "sensor.cpu"})
    hass.states.async_set("sensor.cpu", "250")
    with caplog.at_level(logging.WARNING), patch_psi(), patch_disk():
        result = await coord._async_calc_hardware()
    assert result.cpu == 100.0
    assert result.p_cpu == 80
    assert "expected 0-100%" in caplog.text


async def test_ram_sensor_above_100_is_clamped_and_logged(hass, caplog) -> None:
    coord = make_coordinator(hass, data={"ram_sensor": "sensor.ram"})
    hass.states.async_set("sensor.ram", "150")
    with caplog.at_level(logging.WARNING), patch_psi(), patch_disk():
        result = await coord._async_calc_hardware()
    assert result.ram == 100.0
    assert result.p_ram == 80
    assert "expected 0-100%" in caplog.text
