"""Tests for dead-device detection (#120).

A dead device has at least one registered entity, and all of its entities
are unavailable/unknown past the zombie grace window. The detector is
informational: it adds no score penalty, the entity-level zombie points
stay authoritative.
"""

from __future__ import annotations

from datetime import timedelta
from types import SimpleNamespace

from homeassistant.const import STATE_UNAVAILABLE
from homeassistant.core import CoreState, HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.haghs import coordinator as coordinator_module
from custom_components.haghs.const import CONFIG_AUDIT_MAX_BONUS, REC_DEAD_DEVICES
from custom_components.haghs.coordinator import _ApplicationResult, _HardwareResult
from tests.factories import make_coordinator


def _make_device(hass: HomeAssistant, name: str):
    """Create a device with a stable identifier and a display name."""
    owner = MockConfigEntry(domain="test_platform", data={})
    owner.add_to_hass(hass)
    return dr.async_get(hass).async_get_or_create(
        config_entry_id=owner.entry_id,
        identifiers={("test_dead_devices", name)},
        name=name,
    )


def _make_entity(
    hass: HomeAssistant,
    device_id: str,
    object_id: str,
    *,
    unavailable_age_minutes: int | None = 30,
    device_class: str | None = None,
) -> str:
    """Create a registered entity on *device_id* and return its entity_id.

    unavailable_age_minutes=None creates a live entity. An integer creates an
    unavailable entity whose last_changed is backdated accordingly.
    """
    entry = er.async_get(hass).async_get_or_create(
        "sensor",
        "test_platform",
        f"uid_{object_id}",
        suggested_object_id=object_id,
        device_id=device_id,
    )
    if unavailable_age_minutes is None:
        hass.states.async_set(entry.entity_id, "42")
    else:
        attrs = {"device_class": device_class} if device_class else {}
        hass.states.async_set(entry.entity_id, STATE_UNAVAILABLE, attrs)
        hass.states.get(entry.entity_id).last_changed = dt_util.utcnow() - timedelta(
            minutes=unavailable_age_minutes
        )
    return entry.entity_id


async def test_dead_device_detected(hass: HomeAssistant) -> None:
    """A device with all entities unavailable past the grace is flagged."""
    device = _make_device(hass, "dead_plug")
    _make_entity(hass, device.id, "dead_plug_power")
    _make_entity(hass, device.id, "dead_plug_energy")

    coord = make_coordinator(hass)
    dead_list, dead_count = coord._calc_dead_devices()

    assert dead_count == 1
    assert dead_list == ["dead_plug"]


async def test_dead_device_with_live_entity_not_flagged(hass: HomeAssistant) -> None:
    """One live entity keeps the whole device off the list."""
    device = _make_device(hass, "half_alive")
    _make_entity(hass, device.id, "half_alive_dead")
    _make_entity(hass, device.id, "half_alive_live", unavailable_age_minutes=None)

    coord = make_coordinator(hass)

    assert coord._calc_dead_devices() == ([], 0)


async def test_grace_window_suppresses_fresh_outage(hass: HomeAssistant) -> None:
    """A short outage below the 5-minute window does not flag the device."""
    device = _make_device(hass, "recent_outage")
    _make_entity(hass, device.id, "recent_outage_a", unavailable_age_minutes=1)
    _make_entity(hass, device.id, "recent_outage_b", unavailable_age_minutes=1)

    coord = make_coordinator(hass)

    assert coord._calc_dead_devices() == ([], 0)


async def test_battery_grace_window_applies(hass: HomeAssistant) -> None:
    """Battery-class entities use the extended 60-minute window."""
    device = _make_device(hass, "battery_dev")
    _make_entity(
        hass,
        device.id,
        "battery_dev_a",
        unavailable_age_minutes=30,
        device_class="battery",
    )
    _make_entity(hass, device.id, "battery_dev_b", unavailable_age_minutes=30)

    coord = make_coordinator(hass)
    assert coord._calc_dead_devices() == ([], 0)

    # Past the 60-minute battery window the device is flagged.
    hass.states.get("sensor.battery_dev_a").last_changed = dt_util.utcnow() - timedelta(minutes=70)
    assert coord._calc_dead_devices() == (["battery_dev"], 1)


async def test_device_ignore_label_suppresses(hass: HomeAssistant) -> None:
    """An ignore label on the device mutes it."""
    device = _make_device(hass, "ignored_device")
    _make_entity(hass, device.id, "ignored_device_a")
    dr.async_get(hass).async_update_device(device.id, labels={"haghs_ignore"})

    coord = make_coordinator(hass, options={"ignore_labels": ["haghs_ignore"]})

    assert coord._calc_dead_devices() == ([], 0)


async def test_ignore_pattern_suppresses_when_all_entities_match(
    hass: HomeAssistant,
) -> None:
    """Patterns that cover every entity mute the device as well."""
    device = _make_device(hass, "patterned")
    _make_entity(hass, device.id, "pattern_x")
    _make_entity(hass, device.id, "pattern_y")

    coord = make_coordinator(hass, options={"ignore_patterns": ["sensor.pattern_*"]})

    assert coord._calc_dead_devices() == ([], 0)


async def test_live_ignored_entity_prevents_flag(hass: HomeAssistant) -> None:
    """A live (but ignored) entity means the device is not fully dead."""
    device = _make_device(hass, "mixed")
    _make_entity(hass, device.id, "mixed_dead")
    live_id = _make_entity(hass, device.id, "mixed_live", unavailable_age_minutes=None)
    er.async_get(hass).async_update_entity(live_id, labels={"haghs_ignore"})

    coord = make_coordinator(hass, options={"ignore_labels": ["haghs_ignore"]})

    assert coord._calc_dead_devices() == ([], 0)


async def test_devices_without_entities_ignored(hass: HomeAssistant) -> None:
    """Empty devices belong to #93, not to this feature."""
    _make_device(hass, "empty_device")

    coord = make_coordinator(hass)

    assert coord._calc_dead_devices() == ([], 0)


async def test_dead_devices_skipped_during_startup(hass: HomeAssistant) -> None:
    """During HA startup the detector defers like the zombie check."""
    device = _make_device(hass, "startup_device")
    _make_entity(hass, device.id, "startup_device_a")
    hass.set_state(CoreState.starting)

    coord = make_coordinator(hass)

    assert coord._calc_dead_devices() == ([], 0)


async def test_list_cap_keeps_full_count(hass: HomeAssistant, monkeypatch) -> None:
    """The name list is capped, the count stays complete."""
    monkeypatch.setattr(coordinator_module, "DEAD_DEVICE_LIST_CAP", 1)
    for index in range(2):
        device = _make_device(hass, f"cap_{index}")
        _make_entity(hass, device.id, f"cap_{index}_a")

    coord = make_coordinator(hass)
    dead_list, dead_count = coord._calc_dead_devices()

    assert dead_count == 2
    assert len(dead_list) == 1


async def test_dead_devices_add_no_score_penalty(hass: HomeAssistant) -> None:
    """The marker must not change the score: zombie points stay authoritative."""
    device = _make_device(hass, "score_device")
    _make_entity(hass, device.id, "score_device_a")

    coord = make_coordinator(hass)
    app = await coord._async_calc_application()

    assert app.dead_device_count == 1
    assert app.zombie_count == 1
    # 100 - p_zombie (ratio 1/1 -> capped 20), no other penalties, no bonus.
    assert app.app_score == 80


def test_dead_device_recommendation_and_flag(hass: HomeAssistant) -> None:
    """The flag pairs with the rendered recommendation text."""
    coord = make_coordinator(hass)
    hw = _HardwareResult()
    app = _ApplicationResult(
        config_bonus=CONFIG_AUDIT_MAX_BONUS,
        dead_device_count=1,
        dead_device_list=["flagged"],
    )

    advice = coord._build_recommendations(hw, app)
    assert REC_DEAD_DEVICES.format(count=1) in advice
    assert coord._build_rec_flags(hw, app)["rec_dead_devices"] is True


def test_neutral_result_has_dead_device_keys(hass: HomeAssistant) -> None:
    """The neutral result carries the new attributes and a False flag."""
    coord = make_coordinator(hass)

    result = coord._neutral_result()

    assert result["dead_device_count"] == 0
    assert result["dead_devices"] == []
    assert result["rec_dead_devices"] is False


async def test_registry_entry_without_state_is_skipped(hass: HomeAssistant) -> None:
    """Registry entries without a state neither count nor block the device."""
    device = _make_device(hass, "no_state")
    _make_entity(hass, device.id, "no_state_dead")
    # Second entry exists in the registry but never appeared in the state
    # machine (e.g. a platform that did not load).
    er.async_get(hass).async_get_or_create(
        "sensor",
        "test_platform",
        "uid_no_state_ghost",
        suggested_object_id="no_state_ghost",
        device_id=device.id,
    )

    coord = make_coordinator(hass)
    dead_list, dead_count = coord._calc_dead_devices()

    assert dead_count == 1
    assert dead_list == ["no_state"]


async def test_vanished_device_is_skipped(hass: HomeAssistant, monkeypatch) -> None:
    """A device lookup that returns None between the passes is tolerated."""
    device = _make_device(hass, "vanished")
    _make_entity(hass, device.id, "vanished_a")

    monkeypatch.setattr(
        coordinator_module.dr,
        "async_get",
        lambda _hass: SimpleNamespace(async_get=lambda _device_id: None),
    )

    coord = make_coordinator(hass)

    assert coord._calc_dead_devices() == ([], 0)
