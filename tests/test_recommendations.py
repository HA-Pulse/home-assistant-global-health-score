"""Tests for the recommendation builder, PSI-aware variants (#8)."""

from __future__ import annotations

from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.haghs.const import DOMAIN, REC_ALL_CLEAR
from custom_components.haghs.coordinator import (
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
