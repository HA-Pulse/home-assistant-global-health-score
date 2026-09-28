"""Ignore paths, registry skip rules and the safety-net branches."""

from __future__ import annotations

import asyncio
import logging
from datetime import timedelta
from types import SimpleNamespace

from homeassistant.const import STATE_UNAVAILABLE
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
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
