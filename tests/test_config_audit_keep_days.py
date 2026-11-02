"""Config-Audit bonus against a real recorder: purge bonus only for a retention of at most 10 days.

Home Assistant always sets purge_keep_days (default 10), so "configured" alone rewarded every installation. The
entity-filter bonus needs a user include/exclude; without one the recorder leaves its filter at None.
"""

from __future__ import annotations

import pytest
from homeassistant.core import HomeAssistant

from custom_components.haghs.coordinator import _RecorderInfo
from tests.factories import make_coordinator

TEXT = "🔧 Config-Audit: {missing} bonus point(s) not earned (recorder keeps more than 10 days / no entity filter)."


@pytest.fixture
def recorder_db_url() -> str:
    return "sqlite://"


def _from_recorder(hass: HomeAssistant):
    coord = make_coordinator(hass)
    coord.recorder_info = coord._read_recorder_info()
    return coord


async def test_default_recorder_keeps_ten_days_and_has_no_filter(recorder_mock, hass) -> None:
    coord = _from_recorder(hass)
    assert (coord.recorder_info.keep_days, coord.recorder_info.entity_filter_active) == (10, False)
    assert coord._calc_config_audit() == 5


@pytest.mark.parametrize(
    ("recorder_config", "keep_days", "filter_active", "bonus"),
    [
        ({"purge_keep_days": 30}, 30, False, 0),
        ({"purge_keep_days": 11}, 11, False, 0),
        ({"purge_keep_days": 3}, 3, False, 5),
        ({"exclude": {"domains": ["automation"]}}, 10, True, 10),
        ({"purge_keep_days": 30, "exclude": {"domains": ["automation"]}}, 30, True, 5),
        ({"include": {"domains": ["sensor"]}}, 10, True, 10),
    ],
)
async def test_user_recorder_configuration(
    recorder_mock, hass, recorder_config, keep_days, filter_active, bonus
):
    coord = _from_recorder(hass)
    assert (coord.recorder_info.keep_days, coord.recorder_info.entity_filter_active) == (
        keep_days,
        filter_active,
    )
    assert coord._calc_config_audit() == bonus


@pytest.mark.parametrize(
    ("keep_days", "bonus"),
    [(None, 0), (1, 5), (10, 5), (11, 0), (365, 0)],
)
def test_purge_bonus_boundary(hass, keep_days, bonus) -> None:
    coord = make_coordinator(hass)
    coord.recorder_info = _RecorderInfo(keep_days=keep_days, available=True)
    assert coord._calc_config_audit() == bonus


async def test_long_retention_shows_the_line_and_the_flag(hass, monkeypatch) -> None:
    coord = make_coordinator(hass)
    info = _RecorderInfo(keep_days=30, entity_filter_active=True, available=True)
    monkeypatch.setattr(
        coord, "_read_recorder_info", lambda: info
    )  # the cycle re-reads the recorder
    await coord.async_refresh()
    data = coord.data
    assert data["config_audit_bonus"] == 5
    assert data["rec_config_audit"] is True
    assert TEXT.format(missing=5) in data["recommendations"].split("\n")


async def test_default_retention_with_a_filter_earns_everything(hass, monkeypatch) -> None:
    coord = make_coordinator(hass)
    info = _RecorderInfo(keep_days=10, entity_filter_active=True, available=True)
    monkeypatch.setattr(coord, "_read_recorder_info", lambda: info)
    await coord.async_refresh()
    assert coord.data["config_audit_bonus"] == 10
    assert coord.data["rec_config_audit"] is False
    assert "Config-Audit" not in coord.data["recommendations"]
