"""Lite and Pro cards show "no successful automatic backup known" once, with a link to the backup settings (#218)."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant

from custom_components.haghs.const import DOMAIN, REC_BACKUP_NOT_CONFIGURED
from tests.test_cards_v14_rendering import _attributes, _render

LINE = "💾 No successful automatic backup known"


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


@pytest.mark.parametrize("name", ["Lite", "Pro"])
async def test_not_configured_line_links_the_backup_settings_once(
    hass: HomeAssistant,
    cards,
    name,
) -> None:
    attrs, _ = await _attributes(hass)
    attrs.update(rec_backup_not_configured=True, recommendations=REC_BACKUP_NOT_CONFIGURED)
    rendered = _render(hass, cards[name], attrs)
    assert rendered.count(LINE) == 1
    line = next(line for line in rendered.splitlines() if LINE in line)
    assert "/config/backup" in line
    assert (
        "set up automatic backups in Home Assistant" not in rendered
    )  # the advisor line is hidden


@pytest.mark.parametrize("name", ["Lite", "Pro"])
async def test_no_line_without_the_flag_or_on_an_older_attribute_set(
    hass: HomeAssistant,
    cards,
    name,
) -> None:
    attrs, _ = await _attributes(hass)
    attrs["rec_backup_not_configured"] = False
    assert LINE not in _render(hass, cards[name], attrs)
    attrs.pop("rec_backup_not_configured")
    assert LINE not in _render(hass, cards[name], attrs)
