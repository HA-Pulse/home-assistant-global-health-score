"""Empty devices never report a parent of child devices or a composite device (HAGHS-20261103-001).

HA 2026.9+ keeps child devices in ``dev_reg.child_devices``; a parent whose entities sit on its
children has no entity of its own. One report fewer rather than a wrong one.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import attr
import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.haghs import coordinator as coordinator_module
from custom_components.haghs.const import DOMAIN
from tests.factories import make_coordinator


@pytest.fixture(autouse=True)
def _reset_states(hass):
    """No integration was really loaded: avoid fake loaded states at teardown."""
    yield
    for entry in hass.config_entries.async_entries():
        if entry.domain != DOMAIN:
            object.__setattr__(entry, "state", ConfigEntryState.NOT_LOADED)


def _owner(hass: HomeAssistant) -> MockConfigEntry:
    entry = MockConfigEntry(domain="test_platform", data={})
    entry.add_to_hass(hass)
    object.__setattr__(entry, "state", ConfigEntryState.LOADED)
    return entry


def _device(hass: HomeAssistant, owner: MockConfigEntry, name: str, **kwargs):
    return dr.async_get(hass).async_get_or_create(
        config_entry_id=owner.entry_id, identifiers={("test_child", name)}, name=name, **kwargs
    )


def _child(hass: HomeAssistant, owner: MockConfigEntry, parent_id: str, name: str):
    return dr.async_get(hass).async_get_or_create_child(
        config_entry_id=owner.entry_id,
        identifiers={("test_child", name)},
        name=name,
        parent_device_id=parent_id,
    )


def _entity(hass: HomeAssistant, device_id: str, object_id: str) -> None:
    er.async_get(hass).async_get_or_create(
        "sensor",
        "test_platform",
        f"uid_{object_id}",
        suggested_object_id=object_id,
        device_id=device_id,
    )


def _empty(hass: HomeAssistant):
    coord = make_coordinator(hass)
    coord._registries_ready = True
    return coord._calc_empty_devices()


async def test_parent_whose_entities_sit_on_child_devices_is_not_empty(hass) -> None:
    owner = _owner(hass)
    parent = _device(hass, owner, "dishwasher")
    child = _child(hass, owner, parent.id, "dishwasher pump")
    _entity(hass, child.id, "pump_power")
    _device(hass, owner, "leftover")

    assert _empty(hass) == (["leftover"], 1)


async def test_parent_with_a_child_without_entities_is_not_empty(hass) -> None:
    owner = _owner(hass)
    parent = _device(hass, owner, "hub")
    _child(hass, owner, parent.id, "hub port")

    assert _empty(hass) == ([], 0)


async def test_via_device_of_a_child_marks_its_target_as_parent(hass) -> None:
    owner = _owner(hass)
    bridge = _device(hass, owner, "bridge")
    lamp = _device(hass, owner, "lamp")
    _entity(hass, lamp.id, "lamp_light")
    child = SimpleNamespace(parent_device_id=lamp.id, via_device_id=bridge.id)

    assert coordinator_module._parent_device_ids(SimpleNamespace(child_devices=[child]), []) == {
        bridge.id,
        lamp.id,
    }
    real = coordinator_module._parent_device_ids
    with patch.object(
        coordinator_module,
        "_parent_device_ids",
        lambda dev_reg, devices: real(SimpleNamespace(child_devices=[child]), devices),
    ):
        assert _empty(hass) == ([], 0)
    assert _empty(hass) == (["bridge"], 1)  # without the child the bridge has no entity of its own


@pytest.mark.parametrize(
    "changes",
    [
        {"composite_device_id": "0123456789abcdef0123456789abcdef"},
        {"has_composite_identifiers": True},
    ],
)
async def test_composite_and_split_devices_are_not_empty(hass, changes) -> None:
    owner = _owner(hass)
    device = _device(hass, owner, "merged")
    if not all(hasattr(device, name) for name in changes):
        pytest.skip("this HA version has no composite devices")
    composite = attr.evolve(device, **changes)
    leftover = _device(hass, owner, "leftover")

    with patch.object(coordinator_module, "_device_entries", return_value=[composite, leftover]):
        assert _empty(hass) == (["leftover"], 1)


def test_is_composite_reads_every_marker_and_defaults_to_false() -> None:
    assert not coordinator_module._is_composite(SimpleNamespace())
    assert not coordinator_module._is_composite(
        SimpleNamespace(
            composite_device_id=None, has_composite_identifiers=False, is_composite_device=False
        )
    )
    assert coordinator_module._is_composite(SimpleNamespace(composite_device_id="x"))
    assert coordinator_module._is_composite(SimpleNamespace(has_composite_identifiers=True))
    assert coordinator_module._is_composite(SimpleNamespace(is_composite_device=True))


async def test_ha_without_child_devices_behaves_as_before(hass) -> None:
    """HA 2024.10 shape: no ``child_devices`` collection, device entries without composite fields."""
    owner = _owner(hass)
    hub = _device(hass, owner, "hub")
    member = _device(hass, owner, "member", via_device_id=hub.id)
    _entity(hass, member.id, "member_power")
    leftover = _device(hass, owner, "leftover")
    fields = (
        "id",
        "name",
        "name_by_user",
        "disabled_by",
        "entry_type",
        "via_device_id",
        "labels",
        "area_id",
        "config_entries",
    )

    def old(device):
        return SimpleNamespace(
            **{name: getattr(device, name, None) for name in fields[:-1]},
            config_entries={owner.entry_id},
        )

    old_registry = SimpleNamespace(devices=[old(d) for d in dr.async_get(hass).devices])
    assert not hasattr(old_registry, "child_devices")
    assert coordinator_module._parent_device_ids(old_registry, old_registry.devices) == {hub.id}
    assert not any(coordinator_module._is_composite(d) for d in old_registry.devices)
    real = coordinator_module._parent_device_ids
    with (
        patch.object(coordinator_module, "_device_entries", return_value=old_registry.devices),
        patch.object(
            coordinator_module,
            "_parent_device_ids",
            lambda dev_reg, devices: real(old_registry, devices),
        ),
    ):
        assert _empty(hass) == (["leftover"], 1)
    assert leftover.name == "leftover"
