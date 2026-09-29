"""Repairs pillar tests (#97).

Facts used: HA's issue registry holds every domain in one dict keyed by
(domain, issue_id); `active` marks issues that exist in this session;
`dismissed_version` is set by the native "Ignore" action in the repairs UI.
"""

from __future__ import annotations

from homeassistant.helpers import issue_registry as ir

from custom_components.haghs.const import DOMAIN, REC_REPAIRS, REPAIR_LIST_CAP
from custom_components.haghs.coordinator import _RecorderInfo
from tests.factories import make_coordinator


def _add_issue(hass, domain: str, issue_id: str) -> None:
    """Create an active, non-dismissed issue for the given domain."""
    ir.async_create_issue(
        hass,
        domain,
        issue_id,
        is_fixable=False,
        is_persistent=True,
        severity=ir.IssueSeverity.WARNING,
        translation_key="test",
    )


def _dismiss_issue(hass, domain: str, issue_id: str) -> None:
    ir.async_get(hass).async_ignore(domain, issue_id, True)


def test_no_issues_is_neutral(hass) -> None:
    coord = make_coordinator(hass)
    assert coord._calc_repairs() == (0, 0, [])


def test_single_issue_costs_five_points(hass) -> None:
    _add_issue(hass, "spook", "deleted_device")
    coord = make_coordinator(hass)
    assert coord._calc_repairs() == (5, 1, ["spook/deleted_device"])


def test_penalty_is_capped_at_ten_but_count_stays_full(hass) -> None:
    for index in range(3):
        _add_issue(hass, "spook", f"issue_{index}")
    coord = make_coordinator(hass)
    penalty, count, listing = coord._calc_repairs()
    assert penalty == 10
    assert count == 3
    assert listing == ["spook/issue_0", "spook/issue_1", "spook/issue_2"]


def test_dismissed_issue_is_not_counted(hass) -> None:
    _add_issue(hass, "spook", "ignored_one")
    _dismiss_issue(hass, "spook", "ignored_one")
    coord = make_coordinator(hass)
    assert coord._calc_repairs() == (0, 0, [])


def test_own_domain_is_not_counted(hass) -> None:
    _add_issue(hass, DOMAIN, "fallback_missing")
    coord = make_coordinator(hass)
    assert coord._calc_repairs() == (0, 0, [])


def test_list_is_capped_but_count_is_full(hass) -> None:
    for index in range(REPAIR_LIST_CAP + 10):
        _add_issue(hass, "spook", f"issue_{index:03d}")
    coord = make_coordinator(hass)
    penalty, count, listing = coord._calc_repairs()
    assert penalty == 10
    assert count == REPAIR_LIST_CAP + 10
    assert len(listing) == REPAIR_LIST_CAP


async def test_two_repairs_lower_the_application_score(hass) -> None:
    _add_issue(hass, "spook", "one")
    _add_issue(hass, "spook", "two")
    coord = make_coordinator(hass)
    result = await coord._async_calc_application()
    assert result.repair_count == 2
    assert result.p_repairs == 10
    assert result.app_score == 90  # 100 - 10, kein Bonus ohne Recorder


async def test_perfect_score_is_capped_while_repairs_are_open(hass) -> None:
    _add_issue(hass, "spook", "one")
    coord = make_coordinator(hass)
    coord.recorder_info = _RecorderInfo(keep_days=10, entity_filter_active=True, available=True)
    result = await coord._async_calc_application()
    assert result.config_bonus == 10
    assert result.app_score == 99  # Bonus darf das offene Repair nicht maskieren


async def test_repairs_are_explained(hass) -> None:
    _add_issue(hass, "spook", "one")
    coord = make_coordinator(hass)
    result = await coord._async_calc_application()
    hw = await coord._async_calc_hardware()
    text = " ".join(coord._build_recommendations(hw, result))
    assert REC_REPAIRS.split("{")[0].strip() in text
    assert coord._build_rec_flags(hw, result)["rec_repairs"] is True


async def test_healthy_instance_has_no_repair_flag(hass) -> None:
    coord = make_coordinator(hass)
    result = await coord._async_calc_application()
    hw = await coord._async_calc_hardware()
    assert result.app_score == 100
    assert coord._build_rec_flags(hw, result)["rec_repairs"] is False


def test_registry_failure_is_neutral(hass, monkeypatch) -> None:
    """A broken issue registry must not break the pillar."""
    import custom_components.haghs.coordinator as coordinator_module

    def _raise(_hass):
        raise RuntimeError("boom")

    monkeypatch.setattr(coordinator_module.ir, "async_get", _raise)
    coord = make_coordinator(hass)
    assert coord._calc_repairs() == (0, 0, [])
