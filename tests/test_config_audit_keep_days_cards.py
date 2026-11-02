"""Both dashboard cards show the purge tip whenever the recorder keeps more than 10 days, also with a filter."""

from __future__ import annotations

import pytest
from homeassistant.core import HomeAssistant

from tests.test_cards_v14_rendering import _attributes, _render, cards  # noqa: F401 - fixture

PURGE = "Keep `purge_keep_days` at 10 days or less"
FILTER = "Configure an `include` / `exclude` entity filter"


async def _base(hass: HomeAssistant) -> dict:
    attrs, _ = await _attributes(hass)
    return attrs


@pytest.mark.parametrize(
    ("keep", "filter_active", "purge_tip", "filter_tip"),
    [
        # long retention with an own filter: the case the outer guard used to hide
        (30, True, True, False),
        (30, False, True, True),
        (11, True, True, False),
        (10, True, False, False),  # everything earned: no tips
        (10, False, False, True),
        (None, True, True, False),
    ],
)
async def test_purge_and_filter_tips(
    hass,
    cards,  # noqa: F811 - fixture
    keep,
    filter_active,
    purge_tip,
    filter_tip,
) -> None:
    attrs = dict(await _base(hass), recorder_keep_days=keep, recorder_filter_active=filter_active)
    for name in ("Lite", "Pro"):
        rendered = _render(hass, cards[name], attrs)
        assert (PURGE in rendered, FILTER in rendered) == (purge_tip, filter_tip), name
