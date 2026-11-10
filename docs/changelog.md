[← Back to the README](https://github.com/HA-Pulse/home-assistant-global-health-score/blob/main/README.md)

# Release summaries

A short summary per release. Every change in detail: [v2.4.0_CHANGELOG.md](https://github.com/HA-Pulse/home-assistant-global-health-score/blob/main/v2.4.0_CHANGELOG.md) and [v2.3_CHANGELOG.md](https://github.com/HA-Pulse/home-assistant-global-health-score/blob/main/v2.3_CHANGELOG.md).

## Changelog

### [v2.4.2] - 2026-11-10

Documentation only, no integration change. The README badge names both ways to install ("Marketplace | HACS – Default") and links to the installation steps; `CONTRIBUTING.md` without em dashes. For developers: the tests run on the Core-maintained `pytest-homeassistant` (#192, #200).

### [v2.4.1] - 2026-11-10

Documentation only, no integration change. The README is much shorter (about 1 700 words): each section keeps a short version, and the full text moved word for word to [docs/scoring.md](https://github.com/HA-Pulse/home-assistant-global-health-score/blob/main/docs/scoring.md) and [docs/faq.md](https://github.com/HA-Pulse/home-assistant-global-health-score/blob/main/docs/faq.md). Released so that the Home Assistant Marketplace, which shows the README of the released version, shows the shorter one.

### [v2.4.0] - 2026-11-10

**Highlights**

* **Exclude individual integration entries from Integration Health.** The new options multi-select excludes only the selected entry IDs from the unhealthy count, penalty, recommendation and flag. The selection is empty by default, can be cleared permanently and does not affect zombie detection or Repairs.
* **Unhealthy integration entries are listed (#134).** New attribute `integration_unhealthy_entries` names the counted config entries as `domain: title`; the Pro card lists them with a link to each integration page.
* **Why and since when each zombie is reported (#154).** New attributes `zombie_count_per_integration`, `zombie_since`, `zombie_count_per_reason` and `zombie_reasons`. Only `config_entry_missing` is a strong hint of an orphaned entity; a zombie is an availability signal, not a deletion list.
* **Opt-in stale entity monitoring (discussion #79).** Passive `stale_candidates` for sensors that stopped reporting, and watch labels that make overdue entities cost points (5 each, cap 10).
* **Ignore labels on areas (discussion #96).** Ignore labels set on an area exclude the entities in that area.
* **Repairs now count in the score (#97).** Open repair issues cost 5 points each (cap 10) and hard-cap the application score at 99 while any repair is open. HA's native *Ignore* action takes a repair out of the count. New attributes `repair_count` / `repairs`, new flag `rec_repairs`.
* **Dead devices are flagged (#120).** A device whose monitored entities are all `unavailable` past the grace window is reported via `dead_device_count`, `dead_devices` and `rec_dead_devices`; `unknown` does not count (#143). Informational only, the entity-level zombie points stay authoritative.
* **Empty devices are reported (#93).** Devices without any entity are reported via `empty_device_count`, `empty_devices` and `rec_empty_devices`, using registry facts only (hubs, parents of child devices, composite devices, services and disabled devices are skipped). Informational only.
* **Device ids for the card links (#172).** `dead_device_ids` and `empty_device_ids` carry the device id next to each listed name, so the Pro card links every dead or empty device to its device page; the Lite card links the device overview.
* **Conditional ignore labels.** Extra ignore labels that apply only while a helper (`input_boolean`, `switch` or `binary_sensor`) is on, e.g. for a vacation mode, without Spook; `conditional_ignore_active` shows the state.
* **Recommendation texts are translatable (#114)**, with Brazilian Portuguese (#138) and German (#163) translations. All recommendation templates resolve through Home Assistant's translation system (category `common`) in your configured language; English is the fallback.
* **Unregistered entities are informational only (#98).** Entities without an entity-registry entry no longer count as zombies and no longer cap the score; they are reported through the `unregistered_*` attributes.
* **Every missing score point is explained (#92).** New attributes `config_audit_bonus` and `integration_unhealthy_count`, new flags `rec_integration_health` and `rec_config_audit`.
* **Calculation failures are visible (#135).** A failed or timed-out pillar sets `pillar_fallback_count`, `pillar_fallbacks` and `rec_pillar_fallback` with a warning instead of an all-clear.

**Behavior changes**

* **Entity lists no longer in recorder history.** `zombie_entities`, `unregistered_entities`, `dead_devices`, `repairs`, `pending_updates` (and the new lists) keep their current values but are no longer recorded, so large instances stay below Home Assistant's 16 KB attribute limit; counts, breakdowns, pillars and flags stay in the history.
* **CPU and RAM without PSI and without a sensor are not measured (#123).** The missing value is left out of the hardware score instead of counting as 0 % load; HAGHS always sets up, and `cpu_ram_source`, `rec_cpu_ram_unmeasured`, a recommendation line, a status line on both cards and a non-blocking repair show it.
* **The 7-day update grace survives restarts.** It counts from the first time HAGHS saw an offered version pending; it used to start again after every Home Assistant restart. A newer offered version starts its own 7 days; after updating HAGHS the first 7 days count from the update.
* **Config-Audit purge bonus only for a recorder retention of at most 10 days.** Home Assistant always reports a retention (default 10), so the +5 used to be given to every installation; a longer retention now earns no purge bonus.
* **Zombie grace default unchanged at 5 minutes.** The b1 notes claimed a change from 15 minutes; the default was already 5 minutes in v2.3.0, and existing custom values are kept.

**Bug fixes**

* Coordinator total safety net so a failing sub-component can no longer stall the sensor (#103).
* Label actions: `homeassistant.add_label_to_entity` / `homeassistant.remove_label_from_entity` come from the Spook custom integration; README example and texts corrected (#99).
* Dead-device false positives removed: `unknown` and unmonitored domains no longer count (#143).
* User-facing punctuation aligned (#136).
* Integration Health names config entries, not integrations, in its recommendation and on the cards.
* Informational checks (dead devices, empty devices, zombie reasons) can no longer take the score down when they fail.
* The device registry is read without the access patterns Home Assistant deprecated.

**Infrastructure**

* Per-pillar test coverage for the hardware and application pillars (#107); CI runs on Python 3.14 and gates the package coverage at 90 % and `coordinator.py` at 80 % (#117, #128).

**Documentation**

* Dashboard cards v1.4 (Lite and Pro): zombie reasons and since, stale lists, calculation status lines and a link to every entity, device and settings page (#133, #137, #145, #154).
* Manual smoke-test guide for live instances in `tests/README.md` (#85).
* Repository-wide documentation check ahead of this release (#130).
* Shorter README; setup, labels, attributes, cards and release summaries in full under `docs/` (#179).

**Upgrade notes:** Open repair issues now count toward the score (**5 pts each**, capped at **10 pts**) and hard-cap the application score at 99 while any repair is open, so instances with open repairs score lower than before, by design; use HA's native *Ignore* action on a repair to take it out of the score. Entities without an entity-registry entry no longer count as zombies, they are reported as informational *unregistered* entries, which can raise the score on instances that previously had such entries deducted. Without PSI, a CPU or RAM value with no sensor selected used to count as 0 % load, so it never lowered the score; now it is left out of the hardware score, which averages only the measured components and can therefore be lower. HAGHS keeps running, and a non-blocking **repair** lets you pick the sensors. Entity lists are no longer kept in the recorder history, recommendation texts follow the Home Assistant language, and new recommendation lines explain every missing point (see Highlights and Behavior changes above).

### [v2.3.0] - 2026-05-25

**Upgrade notes:** v2.3 expanded zombie detection from 9 to 22 domains, added a 7-day grace period before pending updates count, and now hard-caps the application score at 99 while a zombie exists. Fewer update penalties and disabled entities no longer counted can raise the score; previously unnoticed zombies in the new domains can lower it. The recommendations and `rec_*` flags show which factors are active; the card *Tips* block only covers the recorder bonus.

**Highlights**

* **Multi-label ignore + dynamic toggling.** `ignore_labels` now accepts a list; toggle inclusion/exclusion at runtime via the `homeassistant.add_label_to_entity` / `homeassistant.remove_label_from_entity` services of the Spook custom integration (no custom HAGHS service). Migration from the legacy single-label config is automatic.
* **Disabled-entity auto-ignore.** Entities marked *Disable entity* in the entity registry are now excluded from zombie detection and update penalties — no `haghs_ignore` label required.
* **Pattern-based ignore (#64).** New `ignore_patterns` field accepts glob patterns for entities without a unique ID (e.g. `sensor.docker_*`, `sensor.torque_*`).
* **Configurable zombie + battery grace periods.** Two new Options Flow fields (1–240 min each, defaults 5 / 60). Battery-class entities get the longer window because Zigbee / Homematic radios routinely take longer than 15 minutes to re-poll low-priority devices.
* **7-day update grace.** Pending updates only contribute to the penalty after 7 days; the list stays informational so you still see what is queued.
* **ZOMBIE_DOMAINS expanded 9 → 22.** Newly covered domains: `alarm_control_panel`, `cover`, `device_tracker`, `humidifier`, `lawn_mower`, `lock`, `number`, `remote`, `select`, `siren`, `text`, `valve`, `water_heater`. New `zombie_count_per_domain` attribute exposes a per-domain breakdown; `zombie_entities` list cap raised from 20 → 100.
* **Hard-cap at 99 with zombies (#61).** While `zombie_count > 0`, the application score cannot exceed 99 so the Config-Audit bonus can never mask a real issue.
* **Unregistered ghost zombies marked (#61).** Entities without an entity-registry entry are surfaced in `zombie_entities` with a `[unregistered]` prefix and warned in the log.
* **Power Supply Status detection (#21).** Auto-detects `binary_sensor.rpi_power_status` for Raspberry Pi under-voltage and applies a flat 20-point hardware penalty.
* **Boolean `rec_*` recommendation flags.** Ten new state attributes (e.g. `rec_cpu_load`, `rec_zombie`, `rec_backup_stale`) alongside the existing `recommendations` string — easier to consume in templates and automations.
* **PSI-aware recommendation text.** CPU and RAM advice are split into PSI ("PSI CPU stall time is impacting score (12.5%)") and classic ("CPU utilization is impacting score (65.0%)") variants so the metric source is always explicit.
* **Config Flow refactor + RepairsFlow (#49).** CPU/RAM fallback sensors are optional when PSI is available. A new Repair flow lets you recover after PSI disappears post-setup without restarting Home Assistant.

**Bug fixes**

* `async_migrate_entry` now shipped — closes the v2.2.x "Migration handler not found" failure for v1/v2 config entries (#75).
* Options Flow no longer reverts cleared optional fields (`db_sensor`, CPU/RAM fallback, ignore labels/patterns) after an HA restart.
* Registry-race guard now correctly defers zombie detection during HA's `starting` phase, not only when HA is fully shut down (previously the guard used `hass.is_running` which is `True` for both `starting` and `running`).
* Battery-class entities get a separate, longer grace window (#62).
* Zombie denominator counts only the 22 zombie-eligible domains, so instances with many automations/scripts/helpers are no longer artificially diluted (#9).
* Restart grace via boot-time baseline so `last_changed` values restored from the recorder no longer bypass the grace window (#10, #27).

**Infrastructure**

* Full test suite bootstrap (`pyproject.toml`, `requirements_test.txt`, seven test modules: zombies, updates, application, hardware-power, migration, recommendations, options-flow).
* CI workflow runs pytest + ruff on every PR.
* Release-notes augmentation workflow auto-injects a coffee-support block and a contributors list into each release body.

**Documentation**

* External database walkthrough (no-YAML SQL-sensor setup, MariaDB query).
* Pattern-Based Ignore documentation.
* Full long-form story in `v2.3_CHANGELOG.md`.

**Minimum Home Assistant version raised** to 2024.10.0 (for `IssueSeverity` and the modern `LabelSelector`).

### [v2.2.2] - 2026-03-30
* **Feature:** Added optional **Database Size Sensor** override for external databases (MariaDB, PostgreSQL). Configurable in both Setup and Options flow. When set, HAGHS uses the sensor value (in MB) instead of SQLite auto-detection. When left empty, the default SQLite behavior is unchanged. No migration needed, existing installations are unaffected.

### [v2.2.1] - 2026-03-29
* **Bugfix:** Fixed absurd percentage values in hardware recommendations (e.g. "Memory pressure is impacting score (5698.1%)") when a manually configured CPU/RAM sensor reports absolute values (MB/MHz) instead of percent. Values above 100% are now clamped and a warning is logged to help users select the correct sensor.

<details>
<summary><b>Older releases (v2.2.0 and earlier)</b></summary>

### [v2.2.0] - 2026-03-29
* **Architecture:** Full async migration to `DataUpdateCoordinator` with safety-net timeouts.
* **Zero-YAML:** Database size and disk usage are now auto-detected. No manual sensors or `configuration.yaml` changes needed.
* **PSI Integration:** Uses Linux Pressure Stall Information for CPU, Memory, and I/O with automatic fallback to classic sensors. Separate penalty tiers for PSI (stall time) vs. classic sensors (utilization), because their scales differ fundamentally.
* **I/O Scoring:** PSI I/O pressure is now actively scored. When available, the hardware pillar uses 4 components (CPU + RAM + I/O + Disk) instead of 3.
* **CPU Threshold Adjustment:** Classic CPU penalty now starts at >25% (was >10%) to avoid penalizing normal system activity.
* **Smart Disk Thresholds:** Storage-type-aware penalties (SD-Card/eMMC: absolute GB; SSD: percentage-based).
* **Dynamic Database Limit:** DB threshold scales with entity count (`1000 + entities × 2.5` MB).
* **Zombie Improvements:** Ratio-based penalties, 15-minute grace period, attribute list capped at 20.
* **Update Improvements:** Ignore label works on updates, core lag threshold raised to 3 months, pending updates listed by name.
* **Config Audit:** Bonus points for good recorder configuration (purge days + entity filters).
* **Integration Health:** Native detection of unhealthy integrations via ConfigEntry state API (SETUP_ERROR, SETUP_RETRY, FAILED_UNLOAD). 5 pts per integration, max 15 pts.
* **Options Flow:** All settings adjustable at runtime without reinstalling.
* **Configurable Interval:** Update frequency adjustable from 10s to 3600s.
* **i18n Ready:** All strings externalized to `strings.json`.
* **Removed:** Log file monitoring (deprecated since v2.0.2).

### [v2.1.1] - 2026-01-29
* **UI Migration:** Transitioned from YAML variables to a full **Config Flow (Setup Mask)**.
* **Optimization:** `haghs_ignore` label on a Device now automatically covers all its entities.

### [v2.0.2] - 2026-01-26
* **Refinement:** Made Log File monitoring explicitly optional to support HAOS users without CLI access.

### [v2.0.0] - 2026-01-26
* **Major:** Added **Database & Log Hygiene** monitoring.
* **Feature:** Implemented **Deep Label Support**.
* **Logic:** Added **Core Age** penalty (>2 months lag).
* **Logic:** Added **Cumulative Update** counting (capped at 35 pts).

### [v1.3.0] - 2026-01-24
* **NEW:** Implemented Single-Point Configuration using Template Variables.
* **NEW:** Added Heavyweight CPU Tiers.
* **Fixed:** Switched to **Floor Rounding** (Integer) for a more honest health assessment.

</details>
