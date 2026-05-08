"""Tests for the zombie pillar calculation."""

from __future__ import annotations

from datetime import timedelta

from homeassistant.const import EVENT_HOMEASSISTANT_STARTED, STATE_UNAVAILABLE
from homeassistant.core import CoreState, HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.haghs.const import (
    ATTR_UNREGISTERED_PREFIX,
    DATA_BOOT_TIME,
    DOMAIN,
)
from custom_components.haghs.coordinator import HaghsDataUpdateCoordinator


def _make_zombie(hass: HomeAssistant, entity_id: str, age_minutes: int = 30) -> None:
    """Set an entity to STATE_UNAVAILABLE with last_changed in the past.

    The grace period in _calc_zombies skips entities changed less than 15
    minutes ago, so age_minutes must exceed 15 for the entity to be counted.
    """
    hass.states.async_set(entity_id, STATE_UNAVAILABLE)
    state = hass.states.get(entity_id)
    state.last_changed = dt_util.utcnow() - timedelta(minutes=age_minutes)


def _coordinator_with_boot_age(
    hass: HomeAssistant,
    entry: MockConfigEntry,
    boot_age_minutes: int = 60,
) -> HaghsDataUpdateCoordinator:
    """Create a coordinator with a boot-time baseline N minutes in the past.

    By default we simulate "HA booted an hour ago" so any state with
    last_changed in the last hour is treated as post-boot and the natural
    15-minute grace period applies.
    """
    hass.data.setdefault(DOMAIN, {})[DATA_BOOT_TIME] = dt_util.utcnow() - timedelta(
        minutes=boot_age_minutes
    )
    return HaghsDataUpdateCoordinator(hass, entry)


# ============================================================================
# Denominator semantics (#9)
# ============================================================================


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

    coordinator = _coordinator_with_boot_age(hass, entry)
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

    coordinator = _coordinator_with_boot_age(hass, entry)
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

    coordinator = _coordinator_with_boot_age(hass, entry)
    _zombie_list, p_zombie_baseline, zombie_count = coordinator._calc_zombies()

    assert zombie_count == 2
    # Ratio = 2 / 12 ≈ 16.7 % → ceil(16.7 * 7) = 117 → capped at 20.
    assert p_zombie_baseline == 20

    # Inflate the instance with 200 non-zombie-domain entities.
    for i in range(200):
        hass.states.async_set(f"automation.bulk_{i}", "on")
    _zombie_list, p_zombie_after, _zombie_count = coordinator._calc_zombies()

    assert p_zombie_after == p_zombie_baseline


# ============================================================================
# Grace periods (#10 + existing 15-minute window)
# ============================================================================


async def test_grace_period_still_active(hass: HomeAssistant) -> None:
    """Entities unavailable for less than 15 minutes are still ignored."""
    entry = MockConfigEntry(domain=DOMAIN, data={})
    entry.add_to_hass(hass)

    for i in range(5):
        hass.states.async_set(f"sensor.healthy_{i}", "100")
    _make_zombie(hass, "sensor.recent", age_minutes=5)

    coordinator = _coordinator_with_boot_age(hass, entry)
    _zombie_list, p_zombie, zombie_count = coordinator._calc_zombies()

    assert zombie_count == 0
    assert p_zombie == 0


async def test_restart_grace_skips_recently_restored_state(
    hass: HomeAssistant,
) -> None:
    """A 2-hour-old last_changed is ignored within 15 min of HA boot.

    Reproduces #10: after a restart, last_changed is restored from the
    recorder and predates the boot. Without this fix the entity would be
    flagged as a zombie immediately.
    """
    entry = MockConfigEntry(domain=DOMAIN, data={})
    entry.add_to_hass(hass)

    for i in range(5):
        hass.states.async_set(f"sensor.healthy_{i}", "100")
    _make_zombie(hass, "sensor.restored", age_minutes=120)

    coordinator = _coordinator_with_boot_age(hass, entry, boot_age_minutes=5)
    _zombie_list, p_zombie, zombie_count = coordinator._calc_zombies()

    assert zombie_count == 0
    assert p_zombie == 0


async def test_restart_grace_releases_after_15_minutes(hass: HomeAssistant) -> None:
    """After 15 min post-boot, restored zombies are flagged again."""
    entry = MockConfigEntry(domain=DOMAIN, data={})
    entry.add_to_hass(hass)

    for i in range(5):
        hass.states.async_set(f"sensor.healthy_{i}", "100")
    _make_zombie(hass, "sensor.restored", age_minutes=120)

    coordinator = _coordinator_with_boot_age(hass, entry, boot_age_minutes=30)
    _zombie_list, p_zombie, zombie_count = coordinator._calc_zombies()

    assert zombie_count == 1
    assert p_zombie > 0


async def test_post_boot_grace_uses_last_changed(hass: HomeAssistant) -> None:
    """For entities that went unavailable after boot, last_changed wins."""
    entry = MockConfigEntry(domain=DOMAIN, data={})
    entry.add_to_hass(hass)

    for i in range(5):
        hass.states.async_set(f"sensor.healthy_{i}", "100")
    # HA booted 60 min ago, sensor went unavailable 5 min ago. Effective
    # baseline is the (newer) last_changed, so the standard grace applies.
    _make_zombie(hass, "sensor.recent_after_boot", age_minutes=5)

    coordinator = _coordinator_with_boot_age(hass, entry, boot_age_minutes=60)
    _zombie_list, p_zombie, zombie_count = coordinator._calc_zombies()

    assert zombie_count == 0
    assert p_zombie == 0


# ============================================================================
# Registry-race fix (#13)
# ============================================================================


async def test_zombies_skipped_during_startup(hass: HomeAssistant) -> None:
    """During HA startup, zombie detection returns empty even with matches."""
    entry = MockConfigEntry(domain=DOMAIN, data={})
    entry.add_to_hass(hass)

    for i in range(3):
        hass.states.async_set(f"sensor.healthy_{i}", "100")
    _make_zombie(hass, "sensor.battery", age_minutes=60)

    hass.set_state(CoreState.starting)
    coordinator = _coordinator_with_boot_age(hass, entry)
    _zombie_list, p_zombie, zombie_count = coordinator._calc_zombies()

    assert zombie_count == 0
    assert p_zombie == 0
    assert coordinator._registries_ready is False


async def test_zombies_detected_after_started_event(hass: HomeAssistant) -> None:
    """After EVENT_HOMEASSISTANT_STARTED fires, zombie detection resumes."""
    entry = MockConfigEntry(domain=DOMAIN, data={})
    entry.add_to_hass(hass)

    for i in range(3):
        hass.states.async_set(f"sensor.healthy_{i}", "100")
    _make_zombie(hass, "sensor.battery", age_minutes=60)

    hass.set_state(CoreState.starting)
    coordinator = _coordinator_with_boot_age(hass, entry)

    _zombie_list, _p, count_pre = coordinator._calc_zombies()
    assert count_pre == 0

    hass.set_state(CoreState.running)
    hass.bus.async_fire(EVENT_HOMEASSISTANT_STARTED)
    await hass.async_block_till_done()

    assert coordinator._registries_ready is True
    _zombie_list, p_zombie, zombie_count = coordinator._calc_zombies()
    assert zombie_count == 1
    assert p_zombie > 0


async def test_registries_ready_immediately_when_already_running(
    hass: HomeAssistant,
) -> None:
    """If HA is already running at coordinator init, no listener is needed."""
    entry = MockConfigEntry(domain=DOMAIN, data={})
    entry.add_to_hass(hass)

    # The hass fixture is in CoreState.running by default.
    coordinator = _coordinator_with_boot_age(hass, entry)

    assert coordinator._registries_ready is True


# ============================================================================
# Ghost marker (#6)
# ============================================================================


async def test_unregistered_zombie_gets_prefix(hass: HomeAssistant) -> None:
    """Zombies without an entity-registry entry are tagged in the list."""
    entry = MockConfigEntry(domain=DOMAIN, data={})
    entry.add_to_hass(hass)

    _make_zombie(hass, "sensor.ghost", age_minutes=60)

    coordinator = _coordinator_with_boot_age(hass, entry)
    zombie_list, _p, zombie_count = coordinator._calc_zombies()

    assert zombie_count == 1
    assert zombie_list == [f"{ATTR_UNREGISTERED_PREFIX}sensor.ghost"]


async def test_registered_zombie_has_no_prefix(hass: HomeAssistant) -> None:
    """Zombies that have an entity-registry entry keep their plain id."""
    entity_registry = er.async_get(hass)
    entity_registry.async_get_or_create(
        "sensor",
        "test_platform",
        "unique_id_1",
        suggested_object_id="real",
    )

    entry = MockConfigEntry(domain=DOMAIN, data={})
    entry.add_to_hass(hass)

    _make_zombie(hass, "sensor.real", age_minutes=60)

    coordinator = _coordinator_with_boot_age(hass, entry)
    zombie_list, _p, zombie_count = coordinator._calc_zombies()

    assert zombie_count == 1
    assert zombie_list == ["sensor.real"]


async def test_ghost_warning_logged_once_per_entity(hass: HomeAssistant, caplog) -> None:
    """The 'unregistered zombie' warning is emitted at most once per id."""
    entry = MockConfigEntry(domain=DOMAIN, data={})
    entry.add_to_hass(hass)

    _make_zombie(hass, "sensor.ghost_one", age_minutes=60)

    coordinator = _coordinator_with_boot_age(hass, entry)

    with caplog.at_level("WARNING"):
        coordinator._calc_zombies()
        coordinator._calc_zombies()
        coordinator._calc_zombies()

    occurrences = caplog.text.count("Detected unregistered zombie entity")
    assert occurrences == 1


async def test_ghost_warning_logged_per_distinct_entity(hass: HomeAssistant, caplog) -> None:
    """Distinct ghost entities each produce one warning."""
    entry = MockConfigEntry(domain=DOMAIN, data={})
    entry.add_to_hass(hass)

    _make_zombie(hass, "sensor.ghost_a", age_minutes=60)
    _make_zombie(hass, "sensor.ghost_b", age_minutes=60)

    coordinator = _coordinator_with_boot_age(hass, entry)

    with caplog.at_level("WARNING"):
        coordinator._calc_zombies()

    assert "sensor.ghost_a" in caplog.text
    assert "sensor.ghost_b" in caplog.text


# ============================================================================
# hass.data persistence
# ============================================================================


async def test_boot_time_persists_across_coordinator_reloads(
    hass: HomeAssistant,
) -> None:
    """Reloading the integration must not reset the boot-time baseline."""
    entry = MockConfigEntry(domain=DOMAIN, data={})
    entry.add_to_hass(hass)

    first = HaghsDataUpdateCoordinator(hass, entry)
    second = HaghsDataUpdateCoordinator(hass, entry)

    assert first._boot_time == second._boot_time
    assert hass.data[DOMAIN][DATA_BOOT_TIME] == first._boot_time
