"""Device ids next to the dead and empty device names, for the dashboard card links.

``dead_device_ids`` and ``empty_device_ids`` carry the id of the device at the same index as its
name, capped together with the names; the counts stay complete. The ids only feed the card links,
so they stay out of the recorder like the name lists.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.haghs.const import DOMAIN
from custom_components.haghs.coordinator import _DeviceList, _device_ids
from custom_components.haghs.sensor import HaghsSensor
from tests.factories import make_coordinator

CAP = 100  # DEAD_DEVICE_LIST_CAP and EMPTY_DEVICE_LIST_CAP


@pytest.fixture(autouse=True)
def _reset_states(hass):
    """No integration was really loaded: avoid fake loaded states at teardown."""
    yield
    for entry in hass.config_entries.async_entries():
        if entry.domain != DOMAIN:
            object.__setattr__(entry, "state", ConfigEntryState.NOT_LOADED)


def _device(hass: HomeAssistant, key: str, name: str):
    owner = MockConfigEntry(domain="test_platform", data={})
    owner.add_to_hass(hass)
    object.__setattr__(owner, "state", ConfigEntryState.LOADED)
    return dr.async_get(hass).async_get_or_create(
        config_entry_id=owner.entry_id, identifiers={("test_device_ids", key)}, name=name
    )


def _dead_entity(hass: HomeAssistant, device_id: str, object_id: str) -> None:
    entry = er.async_get(hass).async_get_or_create(
        "sensor", "test_platform", f"uid_{object_id}", suggested_object_id=object_id, device_id=device_id
    )
    hass.states.async_set(entry.entity_id, STATE_UNAVAILABLE)
    hass.states.get(entry.entity_id).last_changed = dt_util.utcnow() - timedelta(minutes=30)


def _coordinator(hass: HomeAssistant):
    coord = make_coordinator(hass)
    coord._registries_ready = True
    coord._boot_time = dt_util.utcnow() - timedelta(hours=1)
    return coord


async def test_dead_device_ids_follow_the_names(hass: HomeAssistant) -> None:
    devices = {name: _device(hass, name, name) for name in ("kitchen plug", "attic sensor")}
    for name, device in devices.items():
        _dead_entity(hass, device.id, name.replace(" ", "_"))
    result = _coordinator(hass)._calc_dead_devices()
    assert result == (["attic sensor", "kitchen plug"], 2)
    assert result.ids == [devices["attic sensor"].id, devices["kitchen plug"].id]


async def test_empty_device_ids_follow_the_names(hass: HomeAssistant) -> None:
    devices = {name: _device(hass, name, name) for name in ("zigbee leftover", "bridge ghost")}
    result = _coordinator(hass)._calc_empty_devices()
    assert result == (["bridge ghost", "zigbee leftover"], 2)
    assert result.ids == [devices["bridge ghost"].id, devices["zigbee leftover"].id]


async def test_duplicate_names_keep_every_id(hass: HomeAssistant) -> None:
    first, second = _device(hass, "a", "Plug"), _device(hass, "b", "Plug")
    result = _coordinator(hass)._calc_empty_devices()
    assert result == (["Plug", "Plug"], 2)
    assert result.ids == sorted([first.id, second.id])


@pytest.mark.parametrize("kind", ["dead", "empty"])
async def test_ids_are_capped_with_the_names(hass: HomeAssistant, kind: str) -> None:
    devices = {}
    for index in range(CAP + 5):
        name = f"device {index:03d}"
        devices[name] = _device(hass, name, name)
        if kind == "dead":
            _dead_entity(hass, devices[name].id, f"entity_{index:03d}")
    coord = _coordinator(hass)
    result = coord._calc_dead_devices() if kind == "dead" else coord._calc_empty_devices()
    names, count = result
    assert count == CAP + 5 and len(names) == len(result.ids) == CAP
    assert result.ids == [devices[name].id for name in names]


async def test_update_result_and_sensor_carry_the_ids(hass: HomeAssistant) -> None:
    dead = _device(hass, "dead", "dead plug")
    _dead_entity(hass, dead.id, "dead_plug")
    empty = _device(hass, "empty", "empty bridge")
    coord = _coordinator(hass)
    coord.data = await coord._async_update_data()
    assert (coord.data["dead_devices"], coord.data["dead_device_ids"]) == (["dead plug"], [dead.id])
    assert (coord.data["empty_devices"], coord.data["empty_device_ids"]) == (["empty bridge"], [empty.id])
    sensor = HaghsSensor(coord, hass.config_entries.async_entries(DOMAIN)[0])
    attrs = sensor.extra_state_attributes
    assert (attrs["dead_device_ids"], attrs["empty_device_ids"]) == ([dead.id], [empty.id])


def test_ids_stay_out_of_the_recorder() -> None:
    assert {"dead_device_ids", "empty_device_ids"} <= HaghsSensor._unrecorded_attributes
    assert {"dead_device_count", "empty_device_count"}.isdisjoint(HaghsSensor._unrecorded_attributes)


async def test_neutral_result_and_fallback_have_no_ids(hass: HomeAssistant) -> None:
    neutral = make_coordinator(hass)._neutral_result()
    assert (neutral["dead_device_ids"], neutral["empty_device_ids"]) == ([], [])
    assert _device_ids(([], 0)) == []  # the informational fallback of a failed check
    assert _device_ids(_DeviceList([("a", "1")], 1)) == ["1"]
