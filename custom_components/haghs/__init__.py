"""The HAGHS integration."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import (
    issue_registry as ir,
)
from homeassistant.helpers import (
    label_registry as lr,
)
from homeassistant.helpers.storage import Store

from .const import (
    _CONFIG_VERSION,
    CONF_IGNORE_LABEL,
    CONF_IGNORE_LABELS,
    DOMAIN,
    UPDATE_FIRST_SEEN_LEGACY_STORE_KEY,
    UPDATE_FIRST_SEEN_STORE_VERSION,
    IssueIds,
    VersionInformation,
    entry_issue_id,
    entry_store_key,
)
from .coordinator import HaghsDataUpdateCoordinator, async_report_unreadable_first_seen_store

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[str] = ["sensor"]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up HAGHS from a config entry."""

    # HAGHS 2.4 kept one CPU/RAM repair for every entry; each entry now syncs its own (#217).
    ir.async_delete_issue(hass, DOMAIN, IssueIds.FALLBACK_MISSING)

    coordinator = HaghsDataUpdateCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    entry.async_on_unload(coordinator.async_track_conditional_entity())
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


async def async_remove_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Remove the repairs of a deleted HAGHS entry; the other entries keep theirs (#217)."""
    for issue in IssueIds:
        ir.async_delete_issue(hass, DOMAIN, entry_issue_id(issue, entry.entry_id))


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Migrate old entry to the current _CONFIG_VERSION.

    Migration steps so far:
      <= (3, 2): convert legacy text ignore-label values into label IDs.
      <= (3, 3): convert the single CONF_IGNORE_LABEL into the new
                 CONF_IGNORE_LABELS list (one-element list when the legacy
                 key holds a value, removed entirely when empty).
      <= (3, 4): copy the update first-seen times HAGHS 2.4 kept for every
                 entry into this entry's own store (#217), so running 7-day
                 windows go on. Entries created later never read the old store.
      (3, 5):    current version.
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

    per_entry_state_version = VersionInformation(major=3, minor=4)
    if entry_version <= per_entry_state_version:
        await _async_copy_shared_first_seen(hass, entry)

    hass.config_entries.async_update_entry(
        entry,
        data=data,
        options=options,
        version=_CONFIG_VERSION.major,
        minor_version=_CONFIG_VERSION.minor,
    )

    _LOGGER.info("HAGHS migrated to version %s", _CONFIG_VERSION)
    return True


async def _async_copy_shared_first_seen(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Give an existing entry its own copy of the first-seen store HAGHS 2.4 shared (#217).

    The old file is only read, never changed. An unreadable old file is reported like an
    unreadable own store (warning, a kept copy, the entry's repair); the migration never fails.
    """
    own: Store[Any] = Store(hass, UPDATE_FIRST_SEEN_STORE_VERSION, entry_store_key(entry.entry_id))
    try:
        if await own.async_load() is not None:
            return
    except Exception:
        # An own store exists but is unreadable: never copy over it. The coordinator reads it
        # again on its first load and reports it (warning, kept copy, the entry's repair).
        _LOGGER.debug(
            "HAGHS: Own update first-seen store unreadable, nothing copied", exc_info=True
        )
        return
    shared: Store[Any] = Store(
        hass, UPDATE_FIRST_SEEN_STORE_VERSION, UPDATE_FIRST_SEEN_LEGACY_STORE_KEY
    )
    try:
        data = await shared.async_load()
    except Exception as err:
        await async_report_unreadable_first_seen_store(hass, entry.entry_id, shared.path, err)
        return
    if data is None:
        return
    try:
        await own.async_save(data)
    except Exception:
        _LOGGER.warning(
            "HAGHS: Could not copy the stored update first-seen times for this entry; pending"
            " updates start a new 7-day window",
            exc_info=True,
        )


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
