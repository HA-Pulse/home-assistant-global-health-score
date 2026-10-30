"""Unhealthy integration entries are listed by name (#134).

`integration_unhealthy_entries` names exactly the config entries that
`integration_unhealthy_count` counts, as sorted "domain: title" labels capped at
INTEGRATION_UNHEALTHY_LIST_CAP. Score, penalty, count and flag stay as before.
"""

from __future__ import annotations

import pytest
from homeassistant.config_entries import ConfigEntryState
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.haghs.const import DOMAIN
from custom_components.haghs.coordinator import _HardwareResult
from custom_components.haghs.sensor import HaghsSensor
from tests.factories import make_coordinator

CAP = 50  # INTEGRATION_UNHEALTHY_LIST_CAP, same size as REPAIR_LIST_CAP
COUNTED = (
    ConfigEntryState.SETUP_ERROR,
    ConfigEntryState.SETUP_RETRY,
    ConfigEntryState.FAILED_UNLOAD,
)


def _entry(hass, domain: str, title: str, state: ConfigEntryState) -> MockConfigEntry:
    entry = MockConfigEntry(domain=domain, title=title, data={})
    entry.add_to_hass(hass)
    object.__setattr__(entry, "state", state)
    return entry


@pytest.fixture(autouse=True)
def _reset_states(hass):
    """No actual integration was loaded: avoid fake states at teardown, also after a failure."""
    yield
    for entry in hass.config_entries.async_entries():
        if entry.domain != DOMAIN:
            object.__setattr__(entry, "state", ConfigEntryState.NOT_LOADED)


async def test_counted_entries_are_listed_sorted(hass) -> None:
    _entry(hass, "zwave_js", "Z-Wave", ConfigEntryState.LOADED)
    _entry(hass, "hue", "Bridge", ConfigEntryState.NOT_LOADED)
    _entry(hass, "sonos", "Sonos", ConfigEntryState.SETUP_IN_PROGRESS)
    _entry(hass, "shelly", "Garage", ConfigEntryState.FAILED_UNLOAD)
    _entry(hass, "mqtt", "Mosquitto broker", ConfigEntryState.SETUP_ERROR)
    _entry(hass, "esphome", "Kitchen", ConfigEntryState.SETUP_RETRY)
    coord = make_coordinator(hass)

    assert coord._list_unhealthy_integrations() == [
        "esphome: Kitchen",
        "mqtt: Mosquitto broker",
        "shelly: Garage",
    ]
    assert coord._count_unhealthy_integrations() == 3


async def test_same_integration_twice_and_empty_title(hass) -> None:
    _entry(hass, "mqtt", "Broker B", ConfigEntryState.SETUP_RETRY)
    _entry(hass, "mqtt", "Broker A", ConfigEntryState.SETUP_ERROR)
    _entry(hass, "tuya", "", ConfigEntryState.SETUP_ERROR)
    coord = make_coordinator(hass)

    assert coord._list_unhealthy_integrations() == ["mqtt: Broker A", "mqtt: Broker B", "tuya"]
    assert coord._count_unhealthy_integrations() == 3


async def test_ignored_entry_is_neither_listed_nor_counted(hass) -> None:
    ignored = _entry(hass, "androidtv", "Fire TV", ConfigEntryState.SETUP_RETRY)
    _entry(hass, "androidtv", "Shield", ConfigEntryState.SETUP_RETRY)
    coord = make_coordinator(hass, options={"ignored_integration_entries": [ignored.entry_id]})

    assert coord._list_unhealthy_integrations() == ["androidtv: Shield"]
    assert coord._count_unhealthy_integrations() == 1


async def test_list_is_capped_and_count_stays_full(hass) -> None:
    total = CAP + 5
    for index in range(total):
        _entry(hass, "demo", f"Entry {index:03d}", COUNTED[index % 3])
    coord = make_coordinator(hass)

    app = await coord._async_calc_application()
    result = coord._build_result(_HardwareResult(), app)
    assert result["integration_unhealthy_count"] == total
    assert result["integration_unhealthy_entries"] == [
        f"demo: Entry {index:03d}" for index in range(CAP)
    ]


@pytest.mark.parametrize("failing", [0, 1, 2])
async def test_result_list_matches_count_and_score(hass, failing: int) -> None:
    for index in range(failing):
        _entry(hass, "demo", f"Entry {index}", ConfigEntryState.SETUP_ERROR)
    coord = make_coordinator(hass)

    app = await coord._async_calc_application()
    result = coord._build_result(_HardwareResult(), app)
    assert result["integration_unhealthy_entries"] == [f"demo: Entry {i}" for i in range(failing)]
    assert len(result["integration_unhealthy_entries"]) == result["integration_unhealthy_count"]
    assert result["integration_unhealthy_count"] == failing
    assert result["rec_integration_health"] is (failing > 0)
    assert app.app_score == 100 - 5 * failing


async def test_sensor_attribute_unrecorded_and_neutral_default(hass) -> None:
    coord = make_coordinator(hass)
    assert coord._neutral_result()["integration_unhealthy_entries"] == []

    coord.data = {**coord._neutral_result(), "integration_unhealthy_entries": ["mqtt: Broker"]}
    sensor = HaghsSensor(coord, hass.config_entries.async_entries(DOMAIN)[0])
    assert sensor.extra_state_attributes["integration_unhealthy_entries"] == ["mqtt: Broker"]
    assert "integration_unhealthy_entries" in HaghsSensor._unrecorded_attributes
