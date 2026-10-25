"""Keep German aligned with the English translation schema."""

from __future__ import annotations

import json

import pytest

from tests.factories import make_coordinator
from tests.test_pt_br_translations import TRANSLATIONS, _assert_translation_matches

# Proper names that read the same in German.
SAME_AS_ENGLISH = {"pillar_hardware"}


def _load(name: str) -> dict:
    return json.loads((TRANSLATIONS / name).read_text(encoding="utf-8"))


def test_de_matches_complete_english_schema() -> None:
    """Every English key, leaf type and format field must also exist in German."""
    _assert_translation_matches(_load("en.json"), _load("de.json"))


def test_de_recommendations_are_translated() -> None:
    english = _load("en.json")["common"]
    german = _load("de.json")["common"]
    assert {key for key in english if german[key] == english[key]} == SAME_AS_ENGLISH


async def test_de_recommendation_resolves(hass) -> None:
    hass.config.language = "de"
    coord = make_coordinator(hass)
    loaded = await coord._async_load_rec_translations()
    assert loaded["rec_all_clear"] == "✅ System optimiert"
    assert loaded["rec_integration_health"].format(count=2) == (
        "🧩 Integrationen: 2 Integrationseintrag/-einträge konnten nicht eingerichtet werden."
    )


@pytest.mark.parametrize("key", ["rec_zombies", "rec_dead_devices", "rec_repairs"])
def test_de_texts_keep_their_emoji_prefix(key: str) -> None:
    """The dashboard cards hide lines by their emoji prefix, so the prefix must match English."""
    english = _load("en.json")["common"][key]
    german = _load("de.json")["common"][key]
    assert german.split(" ")[0] == english.split(" ")[0]
