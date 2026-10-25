"""Empty devices: device registry entries without any entity (#93, part 2).

Only Home Assistant facts decide: no entity (disabled ones included), not disabled, no
service entry, no device pointing to it via ``via_device_id`` and every config entry
loaded. Informational only, like dead devices: no score impact.
"""

from __future__ import annotations

from datetime import timedelta
from types import SimpleNamespace

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.helpers import area_registry as ar
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import label_registry as lr
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.haghs import coordinator as coordinator_module
from custom_components.haghs.const import CONF_IGNORE_LABELS, DOMAIN
from custom_components.haghs.coordinator import _HardwareResult
from custom_components.haghs.sensor import HaghsSensor
from tests.factories import make_coordinator

CAP = 100  # EMPTY_DEVICE_LIST_CAP, same as DEAD_DEVICE_LIST_CAP


@pytest.fixture(autouse=True)
def _reset_states(hass):
    """No integration was really loaded: avoid fake loaded states at teardown."""
    yield
    for entry in hass.config_entries.async_entries():
        if entry.domain != DOMAIN:
            object.__setattr__(entry, "state", ConfigEntryState.NOT_LOADED)


def _owner(
    hass: HomeAssistant, state: ConfigEntryState = ConfigEntryState.LOADED
) -> MockConfigEntry:
    entry = MockConfigEntry(domain="test_platform", data={})
    entry.add_to_hass(hass)
    object.__setattr__(entry, "state", state)
    return entry


def _device(hass: HomeAssistant, name: str, *, owner: MockConfigEntry | None = None, **kwargs):
    owner = owner or _owner(hass)
    return dr.async_get(hass).async_get_or_create(
        config_entry_id=owner.entry_id,
        identifiers={("test_empty_devices", name)},
        name=name,
        **kwargs,
    )


def _entity(hass: HomeAssistant, device_id: str, object_id: str, **kwargs) -> None:
    er.async_get(hass).async_get_or_create(
        "sensor",
        "test_platform",
        f"uid_{object_id}",
        suggested_object_id=object_id,
        device_id=device_id,
        **kwargs,
    )


def _coordinator(hass: HomeAssistant, **kwargs):
    coord = make_coordinator(hass, **kwargs)
    coord._registries_ready = True
    return coord


async def test_device_without_entity_is_reported(hass) -> None:
    _device(hass, "leftover")
    full = _device(hass, "plug")
    _entity(hass, full.id, "plug_power")
    disabled_only = _device(hass, "sleeper")
    _entity(hass, disabled_only.id, "sleeper_power", disabled_by=er.RegistryEntryDisabler.USER)

    assert _coordinator(hass)._calc_empty_devices() == (["leftover"], 1)


async def test_hub_service_and_disabled_devices_are_not_reported(hass) -> None:
    hub = _device(hass, "hub")
    child = _device(hass, "child", via_device_id=hub.id)
    _entity(hass, child.id, "child_power")
    assert child.via_device_id == hub.id
    _device(hass, "cloud", entry_type=dr.DeviceEntryType.SERVICE)
    disabled = _device(hass, "off")
    dr.async_get(hass).async_update_device(disabled.id, disabled_by=dr.DeviceEntryDisabler.USER)

    assert _coordinator(hass)._calc_empty_devices() == ([], 0)


@pytest.mark.parametrize(
    "state",
    [ConfigEntryState.SETUP_RETRY, ConfigEntryState.NOT_LOADED, ConfigEntryState.SETUP_ERROR],
)
async def test_device_of_a_not_loaded_entry_is_not_reported(hass, state) -> None:
    _device(hass, "waiting", owner=_owner(hass, state))

    assert _coordinator(hass)._calc_empty_devices() == ([], 0)


async def test_every_config_entry_of_the_device_must_be_loaded(hass, monkeypatch) -> None:
    """Before HA 2026.9 a device could belong to several config entries."""
    first = _owner(hass)
    second = _owner(hass, ConfigEntryState.SETUP_RETRY)
    _device(hass, "shared", owner=first)
    monkeypatch.setattr(
        coordinator_module, "_device_config_entry_ids", lambda _: {first.entry_id, second.entry_id}
    )

    assert _coordinator(hass)._calc_empty_devices() == ([], 0)
    object.__setattr__(second, "state", ConfigEntryState.LOADED)
    assert _coordinator(hass)._calc_empty_devices() == (["shared"], 1)
    monkeypatch.setattr(coordinator_module, "_device_config_entry_ids", lambda _: set())
    assert _coordinator(hass)._calc_empty_devices() == ([], 0)


def test_config_entry_ids_across_ha_versions() -> None:
    ids = coordinator_module._device_config_entry_ids
    assert ids(SimpleNamespace(config_entry_id="a")) == {"a"}
    assert ids(SimpleNamespace(config_entry_id=None)) == set()
    assert ids(SimpleNamespace(config_entries={"a", "b"})) == {"a", "b"}
    assert ids(SimpleNamespace(config_entries=set())) == set()


async def test_registries_not_ready_and_boot_grace_defer_the_check(hass) -> None:
    _device(hass, "leftover")
    coord = make_coordinator(hass)
    coord._registries_ready = False
    assert coord._calc_empty_devices() == ([], 0)

    coord = _coordinator(hass, boot_age_minutes=2)  # below the 5-minute zombie grace
    assert coord._calc_empty_devices() == ([], 0)
    coord._boot_time = dt_util.utcnow() - timedelta(minutes=6)
    assert coord._calc_empty_devices() == (["leftover"], 1)


async def test_ignore_label_on_device_or_area_skips_it(hass) -> None:
    label = lr.async_get(hass).async_create("Keep forever")
    assert label.label_id != label.name
    on_device = _device(hass, "labelled")
    dr.async_get(hass).async_update_device(on_device.id, labels={label.label_id})
    area = ar.async_get(hass).async_create("Attic")
    ar.async_get(hass).async_update(area.id, labels={label.label_id})
    in_area = _device(hass, "in_attic")
    dr.async_get(hass).async_update_device(in_area.id, area_id=area.id)
    _device(hass, "plain")

    coord = _coordinator(hass, options={CONF_IGNORE_LABELS: [label.label_id]})
    assert coord._calc_empty_devices() == (["plain"], 1)
    assert _coordinator(hass)._calc_empty_devices() == (["in_attic", "labelled", "plain"], 3)


async def test_list_is_capped_sorted_and_uses_the_display_name(hass) -> None:
    owner = _owner(hass)
    for index in range(CAP + 20):
        _device(hass, f"dev {index:03d}", owner=owner)
    renamed = _device(hass, "zzz", owner=owner)
    dr.async_get(hass).async_update_device(renamed.id, name_by_user="aaa renamed")

    names, count = _coordinator(hass)._calc_empty_devices()
    assert count == CAP + 21
    assert names == ["aaa renamed"] + [f"dev {index:03d}" for index in range(CAP - 1)]


async def test_device_without_any_name_is_listed_by_its_id(hass) -> None:
    owner = _owner(hass)
    named = _device(hass, "named", owner=owner)
    registry = dr.async_get(hass)
    created = registry.async_get_or_create(
        config_entry_id=owner.entry_id, identifiers={("test_empty_devices", "unnamed")}
    )
    # HA names a new device after its config entry; clear it to reach the id fallback.
    unnamed = registry.async_update_device(created.id, name=None)
    assert unnamed.name is None
    assert unnamed.name_by_user is None
    assert named.name == "named"

    assert _coordinator(hass)._calc_empty_devices() == (sorted(["named", unnamed.id]), 2)


@pytest.mark.parametrize("empty", [0, 2])
async def test_result_flag_and_recommendation_without_score_change(hass, empty: int) -> None:
    for index in range(empty):
        _device(hass, f"leftover {index}")
    coord = _coordinator(hass)

    app = await coord._async_calc_application()
    result = coord._build_result(_HardwareResult(), app)
    assert result["empty_device_count"] == empty
    assert result["empty_devices"] == [f"leftover {index}" for index in range(empty)]
    assert result["rec_empty_devices"] is (empty > 0)
    line = f"🗂️ Devices: {empty} device(s) without any entity."
    assert (line in coord._build_recommendations(_HardwareResult(), app)) is (empty > 0)
    assert app.app_score == 100


async def test_sensor_attributes_unrecorded_and_neutral_default(hass) -> None:
    coord = make_coordinator(hass)
    neutral = coord._neutral_result()
    assert (neutral["empty_device_count"], neutral["empty_devices"]) == (0, [])
    assert neutral["rec_empty_devices"] is False

    coord.data = {**neutral, "empty_device_count": 1, "empty_devices": ["leftover"]}
    sensor = HaghsSensor(coord, hass.config_entries.async_entries(DOMAIN)[0])
    assert sensor.extra_state_attributes["empty_devices"] == ["leftover"]
    assert sensor.extra_state_attributes["empty_device_count"] == 1
    assert "empty_devices" in HaghsSensor._unrecorded_attributes
    assert "empty_device_count" not in HaghsSensor._unrecorded_attributes
