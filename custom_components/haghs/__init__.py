"""The HAGHS integration."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryError
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers import (
    label_registry as lr,
)

from .const import (
    _CONFIG_VERSION,
    CONF_CPU_SENSOR,
    CONF_IGNORE_LABEL,
    CONF_IGNORE_LABELS,
    CONF_RAM_SENSOR,
    DOMAIN,
    IssueIds,
    VersionInformation,
)
from .coordinator import HaghsDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[str] = ["sensor"]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up HAGHS from a config entry."""

    config = {**entry.data, **entry.options}
    psi = await hass.async_add_executor_job(HaghsDataUpdateCoordinator._read_psi_sync)
    if not psi.available and not (CONF_CPU_SENSOR in config and CONF_RAM_SENSOR in config):
        ir.async_create_issue(
            hass,
            DOMAIN,
            IssueIds.FALLBACK_MISSING,
            data={"entry_id": entry.entry_id},
            is_fixable=True,
            is_persistent=True,
            severity=ir.IssueSeverity.CRITICAL,
            translation_key=IssueIds.FALLBACK_MISSING,
        )
        raise ConfigEntryError(
            translation_domain=DOMAIN,
            translation_key=IssueIds.FALLBACK_MISSING,
        )

    ir.async_delete_issue(hass, DOMAIN, IssueIds.FALLBACK_MISSING)

    coordinator = HaghsDataUpdateCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    entry.async_on_unload(entry.add_update_listener(_async_update_options))
    return True


async def _async_update_options(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload the integration when options change."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)
    return unload_ok


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Migrate old entry to the current _CONFIG_VERSION.

    Migration steps so far:
      <= (3, 2): convert legacy text ignore-label values into label IDs.
      <= (3, 3): convert the single CONF_IGNORE_LABEL into the new
                 CONF_IGNORE_LABELS list (one-element list when the legacy
                 key holds a value, removed entirely when empty).
      (3, 4):    current version, no further data shape changes.
    """
    entry_version = VersionInformation(major=entry.version, minor=entry.minor_version)

    if entry_version >= _CONFIG_VERSION:
        return True

    _LOGGER.info("Migrating HAGHS configuration from version %s", entry_version)

    data = dict(entry.data)
    options = dict(entry.options)

    label_change_version = VersionInformation(major=3, minor=2)
    if entry_version <= label_change_version:
        if lr.DATA_REGISTRY not in hass.data:
            await lr.async_load(hass)

        label_registry = lr.async_get(hass)
        _migrate_ignore_label_value(label_registry, data)
        _migrate_ignore_label_value(label_registry, options)

    labels_list_version = VersionInformation(major=3, minor=3)
    if entry_version <= labels_list_version:
        _migrate_label_to_labels(data)
        _migrate_label_to_labels(options)

    hass.config_entries.async_update_entry(
        entry,
        data=data,
        options=options,
        version=_CONFIG_VERSION.major,
        minor_version=_CONFIG_VERSION.minor,
    )

    _LOGGER.info("HAGHS migrated to version %s", _CONFIG_VERSION)
    return True


def _migrate_label_to_labels(config: dict[str, Any]) -> bool:
    """Promote a single CONF_IGNORE_LABEL value into the CONF_IGNORE_LABELS list.

    Idempotent: if the legacy key is absent the function is a no-op. If both
    keys coexist (should not happen, but defensive), the legacy value is
    merged into the list without duplicating.
    """
    legacy = config.pop(CONF_IGNORE_LABEL, None)
    if not legacy:
        return False

    existing = config.get(CONF_IGNORE_LABELS, [])
    if legacy in existing:
        return True

    config[CONF_IGNORE_LABELS] = [legacy, *existing]
    return True


def _migrate_ignore_label_value(
    label_registry: lr.LabelRegistry,
    config: dict[str, Any],
) -> bool:
    """Convert legacy text ignore label value into a label ID."""
    label_value = config.get(CONF_IGNORE_LABEL, None)

    if not label_value:
        return True

    # Idempotency guard: value is already a label ID — nothing to migrate.
    # Without this, a future _CONFIG_VERSION bump would re-run this block on
    # already-migrated entries, fail the name lookup, and create a new label
    # whose name equals the existing label's ID.
    if label_registry.async_get_label(label_value) is not None:
        return True

    if label := label_registry.async_get_label_by_name(label_value):
        config[CONF_IGNORE_LABEL] = label.label_id
        return True

    try:
        created = label_registry.async_create(label_value)
    except ValueError:
        # Handle races/case-normalization collisions.
        if label := label_registry.async_get_label_by_name(label_value):
            config[CONF_IGNORE_LABEL] = label.label_id
            return True
        _LOGGER.warning(
            "HAGHS: Could not migrate ignore label '%s', clearing the value",
            label_value,
        )
        config.pop(CONF_IGNORE_LABEL, None)
        return True

    config[CONF_IGNORE_LABEL] = created.label_id
    _LOGGER.debug(
        "HAGHS: Created label '%s' during migration (id=%s)",
        label_value,
        created.label_id,
    )
    return True
