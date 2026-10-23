"""Recommendation translation tests (#114).

The coordinator resolves the recommendation templates via HA's translation
system (category "common") and falls back to the const.py defaults. These
tests pin the fallback chain: translated value, then English (core), then
const.py.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from custom_components.haghs import coordinator as coordinator_module
from custom_components.haghs.const import (
    CONFIG_AUDIT_MAX_BONUS,
    REC_ALL_CLEAR,
    REC_POWER_UNSTABLE,
    REC_TEMPLATES,
)
from custom_components.haghs.coordinator import (
    _ApplicationResult,
    _HardwareResult,
    _RecorderInfo,
    _StaleResult,
)
from tests.factories import make_coordinator, patch_disk, patch_psi


@pytest.mark.parametrize("translated", [False, True])
def test_stale_template_formats_counts_threshold_and_raw_penalty(hass, translated):
    coord = make_coordinator(hass, options={"stale_threshold_hours": 48})
    app = _ApplicationResult(config_bonus=10, stale=_StaleResult(watch_count=3, penalty=10))
    template = "Meldungen: {count}; Stunden: {hours}; Abzug: {penalty}"
    if translated:
        coord._rec_translations = {"rec_stale": template}
    else:
        template = REC_TEMPLATES["rec_stale"]
    assert coord._build_recommendations(_HardwareResult(), app) == [
        template.format(count=3, hours=48, penalty=10)
    ]
    assert coord._build_rec_flags(_HardwareResult(), app)["rec_stale"] is True


def _app_with_full_bonus() -> _ApplicationResult:
    """An application pillar without the pending Config-Audit recommendation."""
    return _ApplicationResult(config_bonus=CONFIG_AUDIT_MAX_BONUS)


@pytest.mark.parametrize("filename", ["strings.json", "translations/en.json"])
@pytest.mark.parametrize(
    ("key_path", "expected"),
    [
        (
            ("common", "rec_power_unstable"),
            "⚠️ Power: Under-voltage detected: unstable power supply!",
        ),
        (
            ("config", "step", "user", "description"),
            "HAGHS monitors your Home Assistant instance and calculates a health "
            "score from 0 to 100. Database size, disk usage, and update status are "
            "detected automatically, you only need to provide the two fields below.",
        ),
    ],
    ids=["power", "setup"],
)
def test_user_facing_punctuation(filename: str, key_path: tuple[str, ...], expected: str) -> None:
    """Each target text must have the approved wording without long dashes."""
    integration_dir = Path(__file__).resolve().parents[1] / "custom_components" / "haghs"
    value = json.loads((integration_dir / filename).read_text(encoding="utf-8"))
    for key in key_path:
        value = value[key]
    assert value == expected
    assert "\u2013" not in value
    assert "\u2014" not in value


def test_json_mirror_and_power_fallback() -> None:
    """The complete English JSON and power fallback must stay aligned."""
    integration_dir = Path(__file__).resolve().parents[1] / "custom_components" / "haghs"
    strings = json.loads((integration_dir / "strings.json").read_text(encoding="utf-8"))
    english = json.loads((integration_dir / "translations" / "en.json").read_text(encoding="utf-8"))
    assert strings == english
    assert strings["common"]["rec_power_unstable"] == REC_POWER_UNSTABLE
    assert REC_POWER_UNSTABLE == REC_TEMPLATES["rec_power_unstable"]


async def test_english_translations_mirror_const_templates(hass) -> None:
    """translations/en.json must mirror the const.py defaults byte-identically."""
    coord = make_coordinator(hass)
    loaded = await coord._async_load_rec_translations()
    assert loaded
    for key, template in REC_TEMPLATES.items():
        assert loaded[key] == template
    assert loaded["rec_power_unstable"] == (
        "⚠️ Power: Under-voltage detected: unstable power supply!"
    )


async def test_missing_language_falls_back_to_english(hass) -> None:
    """A language without a translation file resolves to the English values."""
    hass.config.language = "zz"
    coord = make_coordinator(hass)
    loaded = await coord._async_load_rec_translations()
    for key, template in REC_TEMPLATES.items():
        assert loaded[key] == template


def test_lookup_miss_uses_const_default(hass) -> None:
    """Without loaded translations the const.py defaults apply."""
    coord = make_coordinator(hass)
    hw = _HardwareResult(p_power=1)
    assert coord._build_recommendations(hw, _app_with_full_bonus()) == [REC_POWER_UNSTABLE]
    assert coord._build_recommendations(hw, _app_with_full_bonus()) == [
        "⚠️ Power: Under-voltage detected: unstable power supply!"
    ]


def test_override_is_used_and_flag_pairing_holds(hass) -> None:
    """A translated template replaces the text; the flag stays paired."""
    coord = make_coordinator(hass)
    coord._rec_translations = {"rec_power_unstable": "Netz instabil!"}
    hw = _HardwareResult(p_power=1)
    assert coord._build_recommendations(hw, _app_with_full_bonus()) == ["Netz instabil!"]
    flags = coord._build_rec_flags(hw, _app_with_full_bonus())
    assert flags["rec_power_unstable"] is True


async def test_loader_failure_is_neutral(hass, monkeypatch) -> None:
    """A failing translation lookup must not break the update path."""

    async def _raise(*_args, **_kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(coordinator_module, "async_get_translations", _raise)
    coord = make_coordinator(hass)
    assert await coord._async_load_rec_translations() == {}


async def test_update_cycle_resolves_translations(hass, monkeypatch) -> None:
    """The main update cycle loads the templates and renders the all-clear text."""
    coord = make_coordinator(hass)
    monkeypatch.setattr(
        coord,
        "_read_recorder_info",
        lambda: _RecorderInfo(
            keep_days=10,
            entity_filter_active=True,
            available=True,
        ),
    )
    with patch_psi(cpu=0.0, memory=0.0, io=0.0), patch_disk():
        result = await coord._async_update_data_inner()
    assert "rec_all_clear" in coord._rec_translations
    assert result["recommendations"] == REC_ALL_CLEAR


@pytest.mark.parametrize("language", ["en", "zz"])
async def test_failure_translation_lookup_and_placeholders(hass, language):
    """New warning and pillar keys resolve through HA, then the const fallback."""
    hass.config.language = language
    coord = make_coordinator(hass)
    loaded = await coord._async_load_rec_translations()
    for key in (
        "pillar_hardware",
        "pillar_application",
        "rec_pillar_fallback",
        "rec_update_failed",
    ):
        assert loaded.get(key) == REC_TEMPLATES[key]
    coord._rec_translations = loaded
    coord._pillar_fallbacks = {"application", "hardware"}
    assert coord._failure_recommendations() == [
        REC_TEMPLATES["rec_pillar_fallback"].format(pillars="Hardware, Application")
    ]
    coord._rec_translations = {
        "pillar_hardware": "Gerät",
        "pillar_application": "Anwendung",
        "rec_pillar_fallback": "Fehler: {pillars}",
    }
    assert coord._failure_recommendations() == ["Fehler: Gerät, Anwendung"]
    coord._rec_translations = {}
    assert coord._failure_recommendations() == [
        REC_TEMPLATES["rec_pillar_fallback"].format(pillars="Hardware, Application")
    ]


ZOMBIE_EN = (
    "\U0001f9df Hygiene: {count} zombie(s) detected. "
    "Check before deleting: unavailable is not the same as unused."
)
ZOMBIE_PT_BR = (
    "\U0001f9df Higiene: {count} zumbi(s) detectado(s). "
    "Verifique antes de excluir: indisponível não significa sem uso."
)


def test_zombie_recommendation_is_not_a_deletion_list(hass) -> None:
    """#154: the zombie line says that unavailable does not mean unused (en, pt-BR)."""
    integration_dir = Path(__file__).resolve().parents[1] / "custom_components" / "haghs"
    for filename, expected in (
        ("strings.json", ZOMBIE_EN),
        ("translations/en.json", ZOMBIE_EN),
        ("translations/pt-BR.json", ZOMBIE_PT_BR),
    ):
        value = json.loads((integration_dir / filename).read_text(encoding="utf-8"))
        assert value["common"]["rec_zombies"] == expected, filename
    assert REC_TEMPLATES["rec_zombies"] == ZOMBIE_EN
    coord = make_coordinator(hass)
    app = _ApplicationResult(config_bonus=CONFIG_AUDIT_MAX_BONUS, p_zombie=4, zombie_count=218)
    assert coord._build_recommendations(_HardwareResult(), app) == [ZOMBIE_EN.format(count=218)]
