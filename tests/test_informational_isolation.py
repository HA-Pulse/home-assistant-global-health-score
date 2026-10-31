"""Informational checks fail on their own (dead devices, empty devices, zombie reasons).

A failure in a check that carries no points must leave only its own attributes empty; the
pillars, the score and every other value are computed as without the error. The failure is
logged as one WARNING per failure streak.
"""

from __future__ import annotations

import logging
from datetime import timedelta

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import STATE_ON, STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import issue_registry as ir
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.haghs.const import DOMAIN
from tests.factories import make_coordinator, patch_disk, patch_psi

INFORMATIONAL = {
    "empty": {"empty_device_count", "empty_devices", "empty_device_ids", "rec_empty_devices"},
    "dead": {"dead_device_count", "dead_devices", "dead_device_ids", "rec_dead_devices"},
    "reasons": {"zombie_count_per_reason", "zombie_reasons"},
}
PREFIX = {"empty": "🗂️", "dead": "🔌"}


@pytest.fixture(autouse=True)
def _reset_states(hass):
    """No integration was really loaded: avoid fake loaded states at teardown."""
    yield
    for entry in hass.config_entries.async_entries():
        if entry.domain != DOMAIN:
            object.__setattr__(entry, "state", ConfigEntryState.NOT_LOADED)


def _scenario(hass: HomeAssistant):
    """A zombie on a loaded entry (dead device), an empty device, a repair and a stale backup."""
    owner = MockConfigEntry(domain="test_platform", data={})
    owner.add_to_hass(hass)
    object.__setattr__(owner, "state", ConfigEntryState.LOADED)
    devices = dr.async_get(hass)
    devices.async_get_or_create(
        config_entry_id=owner.entry_id, identifiers={("test", "leftover")}, name="leftover"
    )
    plug = devices.async_get_or_create(
        config_entry_id=owner.entry_id, identifiers={("test", "plug")}, name="plug"
    )
    entity = er.async_get(hass).async_get_or_create(
        "sensor",
        "test_platform",
        "uid_plug",
        suggested_object_id="plug_power",
        device_id=plug.id,
        config_entry=owner,
    )
    hass.states.async_set(entity.entity_id, STATE_UNAVAILABLE)
    hass.states.get(entity.entity_id).last_changed = dt_util.utcnow() - timedelta(minutes=30)
    ir.async_create_issue(
        hass,
        "other_integration",
        "broken",
        is_fixable=False,
        severity=ir.IssueSeverity.ERROR,
        translation_key="broken",
    )
    hass.states.async_set("binary_sensor.backups_stale", STATE_ON)
    coord = make_coordinator(hass)
    coord._registries_ready = True
    return coord


async def _update(coord):
    with patch_psi(cpu=0.0, memory=0.0, io=0.0), patch_disk():
        return await coord._async_update_data()


def _without(result: dict, kinds: tuple[str, ...]) -> dict:
    keys = set().union(*(INFORMATIONAL[kind] for kind in kinds))
    prefixes = tuple(PREFIX[kind] for kind in kinds if kind in PREFIX)
    kept = {key: value for key, value in result.items() if key not in keys}
    kept["recommendations"] = "\n".join(
        line for line in result["recommendations"].split("\n") if not line.startswith(prefixes)
    )
    return kept


def _warnings(caplog) -> list[str]:
    return [
        r.getMessage()
        for r in caplog.records
        if r.levelno >= logging.WARNING and r.name.startswith("custom_components.haghs")
    ]


async def test_async_get_entry_failure_keeps_the_score(hass, monkeypatch, caplog) -> None:
    """Deniz's test: async_get_entry raises → score identical to the run without the error."""
    coord = _scenario(hass)
    clean = await _update(coord)
    assert clean["empty_devices"] == ["leftover"]
    assert clean["dead_devices"] == ["plug"]
    assert clean["zombie_reasons"] == {"sensor.plug_power": "unavailable"}
    assert clean["repair_count"] == 1
    assert clean["rec_backup_stale"] is True
    assert clean["application_score"] < 100

    def _raise(_entry_id):
        raise RuntimeError("simulated async_get_entry failure")

    monkeypatch.setattr(hass.config_entries, "async_get_entry", _raise)
    caplog.clear()
    failed = await _update(coord)

    assert failed["global_score"] == clean["global_score"]
    assert failed["hardware_score"] == clean["hardware_score"]
    assert failed["application_score"] == clean["application_score"]
    assert failed["pillar_fallback_count"] == 0
    assert _without(failed, ("empty", "reasons")) == _without(clean, ("empty", "reasons"))
    assert (failed["empty_device_count"], failed["empty_devices"]) == (0, [])
    assert failed["empty_device_ids"] == []
    assert failed["rec_empty_devices"] is False
    assert (failed["zombie_reasons"], failed["zombie_count_per_reason"]) == ({}, {})
    assert _warnings(caplog) == [
        "HAGHS: zombie reasons check failed; its attributes stay empty and the score is not affected",
        "HAGHS: empty devices check failed; its attributes stay empty and the score is not affected",
    ]


async def test_dead_device_failure_warns_once_per_streak(hass, monkeypatch, caplog) -> None:
    coord = _scenario(hass)
    clean = await _update(coord)
    original = coord._calc_dead_devices

    def _raise():
        raise RuntimeError("simulated dead-device failure")

    monkeypatch.setattr(coord, "_calc_dead_devices", _raise)
    caplog.clear()
    failed = await _update(coord)
    assert _without(failed, ("dead",)) == _without(clean, ("dead",))
    assert (failed["dead_device_count"], failed["dead_devices"], failed["rec_dead_devices"]) == (
        0,
        [],
        False,
    )
    assert failed["dead_device_ids"] == []
    assert len(_warnings(caplog)) == 1

    caplog.clear()
    await _update(coord)
    assert _warnings(caplog) == []

    monkeypatch.setattr(coord, "_calc_dead_devices", original)
    assert (await _update(coord))["dead_devices"] == ["plug"]
    monkeypatch.setattr(coord, "_calc_dead_devices", _raise)
    caplog.clear()
    await _update(coord)
    assert _warnings(caplog) == [
        "HAGHS: dead devices check failed; its attributes stay empty and the score is not affected"
    ]


async def test_zombie_reason_failure_keeps_zombies_and_penalty(hass, monkeypatch, caplog) -> None:
    coord = _scenario(hass)
    # A second zombie: after the first reason failure the lookup must not run again.
    second = er.async_get(hass).async_get_or_create(
        "sensor", "test_platform", "uid_lamp", suggested_object_id="lamp_power"
    )
    hass.states.async_set(second.entity_id, STATE_UNAVAILABLE)
    hass.states.get(second.entity_id).last_changed = dt_util.utcnow() - timedelta(minutes=30)
    clean = await _update(coord)
    assert clean["zombie_count"] == 2
    assert clean["zombie_count_per_reason"] == {"unavailable": 2}
    original = coord._zombie_reason
    calls: list[str] = []

    def _raise(state, _entry):
        calls.append(state.entity_id)
        raise RuntimeError("simulated reason failure")

    monkeypatch.setattr(coord, "_zombie_reason", _raise)
    caplog.clear()
    failed = await _update(coord)
    assert len(calls) == 1
    for key in (
        "zombie_count",
        "zombie_entities",
        "zombie_since",
        "zombie_count_per_domain",
        "zombie_count_per_integration",
        "application_score",
        "global_score",
    ):
        assert failed[key] == clean[key], key
    assert (failed["zombie_reasons"], failed["zombie_count_per_reason"]) == ({}, {})
    assert _warnings(caplog) == [
        "HAGHS: zombie reasons check failed; its attributes stay empty and the score is not affected"
    ]

    # Still failing: no second WARNING; after a clean cycle a new failure warns again.
    caplog.clear()
    await _update(coord)
    assert _warnings(caplog) == []
    monkeypatch.setattr(coord, "_zombie_reason", original)
    assert (await _update(coord))["zombie_count_per_reason"] == {"unavailable": 2}
    monkeypatch.setattr(coord, "_zombie_reason", _raise)
    caplog.clear()
    await _update(coord)
    assert _warnings(caplog) == [
        "HAGHS: zombie reasons check failed; its attributes stay empty and the score is not affected"
    ]
