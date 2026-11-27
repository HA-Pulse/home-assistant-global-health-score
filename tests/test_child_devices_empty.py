"""Empty child devices are reported like other devices (#219).

HA 2026.11 keeps child devices (one per part, e.g. each socket of a power strip) in
``dev_reg.child_devices``. A child without any entity is registry cruft like a main device without
one; the parent stays unreported (#191).
"""

from __future__ import annotations

import logging

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.helpers import area_registry as ar
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import frame
from homeassistant.helpers import label_registry as lr
from pytest_homeassistant.common import MockConfigEntry

from custom_components.haghs.const import DOMAIN, EMPTY_DEVICE_LIST_CAP
from custom_components.haghs.coordinator import _device_ids
from tests.factories import HAS_CHILD_DEVICES, make_coordinator

pytestmark = pytest.mark.skipif(
    not HAS_CHILD_DEVICES, reason="child devices need Home Assistant 2026.11"
)


@pytest.fixture(autouse=True)
def _reset_states(hass):
    """No integration was really loaded: avoid fake loaded states at teardown."""
    yield
    for entry in hass.config_entries.async_entries():
        if entry.domain != DOMAIN:
            object.__setattr__(entry, "state", ConfigEntryState.NOT_LOADED)


def _owner(hass, state: ConfigEntryState = ConfigEntryState.LOADED) -> MockConfigEntry:
    entry = MockConfigEntry(domain="test_platform", data={})
    entry.add_to_hass(hass)
    object.__setattr__(entry, "state", state)
    return entry


def _parent(hass, owner, name: str, **kwargs):
    return dr.async_get(hass).async_get_or_create(
        config_entry_id=owner.entry_id, identifiers={("test_child", name)}, name=name, **kwargs
    )


def _child(hass, owner, parent_id: str, name: str):
    return dr.async_get(hass).async_get_or_create_child(
        config_entry_id=owner.entry_id,
        identifiers={("test_child", name)},
        name=name,
        parent_device_id=parent_id,
    )


def _entity(hass, device_id: str, object_id: str, **kwargs):
    return er.async_get(hass).async_get_or_create(
        "sensor",
        "test_platform",
        f"uid_{object_id}",
        suggested_object_id=object_id,
        device_id=device_id,
        **kwargs,
    )


def _label(hass, name: str) -> str:
    label = lr.async_get(hass).async_create(name)
    assert label.label_id != label.name
    return label.label_id


def _empty(hass, ignore_labels: list[str] | None = None):
    coord = make_coordinator(hass, options={"ignore_labels": ignore_labels or []})
    coord._registries_ready = True
    result = coord._calc_empty_devices()
    return list(result), _device_ids(result)


async def test_child_without_entities_is_reported_and_parent_is_not(hass) -> None:
    owner = _owner(hass)
    strip = _parent(hass, owner, "power strip")
    _entity(hass, strip.id, "strip_power")
    used = _child(hass, owner, strip.id, "socket 1")
    _entity(hass, used.id, "socket_1_switch")
    empty = _child(hass, owner, strip.id, "socket 2")

    assert _empty(hass) == ([["socket 2"], 1], [empty.id])


async def test_child_with_only_a_disabled_entity_is_not_reported(hass) -> None:
    owner = _owner(hass)
    strip = _parent(hass, owner, "power strip")
    child = _child(hass, owner, strip.id, "socket 1")
    _entity(hass, child.id, "socket_1_switch", disabled_by=er.RegistryEntryDisabler.USER)

    assert _empty(hass) == ([[], 0], [])


async def test_disabled_child_and_child_of_disabled_parent_are_not_reported(hass) -> None:
    owner = _owner(hass)
    reg = dr.async_get(hass)
    strip = _parent(hass, owner, "power strip")
    _entity(hass, strip.id, "strip_power")
    off = _child(hass, owner, strip.id, "socket off")
    reg.async_update_child_device(off.id, disabled_by=dr.DeviceEntryDisabler.USER)
    sleeping = _parent(hass, owner, "sleeping strip")
    _entity(hass, sleeping.id, "sleeping_power")
    _child(hass, owner, sleeping.id, "sleeping socket")
    reg.async_update_device(sleeping.id, disabled_by=dr.DeviceEntryDisabler.USER)
    assert reg.async_get(off.id).disabled_by is not None

    assert _empty(hass) == ([[], 0], [])


async def test_child_of_a_not_loaded_entry_is_not_reported(hass) -> None:
    owner = _owner(hass, ConfigEntryState.SETUP_RETRY)
    strip = _parent(hass, owner, "power strip")
    _entity(hass, strip.id, "strip_power")
    _child(hass, owner, strip.id, "socket 1")

    assert _empty(hass) == ([[], 0], [])


@pytest.mark.parametrize("where", ["child", "parent", "parent_area", "parent_area_no_helper"])
async def test_ignore_label_on_child_parent_or_inherited_area(hass, monkeypatch, where) -> None:
    owner = _owner(hass)
    reg = dr.async_get(hass)
    label = _label(hass, "Keep these sockets")
    strip = _parent(hass, owner, "power strip")
    _entity(hass, strip.id, "strip_power")
    child = _child(hass, owner, strip.id, "socket 1")
    other = _parent(hass, owner, "other strip")
    _entity(hass, other.id, "other_power")
    leftover = _child(hass, owner, other.id, "other socket")
    if where == "child":
        reg.async_update_child_device(child.id, labels={label})
    elif where == "parent":
        reg.async_update_device(strip.id, labels={label})
    else:
        if where == "parent_area_no_helper":  # HA without dr.async_get_effective_area_id
            monkeypatch.delattr(dr, "async_get_effective_area_id")
        area = ar.async_get(hass).async_create("Workshop", labels={label})
        reg.async_update_device(strip.id, area_id=area.id)
        assert reg.async_get(child.id).area_id is None

    assert _empty(hass, [label]) == ([["other socket"], 1], [leftover.id])
    assert _empty(hass) == ([["other socket", "socket 1"], 2], [leftover.id, child.id])


async def test_cap_counts_main_and_child_devices_together(hass) -> None:
    owner = _owner(hass)
    expected: list[tuple[str, str]] = []
    for index in range(60):
        main = _parent(hass, owner, f"main {index:03d}")
        expected.append((main.name, main.id))
    parent = _parent(hass, owner, "strip")
    _entity(hass, parent.id, "strip_power")
    for index in range(60):
        child = _child(hass, owner, parent.id, f"child {index:03d}")
        expected.append((child.name, child.id))
    expected.sort()

    names, ids = _empty(hass)
    assert names == [[name for name, _ in expected[:EMPTY_DEVICE_LIST_CAP]], 120]
    assert ids == [device_id for _, device_id in expected[:EMPTY_DEVICE_LIST_CAP]]


async def test_empty_child_check_logs_no_child_device_warning(hass, caplog, monkeypatch) -> None:
    monkeypatch.setattr(frame, "_REPORTED_INTEGRATIONS", set())
    owner = _owner(hass)
    strip = _parent(hass, owner, "power strip")
    _child(hass, owner, strip.id, "socket 1")
    caplog.set_level(logging.WARNING)

    assert _empty(hass)[0] == [["socket 1"], 1]
    assert [r.getMessage() for r in caplog.records if "ChildDeviceEntry" in r.getMessage()] == []
