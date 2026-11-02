import voluptuous as vol
from homeassistant import data_entry_flow
from homeassistant.components.repairs import RepairsFlow
from homeassistant.core import HomeAssistant

from .config_flow import FALLBACK_SENSORS_SCHEMA, system_monitor_suggestion
from .const import IssueIds


class MissingFallbackSensorRepairFlow(RepairsFlow):
    """Repair flow for CPU/RAM that are not measured (no PSI, no sensor selected; non-blocking since #123)."""

    def __init__(self, entry_id: str) -> None:
        """Initialize repair flow."""
        super().__init__()
        self._entry_id = entry_id

    async def async_step_init(
        self, user_input: dict[str, str] | None = None
    ) -> data_entry_flow.FlowResult:
        """Handle the repair form."""
        return await self.async_step_confirm()

    async def async_step_confirm(
        self, user_input: dict[str, str] | None = None
    ) -> data_entry_flow.FlowResult:
        """Handle the confirm step of a fix flow."""

        entry = self.hass.config_entries.async_get_entry(self._entry_id)
        if entry is None:
            return self.async_abort(reason="config_entry_missing")

        if user_input is not None:
            options = dict(entry.options)
            # Only what the user picked: an empty field keeps the current option (P4, doc audit v2.4.0b4).
            options.update({key: value for key, value in user_input.items() if value})
            self.hass.config_entries.async_update_entry(entry, options=options)
            self.hass.config_entries.async_schedule_reload(entry.entry_id)
            return self.async_create_entry(data={})

        schema = vol.Schema(
            schema={
                vol.Optional(sensor): selector
                for sensor, selector in FALLBACK_SENSORS_SCHEMA.items()
            }
        )
        # Unique System Monitor sensors are offered; nothing is written until the user submits (#123).
        current = {**system_monitor_suggestion(self.hass)}
        current.update({k: v for k, v in {**entry.data, **entry.options}.items() if v})

        return self.async_show_form(
            step_id="confirm",
            data_schema=self.add_suggested_values_to_schema(schema, current),
        )


async def async_create_fix_flow(
    hass: HomeAssistant,
    issue_id: str,
    data: dict[str, str | int | float | None] | None,
) -> RepairsFlow:
    """Create flow."""
    if issue_id == IssueIds.FALLBACK_MISSING:
        return MissingFallbackSensorRepairFlow(data["entry_id"])
