"""Shared factories for the HAGHS test suite.

Deliberately dependency-free (no pytest fixtures, no plugins) so every test
module can import exactly what it needs. New helpers go at the bottom of the
file to keep merges between parallel branches cheap.
"""

from __future__ import annotations

from collections import namedtuple
from datetime import timedelta
from typing import Any
from unittest.mock import patch

from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.haghs import coordinator as coordinator_module
from custom_components.haghs.const import DATA_BOOT_TIME, DOMAIN
from custom_components.haghs.coordinator import (
    HaghsDataUpdateCoordinator,
    _PsiData,
)

GB = 1024**3

DiskUsage = namedtuple("DiskUsage", ["total", "used", "free", "percent"])


def make_coordinator(
    hass: HomeAssistant,
    *,
    data: dict | None = None,
    options: dict | None = None,
    boot_age_minutes: int = 120,
) -> HaghsDataUpdateCoordinator:
    """Create a coordinator wired to a mock config entry.

    boot_age_minutes backdates the boot baseline so zombie grace windows are
    already elapsed without sleeping in tests.
    """
    hass.data.setdefault(DOMAIN, {})[DATA_BOOT_TIME] = dt_util.utcnow() - timedelta(
        minutes=boot_age_minutes
    )
    entry = MockConfigEntry(domain=DOMAIN, data=data or {}, options=options or {})
    entry.add_to_hass(hass)
    return HaghsDataUpdateCoordinator(hass, entry)


def patch_psi(**values: float | None) -> Any:
    """Patch the coordinator PSI reader.

    Missing keys default to None, so patch_psi() simulates a system without
    any PSI support and patch_psi(cpu=1.0, memory=1.0, io=None) a system with
    CPU/memory PSI but no I/O pressure file.
    """
    psi = _PsiData(
        cpu=values.get("cpu"),
        memory=values.get("memory"),
        io=values.get("io"),
    )

    async def _fake_read_psi(_self: HaghsDataUpdateCoordinator) -> _PsiData:
        return psi

    return patch.object(
        HaghsDataUpdateCoordinator,
        "_async_read_psi",
        _fake_read_psi,
    )


def patch_disk(
    *,
    total: float = 500 * GB,
    free: float = 500 * GB,
    percent: float = 0.0,
) -> Any:
    """Patch psutil.disk_usage for the coordinator."""

    def _fake_disk_usage(_path: str) -> DiskUsage:
        return DiskUsage(total=total, used=total - free, free=free, percent=percent)

    return patch.object(coordinator_module.psutil, "disk_usage", _fake_disk_usage)
