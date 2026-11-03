"""Type and meaning of every sensor attribute, the source of the table in docs/attributes.md.

`script/gen_docs.py` renders the table from this file and fails when an attribute the sensor publishes has
no entry here, or an entry names an attribute the sensor no longer publishes. Placeholders are filled from
code (string.Template syntax):

- `$unrecorded`: the recorder note; allowed (and required) only for attributes in
  `HaghsSensor._unrecorded_attributes`.
- `${NAME}`: the value of the constant `NAME` in `custom_components/haghs/const.py` (caps, defaults).
"""

from __future__ import annotations

# attribute: (type, description); the table keeps the order the sensor publishes the attributes in.
ATTRIBUTES: dict[str, tuple[str, str]] = {
    "hardware_score": (
        "int",
        "Hardware pillar score (0\u2013100): average of the measured components (CPU, RAM, I/O when PSI provides it, Disk) minus 20 points on RPi under-voltage",
    ),
    "application_score": ("int", "Application pillar score (0\u2013100)"),
    "stale_candidate_count": (
        "int",
        "Complete passive count of overdue sensor and binary_sensor entities",
    ),
    "stale_candidates": (
        "list",
        "Alphabetically sorted passive entity IDs, capped at ${STALE_LIST_CAP}; $unrecorded",
    ),
    "stale_watch_count": (
        "int",
        "Complete count of overdue directly labelled watched entities in any domain",
    ),
    "stale_watch_entities": (
        "list",
        "Alphabetically sorted overdue watched entity IDs, capped at ${STALE_LIST_CAP}; $unrecorded",
    ),
    "stale_penalty": (
        "int",
        "Raw application deduction before the configuration bonus, ${STALE_PENALTY_PER_ENTITY} per overdue watched entity, capped at ${STALE_PENALTY_CAP}",
    ),
    "stale_threshold_hours": (
        "int",
        "Effective reporting threshold in whole hours, default ${DEFAULT_STALE_THRESHOLD_HOURS}",
    ),
    "zombie_count": (
        "int",
        "Total number of zombie entities (unavailable/unknown past the grace period, with an entity-registry entry)",
    ),
    "zombie_entities": (
        "list",
        "Entity IDs of zombies (capped at ${ZOMBIE_LIST_CAP}; `zombie_count` carries the full total); $unrecorded (`zombie_count` stays in the history)",
    ),
    "zombie_count_per_domain": (
        "dict",
        'Per-domain zombie breakdown (e.g. {"sensor": 3, "switch": 1}); always reflects the full count regardless of the list cap',
    ),
    "zombie_count_per_integration": (
        "dict",
        'Zombies per integration, keyed by the entity\'s integration (e.g. {"matter": 12, "mqtt": 40}); always reflects the full count regardless of the list cap; informational, no score impact',
    ),
    "zombie_since": (
        "dict",
        "Since when each listed zombie is unavailable/unknown (ISO timestamps, same ${ZOMBIE_LIST_CAP} entries and order as `zombie_entities`); counted from the last HA restart at the earliest, because an earlier time is not reliably known; $unrecorded; informational, no score impact",
    ),
    "zombie_count_per_reason": (
        "dict",
        'Zombies per reason, keys in ranking order, only reasons that occur (e.g. {"integration_not_loaded": 3, "unavailable": 40}); always reflects the full count regardless of the list cap, the sum equals `zombie_count`; informational, no score impact',
    ),
    "zombie_reasons": (
        "dict",
        "Reason per listed zombie (same ${ZOMBIE_LIST_CAP} entries and order as `zombie_entities`), from Home Assistant facts only, first match in this order: `config_entry_missing` (the config entry the entity belonged to no longer exists; **the only strong hint of an orphaned entity**), `integration_not_loaded` (the entry exists but is not loaded; fix the integration, not a reason to delete), `not_provided` (HA only restored the stored state because no running integration provides the entity; not a reason to delete without checking), `unavailable` (the integration runs and reports the entity as unavailable/unknown, often temporary; not a reason to delete); $unrecorded",
    ),
    "unregistered_count": (
        "int",
        "Number of entities without an entity-registry entry that are `unavailable`/`unknown` past the grace period in the monitored domains (informational only, does not affect the score)",
    ),
    "unregistered_entities": (
        "list",
        "Entity IDs of unregistered entities (capped at ${UNREGISTERED_LIST_CAP}); $unrecorded (`unregistered_count` stays in the history)",
    ),
    "unregistered_count_per_domain": ("dict", "Per-domain breakdown of unregistered entities"),
    "dead_device_count": (
        "int",
        "Number of devices whose monitored entities in `ZOMBIE_DOMAINS` are all unavailable past their respective grace periods; unknown does not count as an outage (informational, does not affect the score)",
    ),
    "dead_devices": (
        "list",
        "Device names (capped at ${DEAD_DEVICE_LIST_CAP}); $unrecorded (`dead_device_count` stays in the history)",
    ),
    "dead_device_ids": (
        "list",
        "Device ids of the listed dead devices, same ${DEAD_DEVICE_LIST_CAP} entries and order as `dead_devices` (for links to each device page); $unrecorded",
    ),
    "empty_device_count": (
        "int",
        "Number of devices without any entity (disabled entities included), not disabled, not a service, no other device linked through them (hubs), every config entry loaded; informational, no score impact",
    ),
    "empty_devices": (
        "list",
        "Names of those devices, sorted, capped at ${EMPTY_DEVICE_LIST_CAP}; $unrecorded (`empty_device_count` stays in the history)",
    ),
    "empty_device_ids": (
        "list",
        "Device ids of the listed empty devices, same ${EMPTY_DEVICE_LIST_CAP} entries and order as `empty_devices` (for links to each device page); $unrecorded",
    ),
    "db_size_mb": (
        "float",
        "Current database size in MB (auto-detected for SQLite, or from external DB sensor if configured)",
    ),
    "psi_available": (
        "bool",
        "`True` when PSI provides both CPU and memory data. I/O PSI is read independently and may still be present when this is `False`. Disk is always read via `psutil`, never PSI.",
    ),
    "cpu_ram_source": (
        "str/null",
        "Where CPU and RAM come from: `psi`, `sensors` (both measured, at least one by a selected sensor), `partial` (one not measured), `none` (neither measured; no PSI and no sensor selected). Not measured values are left out of the hardware score. `null` while the hardware pillar has no measurement (first failed update, hardware fallback).",
    ),
    "recorder_keep_days": (
        "int/null",
        "Days the recorder keeps history (`purge_keep_days`, Home Assistant's default is 10); null without a recorder",
    ),
    "recorder_filter_active": (
        "bool",
        "Whether a user include/exclude entity filter is configured for the recorder",
    ),
    "conditional_ignore_active": (
        "bool",
        "`True` while the conditional ignore labels apply (their helper is `on`); `False` when none are configured or the helper is `off`, unavailable, unknown or missing",
    ),
    "integration_unhealthy_count": (
        "int",
        "Number of config entries in `SETUP_ERROR`, `SETUP_RETRY`, or `FAILED_UNLOAD` (source of the Integration Health penalty)",
    ),
    "integration_unhealthy_entries": (
        "list",
        "The counted config entries as `domain: title` (bare `domain` when the entry has no title), sorted, capped at ${INTEGRATION_UNHEALTHY_LIST_CAP}; entries excluded in the options are not listed; $unrecorded (`integration_unhealthy_count` stays in the history)",
    ),
    "config_audit_bonus": (
        "int",
        "Earned Config-Audit bonus points (0\u2013${CONFIG_AUDIT_MAX_BONUS})",
    ),
    "repair_count": (
        "int",
        "Number of open repair issues counted toward the score (own domain and dismissed issues excluded)",
    ),
    "repairs": (
        "list",
        "`domain/issue_id` entries of the counted repair issues (capped at ${REPAIR_LIST_CAP}); $unrecorded (`repair_count` stays in the history)",
    ),
    "pending_updates": (
        "list",
        'Names of pending updates (e.g., `["ESPHome 2024.2"]`). Listed immediately; only counted toward the score after HAGHS has seen that version pending for ${UPDATE_GRACE_DAYS} days (also across restarts); $unrecorded (`rec_updates_pending` stays in the history)',
    ),
    "recommendations": (
        "string",
        "Advisor recommendations (CPU, RAM, I/O, disk, DB, power, updates, zombies, dead and empty devices, stale reporting, backup, core lag, integration health, config audit, repairs, calculation warnings)",
    ),
    "pillar_fallback_count": (
        "int",
        "Number of pillar calculations that failed or timed out during the current refresh attempt",
    ),
    "pillar_fallbacks": (
        "list",
        "Affected pillars in stable order: `hardware`, then `application`; an empty list means no observed pillar failure in this attempt",
    ),
    "update_cycle_failed": (
        "bool",
        "The current update attempt failed outside a guarded pillar calculation; existing numeric results are retained, or neutral values are used on the first update",
    ),
    "rec_cpu_load": ("bool", "CPU load (PSI stall or classic utilization) is currently penalised"),
    "rec_ram_pressure": ("bool", "Memory pressure / utilization is currently penalised"),
    "rec_io_pressure": ("bool", "I/O PSI stall time is currently penalised"),
    "rec_disk_low": ("bool", "Disk free space is below the storage-type threshold"),
    "rec_db_over_limit": ("bool", "Database size exceeds the dynamic limit"),
    "rec_power_unstable": ("bool", "RPi under-voltage detected"),
    "rec_backup_stale": ("bool", "`binary_sensor.backups_stale` is on"),
    "rec_updates_pending": (
        "bool",
        "At least one non-ignored update entity has had the same offered version pending for ${UPDATE_GRACE_DAYS} days as seen by HAGHS (also across restarts)",
    ),
    "rec_zombie": ("bool", "At least one zombie entity is reported"),
    "rec_core_lag": ("bool", "HA Core is ≥ 3 months behind the latest release"),
    "rec_integration_health": (
        "bool",
        "At least one integration config entry is in an unhealthy state (source of the Integration Health penalty)",
    ),
    "rec_config_audit": (
        "bool",
        'Config-Audit bonus points are missing (means "bonus not earned", not "config is bad")',
    ),
    "rec_repairs": ("bool", "At least one open repair issue from another integration is counted"),
    "rec_dead_devices": (
        "bool",
        "At least one dead device (all monitored entities in `ZOMBIE_DOMAINS` unavailable past their respective grace periods) is reported; unknown does not count as an outage (informational, no score impact)",
    ),
    "rec_empty_devices": (
        "bool",
        "At least one empty device (no entity at all, see `empty_device_count`) is reported; informational, no score impact",
    ),
    "rec_stale": (
        "bool",
        "An overdue watched entity triggers the reporting recommendation; passive candidates alone do not",
    ),
    "rec_pillar_fallback": (
        "bool",
        "At least one pillar calculation failed or timed out during the current refresh attempt",
    ),
    "rec_update_failed": (
        "bool",
        "The current update attempt failed outside a guarded pillar calculation",
    ),
    "rec_cpu_ram_unmeasured": (
        "bool",
        "No PSI and no sensor selected for CPU and/or RAM: the value is not measured and left out of the hardware score (`cpu_ram_source` is `partial` or `none`)",
    ),
}

# Recommendation flag: the `common` keys of strings.json whose template the coordinator renders for it.
# Every `rec_*` key of `common` belongs to exactly one flag, except `rec_all_clear` (no flag set).
RECOMMENDATION_TEXTS: dict[str, tuple[str, ...]] = {
    "rec_cpu_load": ("rec_cpu_load_psi", "rec_cpu_load_classic"),
    "rec_ram_pressure": ("rec_ram_pressure_psi", "rec_ram_pressure_classic"),
    "rec_io_pressure": ("rec_io_pressure",),
    "rec_disk_low": ("rec_disk_sd_low", "rec_disk_ssd_low"),
    "rec_db_over_limit": ("rec_db_over_limit",),
    "rec_power_unstable": ("rec_power_unstable",),
    "rec_backup_stale": ("rec_backup_stale",),
    "rec_updates_pending": ("rec_updates_pending",),
    "rec_zombie": ("rec_zombies",),
    "rec_core_lag": ("rec_core_lag",),
    "rec_integration_health": ("rec_integration_health",),
    "rec_config_audit": ("rec_config_audit",),
    "rec_repairs": ("rec_repairs",),
    "rec_dead_devices": ("rec_dead_devices",),
    "rec_empty_devices": ("rec_empty_devices",),
    "rec_stale": ("rec_stale",),
    "rec_pillar_fallback": ("rec_pillar_fallback",),
    "rec_update_failed": ("rec_update_failed",),
    "rec_cpu_ram_unmeasured": ("rec_cpu_ram_unmeasured",),
}
ALL_CLEAR_TEXT = "rec_all_clear"
