"""Since when each reported zombie is unavailable (#154): `zombie_since`."""

from __future__ import annotations

from datetime import timedelta

from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import label_registry as lr
from homeassistant.util import dt as dt_util

from custom_components.haghs.const import (
    CONF_IGNORE_LABELS,
    DATA_BOOT_TIME,
    DOMAIN,
    ZOMBIE_LIST_CAP,
)
from custom_components.haghs.sensor import HaghsSensor
from tests.factories import make_coordinator, patch_disk, patch_psi

# Complete result of the same scenario on dev before this change (b90e616..22d6d2b), pinned:
# score, every existing attribute and every rec_* flag must stay exactly as they were.
DEV_RESULT = {
    "application_score": 80,
    "config_audit_bonus": 0,
    "db_size_mb": 0.0,
    "dead_device_count": 0,
    "dead_devices": [],
    "global_score": 88,
    "hardware_score": 100,
    "integration_unhealthy_count": 0,
    "pending_updates": [],
    "pillar_fallback_count": 0,
    "pillar_fallbacks": [],
    "psi_available": True,
    "rec_backup_stale": False,
    "rec_config_audit": True,
    "rec_core_lag": False,
    "rec_cpu_load": False,
    "rec_db_over_limit": False,
    "rec_dead_devices": False,
    "rec_disk_low": False,
    "rec_integration_health": False,
    "rec_io_pressure": False,
    "rec_pillar_fallback": False,
    "rec_power_unstable": False,
    "rec_ram_pressure": False,
    "rec_repairs": False,
    "rec_stale": False,
    "rec_update_failed": False,
    "rec_updates_pending": False,
    "rec_zombie": True,
    "recommendations": "🧟 Hygiene: 3 zombie(s) detected. Check before deleting: unavailable is not "
    "the same as unused.\n"
    "🔧 Config-Audit: 10 bonus point(s) not earned (recorder purge days / entity "
    "filter).",
    "recorder_filter_active": False,
    "recorder_keep_days": None,
    "repair_count": 0,
    "repairs": [],
    "stale_candidate_count": 0,
    "stale_candidates": [],
    "stale_penalty": 0,
    "stale_threshold_hours": 24,
    "stale_watch_count": 0,
    "stale_watch_entities": [],
    "unregistered_count": 1,
    "unregistered_count_per_domain": {"sensor": 1},
    "unregistered_entities": ["sensor.yaml_template"],
    "update_cycle_failed": False,
    "zombie_count": 3,
    "zombie_count_per_domain": {"cover": 1, "sensor": 2},
    "zombie_count_per_integration": {"matter": 1, "mqtt": 1, "zha": 1},
    "zombie_entities": ["sensor.plug_power", "cover.garage", "sensor.old_sensor"],
}


async def _scenario_result(hass):
    label = lr.async_get(hass).async_create("Vacation")
    coord = make_coordinator(hass, options={CONF_IGNORE_LABELS: [label.label_id]})
    coord._registries_ready = True
    registry = er.async_get(hass)
    now = dt_util.utcnow()

    def registered(platform, object_id, state=STATE_UNAVAILABLE, age=30, domain="sensor"):
        entry = registry.async_get_or_create(
            domain, platform, f"uid_{platform}_{object_id}", suggested_object_id=object_id
        )
        hass.states.async_set(entry.entity_id, state)
        hass.states.get(entry.entity_id).last_changed = now - timedelta(minutes=age)
        return entry.entity_id

    registered("matter", "plug_power")
    registered("mqtt", "garage", state=STATE_UNKNOWN, domain="cover")
    registered("zha", "old_sensor", age=600)  # changed before boot: floored at boot
    registered("zha", "fresh", age=1)  # inside the grace period
    labelled = registered("zha", "labelled")
    disabled = registered("shelly", "disabled")
    registry.async_update_entity(labelled, labels={label.label_id})
    registry.async_update_entity(disabled, disabled_by=er.RegistryEntryDisabler.USER)
    hass.states.async_set("sensor.yaml_template", STATE_UNAVAILABLE)
    hass.states.get("sensor.yaml_template").last_changed = now - timedelta(minutes=30)
    hass.states.async_set("sensor.healthy", "21")
    with patch_psi(cpu=1.0, memory=1.0, io=1.0), patch_disk():
        hw = await coord._async_calc_hardware()
        app = await coord._async_calc_application()
    return coord, coord._build_result(hw, app)


async def test_score_and_existing_attributes_are_unchanged(hass: HomeAssistant) -> None:
    """Only zombie_since is added; everything else equals the pinned dev result."""
    _, result = await _scenario_result(hass)
    assert set(result) == set(DEV_RESULT) | {"zombie_since"}
    assert {key: value for key, value in result.items() if key != "zombie_since"} == DEV_RESULT


async def test_since_is_the_grace_baseline_per_listed_zombie(hass: HomeAssistant) -> None:
    """Same keys and order as zombie_entities; last_changed floored at the boot time."""
    _, result = await _scenario_result(hass)
    boot = hass.data[DOMAIN][DATA_BOOT_TIME]
    assert list(result["zombie_since"]) == result["zombie_entities"]
    for entity_id, since in result["zombie_since"].items():
        state = hass.states.get(entity_id)
        assert since == max(state.last_changed, boot).isoformat()
    assert result["zombie_since"]["sensor.old_sensor"] == boot.isoformat()  # changed before boot
    for absent in (
        "sensor.fresh",
        "sensor.labelled",
        "sensor.disabled",
        "sensor.yaml_template",
        "sensor.healthy",
    ):
        assert absent not in result["zombie_since"]


async def test_since_is_capped_with_the_entity_list(hass: HomeAssistant) -> None:
    coord = make_coordinator(hass)
    coord._registries_ready = True
    registry = er.async_get(hass)
    now = dt_util.utcnow()
    total = ZOMBIE_LIST_CAP + 5
    for index in range(total):
        entry = registry.async_get_or_create(
            "light", "esphome", f"uid_{index}", suggested_object_id=f"l{index}"
        )
        hass.states.async_set(entry.entity_id, STATE_UNAVAILABLE)
        hass.states.get(entry.entity_id).last_changed = now - timedelta(minutes=30)
    result = coord._calc_zombies()
    assert result[2] == total
    assert list(result[8]) == result[0]
    assert len(result[8]) == ZOMBIE_LIST_CAP


async def test_empty_without_zombies_during_deferral_and_in_the_neutral_result(
    hass: HomeAssistant,
) -> None:
    coord = make_coordinator(hass)
    coord._registries_ready = True
    assert coord._calc_zombies()[8] == {}
    entry = er.async_get(hass).async_get_or_create(
        "sensor", "matter", "uid_plug", suggested_object_id="plug"
    )
    hass.states.async_set(entry.entity_id, STATE_UNAVAILABLE)
    hass.states.get(entry.entity_id).last_changed = dt_util.utcnow() - timedelta(minutes=30)
    coord._registries_ready = False
    assert coord._calc_zombies()[8] == {}
    assert coord._neutral_result()["zombie_since"] == {}


async def test_sensor_exposes_it_and_keeps_it_out_of_the_recorder(hass: HomeAssistant) -> None:
    coord = make_coordinator(hass)
    since = {"sensor.plug": "2026-10-24T08:00:00+00:00"}
    coord.data = dict(
        coord._neutral_result(), zombie_count=1, zombie_entities=["sensor.plug"], zombie_since=since
    )
    sensor = HaghsSensor(coord, hass.config_entries.async_entries(DOMAIN)[0])
    assert sensor.extra_state_attributes["zombie_since"] == since
    assert "zombie_since" in HaghsSensor._unrecorded_attributes
    assert set(sensor.extra_state_attributes) - {"zombie_since"} == set(DEV_RESULT) - {
        "global_score"
    }
