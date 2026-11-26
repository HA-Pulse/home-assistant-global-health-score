"""Reading parents of child devices never touches ``ChildDeviceEntry.via_device_id`` (#214).

HA 2026.11 logs "accesses ChildDeviceEntry.via_device_id, which does not exist on child devices" for every
custom integration that reads it, and the access stops working in 2027.9.0. Child devices hang off their parent
only through ``parent_device_id``.
"""

from __future__ import annotations

import logging

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import frame
from pytest_homeassistant.common import MockConfigEntry

from custom_components.haghs import coordinator as coordinator_module
from custom_components.haghs.const import DOMAIN
from tests.factories import HAS_CHILD_DEVICES, device_entries, make_coordinator

pytestmark = pytest.mark.skipif(
    not HAS_CHILD_DEVICES, reason="child devices need Home Assistant 2026.11"
)

WARNING = "accesses ChildDeviceEntry.via_device_id"


@pytest.fixture(autouse=True)
def _fresh_frame_reports(monkeypatch):
    """HA reports each integration frame once per process: start every test with an empty record."""
    monkeypatch.setattr(frame, "_REPORTED_INTEGRATIONS", set())


@pytest.fixture(autouse=True)
def _reset_states(hass):
    """No integration was really loaded: avoid fake loaded states at teardown."""
    yield
    for entry in hass.config_entries.async_entries():
        if entry.domain != DOMAIN:
            object.__setattr__(entry, "state", ConfigEntryState.NOT_LOADED)


def _setup(hass):
    owner = MockConfigEntry(domain="test_platform", data={})
    owner.add_to_hass(hass)
    object.__setattr__(owner, "state", ConfigEntryState.LOADED)
    dev_reg = dr.async_get(hass)
    parent = dev_reg.async_get_or_create(
        config_entry_id=owner.entry_id, identifiers={("test_child", "washer")}, name="washer"
    )
    child = dev_reg.async_get_or_create_child(
        config_entry_id=owner.entry_id,
        identifiers={("test_child", "washer pump")},
        name="washer pump",
        parent_device_id=parent.id,
    )
    er.async_get(hass).async_get_or_create(
        "sensor", "test_platform", "uid_pump", suggested_object_id="pump_power", device_id=child.id
    )
    return dev_reg, parent


def _child_warnings(caplog) -> list[str]:
    return [r.getMessage() for r in caplog.records if WARNING in r.getMessage()]


async def test_parent_ids_of_child_devices_log_no_via_device_warning(hass, caplog) -> None:
    dev_reg, parent = _setup(hass)
    caplog.set_level(logging.WARNING)

    assert coordinator_module._parent_device_ids(dev_reg, device_entries(dev_reg)) == {parent.id}
    assert _child_warnings(caplog) == []


async def test_empty_device_check_with_child_devices_logs_no_via_device_warning(
    hass, caplog
) -> None:
    _setup(hass)
    caplog.set_level(logging.WARNING)
    coord = make_coordinator(hass)
    coord._registries_ready = True

    assert coord._calc_empty_devices() == ([], 0)
    assert _child_warnings(caplog) == []
