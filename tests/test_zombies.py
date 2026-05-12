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
    CONF_IGNORE_LABELS,
    CONF_IGNORE_PATTERNS,
    DATA_BOOT_TIME,
    DOMAIN,
)
from custom_components.haghs.coordinator import (
    HaghsDataUpdateCoordinator,
    _compile_patterns,
)


def _make_zombie(
    hass: HomeAssistant,
    entity_id: str,
    age_minutes: int = 30,
    *,
    device_class: str | None = None,
) -> None:
    """Set an entity to STATE_UNAVAILABLE with last_changed in the past.

    The grace period in _calc_zombies skips entities changed less than 15
    minutes ago (60 minutes for device_class=battery), so age_minutes must
    exceed the relevant window for the entity to be counted.
    """
    attrs = {"device_class": device_class} if device_class is not None else {}
    hass.states.async_set(entity_id, STATE_UNAVAILABLE, attrs)
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
    _zombie_list, p_zombie, zombie_count, _per_domain = coordinator._calc_zombies()

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
    _zombie_list, p_zombie, zombie_count, _per_domain = coordinator._calc_zombies()

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
    _zombie_list, p_zombie_baseline, zombie_count, _per_domain = coordinator._calc_zombies()

    assert zombie_count == 2
    # Ratio = 2 / 12 ≈ 16.7 % → ceil(16.7 * 7) = 117 → capped at 20.
    assert p_zombie_baseline == 20

    # Inflate the instance with 200 non-zombie-domain entities.
    for i in range(200):
        hass.states.async_set(f"automation.bulk_{i}", "on")
    _zombie_list, p_zombie_after, _zombie_count, _per_domain = coordinator._calc_zombies()

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
    _zombie_list, p_zombie, zombie_count, _per_domain = coordinator._calc_zombies()

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
    _zombie_list, p_zombie, zombie_count, _per_domain = coordinator._calc_zombies()

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
    _zombie_list, p_zombie, zombie_count, _per_domain = coordinator._calc_zombies()

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
    _zombie_list, p_zombie, zombie_count, _per_domain = coordinator._calc_zombies()

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
    _zombie_list, p_zombie, zombie_count, _per_domain = coordinator._calc_zombies()

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

    _zombie_list, _p, count_pre, _per_domain = coordinator._calc_zombies()
    assert count_pre == 0

    hass.set_state(CoreState.running)
    hass.bus.async_fire(EVENT_HOMEASSISTANT_STARTED)
    await hass.async_block_till_done()

    assert coordinator._registries_ready is True
    _zombie_list, p_zombie, zombie_count, _per_domain = coordinator._calc_zombies()
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
    zombie_list, _p, zombie_count, _per_domain = coordinator._calc_zombies()

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
    zombie_list, _p, zombie_count, _per_domain = coordinator._calc_zombies()

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
# Pattern-based ignore (#64)
# ============================================================================


def test_compile_patterns_returns_empty_for_none_or_empty() -> None:
    """An absent or empty pattern list compiles to an empty list."""
    assert _compile_patterns(None) == []
    assert _compile_patterns([]) == []
    assert _compile_patterns([""]) == []


def test_compile_patterns_translates_glob() -> None:
    """Valid glob patterns compile to regex objects that match entity ids."""
    compiled = _compile_patterns(["sensor.docker_*", "binary_sensor.test_?"])
    assert len(compiled) == 2
    assert compiled[0].match("sensor.docker_cpu")
    assert compiled[0].match("sensor.docker_mem")
    assert not compiled[0].match("sensor.other_cpu")
    assert compiled[1].match("binary_sensor.test_1")
    assert not compiled[1].match("binary_sensor.test_12")


def test_compile_patterns_skips_invalid_with_warning(caplog) -> None:
    """An invalid pattern is logged but does not break the rest."""
    with caplog.at_level("WARNING"):
        compiled = _compile_patterns(["sensor.[unclosed", "sensor.ok_*"])

    assert len(compiled) == 1
    assert compiled[0].match("sensor.ok_one")
    assert "Invalid ignore pattern" in caplog.text


async def test_pattern_match_excludes_zombie(hass: HomeAssistant) -> None:
    """An entity matching a configured glob is not counted as a zombie."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_IGNORE_PATTERNS: ["sensor.docker_*"]},
    )
    entry.add_to_hass(hass)

    _make_zombie(hass, "sensor.docker_cpu", age_minutes=60)
    _make_zombie(hass, "sensor.docker_mem", age_minutes=60)
    _make_zombie(hass, "sensor.other", age_minutes=60)

    coordinator = _coordinator_with_boot_age(hass, entry)
    zombie_list, _p, zombie_count, _per_domain = coordinator._calc_zombies()

    assert zombie_count == 1
    assert zombie_list == [f"{ATTR_UNREGISTERED_PREFIX}sensor.other"]


async def test_pattern_match_excludes_registered_entity(hass: HomeAssistant) -> None:
    """Patterns also work for registered entities (no label needed)."""
    entity_registry = er.async_get(hass)
    entity_registry.async_get_or_create(
        "sensor", "docker_platform", "unique_1", suggested_object_id="docker_cpu"
    )

    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_IGNORE_PATTERNS: ["sensor.docker_*"]},
    )
    entry.add_to_hass(hass)

    _make_zombie(hass, "sensor.docker_cpu", age_minutes=60)

    coordinator = _coordinator_with_boot_age(hass, entry)
    _zombie_list, _p, zombie_count, _per_domain = coordinator._calc_zombies()

    assert zombie_count == 0


async def test_label_and_pattern_combined(hass: HomeAssistant) -> None:
    """Label + pattern are evaluated together; either match excludes."""
    entity_registry = er.async_get(hass)
    label_entry = entity_registry.async_get_or_create(
        "sensor", "p", "labelled", suggested_object_id="labelled"
    )
    entity_registry.async_update_entity(label_entry.entity_id, labels={"haghs_ignore"})

    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_IGNORE_LABELS: ["haghs_ignore"],
            CONF_IGNORE_PATTERNS: ["sensor.torque_*"],
        },
    )
    entry.add_to_hass(hass)

    _make_zombie(hass, "sensor.labelled", age_minutes=60)
    _make_zombie(hass, "sensor.torque_speed", age_minutes=60)
    _make_zombie(hass, "sensor.real", age_minutes=60)

    coordinator = _coordinator_with_boot_age(hass, entry)
    zombie_list, _p, zombie_count, _per_domain = coordinator._calc_zombies()

    assert zombie_count == 1
    assert zombie_list == [f"{ATTR_UNREGISTERED_PREFIX}sensor.real"]


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


# ============================================================================
# Battery grace (#62)
# ============================================================================


async def test_battery_zombie_within_60min_window_skipped(
    hass: HomeAssistant,
) -> None:
    """A battery-class sensor unavailable for 30 min is still inside its grace.

    Reproduces #62: Zigbee/Homematic battery devices often re-poll on a
    multi-minute cycle, so the standard 15 min window flagged them as zombies.
    """
    entry = MockConfigEntry(domain=DOMAIN, data={})
    entry.add_to_hass(hass)

    _make_zombie(hass, "sensor.battery_30m", age_minutes=30, device_class="battery")

    coordinator = _coordinator_with_boot_age(hass, entry)
    _zombie_list, p_zombie, zombie_count, _per_domain = coordinator._calc_zombies()

    assert zombie_count == 0
    assert p_zombie == 0


async def test_battery_zombie_after_60min_window_counted(
    hass: HomeAssistant,
) -> None:
    """After the extended battery window expires, the entity is flagged."""
    entry = MockConfigEntry(domain=DOMAIN, data={})
    entry.add_to_hass(hass)

    _make_zombie(hass, "sensor.battery_61m", age_minutes=61, device_class="battery")

    coordinator = _coordinator_with_boot_age(hass, entry)
    _zombie_list, p_zombie, zombie_count, _per_domain = coordinator._calc_zombies()

    assert zombie_count == 1
    assert p_zombie > 0


async def test_non_battery_zombie_still_uses_15min_window(
    hass: HomeAssistant,
) -> None:
    """The extended window applies only to device_class=battery."""
    entry = MockConfigEntry(domain=DOMAIN, data={})
    entry.add_to_hass(hass)

    _make_zombie(hass, "sensor.temp_30m", age_minutes=30, device_class="temperature")

    coordinator = _coordinator_with_boot_age(hass, entry)
    _zombie_list, p_zombie, zombie_count, _per_domain = coordinator._calc_zombies()

    assert zombie_count == 1
    assert p_zombie > 0


# ============================================================================
# Disabled entity exclusion (community feedback)
# ============================================================================


async def test_disabled_entity_is_not_a_zombie(hass: HomeAssistant) -> None:
    """An entity disabled via the registry is excluded without needing a label.

    Reproduces the community report: disabling an entity in
    'Settings > Devices & Services' should be enough; users should not
    have to also add the haghs_ignore label.
    """
    entity_registry = er.async_get(hass)
    entry_obj = entity_registry.async_get_or_create(
        "sensor",
        "test_platform",
        "unique_disabled",
        suggested_object_id="disabled_sensor",
    )
    entity_registry.async_update_entity(
        entry_obj.entity_id,
        disabled_by=er.RegistryEntryDisabler.USER,
    )

    entry = MockConfigEntry(domain=DOMAIN, data={})
    entry.add_to_hass(hass)

    _make_zombie(hass, entry_obj.entity_id, age_minutes=60)

    coordinator = _coordinator_with_boot_age(hass, entry)
    _zombie_list, p_zombie, zombie_count, _per_domain = coordinator._calc_zombies()

    assert zombie_count == 0
    assert p_zombie == 0


async def test_hidden_entity_is_still_tracked(hass: HomeAssistant) -> None:
    """hidden_by is intentionally NOT an ignore signal — only disabled_by is."""
    entity_registry = er.async_get(hass)
    entry_obj = entity_registry.async_get_or_create(
        "sensor",
        "test_platform",
        "unique_hidden",
        suggested_object_id="hidden_sensor",
    )
    entity_registry.async_update_entity(
        entry_obj.entity_id,
        hidden_by=er.RegistryEntryHider.USER,
    )

    entry = MockConfigEntry(domain=DOMAIN, data={})
    entry.add_to_hass(hass)

    _make_zombie(hass, entry_obj.entity_id, age_minutes=60)

    coordinator = _coordinator_with_boot_age(hass, entry)
    _zombie_list, _p_zombie, zombie_count, _per_domain = coordinator._calc_zombies()

    assert zombie_count == 1


# ============================================================================
# Multi-label support (Phase A)
# ============================================================================


async def test_multiple_ignore_labels_match_any(hass: HomeAssistant) -> None:
    """An entity carrying any of the configured ignore labels is excluded."""
    entity_registry = er.async_get(hass)
    labelled_a = entity_registry.async_get_or_create(
        "sensor", "p", "ml_a", suggested_object_id="ml_a"
    )
    entity_registry.async_update_entity(labelled_a.entity_id, labels={"haghs_ignore"})
    labelled_b = entity_registry.async_get_or_create(
        "sensor", "p", "ml_b", suggested_object_id="ml_b"
    )
    entity_registry.async_update_entity(labelled_b.entity_id, labels={"vacation"})

    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_IGNORE_LABELS: ["haghs_ignore", "vacation"]},
    )
    entry.add_to_hass(hass)

    _make_zombie(hass, labelled_a.entity_id, age_minutes=60)
    _make_zombie(hass, labelled_b.entity_id, age_minutes=60)
    _make_zombie(hass, "sensor.real", age_minutes=60)

    coordinator = _coordinator_with_boot_age(hass, entry)
    zombie_list, _p, zombie_count, _per_domain = coordinator._calc_zombies()

    assert zombie_count == 1
    assert zombie_list == [f"{ATTR_UNREGISTERED_PREFIX}sensor.real"]


async def test_empty_ignore_labels_list_acts_as_no_label(
    hass: HomeAssistant,
) -> None:
    """An empty ignore_labels list does not exclude anything."""
    entity_registry = er.async_get(hass)
    labelled = entity_registry.async_get_or_create(
        "sensor", "p", "ml_empty", suggested_object_id="labelled"
    )
    entity_registry.async_update_entity(labelled.entity_id, labels={"haghs_ignore"})

    entry = MockConfigEntry(domain=DOMAIN, data={CONF_IGNORE_LABELS: []})
    entry.add_to_hass(hass)

    _make_zombie(hass, labelled.entity_id, age_minutes=60)

    coordinator = _coordinator_with_boot_age(hass, entry)
    _zombie_list, _p, zombie_count, _per_domain = coordinator._calc_zombies()

    assert zombie_count == 1


# ============================================================================
# Domain coverage + per-domain breakdown + cap (Z2M expansion)
# ============================================================================


async def test_newly_included_domains_are_detected(hass: HomeAssistant) -> None:
    """Entities in domains added during the Z2M expansion become zombies."""
    entry = MockConfigEntry(domain=DOMAIN, data={})
    entry.add_to_hass(hass)

    _make_zombie(hass, "cover.living_room_blinds", age_minutes=30)
    _make_zombie(hass, "lock.front_door", age_minutes=30)
    _make_zombie(hass, "select.fan_mode", age_minutes=30)
    _make_zombie(hass, "number.target_temperature", age_minutes=30)
    _make_zombie(hass, "valve.garden_irrigation", age_minutes=30)
    _make_zombie(hass, "humidifier.bedroom", age_minutes=30)
    _make_zombie(hass, "siren.alarm", age_minutes=30)

    coordinator = _coordinator_with_boot_age(hass, entry)
    _zombie_list, _p, zombie_count, per_domain = coordinator._calc_zombies()

    assert zombie_count == 7
    assert per_domain == {
        "cover": 1,
        "lock": 1,
        "select": 1,
        "number": 1,
        "valve": 1,
        "humidifier": 1,
        "siren": 1,
    }


async def test_button_unknown_state_is_never_a_zombie(hass: HomeAssistant) -> None:
    """Buttons default to state=unknown and must not be flagged as zombies.

    Regression guard: if someone re-adds `button` to ZOMBIE_DOMAINS, every
    freshly-installed Zigbee/MQTT button would become a false positive.
    """
    entry = MockConfigEntry(domain=DOMAIN, data={})
    entry.add_to_hass(hass)

    _make_zombie(hass, "button.unpressed_zigbee_button", age_minutes=60)

    coordinator = _coordinator_with_boot_age(hass, entry)
    _zombie_list, p_zombie, zombie_count, per_domain = coordinator._calc_zombies()

    assert zombie_count == 0
    assert p_zombie == 0
    assert per_domain == {}


async def test_zombie_list_capped_but_count_and_per_domain_are_full(
    hass: HomeAssistant,
) -> None:
    """zombie_entities is capped at ZOMBIE_LIST_CAP; count + per_domain are not."""
    from custom_components.haghs.const import ZOMBIE_LIST_CAP

    entry = MockConfigEntry(domain=DOMAIN, data={})
    entry.add_to_hass(hass)

    for i in range(ZOMBIE_LIST_CAP + 25):
        _make_zombie(hass, f"sensor.bulk_{i}", age_minutes=30)

    coordinator = _coordinator_with_boot_age(hass, entry)
    zombie_list, _p, zombie_count, per_domain = coordinator._calc_zombies()

    assert len(zombie_list) == ZOMBIE_LIST_CAP
    assert zombie_count == ZOMBIE_LIST_CAP + 25
    assert per_domain == {"sensor": ZOMBIE_LIST_CAP + 25}


async def test_per_domain_only_counts_actual_zombies(hass: HomeAssistant) -> None:
    """Healthy entities and entities still inside the grace window do not count."""
    entry = MockConfigEntry(domain=DOMAIN, data={})
    entry.add_to_hass(hass)

    for i in range(3):
        hass.states.async_set(f"cover.healthy_{i}", "open")
    _make_zombie(hass, "cover.recent", age_minutes=5)
    _make_zombie(hass, "cover.gone", age_minutes=30)
    _make_zombie(hass, "lock.also_gone", age_minutes=30)

    coordinator = _coordinator_with_boot_age(hass, entry)
    _zombie_list, _p, zombie_count, per_domain = coordinator._calc_zombies()

    assert zombie_count == 2
    assert per_domain == {"cover": 1, "lock": 1}
