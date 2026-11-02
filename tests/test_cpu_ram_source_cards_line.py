"""Both dashboard cards (v1.4) read cpu_ram_source: a status line and a matching metric source (#123 follow-up)."""

from __future__ import annotations

import pytest
from homeassistant.core import HomeAssistant

from tests.factories import patch_psi
from tests.test_cards_v14_rendering import _attributes, _render, cards  # noqa: F401 - fixture

NONE = "📊 CPU/RAM not measured (no PSI, no sensor selected); the hardware score uses the other components."
PART = "📊 CPU/RAM partly measured (no PSI, one sensor missing); the hardware score uses the measured components."
CLASSIC = "Classic sensors (CPU + RAM + Disk)"
PSI = "PSI active (CPU + RAM + I/O + Disk)"
MEASURED = "hardware score uses the measured components"


async def _base(hass: HomeAssistant) -> dict:
    with patch_psi(cpu=1.0, memory=1.0, io=1.0):
        attrs, _ = await _attributes(hass)
    return attrs


@pytest.mark.parametrize(
    ("source", "psi", "line", "metric"),
    [
        ("none", False, NONE, "No PSI and no CPU/RAM sensor selected"),
        ("partial", False, PART, "No PSI and one CPU/RAM sensor selected"),
        ("psi", True, None, PSI),
        ("sensors", False, None, CLASSIC),
        (None, False, None, CLASSIC),
    ],
)
async def test_line_and_metric_source_per_value(hass, cards, source, psi, line, metric) -> None:  # noqa: F811
    attrs = dict(await _base(hass), cpu_ram_source=source, psi_available=psi)
    for name in ("Lite", "Pro"):
        rendered = _render(hass, cards[name], attrs)
        assert (NONE in rendered, PART in rendered) == (line == NONE, line == PART), name
        assert metric in rendered, name
        assert (MEASURED in rendered) is (source in ("none", "partial")), name


async def test_an_older_haghs_without_the_attribute_shows_nothing_new(hass, cards) -> None:  # noqa: F811
    attrs = {k: v for k, v in (await _base(hass)).items() if k != "cpu_ram_source"}
    for name in ("Lite", "Pro"):
        rendered = _render(hass, cards[name], attrs)
        assert NONE not in rendered, name
        assert PART not in rendered, name
        assert MEASURED not in rendered, name
