"""Render the unchanged README dashboard YAML with actual coordinator results."""

from __future__ import annotations

import re
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
import yaml
from homeassistant.helpers.template import Template

from custom_components.haghs.coordinator import _ApplicationResult, _HardwareResult
from custom_components.haghs.sensor import HaghsSensor
from tests.factories import make_coordinator


@pytest.fixture
def readme_text():
    """Read source YAML outside the asynchronous template evaluation."""
    return (Path(__file__).resolve().parents[1] / "README.md").read_text()


@pytest.mark.parametrize("card_name", ["Lite", "Pro"])
@pytest.mark.parametrize("scenario", ["healthy", "old", "hardware", "application", "both", "outer"])
async def test_existing_dashboard_failure_visibility(
    hass, monkeypatch, card_name, scenario, readme_text
):
    """Both original advisors show the current warning, never a general all-clear."""
    section = readme_text.split(f"### HAGHS {card_name} v1.4", 1)[1]
    snippet = re.search(r"```yaml\n(.*?)```", section, re.DOTALL).group(1)
    card = yaml.safe_load(snippet)
    coord = make_coordinator(hass)
    monkeypatch.setattr(coord, "_async_calc_hardware", AsyncMock(return_value=_HardwareResult()))
    monkeypatch.setattr(
        coord,
        "_async_calc_application",
        AsyncMock(return_value=_ApplicationResult(config_bonus=10)),
    )
    if scenario in ("hardware", "both"):
        monkeypatch.setattr(
            coord, "_async_calc_hardware", AsyncMock(side_effect=RuntimeError("boom"))
        )
    if scenario in ("application", "both"):
        monkeypatch.setattr(
            coord, "_async_calc_application", AsyncMock(side_effect=RuntimeError("boom"))
        )
    if scenario == "outer":
        monkeypatch.setattr(coord, "_read_recorder_info", lambda: 1 / 0)
    coord.data = await coord._async_update_data()
    sensor = HaghsSensor(coord, hass.config_entries.async_entries("haghs")[0])
    attrs = sensor.extra_state_attributes
    if scenario == "old":
        attrs = {
            key: value
            for key, value in attrs.items()
            if key
            not in {
                "pillar_fallback_count",
                "pillar_fallbacks",
                "update_cycle_failed",
                "rec_pillar_fallback",
                "rec_update_failed",
            }
        }
    hass.states.async_set("sensor.system_ha_global_health_score", sensor.native_value, attrs)
    outputs = [
        Template(item["content"], hass).async_render(parse_result=False)
        for item in card["cards"]
        if item["type"] == "markdown"
    ]
    rendered = "\n".join(outputs)
    if scenario in ("healthy", "old"):
        assert "System healthy. No recommendations." in rendered
        assert "Calculation:" not in rendered
    else:
        assert "Calculation:" in rendered
        assert "System healthy" not in rendered
        assert "Nothing beyond the cards below" not in rendered
        if scenario in ("hardware", "both"):
            assert "Hardware" in rendered
            assert "Hardware" in coord.data["recommendations"]
        if scenario in ("application", "both"):
            assert "Application" in coord.data["recommendations"]
        if scenario == "outer":
            assert "update cycle failed" in rendered
            # v1.4: the language-independent status line from update_cycle_failed.
            assert "The last update cycle failed; previous results are shown." in rendered
        else:
            # v1.4: the language-independent status line from pillar_fallbacks.
            assert "Calculation incomplete:" in rendered
    if scenario in ("healthy", "old"):
        assert "Calculation incomplete:" not in rendered
        assert "The last update cycle failed" not in rendered
