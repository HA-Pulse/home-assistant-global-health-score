"""Tests for coordinator resilience (#103).

The coordinator must never raise: a failure in any scoring sub-component
must not kill the update cycle. These tests define the required behaviour
and are expected to FAIL against the current implementation (red).

See https://github.com/HA-Pulse/home-assistant-global-health-score/issues/103
"""

from __future__ import annotations

import pytest
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.haghs.const import DOMAIN
from custom_components.haghs.coordinator import HaghsDataUpdateCoordinator


def _raise(*_args: object, **_kwargs: object) -> None:
    """Stand-in for a scoring sub-component that fails unexpectedly."""
    raise RuntimeError("simulated failure in scoring sub-component")


async def test_update_data_never_raises_on_recommendations_failure(
    hass: HomeAssistant,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A failure in _build_recommendations must not raise out of the update (#103).

    The recommendations builder runs outside the _safe_calc safety net. If it
    raises, the exception propagates out of _async_update_data and can
    interrupt the DataUpdateCoordinator refresh cycle in Home Assistant Core.
    """
    entry = MockConfigEntry(domain=DOMAIN, data={})
    entry.add_to_hass(hass)
    hass.states.async_set("sensor.healthy_1", "100")

    coordinator = HaghsDataUpdateCoordinator(hass, entry)
    monkeypatch.setattr(coordinator, "_build_recommendations", _raise)

    result = await coordinator._async_update_data()

    assert result is not None
    assert "global_score" in result
    assert isinstance(result["global_score"], int)


async def test_update_data_never_raises_on_rec_flags_failure(
    hass: HomeAssistant,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A failure in _build_rec_flags must not raise out of the update (#103).

    _build_rec_flags is the second scoring sub-component outside the safety
    net. Same contract as the recommendations builder.
    """
    entry = MockConfigEntry(domain=DOMAIN, data={})
    entry.add_to_hass(hass)
    hass.states.async_set("sensor.healthy_1", "100")

    coordinator = HaghsDataUpdateCoordinator(hass, entry)
    monkeypatch.setattr(coordinator, "_build_rec_flags", _raise)

    result = await coordinator._async_update_data()

    assert result is not None
    assert "global_score" in result
    assert isinstance(result["global_score"], int)


async def test_update_data_keeps_last_result_on_failure(
    hass: HomeAssistant,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A failing cycle must keep the last valid score instead of raising (#103).

    The sensor must never lose its value: when a sub-component fails, the
    coordinator should return the previous successful result so the entity
    keeps reporting the last known health state.
    """
    entry = MockConfigEntry(domain=DOMAIN, data={})
    entry.add_to_hass(hass)
    hass.states.async_set("sensor.healthy_1", "100")

    coordinator = HaghsDataUpdateCoordinator(hass, entry)

    first = await coordinator._async_update_data()
    assert first is not None

    # HA Core's async_refresh stores each successful result in .data; the
    # fallback path returns that stored result when a later cycle fails.
    coordinator.data = first

    monkeypatch.setattr(coordinator, "_build_recommendations", _raise)
    second = await coordinator._async_update_data()

    assert second is not first
    assert second["global_score"] == first["global_score"]
    assert second["update_cycle_failed"] is True
    assert first.get("update_cycle_failed", False) is False


@pytest.mark.parametrize("retained", [False, True])
@pytest.mark.parametrize(
    "failure_point", ["_build_result", "_build_recommendations", "_build_rec_flags", "_rec"]
)
async def test_outer_failure_is_safe_and_current(hass, monkeypatch, retained, failure_point):
    """Even a broken text lookup must leave a warning and unchanged numeric data."""
    from copy import deepcopy
    from unittest.mock import AsyncMock

    from custom_components.haghs.coordinator import _ApplicationResult, _HardwareResult
    from tests.factories import make_coordinator

    coord = make_coordinator(hass)
    monkeypatch.setattr(
        coord, "_async_calc_hardware", AsyncMock(return_value=_HardwareResult(hardware_score=60))
    )
    monkeypatch.setattr(
        coord,
        "_async_calc_application",
        AsyncMock(return_value=_ApplicationResult(config_bonus=10)),
    )
    first = await coord._async_update_data()
    original = deepcopy(first)
    if retained:
        coord.data = first
    monkeypatch.setattr(coord, failure_point, _raise)
    result = await coord._async_update_data()
    assert result.get("update_cycle_failed") is True
    assert result["rec_update_failed"] is True
    assert result["pillar_fallbacks"] == []
    assert result["pillar_fallback_count"] == 0
    assert result["rec_pillar_fallback"] is False
    assert "✅" not in result["recommendations"]
    assert "update cycle failed" in result["recommendations"]
    assert result["global_score"] == (84 if retained else 100)
    assert first == original


@pytest.mark.parametrize("point", ["before", "after"])
@pytest.mark.parametrize("broken_translation", [False, True])
async def test_outer_failure_only_reports_observed_pillars(
    hass, monkeypatch, point, broken_translation
):
    """Old failures and unstarted pillars must not leak into the current attempt."""
    from copy import deepcopy
    from unittest.mock import AsyncMock

    from custom_components.haghs.coordinator import _ApplicationResult, _HardwareResult
    from tests.factories import make_coordinator

    coord = make_coordinator(hass)
    monkeypatch.setattr(
        coord, "_async_calc_hardware", AsyncMock(return_value=_HardwareResult(hardware_score=55))
    )
    monkeypatch.setattr(
        coord,
        "_async_calc_application",
        AsyncMock(return_value=_ApplicationResult(app_score=72, config_bonus=10)),
    )
    coord.data = await coord._async_update_data()
    original = deepcopy(coord.data)
    coord._pillar_fallbacks = {"application"}
    with monkeypatch.context() as patcher:
        if point == "before":
            patcher.setattr(coord, "_read_recorder_info", _raise)
        else:
            patcher.setattr(
                coord, "_async_calc_hardware", AsyncMock(side_effect=ValueError("boom"))
            )
            patcher.setattr(
                coord,
                "_async_load_rec_translations",
                AsyncMock(side_effect=ValueError("translation failed")),
            )
        if broken_translation:
            patcher.setattr(coord, "_rec", _raise)
        failed = await coord._async_update_data()
    assert failed["pillar_fallbacks"] == ([] if point == "before" else ["hardware"])
    assert failed["rec_update_failed"] is True
    assert failed["rec_pillar_fallback"] is (point == "after")
    assert "Application" not in failed["recommendations"]
    assert "✅" not in failed["recommendations"]
    assert coord.data == original
    for key, value in original.items():
        if (
            key != "recommendations"
            and not key.startswith("rec_")
            and key not in ("pillar_fallbacks", "pillar_fallback_count", "update_cycle_failed")
        ):
            assert failed[key] == value
    recovered = await coord._async_update_data()
    assert recovered["update_cycle_failed"] is False
    assert recovered["rec_update_failed"] is False
    assert recovered["pillar_fallbacks"] == []


async def test_outer_warning_survives_invalid_translation_value(hass, monkeypatch):
    """Invalid translated text must not break the emergency path itself."""
    from unittest.mock import AsyncMock

    from tests.factories import make_coordinator

    coord = make_coordinator(hass)
    monkeypatch.setattr(
        coord, "_async_update_data_inner", AsyncMock(side_effect=RuntimeError("boom"))
    )
    monkeypatch.setattr(coord, "_rec", lambda _key: None)
    result = await coord._async_update_data()
    assert result["rec_update_failed"] is True
    assert "update cycle failed" in result["recommendations"]
