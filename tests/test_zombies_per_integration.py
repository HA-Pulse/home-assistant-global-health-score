"""Zombies grouped by integration (#154): `zombie_count_per_integration`."""

from __future__ import annotations

from datetime import timedelta

from homeassistant.const import STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import label_registry as lr
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.haghs.const import (
    CONF_IGNORE_LABELS,
    DATA_BOOT_TIME,
    DOMAIN,
    ZOMBIE_LIST_CAP,
)
from custom_components.haghs.coordinator import HaghsDataUpdateCoordinator
from custom_components.haghs.sensor import HaghsSensor


def _coordinator(hass: HomeAssistant, entry: MockConfigEntry) -> HaghsDataUpdateCoordinator:
    hass.data.setdefault(DOMAIN, {})[DATA_BOOT_TIME] = dt_util.utcnow() - timedelta(minutes=60)
    coordinator = HaghsDataUpdateCoordinator(hass, entry)
    coordinator._registries_ready = True
    return coordinator


def _unavailable(hass: HomeAssistant, entity_id: str) -> None:
    hass.states.async_set(entity_id, STATE_UNAVAILABLE)
    hass.states.get(entity_id).last_changed = dt_util.utcnow() - timedelta(minutes=30)


def _registered(
    hass: HomeAssistant,
    platform: str,
    object_id: str,
    *,
    device_id: str | None = None,
    domain: str = "sensor",
) -> str:
    entry = er.async_get(hass).async_get_or_create(
        domain,
        platform,
        f"uid_{platform}_{object_id}",
        suggested_object_id=object_id,
        device_id=device_id,
    )
    _unavailable(hass, entry.entity_id)
    return entry.entity_id


def _device(hass: HomeAssistant, entry: MockConfigEntry, name: str) -> str:
    return (
        dr.async_get(hass)
        .async_get_or_create(
            config_entry_id=entry.entry_id, identifiers={("test", name)}, name=name
        )
        .id
    )


async def test_zombies_are_counted_per_integration(hass: HomeAssistant) -> None:
    """Counts are keyed by the registry platform; the sum equals zombie_count."""
    entry = MockConfigEntry(domain=DOMAIN, data={})
    entry.add_to_hass(hass)
    device = _device(hass, entry, "bridge")
    _registered(hass, "matter", "plug_power", device_id=device)
    _registered(hass, "matter", "plug_voltage", device_id=device)
    _registered(hass, "mqtt", "garage_door", domain="cover")
    _unavailable(hass, "sensor.yaml_template")  # unregistered: never a zombie (#98)

    result = _coordinator(hass, entry)._calc_zombies()
    zombie_count, per_domain, per_integration = result[2], result[3], result[7]

    assert zombie_count == 3
    assert per_domain == {"sensor": 2, "cover": 1}
    assert per_integration == {"matter": 2, "mqtt": 1}
    assert list(per_integration) == sorted(per_integration)
    assert sum(per_integration.values()) == zombie_count


async def test_ignored_and_disabled_entities_are_not_counted(hass: HomeAssistant) -> None:
    """Ignore labels and disabled entities stay excluded from the new breakdown."""
    label = lr.async_get(hass).async_create("Vacation")
    entry = MockConfigEntry(domain=DOMAIN, data={CONF_IGNORE_LABELS: [label.label_id]})
    entry.add_to_hass(hass)
    registry = er.async_get(hass)
    kept = _registered(hass, "zha", "kept")
    labelled = _registered(hass, "zha", "labelled")
    disabled = _registered(hass, "shelly", "disabled")
    registry.async_update_entity(labelled, labels={label.label_id})
    registry.async_update_entity(disabled, disabled_by=er.RegistryEntryDisabler.USER)

    result = _coordinator(hass, entry)._calc_zombies()

    assert result[0] == [kept]
    assert result[7] == {"zha": 1}


async def test_breakdown_is_not_capped_with_the_entity_list(hass: HomeAssistant) -> None:
    """The entity list stops at the cap, the per-integration counts do not."""
    entry = MockConfigEntry(domain=DOMAIN, data={})
    entry.add_to_hass(hass)
    total = ZOMBIE_LIST_CAP + 5
    for index in range(total):
        _registered(hass, "wled" if index % 2 else "esphome", f"light_{index}", domain="light")

    result = _coordinator(hass, entry)._calc_zombies()

    assert len(result[0]) == ZOMBIE_LIST_CAP
    assert result[2] == total
    assert result[7] == {"esphome": 53, "wled": 52}
    assert sum(result[7].values()) == total


async def test_no_zombies_and_startup_deferral_give_an_empty_breakdown(hass: HomeAssistant) -> None:
    entry = MockConfigEntry(domain=DOMAIN, data={})
    entry.add_to_hass(hass)
    coordinator = _coordinator(hass, entry)
    assert coordinator._calc_zombies()[7] == {}

    _registered(hass, "matter", "plug")
    coordinator._registries_ready = False
    assert coordinator._calc_zombies()[7] == {}


async def test_attribute_in_neutral_result_and_sensor(hass: HomeAssistant) -> None:
    """The neutral fallback carries an empty breakdown; the sensor exposes the key."""
    entry = MockConfigEntry(domain=DOMAIN, data={})
    entry.add_to_hass(hass)
    coordinator = _coordinator(hass, entry)

    neutral = coordinator._neutral_result()
    assert neutral["zombie_count_per_integration"] == {}

    coordinator.data = dict(neutral, zombie_count=1, zombie_count_per_integration={"matter": 1})
    attrs = HaghsSensor(coordinator, entry).extra_state_attributes
    assert attrs["zombie_count_per_integration"] == {"matter": 1}
