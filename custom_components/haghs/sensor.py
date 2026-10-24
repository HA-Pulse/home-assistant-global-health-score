"""HAGHS Sensor — CoordinatorEntity backed by HaghsDataUpdateCoordinator."""

from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DEFAULT_NAME, DOMAIN, REC_FLAG_KEYS
from .coordinator import HaghsDataUpdateCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up HAGHS sensor from a config entry."""
    coordinator: HaghsDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([HaghsSensor(coordinator, entry)])


class HaghsSensor(CoordinatorEntity[HaghsDataUpdateCoordinator], SensorEntity):
    """Representation of the HAGHS Sensor."""

    # Capped lists and per-entity maps stay out of recorder history: together they can exceed
    # the recorder's 16 KB attribute limit, and HA then stores no attributes at all. Their counts
    # and breakdowns stay recorded; the current values stay in the state.
    _unrecorded_attributes = frozenset(
        {
            "stale_candidates",
            "stale_watch_entities",
            "zombie_since",
            "zombie_reasons",
            "zombie_entities",
            "unregistered_entities",
            "dead_devices",
            "repairs",
            "pending_updates",
            "integration_unhealthy_entries",
        }
    )

    def __init__(
        self,
        coordinator: HaghsDataUpdateCoordinator,
        entry: ConfigEntry,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._attr_name = DEFAULT_NAME
        self._attr_unique_id = f"{entry.entry_id}_score"
        self._attr_icon = "mdi:shield-check"
        self._attr_native_unit_of_measurement = "%"

    @property
    def native_value(self) -> int | None:
        """Return the current health score."""
        if self.coordinator.data is None:
            return None
        return self.coordinator.data["global_score"]

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return detailed score breakdown as attributes."""
        if self.coordinator.data is None:
            return None
        data = self.coordinator.data
        return {
            "hardware_score": data["hardware_score"],
            "application_score": data["application_score"],
            "stale_candidate_count": data["stale_candidate_count"],
            "stale_candidates": data["stale_candidates"],
            "stale_watch_count": data["stale_watch_count"],
            "stale_watch_entities": data["stale_watch_entities"],
            "stale_penalty": data["stale_penalty"],
            "stale_threshold_hours": data["stale_threshold_hours"],
            "zombie_count": data["zombie_count"],
            "zombie_entities": data["zombie_entities"],
            "zombie_count_per_domain": data["zombie_count_per_domain"],
            "zombie_count_per_integration": data["zombie_count_per_integration"],
            "zombie_since": data["zombie_since"],
            "zombie_count_per_reason": data["zombie_count_per_reason"],
            "zombie_reasons": data["zombie_reasons"],
            "unregistered_count": data["unregistered_count"],
            "unregistered_entities": data["unregistered_entities"],
            "unregistered_count_per_domain": data["unregistered_count_per_domain"],
            "dead_device_count": data["dead_device_count"],
            "dead_devices": data["dead_devices"],
            "db_size_mb": data["db_size_mb"],
            "psi_available": data["psi_available"],
            "recorder_keep_days": data["recorder_keep_days"],
            "recorder_filter_active": data["recorder_filter_active"],
            "integration_unhealthy_count": data["integration_unhealthy_count"],
            "integration_unhealthy_entries": data["integration_unhealthy_entries"],
            "config_audit_bonus": data["config_audit_bonus"],
            "repair_count": data["repair_count"],
            "repairs": data["repairs"],
            "pending_updates": data["pending_updates"],
            "recommendations": data["recommendations"],
            "pillar_fallback_count": data["pillar_fallback_count"],
            "pillar_fallbacks": data["pillar_fallbacks"],
            "update_cycle_failed": data["update_cycle_failed"],
            **{k: data[k] for k in REC_FLAG_KEYS},
        }
