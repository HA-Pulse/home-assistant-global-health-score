"""Tier boundary tests for the hardware penalty functions.

Every threshold gets an assertion just inside and just outside the tier, so a
future threshold edit cannot pass unnoticed. Pure functions only, the
coordinator instance is never needed for the penalty helpers.
"""

from __future__ import annotations

import pytest

from custom_components.haghs.coordinator import HaghsDataUpdateCoordinator as Coord
from tests.factories import make_coordinator


@pytest.mark.parametrize(
    ("cpu", "expected"),
    [
        (0, 0),
        (25, 0),
        (25.1, 10),
        (40, 10),
        (40.1, 25),
        (60, 25),
        (60.1, 50),
        (80, 50),
        (80.1, 80),
        (100, 80),
    ],
)
def test_classic_cpu_penalty_tiers(cpu: float, expected: int) -> None:
    assert Coord._classic_cpu_penalty(cpu) == expected


@pytest.mark.parametrize(
    ("stall", "expected"),
    [
        (0, 0),
        (5, 0),
        (5.1, 10),
        (15, 10),
        (15.1, 25),
        (30, 25),
        (30.1, 50),
        (50, 50),
        (50.1, 80),
    ],
)
def test_psi_cpu_penalty_tiers(stall: float, expected: int) -> None:
    assert Coord._psi_cpu_penalty(stall) == expected


@pytest.mark.parametrize(
    ("ram", "expected"),
    [
        (0, 0),
        (69.9, 0),
        (70, 0),
        (75, 16),
        (79, 29),
        (80, 33),
        (85, 49),
        (89, 63),
        (90, 80),
        (100, 80),
    ],
)
def test_classic_ram_penalty_tiers(ram: float, expected: int) -> None:
    assert Coord._classic_ram_penalty(ram) == expected


@pytest.mark.parametrize(
    ("stall", "expected"),
    [
        (0, 0),
        (5, 0),
        (5.1, 10),
        (10, 10),
        (10.1, 25),
        (25, 25),
        (25.1, 50),
        (40, 50),
        (40.1, 80),
    ],
)
def test_psi_memory_penalty_tiers(stall: float, expected: int) -> None:
    assert Coord._psi_memory_penalty(stall) == expected


@pytest.mark.parametrize(
    ("stall", "expected"),
    [
        (0, 0),
        (5, 0),
        (5.1, 10),
        (15, 10),
        (15.1, 25),
        (30, 25),
        (30.1, 50),
        (50, 50),
        (50.1, 80),
    ],
)
def test_psi_io_penalty_tiers(stall: float, expected: int) -> None:
    assert Coord._psi_io_penalty(stall) == expected


def test_parse_psi_file_returns_some_avg10(tmp_path) -> None:
    """A PSI file with a `some avg10=` line yields that value."""
    path = tmp_path / "cpu"
    path.write_text("some avg10=1.25 avg60=0.50 avg300=0.10\ntotal avg10=0.00\n")
    assert Coord._parse_psi_file(str(path)) == 1.25


def test_parse_psi_file_returns_none_when_pattern_missing(tmp_path) -> None:
    """A readable file without `some avg10=` yields None."""
    path = tmp_path / "cpu"
    path.write_text("total avg10=0.00 with avg10=0.00\n")
    assert Coord._parse_psi_file(str(path)) is None


def test_parse_psi_file_returns_none_on_oserror(tmp_path) -> None:
    """A missing file (no PSI support) yields None instead of raising."""
    assert Coord._parse_psi_file(str(tmp_path / "does-not-exist")) is None


def test_get_float_reads_value(hass) -> None:
    coord = make_coordinator(hass)
    hass.states.async_set("sensor.value", "42.5")
    assert coord._get_float("sensor.value") == 42.5


def test_get_float_zero_without_entity_id(hass) -> None:
    coord = make_coordinator(hass)
    assert coord._get_float(None) == 0.0


def test_get_float_zero_on_missing_state(hass) -> None:
    coord = make_coordinator(hass)
    assert coord._get_float("sensor.missing") == 0.0


def test_get_float_zero_on_unavailable(hass) -> None:
    coord = make_coordinator(hass)
    hass.states.async_set("sensor.value", "unavailable")
    assert coord._get_float("sensor.value") == 0.0


def test_get_float_zero_on_garbage_state(hass) -> None:
    coord = make_coordinator(hass)
    hass.states.async_set("sensor.value", "not-a-number")
    assert coord._get_float("sensor.value") == 0.0
