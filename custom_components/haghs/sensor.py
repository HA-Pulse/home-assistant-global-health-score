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
            "zombie_count": data["zombie_count"],
            "zombie_entities": data["zombie_entities"],
            "zombie_count_per_domain": data["zombie_count_per_domain"],
            "db_size_mb": data["db_size_mb"],
            "psi_available": data["psi_available"],
            "recorder_keep_days": data["recorder_keep_days"],
            "recorder_filter_active": data["recorder_filter_active"],
            "pending_updates": data["pending_updates"],
            "recommendations": data["recommendations"],
            **{k: data[k] for k in REC_FLAG_KEYS},
        }
