"""Application pillar components: integration health, DB, recorder, core lag.

Each test pins one component of _async_calc_application (or its helpers) with
a known input/output pair, mirroring the pilot pattern from
tests/test_hardware_power.py.
"""

from __future__ import annotations

import logging
from pathlib import Path
from types import SimpleNamespace

import pytest
from homeassistant.config_entries import ConfigEntryState
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.haghs.coordinator import _RecorderInfo
from tests.factories import make_coordinator


@pytest.fixture
def clean_local_db(hass):
    """Keep the sqlite size tests independent of test order and leftovers."""
    path = Path(hass.config.path("home-assistant_v2.db"))
    path.unlink(missing_ok=True)
    yield
    path.unlink(missing_ok=True)


def _write_local_db(hass, size: int) -> None:
    """Write a fake sqlite file (sync helper, no blocking open in async code)."""
    with open(hass.config.path("home-assistant_v2.db"), "wb") as handle:
        handle.write(b"x" * size)


# ----------------------------------------------------------------------------
# Integration health
# ----------------------------------------------------------------------------


def _unhealthy_entry(hass, index: int, state: ConfigEntryState) -> None:
    entry = MockConfigEntry(domain=f"other_{index}", data={})
    entry.add_to_hass(hass)
    # ConfigEntry.__setattr__ freezes `state` in this HA version, so bypass it.
    object.__setattr__(entry, "state", state)


def test_integration_health_zero_without_entries(hass) -> None:
    coord = make_coordinator(hass)
    assert coord._calc_integration_health() == 0


def test_integration_health_five_per_entry(hass) -> None:
    _unhealthy_entry(hass, 0, ConfigEntryState.SETUP_ERROR)
    coord = make_coordinator(hass)
    assert coord._calc_integration_health() == 5


def test_integration_health_counts_all_three_states(hass) -> None:
    _unhealthy_entry(hass, 0, ConfigEntryState.SETUP_ERROR)
    _unhealthy_entry(hass, 1, ConfigEntryState.SETUP_RETRY)
    _unhealthy_entry(hass, 2, ConfigEntryState.FAILED_UNLOAD)
    coord = make_coordinator(hass)
    assert coord._calc_integration_health() == 15


def test_integration_health_is_capped_at_15(hass) -> None:
    for index in range(4):
        _unhealthy_entry(hass, index, ConfigEntryState.SETUP_ERROR)
    coord = make_coordinator(hass)
    assert coord._calc_integration_health() == 15


# ----------------------------------------------------------------------------
# Maintenance / database
# ----------------------------------------------------------------------------


async def test_db_limit_is_dynamic(hass) -> None:
    coord = make_coordinator(hass, data={"db_sensor": "sensor.db"})
    for index in range(10):
        hass.states.async_set(f"sensor.filler_{index}", "1")
    hass.states.async_set("sensor.db", "500")
    db_mb, p_db, limit = await coord._async_calc_maintenance()
    assert db_mb == 500.0
    assert limit == 1000 + len(hass.states.async_all()) * 2.5
    assert p_db == 0


async def test_db_above_limit_costs_ten(hass) -> None:
    coord = make_coordinator(hass, data={"db_sensor": "sensor.db"})
    hass.states.async_set("sensor.db", "1500")
    _, p_db, limit = await coord._async_calc_maintenance()
    assert 1500.0 < limit * 2.5
    assert p_db == 10


async def test_db_far_above_limit_costs_thirty(hass) -> None:
    coord = make_coordinator(hass, data={"db_sensor": "sensor.db"})
    hass.states.async_set("sensor.db", "3000")
    _, p_db, _limit = await coord._async_calc_maintenance()
    assert p_db == 30


async def test_external_db_sensor_reporting_zero_skips_the_penalty(hass) -> None:
    coord = make_coordinator(hass, data={"db_sensor": "sensor.db"})
    hass.states.async_set("sensor.db", "0")
    assert await coord._async_get_db_size_mb() == 0.0


async def test_local_sqlite_file_is_measured(hass, clean_local_db) -> None:
    coord = make_coordinator(hass)
    _write_local_db(hass, 2_000_000)
    size_mb = await coord._async_get_db_size_mb()
    assert size_mb == 2_000_000 / (1024 * 1024)


async def test_missing_sqlite_file_returns_zero(hass, clean_local_db) -> None:
    coord = make_coordinator(hass)
    assert await coord._async_get_db_size_mb() == 0.0


# ----------------------------------------------------------------------------
# Config audit bonus
# ----------------------------------------------------------------------------


def _audit_coordinator(hass, **recorder_info):
    coord = make_coordinator(hass)
    coord.recorder_info = _RecorderInfo(**recorder_info)
    return coord


def test_config_audit_zero_without_recorder(hass) -> None:
    assert _audit_coordinator(hass)._calc_config_audit() == 0


def test_config_audit_five_for_keep_days(hass) -> None:
    coord = _audit_coordinator(hass, available=True, keep_days=10)
    assert coord._calc_config_audit() == 5


def test_config_audit_five_for_entity_filter(hass) -> None:
    coord = _audit_coordinator(hass, available=True, entity_filter_active=True)
    assert coord._calc_config_audit() == 5


def test_config_audit_ten_for_both(hass) -> None:
    coord = _audit_coordinator(hass, available=True, keep_days=10, entity_filter_active=True)
    assert coord._calc_config_audit() == 10


# ----------------------------------------------------------------------------
# Recorder info reader
# ----------------------------------------------------------------------------


def test_recorder_info_is_read_from_hass_data(hass) -> None:
    hass.data["recorder_instance"] = SimpleNamespace(
        keep_days=10,
        entity_filter=object(),
    )
    coord = make_coordinator(hass)
    info = coord._read_recorder_info()
    assert info.available is True
    assert info.keep_days == 10
    assert info.entity_filter_active is True


def test_recorder_info_missing_instance(hass) -> None:
    coord = make_coordinator(hass)
    info = coord._read_recorder_info()
    assert info.available is False
    assert info.keep_days is None


def test_recorder_info_failure_is_logged(hass, caplog) -> None:
    class _BrokenRecorder:
        @property
        def keep_days(self):
            raise RuntimeError("boom")

    hass.data["recorder_instance"] = _BrokenRecorder()
    coord = make_coordinator(hass)
    with caplog.at_level(logging.WARNING):
        info = coord._read_recorder_info()
    assert info.available is False
    assert "Failed to read recorder info" in caplog.text


# ----------------------------------------------------------------------------
# Core lag detection
# ----------------------------------------------------------------------------


def _set_core_update(hass, installed: str, latest: str) -> None:
    hass.states.async_set(
        "update.home_assistant_core_update",
        "off",
        {"installed_version": installed, "latest_version": latest},
    )


def test_core_lag_applies_after_three_months(hass) -> None:
    _set_core_update(hass, "2026.1.0", "2026.9.0")
    coord = make_coordinator(hass)
    p_backup, update_count, p_updates, p_core_lag, _ = coord._calc_updates()
    assert p_backup == 0
    assert update_count == 0
    assert p_core_lag == 20
    assert p_updates == 20


def test_core_lag_ignores_recent_versions(hass) -> None:
    _set_core_update(hass, "2026.8.0", "2026.9.0")
    coord = make_coordinator(hass)
    _, _, p_updates, p_core_lag, _ = coord._calc_updates()
    assert p_core_lag == 0
    assert p_updates == 0


def test_core_lag_survives_malformed_versions(hass) -> None:
    _set_core_update(hass, "2026.x", "2026.9.0")
    coord = make_coordinator(hass)
    _, _, _, p_core_lag, _ = coord._calc_updates()
    assert p_core_lag == 0


def test_core_lag_ignores_entity_without_versions(hass) -> None:
    hass.states.async_set("update.home_assistant_core_update", "off")
    coord = make_coordinator(hass)
    _, _, _, p_core_lag, _ = coord._calc_updates()
    assert p_core_lag == 0


def test_core_update_entity_detected_by_id(hass) -> None:
    _set_core_update(hass, "2026.9.0", "2026.9.0")
    coord = make_coordinator(hass)
    assert coord._detect_core_update_entity() == "update.home_assistant_core_update"


def test_core_update_entity_detected_by_title(hass) -> None:
    hass.states.async_set("update.ha_core", "off", {"title": "Home Assistant Core"})
    coord = make_coordinator(hass)
    assert coord._detect_core_update_entity() == "update.ha_core"


def test_core_update_entity_absent(hass) -> None:
    coord = make_coordinator(hass)
    assert coord._detect_core_update_entity() is None
