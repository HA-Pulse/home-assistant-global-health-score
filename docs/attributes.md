[← Back to the README](https://github.com/HA-Pulse/home-assistant-global-health-score/blob/main/README.md)

# Sensor attributes

Every attribute of `sensor.system_ha_global_health_score` with type and meaning. The README lists only the most used ones.

## Sensor Attributes

HAGHS exposes the following attributes for use in dashboard cards, automations, and templates:

<!-- BEGIN GENERATED: attributes (script/gen_docs.py) -->
| Attribute | Type | Description |
|---|---|---|
| `hardware_score` | int | Hardware pillar score (0–100): average of the measured components (CPU, RAM, I/O when PSI provides it, Disk) minus 20 points on RPi under-voltage |
| `application_score` | int | Application pillar score (0–100) |
| `stale_candidate_count` | int | Complete passive count of overdue sensor and binary_sensor entities |
| `stale_candidates` | list | Alphabetically sorted passive entity IDs, capped at 100; current only, excluded from recorder history |
| `stale_watch_count` | int | Complete count of overdue directly labelled watched entities in any domain |
| `stale_watch_entities` | list | Alphabetically sorted overdue watched entity IDs, capped at 100; current only, excluded from recorder history |
| `stale_penalty` | int | Raw application deduction before the configuration bonus, 5 per overdue watched entity, capped at 10 |
| `stale_threshold_hours` | int | Effective reporting threshold in whole hours, default 24 |
| `zombie_count` | int | Total number of zombie entities (unavailable/unknown past the grace period, with an entity-registry entry) |
| `zombie_entities` | list | Entity IDs of zombies (capped at 100; `zombie_count` carries the full total); current only, excluded from recorder history (`zombie_count` stays in the history) |
| `zombie_count_per_domain` | dict | Per-domain zombie breakdown (e.g. {"sensor": 3, "switch": 1}); always reflects the full count regardless of the list cap |
| `zombie_count_per_integration` | dict | Zombies per integration, keyed by the entity's integration (e.g. {"matter": 12, "mqtt": 40}); always reflects the full count regardless of the list cap; informational, no score impact |
| `zombie_since` | dict | Since when each listed zombie is unavailable/unknown (ISO timestamps, same 100 entries and order as `zombie_entities`); counted from the last HA restart at the earliest, because an earlier time is not reliably known; current only, excluded from recorder history; informational, no score impact |
| `zombie_count_per_reason` | dict | Zombies per reason, keys in ranking order, only reasons that occur (e.g. {"integration_not_loaded": 3, "unavailable": 40}); always reflects the full count regardless of the list cap, the sum equals `zombie_count`; informational, no score impact |
| `zombie_reasons` | dict | Reason per listed zombie (same 100 entries and order as `zombie_entities`), from Home Assistant facts only, first match in this order: `config_entry_missing` (the config entry the entity belonged to no longer exists; **the only strong hint of an orphaned entity**), `integration_not_loaded` (the entry exists but is not loaded; fix the integration, not a reason to delete), `not_provided` (HA only restored the stored state because no running integration provides the entity; not a reason to delete without checking), `unavailable` (the integration runs and reports the entity as unavailable/unknown, often temporary; not a reason to delete); current only, excluded from recorder history |
| `unregistered_count` | int | Number of entities without an entity-registry entry that are `unavailable`/`unknown` past the grace period in the monitored domains (informational only, does not affect the score) |
| `unregistered_entities` | list | Entity IDs of unregistered entities (capped at 100); current only, excluded from recorder history (`unregistered_count` stays in the history) |
| `unregistered_count_per_domain` | dict | Per-domain breakdown of unregistered entities |
| `dead_device_count` | int | Number of devices whose monitored entities in `ZOMBIE_DOMAINS` are all unavailable past their respective grace periods; unknown does not count as an outage (informational, does not affect the score) |
| `dead_devices` | list | Device names (capped at 100); current only, excluded from recorder history (`dead_device_count` stays in the history) |
| `dead_device_ids` | list | Device ids of the listed dead devices, same 100 entries and order as `dead_devices` (for links to each device page); current only, excluded from recorder history |
| `empty_device_count` | int | Number of devices without any entity (disabled entities included), not disabled, not a service, no other device linked through them (hubs), no child devices, not a composite device, every config entry loaded; informational, no score impact |
| `empty_devices` | list | Names of those devices, sorted, capped at 100; current only, excluded from recorder history (`empty_device_count` stays in the history) |
| `empty_device_ids` | list | Device ids of the listed empty devices, same 100 entries and order as `empty_devices` (for links to each device page); current only, excluded from recorder history |
| `db_size_mb` | float | Current database size in MB (auto-detected for SQLite, or from external DB sensor if configured) |
| `psi_available` | bool | `True` when PSI provides both CPU and memory data. I/O PSI is read independently and may still be present when this is `False`. Disk is always read via `psutil`, never PSI. |
| `cpu_ram_source` | str/null | Where CPU and RAM come from: `psi`, `sensors` (both measured, at least one by a selected sensor), `partial` (one not measured), `none` (neither measured; no PSI and no sensor selected). Not measured values are left out of the hardware score. `null` while the hardware pillar has no measurement (first failed update, hardware fallback). |
| `recorder_keep_days` | int/null | Days the recorder keeps history (`purge_keep_days`, Home Assistant's default is 10); null without a recorder |
| `recorder_filter_active` | bool | Whether a user include/exclude entity filter is configured for the recorder |
| `conditional_ignore_active` | bool | `True` while the conditional ignore labels apply (their helper is `on`); `False` when none are configured or the helper is `off`, unavailable, unknown or missing |
| `integration_unhealthy_count` | int | Number of config entries in `SETUP_ERROR`, `SETUP_RETRY`, or `FAILED_UNLOAD` (source of the Integration Health penalty) |
| `integration_unhealthy_entries` | list | The counted config entries as `domain: title` (bare `domain` when the entry has no title), sorted, capped at 50; entries excluded in the options are not listed; current only, excluded from recorder history (`integration_unhealthy_count` stays in the history) |
| `config_audit_bonus` | int | Earned Config-Audit bonus points (0–10) |
| `repair_count` | int | Number of open repair issues counted toward the score (own domain and dismissed issues excluded) |
| `repairs` | list | `domain/issue_id` entries of the counted repair issues (capped at 50); current only, excluded from recorder history (`repair_count` stays in the history) |
| `pending_updates` | list | Names of pending updates (e.g., `["ESPHome 2024.2"]`). Listed immediately; only counted toward the score after HAGHS has seen that version pending for 7 days (also across restarts); current only, excluded from recorder history (`rec_updates_pending` stays in the history) |
| `recommendations` | string | Advisor recommendations (CPU, RAM, I/O, disk, DB, power, updates, zombies, dead and empty devices, stale reporting, backup, core lag, integration health, config audit, repairs, calculation warnings) |
| `pillar_fallback_count` | int | Number of pillar calculations that failed or timed out during the current refresh attempt |
| `pillar_fallbacks` | list | Affected pillars in stable order: `hardware`, then `application`; an empty list means no observed pillar failure in this attempt |
| `update_cycle_failed` | bool | The current update attempt failed outside a guarded pillar calculation; existing numeric results are retained, or neutral values are used on the first update |
| `rec_cpu_load` | bool | CPU load (PSI stall or classic utilization) is currently penalised |
| `rec_ram_pressure` | bool | Memory pressure / utilization is currently penalised |
| `rec_io_pressure` | bool | I/O PSI stall time is currently penalised |
| `rec_disk_low` | bool | Disk free space is below the storage-type threshold |
| `rec_db_over_limit` | bool | Database size exceeds the dynamic limit |
| `rec_power_unstable` | bool | RPi under-voltage detected |
| `rec_backup_stale` | bool | `binary_sensor.backups_stale` is on |
| `rec_updates_pending` | bool | At least one non-ignored update entity has had the same offered version pending for 7 days as seen by HAGHS (also across restarts) |
| `rec_zombie` | bool | At least one zombie entity is reported |
| `rec_core_lag` | bool | HA Core is ≥ 3 months behind the latest release |
| `rec_integration_health` | bool | At least one integration config entry is in an unhealthy state (source of the Integration Health penalty) |
| `rec_config_audit` | bool | Config-Audit bonus points are missing (means "bonus not earned", not "config is bad") |
| `rec_repairs` | bool | At least one open repair issue from another integration is counted |
| `rec_dead_devices` | bool | At least one dead device (all monitored entities in `ZOMBIE_DOMAINS` unavailable past their respective grace periods) is reported; unknown does not count as an outage (informational, no score impact) |
| `rec_empty_devices` | bool | At least one empty device (no entity at all, see `empty_device_count`) is reported; informational, no score impact |
| `rec_stale` | bool | An overdue watched entity triggers the reporting recommendation; passive candidates alone do not |
| `rec_pillar_fallback` | bool | At least one pillar calculation failed or timed out during the current refresh attempt |
| `rec_update_failed` | bool | The current update attempt failed outside a guarded pillar calculation |
| `rec_cpu_ram_unmeasured` | bool | No PSI and no sensor selected for CPU and/or RAM: the value is not measured and left out of the hardware score (`cpu_ram_source` is `partial` or `none`) |
<!-- END GENERATED: attributes -->

**Calculation failures:** Neutral fallback values are not successful measurements. If a pillar fails or times out, `pillar_fallbacks` names the affected pillar and `recommendations` includes a warning instead of an all-clear message. Both dashboard examples display that recommendation. If the outer update cycle fails, `update_cycle_failed` is set and the existing numeric result is retained, or neutral values are returned on the first update. A successful refresh clears the failure indicators. Failure indicators do not change the score.

## Recommendation texts

Each `rec_*` flag adds one line to `recommendations` while it is set; with no flag set the line reads as in the last row. The table is generated from the English texts (`strings.json`); placeholders in braces are filled at runtime.

<!-- BEGIN GENERATED: recommendations (script/gen_docs.py) -->
| Flag | Recommendation text (English template) |
|---|---|
| `rec_cpu_load` | `⚡ Optimization: PSI CPU stall time is impacting score ({cpu_pct:.1f}%).`<br>`⚡ Optimization: CPU utilization is impacting score ({cpu_pct:.1f}%).` |
| `rec_ram_pressure` | `⚡ Optimization: PSI memory stall time is impacting score ({ram_pct:.1f}%).`<br>`⚡ Optimization: Memory utilization is impacting score ({ram_pct:.1f}%).` |
| `rec_io_pressure` | `⚡ Optimization: I/O pressure is impacting score ({io_pct:.1f}%).` |
| `rec_disk_low` | `⚠️ Disk Space: Only {free_gb:.1f} GB free on {storage_type}!`<br>`⚠️ Disk Space: Less than 10% free ({free_gb:.1f} GB)!` |
| `rec_db_over_limit` | `🗄️ Database: DB ({db_gb:.1f} GB) exceeds dynamic limit ({limit_gb:.1f} GB).` |
| `rec_power_unstable` | `⚠️ Power: Under-voltage detected: unstable power supply!` |
| `rec_backup_stale` | `🚨 Security: Stale backup detected!` |
| `rec_updates_pending` | `📦 Maintenance: {count} update(s) pending.` |
| `rec_zombie` | `🧟 Hygiene: {count} zombie(s) detected. Check before deleting: unavailable is not the same as unused.` |
| `rec_core_lag` | `👴 Legacy: Core version is ≥3 months old.` |
| `rec_integration_health` | `🧩 Integrations: {count} integration entry(ies) failed to set up.` |
| `rec_config_audit` | `🔧 Config-Audit: {missing} bonus point(s) not earned (recorder keeps more than 10 days / no entity filter).` |
| `rec_repairs` | `🛠️ Repairs: {count} open repair issue(s) detected.` |
| `rec_dead_devices` | `🔌 Devices: {count} device(s) with all monitored entities unavailable past the grace period.` |
| `rec_empty_devices` | `🗂️ Devices: {count} device(s) without any entity.` |
| `rec_stale` | `Stale reporting: {count} watched entity/entities have not reported for more than {hours} hour(s); application penalty {penalty} point(s) before the configuration bonus.` |
| `rec_pillar_fallback` | `⚠️ Calculation: {pillars} failed or timed out; neutral fallback values are not measurements.` |
| `rec_update_failed` | `⚠️ Calculation: The update cycle failed; previous results or neutral initial values are shown.` |
| `rec_cpu_ram_unmeasured` | `📊 Hardware: CPU and/or RAM are not measured (no PSI, no sensor selected); the hardware score uses the other components.` |
| (none set) | `✅ System optimized` |
<!-- END GENERATED: recommendations -->
