"""Dead child devices, and ignore labels on a parent that cover its child devices (#219).

Entities of a child device carry the child's id as ``device_id``. A label on the parent device
excludes them everywhere ``_is_ignored`` decides: zombies, pending updates, dead devices. On Home
Assistant without child devices nothing changes: a main device has no ``parent_device_id``.
"""

from __future__ import annotations

from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import STATE_UNAVAILABLE
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import label_registry as lr
from homeassistant.util import dt as dt_util
from pytest_homeassistant.common import MockConfigEntry

from custom_components.haghs import coordinator as coordinator_module
from custom_components.haghs.const import DATA_UPDATE_FIRST_SEEN, DOMAIN, UPDATE_GRACE_DAYS
from tests.factories import HAS_CHILD_DEVICES, make_coordinator

needs_children = pytest.mark.skipif(
    not HAS_CHILD_DEVICES, reason="child devices need Home Assistant 2026.11"
)


@pytest.fixture(autouse=True)
def _reset_states(hass):
    """No integration was really loaded: avoid fake loaded states at teardown."""
    yield
    for entry in hass.config_entries.async_entries():
        if entry.domain != DOMAIN:
            object.__setattr__(entry, "state", ConfigEntryState.NOT_LOADED)


def _owner(hass) -> MockConfigEntry:
    entry = MockConfigEntry(domain="test_platform", data={})
    entry.add_to_hass(hass)
    object.__setattr__(entry, "state", ConfigEntryState.LOADED)
    return entry


def _label(hass, name: str) -> str:
    label = lr.async_get(hass).async_create(name)
    assert label.label_id != label.name
    return label.label_id


def _strip(hass, owner, name: str):
    """A parent device with one live entity and a child device ``<name> socket``."""
    reg = dr.async_get(hass)
    parent = reg.async_get_or_create(
        config_entry_id=owner.entry_id, identifiers={("test_child", name)}, name=name
    )
    _sensor(hass, parent.id, f"{name.replace(' ', '_')}_power", dead=False)
    child = reg.async_get_or_create_child(
        config_entry_id=owner.entry_id,
        identifiers={("test_child", f"{name} socket")},
        name=f"{name} socket",
        parent_device_id=parent.id,
    )
    return parent, child


def _sensor(hass, device_id: str, object_id: str, *, dead: bool = True) -> str:
    entry = er.async_get(hass).async_get_or_create(
        "sensor",
        "test_platform",
        f"uid_{object_id}",
        suggested_object_id=object_id,
        device_id=device_id,
    )
    if dead:
        hass.states.async_set(entry.entity_id, STATE_UNAVAILABLE)
        hass.states.get(entry.entity_id).last_changed = dt_util.utcnow() - timedelta(minutes=30)
    else:
        hass.states.async_set(entry.entity_id, "42")
    return entry.entity_id


def _coordinator(hass, labels: list[str]):
    coord = make_coordinator(hass, options={"ignore_labels": labels})
    coord._registries_ready = True
    return coord


@needs_children
async def test_dead_child_device_is_reported_by_its_own_name(hass) -> None:
    owner = _owner(hass)
    _parent, child = _strip(hass, owner, "kitchen strip")
    _sensor(hass, child.id, "kitchen_socket_switch")

    result = _coordinator(hass, [])._calc_dead_devices()
    assert result == (["kitchen strip socket"], 1)
    assert coordinator_module._device_ids(result) == [child.id]


@needs_children
async def test_label_on_parent_silences_dead_child_but_not_other_devices(hass) -> None:
    owner = _owner(hass)
    reg = dr.async_get(hass)
    label = _label(hass, "Holiday strips")
    parent, child = _strip(hass, owner, "kitchen strip")
    _sensor(hass, child.id, "kitchen_socket_switch")
    other_parent, other_child = _strip(hass, owner, "office strip")
    _sensor(hass, other_child.id, "office_socket_switch")
    reg.async_update_device(parent.id, labels={label})
    unrelated = reg.async_get_or_create(
        config_entry_id=owner.entry_id, identifiers={("test_child", "lamp")}, name="lamp"
    )
    reg.async_update_device(unrelated.id, labels={label})

    assert _coordinator(hass, [label])._calc_dead_devices() == (["office strip socket"], 1)
    assert other_parent.labels == set()


@needs_children
async def test_label_on_parent_excludes_zombie_on_child(hass) -> None:
    owner = _owner(hass)
    reg = dr.async_get(hass)
    label = _label(hass, "Holiday strips")
    parent, child = _strip(hass, owner, "kitchen strip")
    zombie = _sensor(hass, child.id, "kitchen_socket_switch")
    _other_parent, other_child = _strip(hass, owner, "office strip")
    counted = _sensor(hass, other_child.id, "office_socket_switch")

    for index in range(96):  # 100 sensors in total: 2 % zombies cost 14 points, 1 % costs 7
        hass.states.async_set(f"sensor.healthy_{index}", "1")

    coord = _coordinator(hass, [label])
    zombies, p_zombie, count, *_ = coord._calc_zombies()
    assert (sorted(zombies), count, p_zombie) == (sorted([zombie, counted]), 2, 14)

    reg.async_update_device(parent.id, labels={label})
    zombies, p_zombie, count, *_ = coord._calc_zombies()
    assert (zombies, count, p_zombie) == ([counted], 1, 7)


@needs_children
async def test_label_on_parent_excludes_pending_update_on_child(hass) -> None:
    owner = _owner(hass)
    reg = dr.async_get(hass)
    label = _label(hass, "Holiday strips")
    parent, child = _strip(hass, owner, "kitchen strip")
    entry = er.async_get(hass).async_get_or_create(
        "update",
        "test_platform",
        "socket_firmware",
        suggested_object_id="socket_firmware",
        device_id=child.id,
        original_name="Socket firmware",
    )
    hass.states.async_set(entry.entity_id, "on", {"friendly_name": "Socket firmware"})
    coord = _coordinator(hass, [label])
    hass.data.setdefault(DOMAIN, {}).setdefault(DATA_UPDATE_FIRST_SEEN, {})[entry.entity_id] = (
        dt_util.utcnow() - timedelta(days=UPDATE_GRACE_DAYS + 1)
    )
    assert coord._calc_updates() == (0, 1, 5, 0, ["Socket firmware"])

    reg.async_update_device(parent.id, labels={label})
    assert coord._calc_updates() == (0, 0, 0, 0, [])


async def test_main_device_without_parent_link_is_ignored_as_before(hass) -> None:
    """Older HA shape: device entries have no ``parent_device_id``; only their own labels count."""
    label = _label(hass, "Keep")
    coord = _coordinator(hass, [label])
    own = SimpleNamespace(labels={label}, area_id=None)
    plain = SimpleNamespace(labels=set(), area_id=None)
    registry = SimpleNamespace(async_get={"own": own, "plain": plain}.get)
    entity = SimpleNamespace(disabled_by=None, labels=set(), device_id="own", area_id=None)

    with (
        patch.object(coordinator_module.dr, "async_get", return_value=registry),
        patch.object(
            coordinator_module.er, "async_get_effective_area_id", return_value=None, create=True
        ),
    ):
        assert coord._is_ignored("sensor.own", entity)
        assert not coord._is_ignored(
            "sensor.plain",
            SimpleNamespace(disabled_by=None, labels=set(), device_id="plain", area_id=None),
        )
    assert coordinator_module._parent_of(registry, own) is None
    assert coordinator_module._child_device_entries(SimpleNamespace(devices=[])) == []


async def test_empty_devices_on_main_device_registry_shape_as_before(hass) -> None:
    """Older HA shape (no ``child_devices``, no ``parent_device_id``): the same report as before #219.

    A hub with a member only through ``via_device_id`` stays unreported, a labeled empty device too;
    the unlabeled empty device is the only one reported, exactly as on dev before the change.
    """
    owner = _owner(hass)
    label = _label(hass, "Keep")
    reg = dr.async_get(hass)
    hub = reg.async_get_or_create(
        config_entry_id=owner.entry_id, identifiers={("test_child", "hub")}, name="hub"
    )
    member = reg.async_get_or_create(
        config_entry_id=owner.entry_id, identifiers={("test_child", "member")}, name="member"
    )
    _sensor(hass, member.id, "member_power", dead=False)
    leftover = reg.async_get_or_create(
        config_entry_id=owner.entry_id, identifiers={("test_child", "leftover")}, name="leftover"
    )
    kept = reg.async_get_or_create(
        config_entry_id=owner.entry_id, identifiers={("test_child", "kept")}, name="kept"
    )

    def old(device, **changes):
        fields = dict(
            id=device.id,
            name=device.name,
            name_by_user=None,
            disabled_by=None,
            entry_type=None,
            via_device_id=None,
            labels=set(),
            area_id=None,
            config_entries={owner.entry_id},
        )
        fields.update(changes)
        return SimpleNamespace(**fields)

    devices = [
        old(hub),
        old(member, via_device_id=hub.id),
        old(leftover),
        old(kept, labels={label}),
    ]
    old_registry = SimpleNamespace(devices=devices, async_get={d.id: d for d in devices}.get)
    assert not hasattr(old_registry, "child_devices")
    assert not any(hasattr(d, "parent_device_id") for d in devices)

    class _OldDeviceRegistryModule:
        """``dr`` as the coordinator sees it: the old registry, every other name from the real module."""

        def __getattr__(self, name):
            return getattr(dr, name)

        @staticmethod
        def async_get(_hass):
            return old_registry

    coord = _coordinator(hass, [label])
    with patch.object(coordinator_module, "dr", _OldDeviceRegistryModule()):
        result = coord._calc_empty_devices()
    assert result == (["leftover"], 1)
    assert coordinator_module._device_ids(result) == [leftover.id]
