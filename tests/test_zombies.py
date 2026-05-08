"""Tests for the zombie pillar calculation."""

from __future__ import annotations

from datetime import timedelta

from homeassistant.const import STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.haghs.const import DOMAIN
from custom_components.haghs.coordinator import HaghsDataUpdateCoordinator


def _make_zombie(hass: HomeAssistant, entity_id: str, age_minutes: int = 30) -> None:
    """Set an entity to STATE_UNAVAILABLE with last_changed in the past.

    The grace period in _calc_zombies skips entities changed less than 15
    minutes ago, so age_minutes must exceed 15 for the entity to be counted.
    """
    hass.states.async_set(entity_id, STATE_UNAVAILABLE)
    state = hass.states.get(entity_id)
    state.last_changed = dt_util.utcnow() - timedelta(minutes=age_minutes)


async def test_denominator_uses_zombie_domains_only(hass: HomeAssistant) -> None:
    """Ratio is computed against ZOMBIE_DOMAINS entity count, not total states.

    Pre-fix: 1 zombie / 56 total states ≈ 1.8 % → p_zombie ≈ 13.
    Post-fix: 1 zombie / 6 zombie-domain sensors ≈ 16.7 % → p_zombie capped at 20.
    """
    entry = MockConfigEntry(domain=DOMAIN, data={})
    entry.add_to_hass(hass)

    for i in range(5):
        hass.states.async_set(f"sensor.healthy_{i}", "100")
    _make_zombie(hass, "sensor.zombie_one")
    for i in range(50):
        hass.states.async_set(f"automation.test_{i}", "on")

    coordinator = HaghsDataUpdateCoordinator(hass, entry)
    _zombie_list, p_zombie, zombie_count = coordinator._calc_zombies()

    assert zombie_count == 1
    assert p_zombie == 20


async def test_denominator_zero_when_no_zombie_domain_states(
    hass: HomeAssistant,
) -> None:
    """An instance with no entities in ZOMBIE_DOMAINS yields p_zombie = 0."""
    entry = MockConfigEntry(domain=DOMAIN, data={})
    entry.add_to_hass(hass)

    for i in range(20):
        hass.states.async_set(f"automation.x_{i}", "on")
    for i in range(10):
        hass.states.async_set(f"script.y_{i}", "off")

    coordinator = HaghsDataUpdateCoordinator(hass, entry)
    _zombie_list, p_zombie, zombie_count = coordinator._calc_zombies()

    assert zombie_count == 0
    assert p_zombie == 0


async def test_denominator_ignores_non_zombie_domains(hass: HomeAssistant) -> None:
    """Adding many non-zombie-domain states does not lower the penalty."""
    entry = MockConfigEntry(domain=DOMAIN, data={})
    entry.add_to_hass(hass)

    for i in range(10):
        hass.states.async_set(f"sensor.ok_{i}", "100")
    _make_zombie(hass, "sensor.zombie_one")
    _make_zombie(hass, "sensor.zombie_two")

    coordinator = HaghsDataUpdateCoordinator(hass, entry)
    _zombie_list, p_zombie_baseline, zombie_count = coordinator._calc_zombies()

    assert zombie_count == 2
    # Ratio = 2 / 12 ≈ 16.7 % → ceil(16.7 * 7) = 117 → capped at 20.
    assert p_zombie_baseline == 20

    # Inflate the instance with 200 non-zombie-domain entities.
    for i in range(200):
        hass.states.async_set(f"automation.bulk_{i}", "on")
    _zombie_list, p_zombie_after, _zombie_count = coordinator._calc_zombies()

    assert p_zombie_after == p_zombie_baseline


async def test_grace_period_still_active(hass: HomeAssistant) -> None:
    """Entities unavailable for less than 15 minutes are still ignored."""
    entry = MockConfigEntry(domain=DOMAIN, data={})
    entry.add_to_hass(hass)

    for i in range(5):
        hass.states.async_set(f"sensor.healthy_{i}", "100")
    _make_zombie(hass, "sensor.recent", age_minutes=5)

    coordinator = HaghsDataUpdateCoordinator(hass, entry)
    _zombie_list, p_zombie, zombie_count = coordinator._calc_zombies()

    assert zombie_count == 0
    assert p_zombie == 0
