"""With PSI the cards name the measured parts without a component count (#123 follow-up, doc audit v2.4.0b4).

`psi_available` covers CPU and memory PSI only; I/O PSI can be missing, so the card cannot know whether the pillar
uses 4 or 3 components.
"""

from __future__ import annotations

from homeassistant.core import HomeAssistant

from tests.factories import patch_psi
from tests.test_cards_v14_rendering import _attributes, _render, cards  # noqa: F401 - fixture

PSI = "PSI active (CPU + RAM + Disk, I/O when the kernel provides it)"


async def _base(hass: HomeAssistant) -> dict:
    with patch_psi(cpu=1.0, memory=1.0, io=None):
        attrs, _ = await _attributes(hass)
    return attrs


async def test_psi_line_has_no_component_count(hass, cards) -> None:  # noqa: F811
    attrs = dict(await _base(hass), psi_available=True, cpu_ram_source="psi")
    for name in ("Lite", "Pro"):
        rendered = _render(hass, cards[name], attrs)
        assert PSI in rendered, name
        assert "4 components" not in rendered, name
        assert "3 components" not in rendered, name


async def test_classic_line_names_its_components(hass, cards) -> None:  # noqa: F811
    attrs = dict(await _base(hass), psi_available=False, cpu_ram_source="sensors")
    for name in ("Lite", "Pro"):
        assert (
            "Classic sensors (CPU + RAM + Disk); I/O pressure counts when the kernel provides it"
            in _render(hass, cards[name], attrs)
        ), name
