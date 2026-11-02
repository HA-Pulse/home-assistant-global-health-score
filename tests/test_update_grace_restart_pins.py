"""Without a restart nothing changes: score and every attribute equal the pins captured on dev before the store.

The pins in tests/data/update_grace_dev.json were captured on a clean checkout of dev ad42a7f (no store code) with the
clock frozen (one-off capture by the same scenario; the capture code is not kept).
"""

from __future__ import annotations

import json
from datetime import timedelta
from pathlib import Path

from homeassistant.util import dt as dt_util

from custom_components.haghs.const import DATA_UPDATE_FIRST_SEEN, DOMAIN
from tests.factories import make_coordinator, patch_disk, patch_psi

PINNED = json.loads((Path(__file__).parent / "data" / "update_grace_dev.json").read_text())


async def test_cycle_without_restart_matches_dev(hass, freezer) -> None:
    freezer.move_to("2026-11-02T10:00:00+00:00")
    hass.states.async_set("update.fresh", "on", {"friendly_name": "Fresh", "latest_version": "1.1"})
    hass.states.async_set("update.old", "on", {"friendly_name": "Old"})
    hass.states.async_set("update.done", "off", {"friendly_name": "Done"})
    coordinator = make_coordinator(hass)
    hass.data[DOMAIN][DATA_UPDATE_FIRST_SEEN]["update.old"] = dt_util.utcnow() - timedelta(days=8)
    with patch_psi(cpu=1.0, memory=1.0, io=1.0), patch_disk():
        await coordinator.async_refresh()
    result = json.loads(json.dumps(coordinator.data, default=str, sort_keys=True))
    assert result == PINNED
