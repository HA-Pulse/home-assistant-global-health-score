"""The recorded score-sensor attributes stay below the recorder's 16 KB limit (worst case)."""

from __future__ import annotations

import json
from datetime import timedelta
from pathlib import Path

import pytest
from homeassistant.components.recorder.db_schema import (
    ALL_DOMAIN_EXCLUDE_ATTRS,
    MAX_STATE_ATTRS_BYTES,
)
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.json import json_bytes
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry, MockEntityPlatform
from pytest_homeassistant_custom_component.components.recorder.common import (
    async_wait_recording_done,
)

from custom_components.haghs.const import DOMAIN
from custom_components.haghs.sensor import HaghsSensor
from tests.factories import make_coordinator, patch_disk, patch_psi

FROZEN = "2026-10-24T12:00:00+00:00"  # clock of the dev capture
LISTS = {"zombie_entities", "unregistered_entities", "dead_devices", "repairs", "pending_updates"}
# List or dict attributes that stay in recorder history on purpose: bounded and small.
RECORDED_STRUCTURES = {
    "pillar_fallbacks": "at most two fixed names (hardware, application)",
    "zombie_count_per_domain": "one short domain key with a count per domain",
    "zombie_count_per_integration": "one integration key with a count per integration",
    "unregistered_count_per_domain": "one short domain key with a count per domain",
    "zombie_count_per_reason": "at most four fixed reason keys",
}
# Sensor attributes of the same scenario on dev 6533ffd before this change, captured on a clean
# checkout of that commit without PR code, clock frozen at FROZEN. The change only touches the
# recorder, so the current attributes must stay exactly as they were.
DEV_ATTRIBUTES = json.loads(
    (Path(__file__).parent / "data" / "recorder_attribute_size_dev.json").read_text()
)


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations() -> None:
    """The recorder must start before hass; this module loads no custom integration."""
    return


async def _worst_case(
    hass: HomeAssistant, length: int = 200
) -> tuple[HaghsSensor, MockConfigEntry]:
    """Every capped list full with long ids and names, plus 50 repairs and 100 pending updates."""
    coord = make_coordinator(hass)
    coord._registries_ready = True
    entry = MockConfigEntry(domain="liveint", data={})
    entry.add_to_hass(hass)
    object.__setattr__(entry, "state", ConfigEntryState.LOADED)
    devices = dr.async_get(hass)
    registry = er.async_get(hass)
    now = dt_util.utcnow()
    object_len = length - len("sensor.")
    for index in range(120):  # zombies, each on its own device, so every device is dead
        object_id = (f"z{index:03d}_" + "x" * object_len)[:object_len]
        device = devices.async_get_or_create(
            config_entry_id=entry.entry_id,
            identifiers={("liveint", object_id)},
            name=(f"Device {index:03d} " + "y" * length)[:length],
        )
        created = registry.async_get_or_create(
            "sensor",
            "liveint",
            f"uid_{index}",
            suggested_object_id=object_id,
            config_entry=entry,
            device_id=device.id,
        )
        hass.states.async_set(created.entity_id, STATE_UNAVAILABLE)
        hass.states.get(created.entity_id).last_changed = now - timedelta(minutes=30)
    for index in range(120):  # unregistered entities
        entity_id = ("sensor." + f"u{index:03d}_" + "w" * object_len)[:length]
        hass.states.async_set(entity_id, STATE_UNAVAILABLE)
        hass.states.get(entity_id).last_changed = now - timedelta(minutes=30)
    for index in range(60):  # repairs of another integration, capped at 50
        ir.async_create_issue(
            hass,
            "someint",
            (f"issue_{index:03d}_" + "r" * length)[:length],
            is_fixable=False,
            severity=ir.IssueSeverity.WARNING,
            translation_key="x",
        )
    for index in range(100):  # pending updates, not capped
        hass.states.async_set(
            f"update.u{index:03d}",
            "on",
            {"friendly_name": (f"Update {index:03d} " + "v" * 60)[:60]},
        )
    with patch_psi(cpu=1.0, memory=1.0, io=1.0), patch_disk():
        hw = await coord._async_calc_hardware()
        app = await coord._async_calc_application()
    coord.data = coord._build_result(hw, app)
    return HaghsSensor(coord, entry), entry


def _recorded(attributes: dict) -> dict:
    excluded = set(ALL_DOMAIN_EXCLUDE_ATTRS) | set(HaghsSensor._unrecorded_attributes)
    return {key: value for key, value in attributes.items() if key not in excluded}


async def test_worst_case_is_recorded_without_size_warning(
    recorder_mock, hass: HomeAssistant, caplog
) -> None:
    sensor, entry = await _worst_case(hass)
    attrs = sensor.extra_state_attributes
    assert len(attrs["zombie_entities"]) == len(attrs["dead_devices"]) == 100
    assert len(attrs["unregistered_entities"]) == 100
    assert len(attrs["repairs"]) == 50
    assert len(attrs["pending_updates"]) == 100
    assert (
        len(json_bytes({k: attrs[k] for k in LISTS})) > MAX_STATE_ATTRS_BYTES
    )  # the lists alone exceed it

    await MockEntityPlatform(hass, domain="sensor", platform_name=DOMAIN).async_add_entities(
        [sensor]
    )
    sensor.async_write_ha_state()
    await async_wait_recording_done(hass)

    assert "exceed maximum size" not in caplog.text
    state = hass.states.get(sensor.entity_id)
    assert LISTS <= set(state.state_info["unrecorded_attributes"])
    recorded = _recorded(state.attributes)
    assert len(json_bytes(recorded)) < MAX_STATE_ATTRS_BYTES
    for key in (
        "zombie_count",
        "unregistered_count",
        "dead_device_count",
        "repair_count",
        "hardware_score",
        "application_score",
    ):
        assert key in recorded
    assert all(key in recorded for key in attrs if key.startswith("rec_"))
    object.__setattr__(entry, "state", ConfigEntryState.NOT_LOADED)


async def test_every_list_or_dict_attribute_is_excluded_or_allow_listed(
    hass: HomeAssistant,
) -> None:
    """A new list or dict attribute fails here until it is excluded or allow-listed with a reason."""
    sensor, entry = await _worst_case(hass)
    attrs = sensor.extra_state_attributes
    structures = {key for key, value in attrs.items() if isinstance(value, (list, dict))}
    unrecorded = set(HaghsSensor._unrecorded_attributes)
    assert structures - unrecorded - set(RECORDED_STRUCTURES) == set()
    assert not unrecorded & set(RECORDED_STRUCTURES)
    assert set(RECORDED_STRUCTURES) <= structures
    assert all(RECORDED_STRUCTURES.values())
    for key in RECORDED_STRUCTURES:  # bounded and small even in the worst case
        assert len(json_bytes({key: attrs[key]})) < 2048, key
    object.__setattr__(entry, "state", ConfigEntryState.NOT_LOADED)


async def test_current_attributes_are_unchanged(hass: HomeAssistant, freezer) -> None:
    """Only the recorder exclusion changes; the state keeps every key and value as on dev."""
    freezer.move_to(FROZEN)
    sensor, entry = await _worst_case(hass, length=80)
    # Keys added since the dev capture (#134, #93, conditional ignore labels); this scenario has no
    # unhealthy entry, every device carries an entity and no conditional labels are configured.
    assert sensor.extra_state_attributes == {
        **DEV_ATTRIBUTES,
        "integration_unhealthy_entries": [],
        "empty_device_count": 0,
        "empty_devices": [],
        "rec_empty_devices": False,
        "conditional_ignore_active": False,
    }
    object.__setattr__(entry, "state", ConfigEntryState.NOT_LOADED)
