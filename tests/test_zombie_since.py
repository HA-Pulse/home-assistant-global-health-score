"""Since when each reported zombie is unavailable (#154): `zombie_since`."""

from __future__ import annotations

from datetime import timedelta

import pytest
from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
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

# Complete results of the same scenarios on dev before this change (22d6d2b), pinned:
# score, every existing attribute and every rec_* flag must stay exactly as they were.
# 0 extra zombies: 3 zombies; 105 extra: 108 zombies, the list capped at ZOMBIE_LIST_CAP.
# Keys added after #154-c by later plans (#154-d, #134, #93); they have their own pinned tests.
ADDED_LATER = {
    "zombie_count_per_reason",
    "zombie_reasons",
    "integration_unhealthy_entries",
    "empty_device_count",
    "empty_devices",
    "rec_empty_devices",
}
DEV_RESULTS = {
    0: {
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
        "recommendations": "🧟 Hygiene: 3 zombie(s) detected. Check before deleting: unavailable is "
        "not the same as unused.\n"
        "🔧 Config-Audit: 10 bonus point(s) not earned (recorder purge days / "
        "entity filter).",
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
    },
    105: {
        "application_score": 80,
        "config_audit_bonus": 0,
        "db_size_mb": 0.0,
        "dead_device_count": 1,
        "dead_devices": ["strip"],
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
        "rec_dead_devices": True,
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
        "recommendations": "🧟 Hygiene: 108 zombie(s) detected. Check before deleting: unavailable is "
        "not the same as unused.\n"
        "🔧 Config-Audit: 10 bonus point(s) not earned (recorder purge days / "
        "entity filter).\n"
        "🔌 Devices: 1 device(s) with all monitored entities unavailable past the "
        "grace period.",
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
        "zombie_count": 108,
        "zombie_count_per_domain": {"cover": 1, "light": 105, "sensor": 2},
        "zombie_count_per_integration": {"esphome": 105, "matter": 1, "mqtt": 1, "zha": 1},
        "zombie_entities": [
            "sensor.plug_power",
            "cover.garage",
            "sensor.old_sensor",
            "light.segment_000",
            "light.segment_001",
            "light.segment_002",
            "light.segment_003",
            "light.segment_004",
            "light.segment_005",
            "light.segment_006",
            "light.segment_007",
            "light.segment_008",
            "light.segment_009",
            "light.segment_010",
            "light.segment_011",
            "light.segment_012",
            "light.segment_013",
            "light.segment_014",
            "light.segment_015",
            "light.segment_016",
            "light.segment_017",
            "light.segment_018",
            "light.segment_019",
            "light.segment_020",
            "light.segment_021",
            "light.segment_022",
            "light.segment_023",
            "light.segment_024",
            "light.segment_025",
            "light.segment_026",
            "light.segment_027",
            "light.segment_028",
            "light.segment_029",
            "light.segment_030",
            "light.segment_031",
            "light.segment_032",
            "light.segment_033",
            "light.segment_034",
            "light.segment_035",
            "light.segment_036",
            "light.segment_037",
            "light.segment_038",
            "light.segment_039",
            "light.segment_040",
            "light.segment_041",
            "light.segment_042",
            "light.segment_043",
            "light.segment_044",
            "light.segment_045",
            "light.segment_046",
            "light.segment_047",
            "light.segment_048",
            "light.segment_049",
            "light.segment_050",
            "light.segment_051",
            "light.segment_052",
            "light.segment_053",
            "light.segment_054",
            "light.segment_055",
            "light.segment_056",
            "light.segment_057",
            "light.segment_058",
            "light.segment_059",
            "light.segment_060",
            "light.segment_061",
            "light.segment_062",
            "light.segment_063",
            "light.segment_064",
            "light.segment_065",
            "light.segment_066",
            "light.segment_067",
            "light.segment_068",
            "light.segment_069",
            "light.segment_070",
            "light.segment_071",
            "light.segment_072",
            "light.segment_073",
            "light.segment_074",
            "light.segment_075",
            "light.segment_076",
            "light.segment_077",
            "light.segment_078",
            "light.segment_079",
            "light.segment_080",
            "light.segment_081",
            "light.segment_082",
            "light.segment_083",
            "light.segment_084",
            "light.segment_085",
            "light.segment_086",
            "light.segment_087",
            "light.segment_088",
            "light.segment_089",
            "light.segment_090",
            "light.segment_091",
            "light.segment_092",
            "light.segment_093",
            "light.segment_094",
            "light.segment_095",
            "light.segment_096",
        ],
    },
}


async def _scenario_result(hass, extra=0):
    label = lr.async_get(hass).async_create("Vacation")
    coord = make_coordinator(hass, options={CONF_IGNORE_LABELS: [label.label_id]})
    coord._registries_ready = True
    config_entry = hass.config_entries.async_entries(DOMAIN)[0]
    devices = dr.async_get(hass)
    registry = er.async_get(hass)
    now = dt_util.utcnow()

    def device(name):  # real registry entries: device first, entities with device_id
        return devices.async_get_or_create(
            config_entry_id=config_entry.entry_id, identifiers={("test", name)}, name=name
        ).id

    def registered(
        platform, object_id, device_id, state=STATE_UNAVAILABLE, age=30, domain="sensor"
    ):
        entry = registry.async_get_or_create(
            domain,
            platform,
            f"uid_{platform}_{object_id}",
            suggested_object_id=object_id,
            device_id=device_id,
        )
        hass.states.async_set(entry.entity_id, state)
        hass.states.get(entry.entity_id).last_changed = now - timedelta(minutes=age)
        return entry.entity_id

    plug, bridge, garage = device("plug"), device("bridge"), device("garage")
    registered("matter", "plug_power", plug)  # after boot
    registered("matter", "plug_voltage", plug, state="230")  # the plug stays partly alive
    registered("mqtt", "garage", garage, state=STATE_UNKNOWN, domain="cover")
    registered("zha", "old_sensor", bridge, age=600)  # changed before boot: floored at boot
    registered("zha", "fresh", bridge, age=1)  # inside the grace period
    labelled = registered("zha", "labelled", bridge)
    disabled = registered("shelly", "disabled", bridge)
    registry.async_update_entity(labelled, labels={label.label_id})
    registry.async_update_entity(disabled, disabled_by=er.RegistryEntryDisabler.USER)
    strip = device("strip") if extra else None
    for index in range(extra):  # capped case: more zombies than ZOMBIE_LIST_CAP
        registered("esphome", f"segment_{index:03d}", strip, domain="light")
    hass.states.async_set("sensor.yaml_template", STATE_UNAVAILABLE)
    hass.states.get("sensor.yaml_template").last_changed = now - timedelta(minutes=30)
    hass.states.async_set("sensor.healthy", "21")
    with patch_psi(cpu=1.0, memory=1.0, io=1.0), patch_disk():
        hw = await coord._async_calc_hardware()
        app = await coord._async_calc_application()
    return coord, coord._build_result(hw, app)


@pytest.mark.parametrize("extra", [0, 105])
async def test_score_and_existing_attributes_are_unchanged(hass: HomeAssistant, extra: int) -> None:
    """Exactly zombie_since (and the later #154-d keys) is added; every other value equals dev."""
    _, result = await _scenario_result(hass, extra)
    assert set(result) == set(DEV_RESULTS[extra]) | {"zombie_since"} | ADDED_LATER
    assert result["integration_unhealthy_entries"] == []
    assert (result["empty_device_count"], result["empty_devices"]) == (0, [])
    assert result["rec_empty_devices"] is False
    added = {"zombie_since"} | ADDED_LATER
    assert {key: value for key, value in result.items() if key not in added} == DEV_RESULTS[extra]


async def test_since_is_the_grace_baseline_per_listed_zombie(hass: HomeAssistant) -> None:
    """Same keys and order as zombie_entities; last_changed floored at the boot time."""
    _, result = await _scenario_result(hass)
    boot = hass.data[DOMAIN][DATA_BOOT_TIME]
    assert list(result["zombie_since"]) == result["zombie_entities"]
    for entity_id, since in result["zombie_since"].items():
        state = hass.states.get(entity_id)
        assert since == max(state.last_changed, boot).isoformat()
    plug = hass.states.get("sensor.plug_power")
    assert plug.last_changed > boot  # changed after boot: its own time
    assert result["zombie_since"]["sensor.plug_power"] == plug.last_changed.isoformat()
    assert result["zombie_since"]["sensor.old_sensor"] == boot.isoformat()  # changed before boot
    for absent in (
        "sensor.fresh",
        "sensor.labelled",
        "sensor.disabled",
        "sensor.plug_voltage",
        "sensor.yaml_template",
        "sensor.healthy",
    ):
        assert absent not in result["zombie_since"]


async def test_since_is_capped_with_the_entity_list(hass: HomeAssistant) -> None:
    _, result = await _scenario_result(hass, extra=ZOMBIE_LIST_CAP + 5)
    assert result["zombie_count"] == ZOMBIE_LIST_CAP + 8
    assert list(result["zombie_since"]) == result["zombie_entities"]
    assert len(result["zombie_since"]) == ZOMBIE_LIST_CAP


async def test_empty_without_zombies_during_deferral_and_in_the_neutral_result(
    hass: HomeAssistant,
) -> None:
    coord = make_coordinator(hass)
    coord._registries_ready = True
    assert coord._calc_zombies()[8] == {}
    config_entry = hass.config_entries.async_entries(DOMAIN)[0]
    device = dr.async_get(hass).async_get_or_create(
        config_entry_id=config_entry.entry_id, identifiers={("test", "plug")}, name="plug"
    )
    entry = er.async_get(hass).async_get_or_create(
        "sensor", "matter", "uid_plug", suggested_object_id="plug", device_id=device.id
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
    assert (
        set(sensor.extra_state_attributes)
        == (set(DEV_RESULTS[0]) - {"global_score"}) | {"zombie_since"} | ADDED_LATER
    )
