"""Tests for the application-pillar hard cap (#7)."""

from __future__ import annotations

from datetime import timedelta

from homeassistant.const import STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.haghs.const import DATA_BOOT_TIME, DOMAIN
from custom_components.haghs.coordinator import (
    HaghsDataUpdateCoordinator,
    _RecorderInfo,
)


def _make_zombie(hass: HomeAssistant, entity_id: str, age_minutes: int = 30) -> None:
    """Create a registered zombie: state unavailable past the grace period.

    A registry entry is created when missing so the entity counts as a
    real zombie (unregistered entities are reported separately since #98).
    """
    entity_registry = er.async_get(hass)
    if entity_registry.async_get(entity_id) is None:
        domain, object_id = entity_id.split(".", 1)
        entity_registry.async_get_or_create(
            domain,
            "test_platform",
            f"uid_{entity_id}",
            suggested_object_id=object_id,
        )
    hass.states.async_set(entity_id, STATE_UNAVAILABLE)
    state = hass.states.get(entity_id)
    state.last_changed = dt_util.utcnow() - timedelta(minutes=age_minutes)


def _coordinator_with_recorder_bonus(
    hass: HomeAssistant,
    entry: MockConfigEntry,
    *,
    boot_age_minutes: int = 60,
    bonus_full: bool = True,
) -> HaghsDataUpdateCoordinator:
    """Create a coordinator with a populated recorder_info granting +10 bonus."""
    hass.data.setdefault(DOMAIN, {})[DATA_BOOT_TIME] = dt_util.utcnow() - timedelta(
        minutes=boot_age_minutes
    )
    coordinator = HaghsDataUpdateCoordinator(hass, entry)
    coordinator.recorder_info = _RecorderInfo(
        keep_days=10 if bonus_full else None,
        entity_filter_active=bonus_full,
        available=True,
    )
    return coordinator


async def test_hard_cap_prevents_score_100_when_zombies_present(
    hass: HomeAssistant,
) -> None:
    """A single zombie among many healthy sensors must not yield app_score 100.

    Reproduces #7: a small ratio-based p_zombie (e.g. 7) could previously be
    fully offset by the +10 config bonus, hiding the zombie behind a perfect
    score.
    """
    entry = MockConfigEntry(domain=DOMAIN, data={})
    entry.add_to_hass(hass)

    for i in range(99):
        hass.states.async_set(f"sensor.healthy_{i}", "100")
    _make_zombie(hass, "sensor.lone_zombie", age_minutes=60)

    coordinator = _coordinator_with_recorder_bonus(hass, entry)
    result = await coordinator._async_calc_application()

    assert result.zombie_count == 1
    assert result.config_bonus == 10
    assert result.app_score <= 99


async def test_app_score_100_possible_without_zombies(hass: HomeAssistant) -> None:
    """A healthy instance with full bonus still reaches the perfect score."""
    entry = MockConfigEntry(domain=DOMAIN, data={})
    entry.add_to_hass(hass)

    for i in range(10):
        hass.states.async_set(f"sensor.healthy_{i}", "100")

    coordinator = _coordinator_with_recorder_bonus(hass, entry)
    result = await coordinator._async_calc_application()

    assert result.zombie_count == 0
    assert result.config_bonus == 10
    assert result.app_score == 100


async def test_hard_cap_does_not_inflate_lower_scores(hass: HomeAssistant) -> None:
    """The cap only applies when the natural score would have reached 100."""
    entry = MockConfigEntry(domain=DOMAIN, data={})
    entry.add_to_hass(hass)

    # Many sensors to keep p_zombie small (1 / 50 -> ratio 2 % -> ceil(14) = 14)
    for i in range(49):
        hass.states.async_set(f"sensor.ok_{i}", "100")
    _make_zombie(hass, "sensor.bad", age_minutes=60)
    # Add a stale-backup penalty (+30) so the natural score is well under 99.
    hass.states.async_set("binary_sensor.backups_stale", "on")

    coordinator = _coordinator_with_recorder_bonus(hass, entry)
    result = await coordinator._async_calc_application()

    assert result.zombie_count == 1
    assert result.app_score < 99


async def test_unregistered_entity_does_not_cap_app_score(
    hass: HomeAssistant,
) -> None:
    """Unregistered entities must not reduce the score or trigger the cap (#98).

    Reproduces the community report: a YAML-based entity without a
    registry entry is fully operational and must not be treated as a
    zombie, while remaining visible via the unregistered_* attributes.
    """
    entry = MockConfigEntry(domain=DOMAIN, data={})
    entry.add_to_hass(hass)

    for i in range(10):
        hass.states.async_set(f"sensor.healthy_{i}", "100")

    hass.states.async_set("sensor.yaml_entity", STATE_UNAVAILABLE)
    state = hass.states.get("sensor.yaml_entity")
    state.last_changed = dt_util.utcnow() - timedelta(minutes=60)

    coordinator = _coordinator_with_recorder_bonus(hass, entry)
    result = await coordinator._async_calc_application()

    assert result.zombie_count == 0
    assert result.unregistered_count == 1
    assert result.unregistered_list == ["sensor.yaml_entity"]
    assert result.unregistered_per_domain == {"sensor": 1}
    assert result.app_score == 100
