# HAGHS Roadmap

This document outlines completed, planned, and declined features for the
Home Assistant Global Health Score. It lives next to the active changelog
file and is refreshed whenever a release lands.

---

## Completed in v2.4

All work below is committed on `dev` and described in detail in
[`v2.4.0_CHANGELOG.md`](./v2.4.0_CHANGELOG.md).

### Features

- **Repairs now count in the application score (#97)**: Open repair issues
  from HA's issue registry cost 5 points each (cap 10), and the hard cap of
  99 now also applies while repairs are open so the Config-Audit bonus cannot
  mask a broken integration. New attributes `repair_count` and `repairs`,
  new flag `rec_repairs`. HA's native "Ignore" action takes a repair out of
  the count; HAGHS's own repairs are excluded. Visible score change,
  documented in the changelog.

### Bug fixes

- **Every missing score point explained (#92)**: The Config-Audit bonus and
  the Integration Health penalty now produce a recommendation line and a
  `rec_*` flag. Two new attributes (`config_audit_bonus`,
  `integration_unhealthy_count`) expose the raw numbers, and a new invariant
  test fails whenever a point source would be missing a text and a flag. No
  score change.

### Infrastructure

- **Pillar test coverage and CI refresh (#107, #117)**: The suite grows from
  103 to 257 tests and `coordinator.py` reaches 100 % statement and branch
  coverage. CI runs on Python 3.14 (Home Assistant 2026.9.4 instead of
  2025.1.4) and gates `coordinator.py` coverage at 80 %.

## Completed in v2.3

All work below is committed on `dev` and described in detail in
[`v2.3_CHANGELOG.md`](./v2.3_CHANGELOG.md).

### Features

- **Power Supply Status Detection (#21)**: Raspberry Pi under-voltage
  auto-detection via `binary_sensor.rpi_power_status`, flat 20-point
  penalty to the hardware score.
- **Config Flow refactor + RepairsFlow (#49)**: CPU/RAM sensors optional
  when PSI is available; coordinator split into `coordinator.py`; new
  Repairs flow recovers from PSI disappearing post-setup.
- **Pattern-based ignore (#64)**: `ignore_patterns` field accepts glob
  patterns for entities without a unique ID (e.g. `monitor_docker`,
  `torque`).
- **Boolean recommendation flags**: Ten `rec_*` boolean state attributes
  alongside the existing `recommendations` string, exported via
  `REC_FLAG_KEYS`.
- **PSI-aware recommendation text**: `REC_CPU_LOAD` and
  `REC_RAM_PRESSURE` split into PSI / classic variants so the advisor
  text makes the metric source explicit.
- **7-day update grace period (#26)**: Pending updates only contribute
  to the penalty after `UPDATE_GRACE_DAYS = 7`; pending list is
  unaffected so users still see what is queued.
- **Multi-label ignore + dynamic toggling**: `ignore_labels` accepts
  multiple labels. Inclusion/exclusion is toggled at runtime via the
  `homeassistant.add_label_to_entity` /
  `homeassistant.remove_label_from_entity` service actions of the Spook
  custom integration (HA itself has no label service), so automations
  can flip exclusions (e.g. a `vacation` label) without reloading the
  integration. Migration `(3,2)→(3,3)` converts the legacy single-label
  setting transparently.
- **Disabled-entity auto-ignore**: Entities marked
  `disabled_by != None` in the entity registry are excluded from zombie
  detection and update penalties without requiring a label. Removes the
  community-flagged friction of having to label every disabled entity.
- **ZOMBIE_DOMAINS expansion (9 → 22) + per-domain breakdown + cap
  raise**: Scoring scope expanded to 22 physical/UI-relevant domains.
  Newly covered: `alarm_control_panel`, `cover`, `device_tracker`,
  `humidifier`, `lawn_mower`, `lock`, `number`, `remote`, `select`,
  `siren`, `text`, `valve`, `water_heater`; `button` / `event`
  deliberately excluded, their default `unknown` would cause false
  positives. New `zombie_count_per_domain` attribute exposes a
  per-domain dict; `ZOMBIE_LIST_CAP` raised from 20 → 100 entries (the
  count and per-domain map always carry full totals regardless of the
  display cap).
- **Configurable zombie + battery grace periods**: Two new Options
  Flow fields: `zombie_grace_minutes` (1-240, default 5) and
  `battery_grace_minutes` (1-240, default 60). Both periods are
  independent (battery grace can be set below the general grace, this
  intentionally disables the extension). Replaces the previous
  hard-coded `ZOMBIE_GRACE_SECONDS` / `BATTERY_GRACE_SECONDS`
  constants.

### Bug fixes

- **Hard cap at 99 while zombies exist (#61)**: `app_score` is capped at
  99 whenever `zombie_count > 0` so the config-audit bonus cannot mask a
  real zombie.
- **Unregistered ghost zombies marked (#61)**: Entities without an
  entity-registry entry are prepended with `[unregistered]` in the
  `zombie_entities` attribute and warned in the log.
- **Registry-race guard after restart (#62)**: Zombie detection is
  deferred until `EVENT_HOMEASSISTANT_STARTED`, so labels are loaded
  before the first scan.
- **Restart grace via boot-time baseline (#27)**: `_calc_zombies` uses
  `max(state.last_changed, boot_time)` so `last_changed` values restored
  from the recorder no longer bypass the grace window.
- **Battery-class extended grace (#62)**: `device_class=battery`
  entities get a 60-minute grace window instead of 15 minutes.
- **Denominator counts only `ZOMBIE_DOMAINS` (#9)**: `p_zombie` is no
  longer diluted by automations, scripts, helpers, etc.
- **Ignore label: `LabelSelector` (#30)**: Replaces the failing
  `TextSelector` (special characters / case were silently ignored).
- **Translation key alignment + Node.js 20 deprecation**: Fixed
  hassfest after PR #49 adoption.
- **Pro-card improvements bundle**: Pending-updates list now renders
  one item per line with a bullet prefix; zombie list separates tracked
  entities (run through `expand()` for friendly names) from
  `[unregistered]` ghosts (rendered as a separate `<details>` block so
  ghost markers no longer get silently dropped); per-domain summary
  reads from the new `zombie_count_per_domain` attribute with a
  namespace-loop fallback for users still on v2.2.2; cap message
  rewritten to use `z_count > z_list | length` instead of a hard-coded
  "first 100".

### Documentation

- **External database walkthrough (#63)**: Full no-YAML SQL-sensor
  setup with MariaDB query and Advanced Options.
- **Setup paths corrected (#66)**: `Settings > Devices & Services > …`
  everywhere.
- **UI Integration clarification (#65)**: Card YAML must be added via
  *Add Card → Manual*, plus a fix for the Lite card recommendations
  block.
- **Config-Audit tips in both cards (#67)**: Visual *Tips* block shows
  which recorder bonus points are not yet earned.
- **Pattern-Based Ignore documentation (#64)**: New README section
  with glob examples.
- **`rec_*` flags documented**: Added to the Sensor Attributes table.

### Infrastructure

- **Test bootstrap + migration coverage + pilot pillar (#54)**:
  `tests/` directory, `pyproject.toml`, `requirements_test.txt`,
  `.github/workflows/ci.yml`, plus the three phases of #54 (infra,
  migration tests, `p_power` pilot pillar).
- **`CONTRIBUTING.md` refresh**: Tests now mandatory, CI checks
  documented, `vol.Exclusive("fixable")` trap noted.

---

## Planned

### Implemented on dev

HAGHS checks when Home Assistant last received a state report, not when the value last changed. Passive checks cover only sensor and binary_sensor entities. The default stale threshold is 24 hours; you can set it from 1 to 8760 whole hours in the integration options. A state is a candidate only after this threshold has been exceeded.

The passive list does not affect your score. To opt in to scoring, select Stale watch labels in the integration options and apply one of those labels directly to each entity that must keep reporting. Watched entities can belong to any domain. Device and area labels do not opt entities in. Ignore rules take priority. Each overdue watched entity costs 5 application points, capped at 10 before the configuration bonus. While a watched entity is overdue, the application score cannot exceed 99. These are explicit project rules, not validated failure probabilities.

The sensor exposes stale_candidate_count and stale_candidates for passive findings in sensor and binary_sensor, stale_watch_count and stale_watch_entities for opted-in findings in any domain, stale_penalty for the raw application deduction, stale_threshold_hours for the active threshold, and rec_stale for the watched-entity recommendation. Both lists are sorted and limited to 100 entity IDs; their counts remain complete. Watched entities outside sensor and binary_sensor appear only in the watched list and count, not in the passive list and count. The two entity-ID lists remain visible as current attributes but are excluded from recorder history; the counts remain recorded.

Unknown, unavailable, disabled, ignored and HAGHS-owned entities are excluded from this check. Entities without registry entries may appear in the passive list only if they belong to sensor or binary_sensor, but cannot opt in through entity labels. Old reports are a reason to investigate, not proof of a broken device: quiet integrations and devices can legitimately stop reporting. Restarts can reset the report timestamp, so HAGHS does not reconstruct downtime across restarts.

Data source: Home Assistant state.last_reported. No recorder queries, external requests or device polling are added.

### Repairs penalties: severity weighting and a grace window (v2.5 candidate)

**Status:** Deliberately out of scope for #97.

**Reasoning:** v1 counts every open repair issue with a flat 5 points (cap 10)
and without a grace window, so the rule stays simple and explainable. Two
follow-ups are on record: weighting `CRITICAL` higher than `WARNING` (users
currently pay the same for both) and a grace window for repairs that appear
during boot. Both are cheap to add later; the `created` timestamp on every
issue entry is already available.

---

## Declined

### CPU Temperature Monitoring (#21)

**Status:** Will not be implemented.

**Reasoning:** CPU temperature is a predictive hardware metric, not a
current health indicator. If thermal throttling occurs, it already
surfaces through elevated PSI stall values, which HAGHS captures. Adding
temperature as a scoring component would dilute the existing hardware
score without adding actionable health information. The required user
configuration (sensor selection, threshold definition per hardware
platform) conflicts with the pragmatism principle.

### Check Entities URL Filtering

**Status:** Not implementable within HAGHS.

**Reasoning:** HA does not support URL-based filtering of the entity
list by status. `/config/entities/edit/ENTITY_ID` is not a valid route.
The `?domain=` URL parameter is ignored by HA's entity configuration
page. Markdown links inside HTML `<summary>` tags are not rendered as
clickable links. This would require a feature request to HA Core.

---

*Last updated: 2026-09-29*