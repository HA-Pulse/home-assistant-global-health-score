"""Config flow and options flow for HAGHS integration."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import UnitOfTime
from homeassistant.helpers import label_registry as lr
from homeassistant.helpers import selector

from .const import (
    _CONFIG_VERSION,
    CONF_BATTERY_GRACE_MINUTES,
    CONF_CPU_SENSOR,
    CONF_DB_SENSOR,
    CONF_IGNORE_LABELS,
    CONF_IGNORE_PATTERNS,
    CONF_RAM_SENSOR,
    CONF_STORAGE_TYPE,
    CONF_UPDATE_INTERVAL,
    CONF_ZOMBIE_GRACE_MINUTES,
    DEFAULT_BATTERY_GRACE_MINUTES,
    DEFAULT_IGNORE_LABEL_NAME,
    DEFAULT_STORAGE_TYPE,
    DEFAULT_UPDATE_INTERVAL,
    DEFAULT_ZOMBIE_GRACE_MINUTES,
    DOMAIN,
    STORAGE_TYPES,
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
        selector.EntitySelectorConfig(filter=(selector.EntityFilterSelectorConfig(domain="sensor")))
    ),
    CONF_RAM_SENSOR: selector.EntitySelector(
        selector.EntitySelectorConfig(filter=(selector.EntityFilterSelectorConfig(domain="sensor")))
    ),
}


_BASE_SCHEMA = {
    vol.Required(CONF_STORAGE_TYPE, default=DEFAULT_STORAGE_TYPE): selector.SelectSelector(
        selector.SelectSelectorConfig(
            options=STORAGE_TYPES,
            mode=selector.SelectSelectorMode.DROPDOWN,
        )
    ),
    vol.Optional(CONF_IGNORE_LABELS): selector.LabelSelector(
        selector.LabelSelectorConfig(multiple=True)
    ),
    vol.Optional(CONF_IGNORE_PATTERNS): selector.TextSelector(
        selector.TextSelectorConfig(multiple=True)
    ),
    vol.Optional(CONF_DB_SENSOR): selector.EntitySelector(
        selector.EntitySelectorConfig(filter=selector.EntityFilterSelectorConfig(domain="sensor"))
    ),
}

# Optional fields the user must be able to clear. Without this normalization a
# missing key in user_input would never reach entry.options, and the
# {**data, **options} merge in the coordinator would resurrect the original
# value from entry.data after every HA restart (community bug report).
_NULLABLE_OPTIONAL_KEYS: tuple[str, ...] = (
    CONF_DB_SENSOR,
    CONF_CPU_SENSOR,
    CONF_RAM_SENSOR,
    CONF_IGNORE_LABELS,
    CONF_IGNORE_PATTERNS,
)
_LIST_OPTIONAL_KEYS: frozenset[str] = frozenset({CONF_IGNORE_LABELS, CONF_IGNORE_PATTERNS})


def _normalize_optional(user_input: dict[str, Any]) -> dict[str, Any]:
    """Force every leave-able optional field to an explicit None / []."""
    for key in _NULLABLE_OPTIONAL_KEYS:
        value = user_input.get(key)
        if value in (None, "", []):
            user_input[key] = [] if key in _LIST_OPTIONAL_KEYS else None
    return user_input


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
    ),
    vol.Optional(
        CONF_ZOMBIE_GRACE_MINUTES,
        default=DEFAULT_ZOMBIE_GRACE_MINUTES,
    ): selector.NumberSelector(
        selector.NumberSelectorConfig(
            min=1,
            max=240,
            step=1,
            unit_of_measurement=UnitOfTime.MINUTES,
            mode=selector.NumberSelectorMode.BOX,
        )
    ),
    vol.Optional(
        CONF_BATTERY_GRACE_MINUTES,
        default=DEFAULT_BATTERY_GRACE_MINUTES,
    ): selector.NumberSelector(
        selector.NumberSelectorConfig(
            min=1,
            max=240,
            step=1,
            unit_of_measurement=UnitOfTime.MINUTES,
            mode=selector.NumberSelectorMode.BOX,
        )
    ),
}


def _ensure_default_label(hass) -> str | None:
    """Ensure the default ignore label exists and return its label_id."""
    label_reg = lr.async_get(hass)
    for label_id, label_entry in label_reg.labels.items():
        if label_entry.name.lower() == DEFAULT_IGNORE_LABEL_NAME.lower():
            return label_id
    try:
        created = label_reg.async_create(DEFAULT_IGNORE_LABEL_NAME)
        return created.label_id
    except ValueError:
        for label_id, label_entry in label_reg.labels.items():
            if label_entry.name.lower() == DEFAULT_IGNORE_LABEL_NAME.lower():
                return label_id
    return None


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
            return self.async_create_entry(
                title="Global Health Score",
                data=_normalize_optional(user_input),
            )
        psi = await self.hass.async_add_executor_job(HaghsDataUpdateCoordinator._read_psi_sync)
        schema = _schema_with_psi(psi.available)

        ignore_label_id = _ensure_default_label(self.hass)
        suggested = {}
        if ignore_label_id:
            suggested[CONF_IGNORE_LABELS] = [ignore_label_id]

        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(schema, suggested),
        )


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
            return self.async_create_entry(title="", data=_normalize_optional(user_input))

        # Current values: options take priority, then data, then defaults
        current = {**self._config_entry.data, **self._config_entry.options}
        psi = await self.hass.async_add_executor_job(HaghsDataUpdateCoordinator._read_psi_sync)
        schema = _schema_with_psi(psi.available).extend(_EXTRA_OPTIONS_SCHEMA)

        return self.async_show_form(
            step_id="init",
            data_schema=self.add_suggested_values_to_schema(
                schema,
                current,
            ),
        )
