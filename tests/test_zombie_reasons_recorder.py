"""More than 100 zombies cause no recorder attribute-size warning (#154, plan condition)."""

from __future__ import annotations

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.helpers.json import json_bytes
from pytest_homeassistant_custom_component.common import MockEntityPlatform
from pytest_homeassistant_custom_component.components.recorder.common import (
    async_wait_recording_done,
)

from custom_components.haghs.const import DOMAIN
from custom_components.haghs.sensor import HaghsSensor
from tests.test_zombie_reasons import _scenario_result


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations() -> None:
    """The recorder must start before hass; this module loads no custom integration."""
    return


async def test_no_attribute_size_warning_with_more_than_100_zombies(
    recorder_mock, hass: HomeAssistant, monkeypatch: pytest.MonkeyPatch, caplog
) -> None:
    """The real recorder stores the sensor with 113 zombies with long ids without a size warning."""
    coord, result = await _scenario_result(hass, monkeypatch, extra=105, long_ids=True)
    assert result["zombie_count"] == 113
    assert min(len(e) for e in result["zombie_entities"] if e.startswith("light.")) > 70
    coord.data = result
    sensor = HaghsSensor(coord, hass.config_entries.async_entries(DOMAIN)[0])
    await MockEntityPlatform(hass, domain="sensor", platform_name=DOMAIN).async_add_entities(
        [sensor]
    )
    sensor.async_write_ha_state()
    await async_wait_recording_done(hass)
    assert "exceed maximum size" not in caplog.text
    state = hass.states.get(sensor.entity_id)
    assert {"zombie_reasons", "zombie_since"} <= set(state.state_info["unrecorded_attributes"])
    recorded = {
        k: v for k, v in state.attributes.items() if k not in HaghsSensor._unrecorded_attributes
    }
    # Same compact encoder the recorder uses for shared attributes.
    assert len(json_bytes(recorded)) < 16384
    unrecorded = {k: state.attributes[k] for k in ("zombie_reasons", "zombie_since")}
    assert len(json_bytes(unrecorded)) > 8000  # the new data would matter if it were recorded
