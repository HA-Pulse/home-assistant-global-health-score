"""Pilot golden tests for the power-supply pillar (#54 phase 3).

Picked as the simplest pillar in HAGHS: a single binary state (`on` or
`off`) translates into a flat 20-point penalty applied after the
hardware-pillar averaging. These tests establish the input/output
pattern that future per-pillar suites should follow.
"""

from __future__ import annotations

from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.haghs.const import DOMAIN, REC_POWER_UNSTABLE
from custom_components.haghs.coordinator import (
    HaghsDataUpdateCoordinator,
    _ApplicationResult,
)

POWER_ENTITY = "binary_sensor.rpi_power_status"


def _coordinator(hass: HomeAssistant) -> HaghsDataUpdateCoordinator:
    entry = MockConfigEntry(domain=DOMAIN, data={})
    entry.add_to_hass(hass)
    return HaghsDataUpdateCoordinator(hass, entry)


# ============================================================================
# Penalty calculation (_async_calc_hardware -> _HardwareResult.p_power)
# ============================================================================


async def test_p_power_zero_when_sensor_absent(hass: HomeAssistant) -> None:
    """No rpi_power_status entity at all yields p_power = 0.

    Most non-RPi hardware never creates this entity, so the check must
    be invisible to those users.
    """
    coordinator = _coordinator(hass)
    result = await coordinator._async_calc_hardware()
    assert result.p_power == 0


async def test_p_power_twenty_when_problem_reported(hass: HomeAssistant) -> None:
    """rpi_power_status 'on' indicates under-voltage; p_power = 20."""
    hass.states.async_set(POWER_ENTITY, "on")
    coordinator = _coordinator(hass)
    result = await coordinator._async_calc_hardware()
    assert result.p_power == 20


async def test_p_power_zero_when_status_ok(hass: HomeAssistant) -> None:
    """rpi_power_status 'off' indicates normal supply; p_power = 0."""
    hass.states.async_set(POWER_ENTITY, "off")
    coordinator = _coordinator(hass)
    result = await coordinator._async_calc_hardware()
    assert result.p_power == 0


async def test_p_power_zero_when_sensor_unavailable(hass: HomeAssistant) -> None:
    """rpi_power_status 'unavailable' is treated as no penalty."""
    hass.states.async_set(POWER_ENTITY, "unavailable")
    coordinator = _coordinator(hass)
    result = await coordinator._async_calc_hardware()
    assert result.p_power == 0


async def test_p_power_zero_when_sensor_unknown(hass: HomeAssistant) -> None:
    """rpi_power_status 'unknown' is treated as no penalty."""
    hass.states.async_set(POWER_ENTITY, "unknown")
    coordinator = _coordinator(hass)
    result = await coordinator._async_calc_hardware()
    assert result.p_power == 0


# ============================================================================
# Hardware-score integration
# ============================================================================


async def test_hardware_score_drops_when_power_unstable(hass: HomeAssistant) -> None:
    """Hardware score loses 20 points when the power penalty is active.

    Invariant: hardware_score = clamp(average - p_power, 0, 100). With
    p_power = 20 the score is therefore at most 80, regardless of which
    other pillars contribute.
    """
    hass.states.async_set(POWER_ENTITY, "on")
    coordinator = _coordinator(hass)
    result = await coordinator._async_calc_hardware()
    assert result.p_power == 20
    assert result.hardware_score <= 80


# ============================================================================
# Recommendation surface (_build_recommendations + _build_rec_flags)
# ============================================================================


async def test_advice_contains_power_message_when_unstable(
    hass: HomeAssistant,
) -> None:
    """REC_POWER_UNSTABLE appears in the advice list when p_power > 0."""
    hass.states.async_set(POWER_ENTITY, "on")
    coordinator = _coordinator(hass)
    hw = await coordinator._async_calc_hardware()
    advice = coordinator._build_recommendations(hw, _ApplicationResult())
    assert REC_POWER_UNSTABLE in advice


async def test_rec_power_unstable_flag_true_when_unstable(
    hass: HomeAssistant,
) -> None:
    """The rec_power_unstable boolean mirrors the recommendation."""
    hass.states.async_set(POWER_ENTITY, "on")
    coordinator = _coordinator(hass)
    hw = await coordinator._async_calc_hardware()
    flags = coordinator._build_rec_flags(hw, _ApplicationResult())
    assert flags["rec_power_unstable"] is True


async def test_rec_power_unstable_flag_false_when_status_ok(
    hass: HomeAssistant,
) -> None:
    """The rec_power_unstable boolean is False when no penalty is active."""
    hass.states.async_set(POWER_ENTITY, "off")
    coordinator = _coordinator(hass)
    hw = await coordinator._async_calc_hardware()
    flags = coordinator._build_rec_flags(hw, _ApplicationResult())
    assert flags["rec_power_unstable"] is False
