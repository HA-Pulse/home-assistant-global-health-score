"""Recommendation translation tests (#114).

The coordinator resolves the recommendation templates via HA's translation
system (category "common") and falls back to the const.py defaults. These
tests pin the fallback chain: translated value, then English (core), then
const.py.
"""

from __future__ import annotations

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
)
from tests.factories import make_coordinator, patch_disk, patch_psi


def _app_with_full_bonus() -> _ApplicationResult:
    """An application pillar without the pending Config-Audit recommendation."""
    return _ApplicationResult(config_bonus=CONFIG_AUDIT_MAX_BONUS)


async def test_english_translations_mirror_const_templates(hass) -> None:
    """translations/en.json must mirror the const.py defaults byte-identically."""
    coord = make_coordinator(hass)
    loaded = await coord._async_load_rec_translations()
    assert loaded
    for key, template in REC_TEMPLATES.items():
        assert loaded[key] == template


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
