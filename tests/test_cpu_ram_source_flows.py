"""#123 follow-up: CPU and RAM are optional in the setup and options flow, also without PSI.

Without PSI both flows suggest System Monitor's processor and memory sensors when the registry has them; the
suggestion only pre-fills the form, nothing is stored until the user submits.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.haghs.const import CONF_CPU_SENSOR, CONF_RAM_SENSOR, CONF_STORAGE_TYPE, DOMAIN
from custom_components.haghs.coordinator import HaghsDataUpdateCoordinator, _PsiData

PSI = {"present": _PsiData(cpu=1.0, memory=1.0, io=1.0), "absent": _PsiData(cpu=None, memory=None, io=None)}


def _system_monitor(hass: HomeAssistant) -> dict[str, str]:
    owner = MockConfigEntry(domain="systemmonitor")
    owner.add_to_hass(hass)
    registry = er.async_get(hass)
    return {
        option: registry.async_get_or_create(
            "sensor", "systemmonitor", unique_id, config_entry=owner, suggested_object_id=unique_id
        ).entity_id
        for option, unique_id in ((CONF_CPU_SENSOR, "processor_use"), (CONF_RAM_SENSOR, "memory_use_percent"))
    }


def _fields(form: dict) -> dict[str, tuple[type, object]]:
    """CPU/RAM marker type and suggested value of a shown form."""
    return {
        str(key): (type(key), (key.description or {}).get("suggested_value"))
        for key in form["data_schema"].schema
        if str(key) in (CONF_CPU_SENSOR, CONF_RAM_SENSOR)
    }


@pytest.mark.parametrize(("case", "suggested"), [("absent", True), ("present", False)])
async def test_setup_flow_fields_are_optional_and_suggested_only_without_psi(hass, case, suggested) -> None:
    monitor = _system_monitor(hass)
    with patch.object(HaghsDataUpdateCoordinator, "_read_psi_sync", return_value=PSI[case]):
        form = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    assert form["type"] is FlowResultType.FORM
    assert _fields(form) == {
        option: (vol.Optional, monitor[option] if suggested else None) for option in (CONF_CPU_SENSOR, CONF_RAM_SENSOR)
    }


async def test_setup_without_psi_and_without_sensors_creates_the_entry(hass: HomeAssistant) -> None:
    with patch.object(HaghsDataUpdateCoordinator, "_read_psi_sync", return_value=PSI["absent"]):
        form = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
        with patch("custom_components.haghs.async_setup_entry", return_value=True):
            done = await hass.config_entries.flow.async_configure(
                form["flow_id"], user_input={CONF_STORAGE_TYPE: "ssd"}
            )
    assert done["type"] is FlowResultType.CREATE_ENTRY
    assert (done["data"].get(CONF_CPU_SENSOR), done["data"].get(CONF_RAM_SENSOR)) == (None, None)


async def test_options_flow_suggests_only_empty_fields_without_psi(hass: HomeAssistant) -> None:
    monitor = _system_monitor(hass)
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_STORAGE_TYPE: "ssd"},
        options={CONF_CPU_SENSOR: "sensor.my_cpu", CONF_RAM_SENSOR: None},
        version=3,
        minor_version=4,
    )
    entry.add_to_hass(hass)
    with patch.object(HaghsDataUpdateCoordinator, "_read_psi_sync", return_value=PSI["absent"]):
        form = await hass.config_entries.options.async_init(entry.entry_id)
    assert _fields(form) == {
        CONF_CPU_SENSOR: (vol.Optional, "sensor.my_cpu"),  # the user's own choice stays
        CONF_RAM_SENSOR: (vol.Optional, monitor[CONF_RAM_SENSOR]),
    }
    assert dict(entry.options) == {CONF_CPU_SENSOR: "sensor.my_cpu", CONF_RAM_SENSOR: None}


async def test_options_flow_with_psi_suggests_nothing(hass: HomeAssistant) -> None:
    _system_monitor(hass)
    entry = MockConfigEntry(domain=DOMAIN, data={CONF_STORAGE_TYPE: "ssd"}, version=3, minor_version=4)
    entry.add_to_hass(hass)
    with patch.object(HaghsDataUpdateCoordinator, "_read_psi_sync", return_value=PSI["present"]):
        form = await hass.config_entries.options.async_init(entry.entry_id)
    assert _fields(form) == {CONF_CPU_SENSOR: (vol.Optional, None), CONF_RAM_SENSOR: (vol.Optional, None)}
