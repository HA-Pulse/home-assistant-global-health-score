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

    assert second == first
