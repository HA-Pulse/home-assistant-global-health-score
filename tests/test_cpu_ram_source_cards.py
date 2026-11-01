"""#123 follow-up: both README cards (v1.4) show "CPU/RAM not measured", and only when it is true.

`none`/`partial` come with the 📊 recommendation line, which neither card filters. `null` means the whole hardware
pillar has no measurement (first failed update, hardware fallback); the cards then show their calculation status
line instead, and no CPU/RAM line.
"""

from __future__ import annotations

from homeassistant.core import HomeAssistant

from custom_components.haghs.const import REC_CPU_RAM_UNMEASURED, REC_TEMPLATES
from tests.factories import patch_psi
from tests.test_cards_v14_rendering import _attributes, _render, cards  # noqa: F401 - fixture

LINE = REC_CPU_RAM_UNMEASURED.split(";")[0]  # "📊 Hardware: CPU and/or RAM are not measured (…)"


async def test_both_cards_show_the_unmeasured_line(hass: HomeAssistant, cards) -> None:  # noqa: F811
    with patch_psi():  # no PSI, and the test instance selects no sensors
        attrs, _ = await _attributes(hass)
    assert (attrs["cpu_ram_source"], attrs["rec_cpu_ram_unmeasured"]) == ("none", True)
    for name in ("Lite", "Pro"):
        assert LINE in _render(hass, cards[name], attrs), name


async def test_measured_source_shows_no_line(hass: HomeAssistant, cards) -> None:  # noqa: F811
    with patch_psi(cpu=1.0, memory=1.0, io=1.0):
        attrs, _ = await _attributes(hass)
    assert (attrs["cpu_ram_source"], attrs["rec_cpu_ram_unmeasured"]) == ("psi", False)
    for name in ("Lite", "Pro"):
        assert LINE not in _render(hass, cards[name], attrs), name


async def test_null_source_shows_the_calculation_line_not_the_cpu_ram_line(
    hass: HomeAssistant,
    cards,  # noqa: F811
) -> None:
    attrs, _ = await _attributes(hass)
    fallback = REC_TEMPLATES["rec_pillar_fallback"].format(pillars="Hardware")
    failed = dict(
        attrs,
        cpu_ram_source=None,
        rec_cpu_ram_unmeasured=False,
        pillar_fallback_count=1,
        pillar_fallbacks=["hardware"],
        rec_pillar_fallback=True,
        recommendations=fallback,
    )
    for name in ("Lite", "Pro"):
        rendered = _render(hass, cards[name], failed)
        assert LINE not in rendered, name
        assert "Hardware" in rendered, name
        assert "failed or timed out" in rendered, name
