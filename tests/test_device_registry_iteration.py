"""The device registry is enumerated without the deprecated mapping access (HA 2026.9+)."""

from __future__ import annotations

import logging
from types import SimpleNamespace

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.helpers import device_registry as dr
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.haghs import coordinator as coordinator_module
from custom_components.haghs.const import DOMAIN
from tests.factories import make_coordinator

DEPRECATION = "uses `device_registry.devices` as a mapping"


@pytest.fixture(autouse=True)
def _reset_states(hass):
    yield
    for entry in hass.config_entries.async_entries():
        if entry.domain != DOMAIN:
            object.__setattr__(entry, "state", ConfigEntryState.NOT_LOADED)


async def test_empty_devices_without_deprecation_record(hass, caplog) -> None:
    owner = MockConfigEntry(domain="test_platform", data={})
    owner.add_to_hass(hass)
    object.__setattr__(owner, "state", ConfigEntryState.LOADED)
    dr.async_get(hass).async_get_or_create(
        config_entry_id=owner.entry_id, identifiers={("test", "leftover")}, name="leftover"
    )
    coord = make_coordinator(hass)
    coord._registries_ready = True

    with caplog.at_level(logging.DEBUG):
        assert coord._calc_empty_devices() == (["leftover"], 1)
    assert not [r for r in caplog.records if DEPRECATION in r.getMessage()]


def test_older_ha_registry_yields_ids() -> None:
    first, second = SimpleNamespace(id="a"), SimpleNamespace(id="b")
    known = {"a": first, "b": second}
    older = SimpleNamespace(devices=["a", "unknown", "b"], async_get=known.get)
    assert coordinator_module._device_entries(older) == [first, second]


def test_newer_ha_registry_yields_entries() -> None:
    first, second = SimpleNamespace(id="a"), SimpleNamespace(id="b")
    newer = SimpleNamespace(devices=[first, second], async_get=lambda _id: None)
    assert coordinator_module._device_entries(newer) == [first, second]


class _BothShapes:
    """A newer DeviceEntry that still has the deprecated shim; reading it must not happen."""

    config_entry_id = "entry-1"

    @property
    def config_entries(self) -> set[str]:
        raise AssertionError("config_entries must not be read when config_entry_id exists")


def test_config_entry_id_wins_without_touching_config_entries() -> None:
    assert coordinator_module._device_config_entry_ids(_BothShapes()) == {"entry-1"}
