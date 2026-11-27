"""Shared factories for the HAGHS test suite.

Deliberately dependency-free (no pytest fixtures, no plugins) so every test
module can import exactly what it needs. New helpers go at the bottom of the
file to keep merges between parallel branches cheap.
"""

from __future__ import annotations

import inspect
from collections import namedtuple
from datetime import timedelta
from typing import Any
from unittest.mock import patch

from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.util import dt as dt_util
from pytest_homeassistant.common import MockConfigEntry

from custom_components.haghs import coordinator as coordinator_module
from custom_components.haghs.const import DATA_BOOT_TIME, DOMAIN
from custom_components.haghs.coordinator import (
    HaghsDataUpdateCoordinator,
    _PsiData,
)

GB = 1024**3

DiskUsage = namedtuple("DiskUsage", ["total", "used", "free", "percent"])


# Backup Health keys (#218) on an instance without the add-on and without the built-in backup integration:
# no source, no deduction, no recommendation. Tests that pin the full attribute set add exactly these.
BACKUP_WITHOUT_SOURCE: dict[str, Any] = {
    "backup_source": "none",
    "backup_status": "no_source",
    "backup_last_success": None,
    "backup_age_hours": None,
    "backup_max_age_hours": None,
    "rec_backup_not_configured": False,
}


def make_coordinator(
    hass: HomeAssistant,
    *,
    data: dict | None = None,
    options: dict | None = None,
    boot_age_minutes: int = 120,
    entry_id: str | None = None,
) -> HaghsDataUpdateCoordinator:
    """Create a coordinator wired to a mock config entry.

    boot_age_minutes backdates the boot baseline so zombie grace windows are
    already elapsed without sleeping in tests. With ``entry_id`` the same HAGHS
    entry is reused across calls, like a Home Assistant restart keeps it (state
    per entry since #217); without it every call is a new entry.
    """
    hass.data.setdefault(DOMAIN, {})[DATA_BOOT_TIME] = dt_util.utcnow() - timedelta(
        minutes=boot_age_minutes
    )
    entry = hass.config_entries.async_get_entry(entry_id) if entry_id else None
    if entry is None:
        kwargs = {"entry_id": entry_id} if entry_id else {}
        entry = MockConfigEntry(domain=DOMAIN, data=data or {}, options=options or {}, **kwargs)
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


# Home Assistant before 2026.11 (the minimum-version CI job, #237): iterating ``devices`` yields ids, ``via_device_id``
# is not a keyword of ``async_get_or_create`` and child devices do not exist yet.
HAS_CHILD_DEVICES = hasattr(dr.DeviceRegistry, "async_get_or_create_child")


def device_entries(dev_reg: dr.DeviceRegistry) -> list[Any]:
    """All device entries, whether the registry iterates entries or ids."""
    entries = (
        dev_reg.async_get(item) if isinstance(item, str) else item for item in dev_reg.devices
    )
    return [entry for entry in entries if entry is not None]


_HAS_VIA_DEVICE_ID = (
    "via_device_id" in inspect.signature(dr.DeviceRegistry.async_get_or_create).parameters
)


def via(parent: dr.DeviceEntry) -> dict[str, Any]:
    """Keyword arguments that link a new device to ``parent`` on every supported Home Assistant version.

    Newer Home Assistant takes ``via_device_id`` (``via_device`` is deprecated there); older versions only know
    ``via_device`` with an identifier of the parent.
    """
    if _HAS_VIA_DEVICE_ID:
        return {"via_device_id": parent.id}
    return {"via_device": next(iter(parent.identifiers))}
