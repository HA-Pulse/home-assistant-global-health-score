"""The Integration Health recommendation names config entries, not integrations.

`integration_unhealthy_count` counts config entries; one integration with two failing entries
counts 2. The recommendation therefore says "integration entry(ies)" (English and pt-BR).
"""

from __future__ import annotations

import json
from pathlib import Path

from homeassistant.config_entries import ConfigEntryState
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.haghs.const import DOMAIN
from custom_components.haghs.coordinator import _HardwareResult
from tests.factories import make_coordinator

TRANSLATIONS = Path(__file__).resolve().parents[1] / "custom_components/haghs/translations"


async def test_two_entries_of_one_integration_are_named_entries(hass) -> None:
    for title in ("Broker A", "Broker B"):
        entry = MockConfigEntry(domain="mqtt", title=title, data={})
        entry.add_to_hass(hass)
        object.__setattr__(entry, "state", ConfigEntryState.SETUP_ERROR)
    coord = make_coordinator(hass)

    app = await coord._async_calc_application()
    advice = coord._build_recommendations(_HardwareResult(), app)
    assert "🧩 Integrations: 2 integration entry(ies) failed to set up." in advice
    for entry in hass.config_entries.async_entries():
        if entry.domain != DOMAIN:
            object.__setattr__(entry, "state", ConfigEntryState.NOT_LOADED)


def test_translations_name_entries() -> None:
    english = json.loads((TRANSLATIONS / "en.json").read_text(encoding="utf-8"))
    portuguese = json.loads((TRANSLATIONS / "pt-BR.json").read_text(encoding="utf-8"))
    assert (
        english["common"]["rec_integration_health"]
        == "🧩 Integrations: {count} integration entry(ies) failed to set up."
    )
    assert (
        portuguese["common"]["rec_integration_health"]
        == "🧩 Integrações: falha na configuração de {count} entrada(s) de integração."
    )
