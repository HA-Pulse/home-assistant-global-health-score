"""#123 follow-up: with PSI or with both sensors, score and every attribute stay as on dev.

The pins in tests/data/cpu_ram_source_dev.json are the complete results of the same scenarios on dev
bcc2e46 before this change, captured on a clean checkout of that commit without PR code, clock frozen at
FROZEN. Only the two new keys are added; their values are compared exactly.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from homeassistant.core import HomeAssistant

from custom_components.haghs.const import CONF_CPU_SENSOR, CONF_RAM_SENSOR, CONF_STORAGE_TYPE
from tests.factories import GB, make_coordinator, patch_disk, patch_psi

FROZEN = "2026-11-01T08:00:00+00:00"
PINS = json.loads(
    (Path(__file__).parent / "data" / "cpu_ram_source_dev.json").read_text(encoding="utf-8")
)
NEW_KEYS = {"cpu_ram_source", "rec_cpu_ram_unmeasured"}

# name -> (PSI values, configured sensors with their states)
SCENARIOS = {
    "psi": (dict(cpu=10.0, memory=20.0, io=5.0), {}),
    "psi_without_io": (dict(cpu=10.0, memory=20.0, io=None), {}),
    "sensors": ({}, {"sensor.cpu": "30", "sensor.ram": "75"}),
    "sensors_with_io": (dict(io=5.0), {"sensor.cpu": "30", "sensor.ram": "75"}),
}


async def scenario_result(hass: HomeAssistant, name: str) -> dict:
    psi, sensors = SCENARIOS[name]
    data = {CONF_STORAGE_TYPE: "ssd"}
    if sensors:
        data |= {CONF_CPU_SENSOR: "sensor.cpu", CONF_RAM_SENSOR: "sensor.ram"}
    coord = make_coordinator(hass, data=data)
    for entity_id, state in sensors.items():
        hass.states.async_set(entity_id, state)
    with patch_psi(**psi), patch_disk(total=100 * GB, free=8 * GB, percent=92.0):
        hw = await coord._async_calc_hardware()
        app = await coord._async_calc_application()
    coord._rec_translations = await coord._async_load_rec_translations()
    return coord._build_result(hw, app)


@pytest.mark.parametrize("name", sorted(SCENARIOS))
async def test_score_and_every_attribute_unchanged(hass: HomeAssistant, freezer, name: str) -> None:
    freezer.move_to(FROZEN)
    result = await scenario_result(hass, name)
    assert set(result) == set(PINS[name]) | NEW_KEYS
    assert {key: value for key, value in result.items() if key not in NEW_KEYS} == PINS[name]
    expected = "psi" if name.startswith("psi") else "sensors"
    assert (result["cpu_ram_source"], result["rec_cpu_ram_unmeasured"]) == (expected, False)
