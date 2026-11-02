"""The Pro card names the recorder retention it reads; Home Assistant always sets one while the recorder runs."""

from __future__ import annotations

from homeassistant.core import HomeAssistant

from tests.test_cards_v14_rendering import _attributes, _render, cards  # noqa: F401 - fixture


async def _base(hass: HomeAssistant) -> dict:
    attrs, _ = await _attributes(hass)
    return attrs


async def test_retention_is_shown_in_days(hass, cards) -> None:  # noqa: F811
    rendered = _render(hass, cards["Pro"], dict(await _base(hass), recorder_keep_days=10))
    assert "Recorder keeps 10 days of history" in rendered
    assert "no purge configured" not in rendered


async def test_without_a_recorder_the_card_says_so(hass, cards) -> None:  # noqa: F811
    rendered = _render(hass, cards["Pro"], dict(await _base(hass), recorder_keep_days=None))
    assert "Recorder not found" in rendered
