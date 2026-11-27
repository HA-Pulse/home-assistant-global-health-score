"""Lite and Pro cards show "no successful automatic backup known" once, with a link to the backup settings (#218)."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant

from custom_components.haghs.const import DOMAIN, REC_BACKUP_NO_SCHEDULE, REC_BACKUP_UNKNOWN
from tests.test_cards_v14_rendering import _attributes, _render

LINES = {
    "not_configured": "💾 No automatic backup schedule",
    "unknown": "💾 No successful automatic backup reported",
}


@pytest.fixture
def cards():
    """Both card configurations (docs/cards/), read outside the event loop."""
    folder = Path(__file__).resolve().parents[1] / "docs" / "cards"
    return {
        name: yaml.safe_load((folder / f"{name.lower()}.yaml").read_text())
        for name in ("Lite", "Pro")
    }


@pytest.fixture(autouse=True)
def _reset_states(hass):
    """No integration was really loaded: avoid fake loaded states at teardown."""
    yield
    for entry in hass.config_entries.async_entries():
        if entry.domain != DOMAIN:
            object.__setattr__(entry, "state", ConfigEntryState.NOT_LOADED)


@pytest.mark.parametrize("status", ["not_configured", "unknown"])
@pytest.mark.parametrize("name", ["Lite", "Pro"])
async def test_unverified_line_names_the_case_and_links_the_backups_once(
    hass: HomeAssistant, cards, name, status
) -> None:
    attrs, _ = await _attributes(hass)
    text = REC_BACKUP_NO_SCHEDULE if status == "not_configured" else REC_BACKUP_UNKNOWN
    attrs.update(rec_backup_unverified=True, backup_status=status, recommendations=text)
    rendered = _render(hass, cards[name], attrs)
    assert rendered.count(LINES[status]) == 1
    other = LINES["unknown" if status == "not_configured" else "not_configured"]
    assert other not in rendered
    line = next(line for line in rendered.splitlines() if LINES[status] in line)
    assert "/config/backup" in line
    assert text not in rendered  # the advisor line is hidden, shown once as the linked line


@pytest.mark.parametrize("name", ["Lite", "Pro"])
async def test_no_line_without_the_flag_or_on_an_older_attribute_set(
    hass: HomeAssistant, cards, name
) -> None:
    attrs, _ = await _attributes(hass)
    attrs["rec_backup_unverified"] = False
    rendered = _render(hass, cards[name], attrs)
    assert not any(line in rendered for line in LINES.values())
    attrs.pop("rec_backup_unverified")
    rendered = _render(hass, cards[name], attrs)
    assert not any(line in rendered for line in LINES.values())
