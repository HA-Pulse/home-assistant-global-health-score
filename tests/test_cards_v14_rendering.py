"""Dashboard cards v1.4 rendered from the README with real coordinator results.

Zombie reason and "for" per entity, the zombie hint, device links through the device ids,
stale lists, status lines, the backup link, and older attribute sets without the v2.4 keys.
Every link a card renders belongs to a fixed set of Home Assistant routes.
"""

from __future__ import annotations

import re
from datetime import timedelta
from pathlib import Path

import pytest
import yaml
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.template import Template
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.haghs.const import DOMAIN
from custom_components.haghs.sensor import HaghsSensor
from tests.factories import make_coordinator

SENSOR = "sensor.system_ha_global_health_score"
HINT = "A zombie is an availability signal, not a deletion list."
# Route families of card links (the browser check of the tools repo clicks the same set).
ROUTES = (
    r"/config/entities",
    r"/config/entities\?more-info-entity-id=[a-z_]+\.[a-z0-9_]+",
    r"/config/devices/dashboard",
    r"/config/devices/device/[0-9a-f]{32}",
    r"/config/integrations",
    r"/config/integrations/integration/[a-z0-9_]+",
    r"/config/repairs",
    r"/config/updates",
    r"/config/backup",
    r"https://www\.home-assistant\.io/integrations/recorder/",
)
V24_KEYS = {
    "zombie_count_per_integration",
    "zombie_since",
    "zombie_count_per_reason",
    "zombie_reasons",
    "dead_device_ids",
    "empty_device_count",
    "empty_devices",
    "empty_device_ids",
    "rec_empty_devices",
    "stale_candidate_count",
    "stale_candidates",
    "stale_watch_count",
    "stale_watch_entities",
    "stale_penalty",
    "stale_threshold_hours",
    "rec_stale",
    "conditional_ignore_active",
    "integration_unhealthy_entries",
    "pillar_fallback_count",
    "pillar_fallbacks",
    "update_cycle_failed",
    "rec_pillar_fallback",
    "rec_update_failed",
}


@pytest.fixture(autouse=True)
def _reset_states(hass):
    """No integration was really loaded: avoid fake loaded states at teardown."""
    yield
    for entry in hass.config_entries.async_entries():
        if entry.domain != DOMAIN:
            object.__setattr__(entry, "state", ConfigEntryState.NOT_LOADED)


@pytest.fixture
def cards():
    """Both card configurations of the README, read outside the event loop."""
    readme = (Path(__file__).resolve().parents[1] / "README.md").read_text()
    found = {}
    for name in ("Lite", "Pro"):
        section = readme.split(f"### HAGHS {name} v1.4", 1)[1]
        found[name] = yaml.safe_load(re.search(r"```yaml\n(.*?)```", section, re.DOTALL).group(1))
    return found


def _device(hass: HomeAssistant, key: str):
    owner = MockConfigEntry(domain="test_platform", data={})
    owner.add_to_hass(hass)
    object.__setattr__(owner, "state", ConfigEntryState.LOADED)
    return dr.async_get(hass).async_get_or_create(
        config_entry_id=owner.entry_id, identifiers={("test_cards", key)}, name=key
    )


async def _attributes(hass: HomeAssistant) -> tuple[dict, dict]:
    """One zombie on a dead device and one empty device, through the real coordinator."""
    dead = _device(hass, "kitchen plug")
    entry = er.async_get(hass).async_get_or_create(
        "sensor", "test_platform", "uid_kitchen", suggested_object_id="kitchen_power", device_id=dead.id
    )
    hass.states.async_set(entry.entity_id, STATE_UNAVAILABLE, {"friendly_name": "Kitchen power"})
    hass.states.get(entry.entity_id).last_changed = dt_util.utcnow() - timedelta(minutes=30)
    empty = _device(hass, "leftover bridge")
    coord = make_coordinator(hass)
    coord._registries_ready = True
    coord._boot_time = dt_util.utcnow() - timedelta(hours=1)
    coord.data = await coord._async_update_data()
    attrs = dict(HaghsSensor(coord, hass.config_entries.async_entries(DOMAIN)[0]).extra_state_attributes)
    return attrs, {"dead": dead.id, "empty": empty.id, "zombie": entry.entity_id}


def _render(hass: HomeAssistant, card: dict, attrs: dict, state: str = "88") -> str:
    hass.states.async_set(SENSOR, state, attrs)
    return "\n".join(
        Template(item["content"], hass).async_render(parse_result=False)
        for item in card["cards"]
        if item["type"] == "markdown"
    )


def _links(rendered: str) -> list[str]:
    return re.findall(r'href="([^"]+)"', rendered) + re.findall(r"\]\(([^)\s]+)\)", rendered)


async def test_pro_shows_reason_since_hint_and_device_links(hass: HomeAssistant, cards) -> None:
    attrs, ids = await _attributes(hass)
    reason = attrs["zombie_reasons"][ids["zombie"]]
    rendered = _render(hass, cards["Pro"], attrs)
    assert HINT in rendered
    assert "By reason:" in rendered
    line = next(line for line in rendered.splitlines() if ids["zombie"] in line)
    assert " · for " in line
    assert reason.replace("_", " ") in line or "reported unavailable" in line
    assert f'href="/config/devices/device/{ids["dead"]}">kitchen plug</a>' in rendered
    assert f'href="/config/devices/device/{ids["empty"]}">leftover bridge</a>' in rendered


async def test_lite_shows_zombies_by_reason(hass: HomeAssistant, cards) -> None:
    attrs, _ = await _attributes(hass)
    rendered = _render(hass, cards["Lite"], attrs)
    assert re.search(r"🧟 1 zombie\(s\) \([a-z ]+: 1\), \[Check Entities\]", rendered)


@pytest.mark.parametrize("name", ["Lite", "Pro"])
async def test_every_link_belongs_to_a_route_family(hass: HomeAssistant, cards, name) -> None:
    attrs, ids = await _attributes(hass)
    attrs.update(
        rec_backup_stale=True,
        stale_watch_count=1,
        stale_watch_entities=[ids["zombie"]],
        stale_candidate_count=1,
        stale_candidates=[ids["zombie"]],
        repair_count=1,
        repairs=["mqtt/broken"],
        integration_unhealthy_count=1,
        integration_unhealthy_entries=["mqtt: Broker"],
        pending_updates=["ESPHome 2026.10"],
        recorder_keep_days=None,
    )
    links = _links(_render(hass, cards[name], attrs))
    assert links
    for link in links:
        assert any(re.fullmatch(route, link) for route in ROUTES), link


async def test_status_lines_and_backup(hass: HomeAssistant, cards) -> None:
    attrs, _ = await _attributes(hass)
    attrs.update(
        conditional_ignore_active=True,
        pillar_fallbacks=["hardware"],
        update_cycle_failed=True,
        rec_backup_stale=True,
        recommendations="🚨 Security: Stale backup detected!",
    )
    pro = _render(hass, cards["Pro"], attrs)
    lite = _render(hass, cards["Lite"], attrs)
    assert "🏖️ Conditional ignore labels are active" in pro
    for rendered in (pro, lite):
        assert "Calculation incomplete: Hardware" in rendered
        assert "The last update cycle failed" in rendered
        assert "/config/backup" in rendered
        assert "Stale backup detected" not in rendered  # shown once, as the linked line
    assert "Conditional ignore labels" not in lite


async def test_stale_lists_link_each_entity(hass: HomeAssistant, cards) -> None:
    attrs, ids = await _attributes(hass)
    attrs.update(
        stale_watch_count=101,
        stale_watch_entities=[ids["zombie"]],
        stale_candidate_count=1,
        stale_candidates=["sensor.outdoor_temp"],
        stale_threshold_hours=12,
    )
    rendered = _render(hass, cards["Pro"], attrs)
    assert "101 watched entity(ies) not reporting for more than 12 h" in rendered
    assert f'href="/config/entities?more-info-entity-id={ids["zombie"]}"' in rendered
    assert 'href="/config/entities?more-info-entity-id=sensor.outdoor_temp"' in rendered
    assert "showing first 1, 100 more hidden" in rendered


@pytest.mark.parametrize("name", ["Lite", "Pro"])
async def test_older_attribute_sets_render_without_the_new_parts(hass: HomeAssistant, cards, name) -> None:
    attrs, ids = await _attributes(hass)
    old = {key: value for key, value in attrs.items() if key not in V24_KEYS}
    rendered = _render(hass, cards[name], old)
    assert "kitchen plug" in rendered or name == "Lite"
    assert f"/config/devices/device/{ids['dead']}" not in rendered
    assert "By reason:" not in rendered
    assert "Calculation incomplete" not in rendered
    assert " · for " not in rendered
