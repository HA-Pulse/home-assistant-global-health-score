"""Ignore paths, registry skip rules and the safety-net branches."""

from __future__ import annotations

import asyncio
import logging
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import Mock

import attr
import pytest
from homeassistant.const import STATE_UNAVAILABLE
from homeassistant.helpers import area_registry as ar
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import label_registry as lr
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.haghs import coordinator as coordinator_module
from tests.factories import make_coordinator


async def test_device_label_ignores_entity(hass) -> None:
    owner = MockConfigEntry(domain="test_platform", data={})
    owner.add_to_hass(hass)
    device = dr.async_get(hass).async_get_or_create(
        config_entry_id=owner.entry_id,
        identifiers={("test", "device_1")},
    )
    dr.async_get(hass).async_update_device(device.id, labels={"haghs_ignore"})
    entry = er.async_get(hass).async_get_or_create(
        "sensor",
        "test_platform",
        "uid_device_label",
        suggested_object_id="device_label",
        device_id=device.id,
    )
    coord = make_coordinator(hass, options={"ignore_labels": ["haghs_ignore"]})
    assert coord._is_ignored(entry.entity_id, entry) is True


async def test_entity_label_ignores_entity(hass) -> None:
    entry = er.async_get(hass).async_get_or_create(
        "sensor",
        "test_platform",
        "uid_entity_label",
        suggested_object_id="entity_label",
    )
    er.async_get(hass).async_update_entity(entry.entity_id, labels={"haghs_ignore"})
    coord = make_coordinator(hass, options={"ignore_labels": ["haghs_ignore"]})
    assert coord._is_ignored(entry.entity_id, er.async_get(hass).async_get(entry.entity_id)) is True


async def test_disabled_entity_is_ignored(hass) -> None:
    entry = er.async_get(hass).async_get_or_create(
        "sensor",
        "test_platform",
        "uid_disabled",
        suggested_object_id="disabled_entity",
    )
    er.async_get(hass).async_update_entity(
        entry.entity_id, disabled_by=er.RegistryEntryDisabler.USER
    )
    coord = make_coordinator(hass)
    updated = er.async_get(hass).async_get(entry.entity_id)
    assert coord._is_ignored(entry.entity_id, updated) is True


async def test_device_without_matching_label_is_not_ignored(hass) -> None:
    owner = MockConfigEntry(domain="test_platform", data={})
    owner.add_to_hass(hass)
    device = dr.async_get(hass).async_get_or_create(
        config_entry_id=owner.entry_id,
        identifiers={("test", "device_2")},
    )
    dr.async_get(hass).async_update_device(device.id, labels={"other_label"})
    entry = er.async_get(hass).async_get_or_create(
        "sensor",
        "test_platform",
        "uid_device_other_label",
        suggested_object_id="device_other_label",
        device_id=device.id,
    )
    coord = make_coordinator(hass, options={"ignore_labels": ["haghs_ignore"]})
    assert coord._is_ignored(entry.entity_id, entry) is False


async def test_stale_device_reference_is_not_ignored(hass, monkeypatch) -> None:
    """A device id whose registry entry is gone must not break the check."""
    owner = MockConfigEntry(domain="test_platform", data={})
    owner.add_to_hass(hass)
    device = dr.async_get(hass).async_get_or_create(
        config_entry_id=owner.entry_id,
        identifiers={("test", "device_3")},
    )
    entry = er.async_get(hass).async_get_or_create(
        "sensor",
        "test_platform",
        "uid_stale_device",
        suggested_object_id="stale_device",
        device_id=device.id,
    )
    # Emulate a desynced registry read: entity id set, device lookup empty.
    monkeypatch.setattr(
        coordinator_module.dr,
        "async_get",
        lambda _hass: SimpleNamespace(async_get=lambda _device_id: None),
    )
    coord = make_coordinator(hass, options={"ignore_labels": ["haghs_ignore"]})
    assert coord._is_ignored(entry.entity_id, entry) is False


async def test_integration_health_entities_are_never_zombies(hass) -> None:
    """HAGHS must not count its own diagnostic helper entities as zombies."""
    registry = er.async_get(hass)
    registry.async_get_or_create(
        "sensor",
        "test_platform",
        "uid_integration_health",
        suggested_object_id="integration_health_test",
    )
    control = registry.async_get_or_create(
        "sensor",
        "test_platform",
        "uid_control_zombie",
        suggested_object_id="control_zombie",
    )
    for entity_id in ("sensor.integration_health_test", "sensor.control_zombie"):
        hass.states.async_set(entity_id, STATE_UNAVAILABLE)
        hass.states.get(entity_id).last_changed = dt_util.utcnow() - timedelta(minutes=60)
    coord = make_coordinator(hass)
    zombie_list, _p_zombie, zombie_count, *_rest = coord._calc_zombies()
    assert zombie_count == 1
    assert zombie_list == [control.entity_id]


async def test_safe_calc_timeout_returns_fallback(hass, caplog, monkeypatch) -> None:
    coord = make_coordinator(hass)
    monkeypatch.setattr(coordinator_module, "PILLAR_TIMEOUT", 0.01)

    async def _slow() -> str:
        await asyncio.sleep(0.5)
        return "never"

    with caplog.at_level(logging.WARNING):
        result = await coord._safe_calc("demo", _slow(), "fallback")
    assert result == "fallback"
    assert "timed out" in caplog.text


async def test_safe_calc_exception_returns_fallback(hass, caplog) -> None:
    coord = make_coordinator(hass)

    async def _broken() -> str:
        raise ValueError("boom")

    with caplog.at_level(logging.WARNING):
        result = await coord._safe_calc("demo", _broken(), "fallback")
    assert result == "fallback"
    assert "calculation failed" in caplog.text


async def test_invalid_ignore_pattern_is_skipped(hass, caplog, monkeypatch) -> None:
    """A pattern that cannot be compiled is dropped with a warning."""
    monkeypatch.setattr(coordinator_module.fnmatch, "translate", lambda _pattern: "(")
    with caplog.at_level(logging.WARNING):
        patterns = coordinator_module._compile_patterns(["broken["])
    assert patterns == []
    assert "Invalid ignore pattern" in caplog.text


@pytest.mark.parametrize(
    ("scenario", "expected"),
    [
        ("entity_area", True),
        ("device_area", True),
        ("own_unlabeled_area", False),
        ("own_labeled_area", True),
        ("other_label", False),
        ("empty_selection", False),
        ("display_name_selection", False),
        ("multiple_selection", True),
        ("no_registry_entry", False),
        ("no_device_or_area", False),
        ("missing_device", False),
        ("missing_device_with_own_area", True),
        ("missing_area", False),
        ("entity_label", True),
        ("device_label", True),
        ("pattern", True),
        ("disabled", True),
    ],
)
async def test_area_ignore_matrix(hass, scenario: str, expected: bool) -> None:
    """Use real registry entries and selected IDs, never display-name matching."""
    labels = lr.async_get(hass)
    label = labels.async_create("area_ignore_internal")
    label = labels.async_update(label.label_id, name="Visible area exclusion")
    other = labels.async_create("other_area_label")
    assert label.label_id != label.name
    areas = ar.async_get(hass)
    ignored_area = areas.async_create("Ignored room", labels={label.label_id})
    plain_area = areas.async_create("Control room")
    owner = MockConfigEntry(domain="test_platform", data={})
    owner.add_to_hass(hass)
    devices = dr.async_get(hass)
    device = devices.async_get_or_create(
        config_entry_id=owner.entry_id, identifiers={("test", "area_matrix")}
    )
    registry = er.async_get(hass)
    entry = registry.async_get_or_create(
        "sensor",
        "test_platform",
        "area_matrix",
        original_name="Area matrix entity",
        device_id=device.id,
    )
    if scenario in {"device_area", "own_unlabeled_area"}:
        devices.async_update_device(device.id, area_id=ignored_area.id)
    if scenario == "own_unlabeled_area":
        registry.async_update_entity(entry.entity_id, area_id=plain_area.id)
    elif scenario == "own_labeled_area":
        devices.async_update_device(device.id, area_id=plain_area.id)
        registry.async_update_entity(entry.entity_id, area_id=ignored_area.id)
    elif scenario in {
        "entity_area",
        "other_label",
        "empty_selection",
        "display_name_selection",
        "multiple_selection",
    }:
        registry.async_update_entity(entry.entity_id, area_id=ignored_area.id)
    elif scenario == "missing_device_with_own_area":
        registry.async_update_entity(entry.entity_id, area_id=ignored_area.id)
    elif scenario == "missing_area":
        registry.async_update_entity(entry.entity_id, area_id="missing_area")
    elif scenario == "no_device_or_area":
        registry.async_update_entity(entry.entity_id, device_id=None)
    elif scenario == "entity_label":
        registry.async_update_entity(
            entry.entity_id, area_id=plain_area.id, labels={label.label_id}
        )
    elif scenario == "device_label":
        registry.async_update_entity(entry.entity_id, area_id=plain_area.id)
        devices.async_update_device(device.id, labels={label.label_id})
    elif scenario == "disabled":
        registry.async_update_entity(entry.entity_id, disabled_by=er.RegistryEntryDisabler.USER)
    selection = [label.label_id]
    if scenario == "other_label":
        selection = [other.label_id]
    elif scenario == "empty_selection":
        selection = []
    elif scenario == "display_name_selection":
        selection = [label.name]
    elif scenario == "multiple_selection":
        selection = [other.label_id, label.label_id]
    coord = make_coordinator(
        hass,
        options={
            "ignore_labels": selection,
            "ignore_patterns": [entry.entity_id] if scenario == "pattern" else [],
        },
    )
    current = None if scenario == "no_registry_entry" else registry.async_get(entry.entity_id)
    if scenario in {"missing_device", "missing_device_with_own_area"}:
        # Registry updates reject dangling devices. Model a stale entry snapshot
        # using the real entry type without corrupting registry internals.
        assert current is not None
        current = attr.evolve(current, device_id="missing_device")
    actual = coord._is_ignored(entry.entity_id, current)
    assert actual is expected, f"{scenario}: actual={actual}, expected={expected}"


async def test_area_ignore_repeated_device_lookups_keep_entity_areas_separate(hass) -> None:
    """Repeated negative device-label lookups cannot hide sibling area labels."""
    label = lr.async_get(hass).async_create("Visible exclusion")
    assert label.label_id != label.name
    areas = ar.async_get(hass)
    ignored = areas.async_create("Ignored sibling room", labels={label.label_id})
    control = areas.async_create("Control sibling room")
    owner = MockConfigEntry(domain="test_platform", data={})
    owner.add_to_hass(hass)
    device = dr.async_get(hass).async_get_or_create(
        config_entry_id=owner.entry_id, identifiers={("test", "area_siblings")}
    )
    registry = er.async_get(hass)
    plain = registry.async_get_or_create(
        "sensor",
        "test_platform",
        "plain_sibling",
        original_name="Plain sibling",
        device_id=device.id,
    )
    labeled = registry.async_get_or_create(
        "sensor",
        "test_platform",
        "labeled_sibling",
        original_name="Labeled sibling",
        device_id=device.id,
    )
    registry.async_update_entity(plain.entity_id, area_id=control.id)
    registry.async_update_entity(labeled.entity_id, area_id=ignored.id)
    coord = make_coordinator(hass, options={"ignore_labels": [label.label_id]})
    for entity_id, expected in (
        (plain.entity_id, False),
        (plain.entity_id, False),
        (labeled.entity_id, True),
        (plain.entity_id, False),
        (labeled.entity_id, True),
    ):
        actual = coord._is_ignored(entity_id, registry.async_get(entity_id))
        assert actual is expected, f"{entity_id}: actual={actual}, expected={expected}"


@pytest.mark.parametrize("change", ["area_labels", "entity_area", "device_area"])
async def test_area_ignore_changes_apply_on_next_lookup(hass, change: str) -> None:
    """Mutate real registries without reload, cache resets or event processing."""
    label = lr.async_get(hass).async_create("Dynamic exclusion")
    assert label.label_id != label.name
    areas = ar.async_get(hass)
    room = areas.async_create("Dynamic room")
    owner = MockConfigEntry(domain="test_platform", data={})
    owner.add_to_hass(hass)
    devices = dr.async_get(hass)
    device = devices.async_get_or_create(
        config_entry_id=owner.entry_id, identifiers={("test", "dynamic_area")}
    )
    registry = er.async_get(hass)
    entry = registry.async_get_or_create(
        "sensor",
        "test_platform",
        "dynamic_area",
        original_name="Dynamic entity",
        device_id=device.id,
    )
    if change == "area_labels":
        devices.async_update_device(device.id, area_id=room.id)
    else:
        areas.async_update(room.id, labels={label.label_id})
    coord = make_coordinator(hass, options={"ignore_labels": [label.label_id]})
    for enabled in (False, True, False, True):
        if change == "area_labels":
            areas.async_update(room.id, labels={label.label_id} if enabled else set())
        elif change == "entity_area":
            registry.async_update_entity(entry.entity_id, area_id=room.id if enabled else None)
        else:
            devices.async_update_device(device.id, area_id=room.id if enabled else None)
        actual = coord._is_ignored(entry.entity_id, registry.async_get(entry.entity_id))
        assert actual is enabled, f"{change}: actual={actual}, expected={enabled}"


async def test_area_ignore_native_parent_device_inheritance(hass) -> None:
    """Native HA inherits parent areas; legacy HA must not invent inheritance."""
    native_available = hasattr(er, "async_get_effective_area_id")
    label = lr.async_get(hass).async_create("Parent room exclusion")
    assert label.label_id != label.name
    area = ar.async_get(hass).async_create("Parent room", labels={label.label_id})
    control = ar.async_get(hass).async_create("Child room")
    owner = MockConfigEntry(domain="test_platform", data={})
    owner.add_to_hass(hass)
    devices = dr.async_get(hass)
    parent = devices.async_get_or_create(
        config_entry_id=owner.entry_id, identifiers={("test", "area_parent")}
    )
    devices.async_update_device(parent.id, area_id=area.id)
    if native_available:
        child = devices.async_get_or_create_child(
            config_entry_id=owner.entry_id,
            identifiers={("test", "area_child")},
            parent_device_id=parent.id,
        )
        assert child.parent_device_id == parent.id
    else:
        child = devices.async_get_or_create(
            config_entry_id=owner.entry_id,
            identifiers={("test", "area_child")},
            via_device=("test", "area_parent"),
        )
        assert child.via_device_id == parent.id
    registry = er.async_get(hass)
    entry = registry.async_get_or_create(
        "sensor", "test_platform", "parent_area_entity", device_id=child.id
    )
    coord = make_coordinator(hass, options={"ignore_labels": [label.label_id]})
    actual = coord._is_ignored(entry.entity_id, registry.async_get(entry.entity_id))
    assert actual is native_available
    devices.async_update_device(child.id, area_id=control.id)
    assert coord._is_ignored(entry.entity_id, registry.async_get(entry.entity_id)) is False


@pytest.mark.parametrize("native_available", [False, True])
async def test_area_ignore_native_routing_or_legacy_fallback(
    hass, monkeypatch, native_available: bool
) -> None:
    """The native adapter proves routing only, not HA inheritance semantics."""
    label = lr.async_get(hass).async_create("Resolver routing exclusion")
    assert label.label_id != label.name
    areas = ar.async_get(hass)
    ignored = areas.async_create("Resolver ignored room", labels={label.label_id})
    control = areas.async_create("Resolver control room")
    registry = er.async_get(hass)
    entry = registry.async_get_or_create("sensor", "test_platform", "resolver_routing")
    entry = registry.async_update_entity(entry.entity_id, area_id=control.id)
    resolver = Mock(return_value=ignored.id)
    if native_available:
        monkeypatch.setattr(er, "async_get_effective_area_id", resolver, raising=False)
    else:
        monkeypatch.delattr(er, "async_get_effective_area_id", raising=False)
    coord = make_coordinator(hass, options={"ignore_labels": [label.label_id]})
    actual = coord._is_ignored(entry.entity_id, entry)
    assert actual is native_available
    if native_available:
        resolver.assert_called_once_with(hass, entry)
    else:
        entry = registry.async_update_entity(entry.entity_id, area_id=ignored.id)
        assert coord._is_ignored(entry.entity_id, entry) is True
        resolver.assert_not_called()
