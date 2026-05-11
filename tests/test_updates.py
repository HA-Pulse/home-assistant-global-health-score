"""Tests for the update-pending pillar, including the 7-day grace (#26)."""

from __future__ import annotations

from datetime import timedelta

from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.haghs.const import (
    DATA_UPDATE_FIRST_SEEN,
    DOMAIN,
    UPDATE_GRACE_DAYS,
)
from custom_components.haghs.coordinator import HaghsDataUpdateCoordinator


def _coordinator(hass: HomeAssistant) -> HaghsDataUpdateCoordinator:
    entry = MockConfigEntry(domain=DOMAIN, data={})
    entry.add_to_hass(hass)
    return HaghsDataUpdateCoordinator(hass, entry)


def _set_first_seen(
    hass: HomeAssistant,
    entity_id: str,
    days_ago: float,
) -> None:
    """Force the recorded first-seen timestamp for an update entity."""
    hass.data.setdefault(DOMAIN, {}).setdefault(DATA_UPDATE_FIRST_SEEN, {})[entity_id] = (
        dt_util.utcnow() - timedelta(days=days_ago)
    )


# ============================================================================
# Grace-period semantics (#26)
# ============================================================================


async def test_freshly_pending_update_does_not_count(hass: HomeAssistant) -> None:
    """A newly-pending update is recorded but does not contribute to penalty.

    Reproduces the request from #26: most users install updates within a
    few days, so the integration should not flag those as a health issue.
    """
    coordinator = _coordinator(hass)
    hass.states.async_set("update.esphome", "on", {"friendly_name": "ESPHome"})

    _p_backup, update_count, p_updates, _p_core_lag, pending = coordinator._calc_updates()

    assert update_count == 0
    assert p_updates == 0
    assert pending == ["ESPHome"]
    assert "update.esphome" in coordinator._update_first_seen


async def test_update_past_grace_counts(hass: HomeAssistant) -> None:
    """An update pending for longer than UPDATE_GRACE_DAYS is counted."""
    coordinator = _coordinator(hass)
    hass.states.async_set("update.esphome", "on", {"friendly_name": "ESPHome"})
    _set_first_seen(hass, "update.esphome", days_ago=UPDATE_GRACE_DAYS + 1)

    _p_backup, update_count, p_updates, _p_core_lag, pending = coordinator._calc_updates()

    assert update_count == 1
    assert p_updates == 5
    assert pending == ["ESPHome"]


async def test_update_within_grace_still_pending_but_uncounted(
    hass: HomeAssistant,
) -> None:
    """6-day-old update still shows in pending_updates but stays uncounted."""
    coordinator = _coordinator(hass)
    hass.states.async_set("update.esphome", "on", {"friendly_name": "ESPHome"})
    _set_first_seen(hass, "update.esphome", days_ago=UPDATE_GRACE_DAYS - 1)

    _p_backup, update_count, _p_updates, _p_core_lag, pending = coordinator._calc_updates()

    assert update_count == 0
    assert pending == ["ESPHome"]


async def test_mixed_ages_only_counts_past_grace(hass: HomeAssistant) -> None:
    """Two old + one fresh update yields update_count == 2."""
    coordinator = _coordinator(hass)
    hass.states.async_set("update.a", "on", {"friendly_name": "A"})
    hass.states.async_set("update.b", "on", {"friendly_name": "B"})
    hass.states.async_set("update.c", "on", {"friendly_name": "C"})
    _set_first_seen(hass, "update.a", days_ago=UPDATE_GRACE_DAYS + 5)
    _set_first_seen(hass, "update.b", days_ago=UPDATE_GRACE_DAYS + 1)
    # update.c gets a fresh timestamp during the run.

    _p_backup, update_count, _p_updates, _p_core_lag, pending = coordinator._calc_updates()

    assert update_count == 2
    assert set(pending) == {"A", "B", "C"}


# ============================================================================
# Pruning + persistence
# ============================================================================


async def test_installed_update_is_pruned_from_tracker(hass: HomeAssistant) -> None:
    """When an update is installed (state != 'on'), its timestamp is dropped."""
    coordinator = _coordinator(hass)
    _set_first_seen(hass, "update.esphome", days_ago=UPDATE_GRACE_DAYS + 1)
    hass.states.async_set("update.esphome", "off")

    coordinator._calc_updates()

    assert "update.esphome" not in coordinator._update_first_seen


async def test_first_seen_dict_survives_coordinator_reload(
    hass: HomeAssistant,
) -> None:
    """A reloaded coordinator picks up the existing first-seen baseline."""
    entry = MockConfigEntry(domain=DOMAIN, data={})
    entry.add_to_hass(hass)

    first = HaghsDataUpdateCoordinator(hass, entry)
    _set_first_seen(hass, "update.esphome", days_ago=UPDATE_GRACE_DAYS + 1)

    second = HaghsDataUpdateCoordinator(hass, entry)
    assert first._update_first_seen is second._update_first_seen
    assert "update.esphome" in second._update_first_seen


# ============================================================================
# Ignore label / pattern integration
# ============================================================================


async def test_ignore_pattern_excludes_update(hass: HomeAssistant) -> None:
    """An update entity matching an ignore pattern is dropped before tracking."""
    from custom_components.haghs.const import CONF_IGNORE_PATTERNS

    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_IGNORE_PATTERNS: ["update.iot_*"]},
    )
    entry.add_to_hass(hass)

    hass.states.async_set("update.iot_bulb", "on", {"friendly_name": "Bulb"})
    hass.states.async_set("update.core", "on", {"friendly_name": "Core"})

    coordinator = HaghsDataUpdateCoordinator(hass, entry)
    _set_first_seen(hass, "update.core", days_ago=UPDATE_GRACE_DAYS + 1)
    coordinator._update_first_seen = hass.data[DOMAIN][DATA_UPDATE_FIRST_SEEN]

    _p_backup, update_count, _p_updates, _p_core_lag, pending = coordinator._calc_updates()

    assert update_count == 1
    assert pending == ["Core"]
    assert "update.iot_bulb" not in coordinator._update_first_seen


# ============================================================================
# Backup pillar sanity (lives in the same function)
# ============================================================================


async def test_stale_backup_yields_30_point_penalty(hass: HomeAssistant) -> None:
    """binary_sensor.backups_stale = 'on' produces p_backup = 30."""
    coordinator = _coordinator(hass)
    hass.states.async_set("binary_sensor.backups_stale", "on")

    p_backup, _update_count, _p_updates, _p_core_lag, _pending = coordinator._calc_updates()

    assert p_backup == 30


async def test_fresh_backup_yields_no_penalty(hass: HomeAssistant) -> None:
    """binary_sensor.backups_stale = 'off' or absent leaves p_backup = 0."""
    coordinator = _coordinator(hass)
    hass.states.async_set("binary_sensor.backups_stale", "off")

    p_backup, *_ = coordinator._calc_updates()

    assert p_backup == 0


async def test_disabled_update_entity_is_excluded(hass: HomeAssistant) -> None:
    """A disabled update entity is excluded from count, pending and tracking.

    Reproduces the community report applied to updates: disabling the
    entity in the registry must be enough to silence the penalty, no
    haghs_ignore label required. Also matches the intent of #70
    (wontfix for a global firmware-update flag) for individual entities.
    """
    from homeassistant.helpers import entity_registry as er

    entity_registry = er.async_get(hass)
    disabled = entity_registry.async_get_or_create(
        "update",
        "device_platform",
        "unique_disabled_update",
        suggested_object_id="device_firmware",
    )
    entity_registry.async_update_entity(
        disabled.entity_id,
        disabled_by=er.RegistryEntryDisabler.USER,
    )
    enabled = entity_registry.async_get_or_create(
        "update",
        "device_platform",
        "unique_enabled_update",
        suggested_object_id="core",
    )

    coordinator = _coordinator(hass)
    hass.states.async_set(disabled.entity_id, "on", {"friendly_name": "Firmware"})
    hass.states.async_set(enabled.entity_id, "on", {"friendly_name": "Core"})
    _set_first_seen(hass, disabled.entity_id, days_ago=UPDATE_GRACE_DAYS + 1)
    _set_first_seen(hass, enabled.entity_id, days_ago=UPDATE_GRACE_DAYS + 1)

    _p_backup, update_count, _p_updates, _p_core_lag, pending = coordinator._calc_updates()

    assert update_count == 1
    assert pending == ["Core"]
    assert disabled.entity_id not in coordinator._update_first_seen
