"""Every list on both dashboard cards is a real list: one item per entry, nothing run together (plan HAGHS-20261102-007).

Markdown lines inside <details> used to be joined into one paragraph; the cards now render <ul><li> lists.
"""

from __future__ import annotations

import re

from homeassistant.core import HomeAssistant

from tests.test_cards_v14_rendering import _attributes, _render, cards  # noqa: F401 - fixture

ZOMBIES = [f"sensor.zz_{i}" for i in range(5)] + [
    "switch.zz_plug",
    "light.zz_lamp",
    "binary_sensor.zz_door",
]
UNREGISTERED = ["sensor.unreg_a", "sensor.unreg_b", "sensor.unreg_c"]
WATCHED = ["sensor.watch_a", "sensor.watch_b", "sensor.watch_c", "sensor.watch_d"]
PASSIVE = ["sensor.passive_a", "sensor.passive_b", "sensor.passive_c", "sensor.passive_d"]


async def _many(hass: HomeAssistant) -> dict:
    attrs, _ = await _attributes(hass)
    for entity_id in ZOMBIES:
        hass.states.async_set(entity_id, "unavailable", {"friendly_name": entity_id.split(".")[1]})
    reasons = ["config_entry_missing", "integration_not_loaded", "not_provided", "unavailable"]
    return dict(
        attrs,
        zombie_count=len(ZOMBIES),
        zombie_entities=ZOMBIES,
        zombie_count_per_domain={"sensor": 5, "switch": 1, "light": 1, "binary_sensor": 1},
        zombie_reasons={z: reasons[i % 4] for i, z in enumerate(ZOMBIES)},
        zombie_since={},
        unregistered_count=3,
        unregistered_entities=UNREGISTERED,
        dead_device_count=3,
        dead_devices=["Plug A", "Plug B", "Plug C"],
        dead_device_ids=["a" * 32, "b" * 32, "c" * 32],
        empty_device_count=3,
        empty_devices=["Bridge A", "Bridge B", "Bridge C"],
        empty_device_ids=["d" * 32, "e" * 32, "f" * 32],
        stale_watch_count=4,
        stale_watch_entities=WATCHED,
        stale_candidate_count=4,
        stale_candidates=PASSIVE,
        repair_count=3,
        repairs=["mqtt/one", "zha/two", "hue/three"],
        integration_unhealthy_count=2,
        integration_unhealthy_entries=["mqtt: Broker", "zha: Coordinator"],
        pending_updates=["ESPHome 2026.10", "Zigbee2MQTT 2.1", "HACS 2.0", "Core 2026.11"],
    )


def _items(rendered: str) -> list[str]:
    return re.findall(r"<li>(.*?)</li>", rendered, re.S)


async def test_pro_card_lists_every_entry_as_its_own_item(hass, cards) -> None:  # noqa: F811
    rendered = _render(hass, cards["Pro"], await _many(hass))
    items = _items(rendered)
    for expected in (
        *ZOMBIES,
        *UNREGISTERED,
        *WATCHED,
        *PASSIVE,
        "Plug A",
        "Plug B",
        "Plug C",
        "Bridge A",
        "Bridge B",
        "Bridge C",
        "mqtt/one",
        "zha/two",
        "hue/three",
        "mqtt: Broker",
        "zha: Coordinator",
        "ESPHome 2026.10",
        "Core 2026.11",
    ):
        assert sum(expected in item for item in items) == 1, expected
    assert len(items) == 8 + 3 + 4 + 4 + 3 + 3 + 3 + 2 + 4
    assert "&nbsp;" not in rendered


async def test_zombie_item_has_name_line_and_detail_line(hass, cards) -> None:  # noqa: F811
    rendered = _render(hass, cards["Pro"], await _many(hass))
    item = next(i for i in _items(rendered) if "sensor.zz_0" in i)
    first, second = item.split("<br>")
    assert "zz_0</a>" in first
    assert second.startswith("<code>sensor.zz_0</code> · unavailable · config entry missing")


async def test_lite_card_has_no_space_padded_bullets(hass, cards) -> None:  # noqa: F811
    rendered = _render(
        hass,
        cards["Lite"],
        dict(await _many(hass), recorder_keep_days=30, recorder_filter_active=False),
    )
    assert "&nbsp;" not in rendered
    assert "- Keep `purge_keep_days` at 10 days or less" in rendered
    assert "- Configure an `include` / `exclude` entity filter" in rendered
    # a blank line ends the tips list, so the metric line is not glued to the last tip
    assert "\n\n**Metric source**" in rendered
