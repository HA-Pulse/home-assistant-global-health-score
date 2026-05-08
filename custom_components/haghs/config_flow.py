"""Config flow and options flow for HAGHS integration."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import UnitOfTime
from homeassistant.helpers import selector

from .const import (
    CONF_CPU_SENSOR,
    CONF_DB_SENSOR,
    CONF_IGNORE_LABEL,
    CONF_RAM_SENSOR,
    CONF_STORAGE_TYPE,
    CONF_UPDATE_INTERVAL,
    DEFAULT_STORAGE_TYPE,
    DEFAULT_UPDATE_INTERVAL,
    DOMAIN,
    STORAGE_TYPES,
    VersionInformation,
)
from .coordinator import HaghsDataUpdateCoordinator


def _schema_with_psi(psi_available: bool) -> vol.Schema:
    """Build flow schema based on PSI availability.

    CPU/RAM are optional when PSI is available and required otherwise.
    """
    schema = {
        vol.Optional(sensor) if psi_available else vol.Required(sensor): selector
        for sensor, selector in FALLBACK_SENSORS_SCHEMA.items()
    }
    return vol.Schema(schema).extend(_BASE_SCHEMA)


FALLBACK_SENSORS_SCHEMA = {
    CONF_CPU_SENSOR: selector.EntitySelector(
        selector.EntitySelectorConfig(
            filter=(selector.EntityFilterSelectorConfig(domain="sensor"))
        )
    ),
    CONF_RAM_SENSOR: selector.EntitySelector(
        selector.EntitySelectorConfig(
            filter=(selector.EntityFilterSelectorConfig(domain="sensor"))
        )
    ),
}


_BASE_SCHEMA = {
    vol.Required(
        CONF_STORAGE_TYPE, default=DEFAULT_STORAGE_TYPE
    ): selector.SelectSelector(
        selector.SelectSelectorConfig(
            options=STORAGE_TYPES,
            mode=selector.SelectSelectorMode.DROPDOWN,
        )
    ),
    vol.Optional(CONF_IGNORE_LABEL): selector.LabelSelector(),
    vol.Optional(CONF_DB_SENSOR): selector.EntitySelector(
        selector.EntitySelectorConfig(
            filter=selector.EntityFilterSelectorConfig(domain="sensor")
        )
    ),
}

_EXTRA_OPTIONS_SCHEMA = {
    vol.Optional(
        CONF_UPDATE_INTERVAL,
        default=DEFAULT_UPDATE_INTERVAL,
    ): selector.NumberSelector(
        selector.NumberSelectorConfig(
            min=10,
            max=3600,
            step=1,
            unit_of_measurement=UnitOfTime.SECONDS,
            mode=selector.NumberSelectorMode.BOX,
        )
    )
}

_CONFIG_VERSION = VersionInformation(major=3, minor=2)


class HaghsConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for HAGHS."""

    VERSION = _CONFIG_VERSION.major
    MINOR_VERSION = _CONFIG_VERSION.minor

    @staticmethod
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> HaghsOptionsFlowHandler:
        """Return the options flow handler."""
        return HaghsOptionsFlowHandler(config_entry)

    async def async_step_user(
        self, user_input: dict[str, str] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Handle the initial step."""

        if user_input is not None:
            return self.async_create_entry(title="Global Health Score", data=user_input)
        psi = await self.hass.async_add_executor_job(
            HaghsDataUpdateCoordinator._read_psi_sync
        )
        schema = _schema_with_psi(psi.available)

        return self.async_show_form(step_id="user", data_schema=schema)


class HaghsOptionsFlowHandler(config_entries.OptionsFlow):
    """Handle HAGHS options — storage type, ignore label, update interval."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Initialize options flow."""
        self._config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Manage the options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        # Current values: options take priority, then data, then defaults
        current = {**self._config_entry.data, **self._config_entry.options}
        psi = await self.hass.async_add_executor_job(
            HaghsDataUpdateCoordinator._read_psi_sync
        )
        schema = _schema_with_psi(psi.available).extend(_EXTRA_OPTIONS_SCHEMA)

        return self.async_show_form(
            step_id="init",
            data_schema=self.add_suggested_values_to_schema(
                schema,
                current,
            ),
        )
