"""Current-attempt visibility without changes to numeric fallbacks (#135)."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

import pytest

from custom_components.haghs import coordinator as coordinator_module
from custom_components.haghs.coordinator import _ApplicationResult, _HardwareResult
from custom_components.haghs.sensor import HaghsSensor
from tests.factories import make_coordinator


async def test_stale_defaults_in_application_fallback(hass, monkeypatch):
    coord = make_coordinator(hass)
    monkeypatch.setattr(
        coord, "_async_calc_application", AsyncMock(side_effect=RuntimeError("stale calculation"))
    )
    result = await coord._async_update_data()
    assert result["pillar_fallbacks"] == ["application"]
    assert (
        result["stale_candidate_count"]
        == result["stale_watch_count"]
        == result["stale_penalty"]
        == 0
    )
    assert result["stale_candidates"] == result["stale_watch_entities"] == []
    assert result["stale_threshold_hours"] == 24
    assert result["rec_stale"] is False


async def test_application_failure_is_visible_without_invented_diagnosis(hass, monkeypatch):
    """An unmeasured application pillar must not imply a missing audit bonus."""
    coord = make_coordinator(hass)
    monkeypatch.setattr(coord, "_async_calc_hardware", AsyncMock(return_value=_HardwareResult()))
    monkeypatch.setattr(
        coord, "_async_calc_application", AsyncMock(side_effect=RuntimeError("boom"))
    )
    result = await coord._async_update_data()
    assert result.get("pillar_fallbacks") == ["application"]
    assert result["pillar_fallback_count"] == 1
    assert result["rec_pillar_fallback"] is True
    assert result["rec_update_failed"] is False
    assert result["update_cycle_failed"] is False
    assert result["global_score"] == 100
    assert result["application_score"] == _ApplicationResult().app_score
    assert result["config_audit_bonus"] == 0
    assert result["rec_config_audit"] is False
    assert "Application" in result["recommendations"]
    assert "Config-Audit" not in result["recommendations"]
    assert "✅" not in result["recommendations"]


async def test_neutral_result_includes_empty_failure_attributes(hass):
    coord = make_coordinator(hass)
    result = coord._neutral_result()
    assert result["pillar_fallbacks"] == []
    assert result["pillar_fallback_count"] == 0
    assert result["update_cycle_failed"] is False
    assert result["rec_pillar_fallback"] is False
    assert result["rec_update_failed"] is False


async def test_sensor_exports_current_failures(hass, monkeypatch):
    coord = make_coordinator(hass)
    monkeypatch.setattr(coord, "_async_calc_hardware", AsyncMock(side_effect=RuntimeError("boom")))
    monkeypatch.setattr(
        coord,
        "_async_calc_application",
        AsyncMock(return_value=_ApplicationResult(config_bonus=10)),
    )
    coord.data = await coord._async_update_data()
    sensor = HaghsSensor(coord, hass.config_entries.async_entries("haghs")[0])
    attrs = sensor.extra_state_attributes
    assert attrs.get("pillar_fallbacks") == ["hardware"]
    assert attrs["pillar_fallback_count"] == 1
    assert attrs["update_cycle_failed"] is False
    assert attrs["rec_pillar_fallback"] is True
    assert attrs["rec_update_failed"] is False


@pytest.mark.parametrize("pillars", [("hardware",), ("application",), ("hardware", "application")])
@pytest.mark.parametrize("failure", ["exception", "timeout"])
async def test_failure_matrix_and_recovery(hass, monkeypatch, pillars, failure):
    coord = make_coordinator(hass)
    hw = _HardwareResult(hardware_score=60, p_cpu=40, cpu=90)
    app = _ApplicationResult(app_score=70, config_bonus=10, p_backup=30)
    monkeypatch.setattr(coord, "_async_calc_hardware", AsyncMock(return_value=hw))
    monkeypatch.setattr(coord, "_async_calc_application", AsyncMock(return_value=app))
    monkeypatch.setattr(coordinator_module, "PILLAR_TIMEOUT", 0.01)

    async def fail():
        if failure == "timeout":
            await asyncio.Event().wait()
        raise RuntimeError("pillar failed")

    with monkeypatch.context() as patcher:
        for pillar in pillars:
            patcher.setattr(coord, f"_async_calc_{pillar}", fail)
        result = await coord._async_update_data()
    assert result["pillar_fallbacks"] == list(pillars)
    assert result["pillar_fallback_count"] == len(pillars)
    assert result["rec_pillar_fallback"] is True
    assert "✅" not in result["recommendations"]
    for pillar in pillars:
        assert result["recommendations"].count(pillar.title()) == 1
    assert result["hardware_score"] == (100 if "hardware" in pillars else 60)
    assert result["application_score"] == (100 if "application" in pillars else 70)
    expected = {("hardware",): 82, ("application",): 84, ("hardware", "application"): 100}
    assert result["global_score"] == expected[pillars]
    assert result["rec_cpu_load"] is ("hardware" not in pillars)
    assert result["rec_backup_stale"] is ("application" not in pillars)
    assert result["rec_config_audit"] is False
    recovered = await coord._async_update_data()
    assert recovered["pillar_fallbacks"] == []
    assert recovered["pillar_fallback_count"] == 0
    assert recovered["rec_pillar_fallback"] is False
    assert recovered["rec_update_failed"] is False
    assert recovered["update_cycle_failed"] is False
    assert "Calculation:" not in recovered["recommendations"]
    assert recovered["global_score"] == 66


async def test_cancellation_propagates(hass, monkeypatch):
    coord = make_coordinator(hass)
    monkeypatch.setattr(
        coord, "_async_calc_hardware", AsyncMock(side_effect=asyncio.CancelledError)
    )
    with pytest.raises(asyncio.CancelledError):
        await coord._async_update_data()
    assert coord._failure_attributes()["pillar_fallbacks"] == []
