# HAGHS Roadmap

This document outlines completed, planned, and declined features for the
Home Assistant Global Health Score. It lives next to the active changelog
(`v2.3_CHANGELOG.md`) and is refreshed whenever a release lands.

---

## Completed in v2.3 (dev branch)

All work below is committed on `dev` and described in detail in
[`v2.3_CHANGELOG.md`](./v2.3_CHANGELOG.md).

### Features

- **Power Supply Status Detection (#21)** — Raspberry Pi under-voltage
  auto-detection via `binary_sensor.rpi_power_status`, flat 20-point
  penalty to the hardware score.
- **Config Flow refactor + RepairsFlow (#49)** — CPU/RAM sensors optional
  when PSI is available; coordinator split into `coordinator.py`; new
  Repairs flow recovers from PSI disappearing post-setup.
- **Pattern-based ignore (#64)** — `ignore_patterns` field accepts glob
  patterns for entities without a unique ID (e.g. `monitor_docker`,
  `torque`).
- **Boolean recommendation flags** — Ten `rec_*` boolean state attributes
  alongside the existing `recommendations` string, exported via
  `REC_FLAG_KEYS`.
- **PSI-aware recommendation text** — `REC_CPU_LOAD` and
  `REC_RAM_PRESSURE` split into PSI / classic variants so the advisor
  text makes the metric source explicit.
- **7-day update grace period (#26)** — Pending updates only contribute
  to the penalty after `UPDATE_GRACE_DAYS = 7`; pending list is
  unaffected so users still see what is queued.
- **Multi-label ignore + dynamic toggling** — `ignore_labels` accepts
  multiple labels. Inclusion/exclusion is toggled at runtime via HA's
  native `label.assign` / `label.remove` service actions, so automations
  can flip exclusions (e.g. a `vacation` label) without reloading the
  integration. Migration `(3,2)→(3,3)` converts the legacy single-label
  setting transparently.
- **Disabled-entity auto-ignore** — Entities marked
  `disabled_by != None` in the entity registry are excluded from zombie
  detection and update penalties without requiring a label. Removes the
  community-flagged friction of having to label every disabled entity.
- **ZOMBIE_DOMAINS expansion (9 → 22) + per-domain breakdown + cap
  raise** — Scoring scope expanded to 22 physical/UI-relevant domains
  (`alarm_control_panel`, `camera`, `climate`, `cover`,
  `device_tracker`, `fan`, `humidifier`, `lawn_mower`, `light`, `lock`,
  `media_player`, `number`, `remote`, `select`, `siren`, `switch`,
  `text`, `vacuum`, `valve`, `water_heater` added; `button` / `event`
  deliberately excluded — their default `unknown` would cause false
  positives). New `zombie_count_per_domain` attribute exposes a
  per-domain dict; `ZOMBIE_LIST_CAP` raised from 20 → 100 entries (the
  count and per-domain map always carry full totals regardless of the
  display cap).
- **Configurable zombie + battery grace periods** — Two new Options
  Flow fields: `zombie_grace_minutes` (1–240, default 15) and
  `battery_grace_minutes` (1–240, default 60). Both periods are
  independent (battery grace can be set below the general grace — this
  intentionally disables the extension). Replaces the previous
  hard-coded `ZOMBIE_GRACE_SECONDS` / `BATTERY_GRACE_SECONDS`
  constants.

### Bug fixes

- **Hard cap at 99 while zombies exist (#61)** — `app_score` is capped at
  99 whenever `zombie_count > 0` so the config-audit bonus cannot mask a
  real zombie.
- **Unregistered ghost zombies marked (#61)** — Entities without an
  entity-registry entry are prepended with `[unregistered]` in the
  `zombie_entities` attribute and warned in the log.
- **Registry-race guard after restart (#62)** — Zombie detection is
  deferred until `EVENT_HOMEASSISTANT_STARTED`, so labels are loaded
  before the first scan.
- **Restart grace via boot-time baseline (#27)** — `_calc_zombies` uses
  `max(state.last_changed, boot_time)` so `last_changed` values restored
  from the recorder no longer bypass the grace window.
- **Battery-class extended grace (#62)** — `device_class=battery`
  entities get a 60-minute grace window instead of 15 minutes.
- **Denominator counts only `ZOMBIE_DOMAINS` (#9)** — `p_zombie` is no
  longer diluted by automations, scripts, helpers, etc.
- **Ignore label: `LabelSelector` (#30)** — Replaces the failing
  `TextSelector` (special characters / case were silently ignored).
- **Translation key alignment + Node.js 20 deprecation** — Fixed
  hassfest after PR #49 adoption.
- **Pro-card improvements bundle** — Pending-updates list now renders
  one item per line with a bullet prefix; zombie list separates tracked
  entities (run through `expand()` for friendly names) from
  `[unregistered]` ghosts (rendered as a separate `<details>` block so
  ghost markers no longer get silently dropped); per-domain summary
  reads from the new `zombie_count_per_domain` attribute with a
  namespace-loop fallback for users still on v2.2.2; cap message
  rewritten to use `z_count > z_list | length` instead of a hard-coded
  "first 100".

### Documentation

- **External database walkthrough (#63)** — Full no-YAML SQL-sensor
  setup with MariaDB query and Advanced Options.
- **Setup paths corrected (#66)** — `Settings > Devices & Services > …`
  everywhere.
- **UI Integration clarification (#65)** — Card YAML must be added via
  *Add Card → Manual*, plus a fix for the Lite card recommendations
  block.
- **Config-Audit tips in both cards (#67)** — Visual *Tips* block shows
  which recorder bonus points are not yet earned.
- **Pattern-Based Ignore documentation (#64)** — New README section
  with glob examples.
- **`rec_*` flags documented** — Added to the Sensor Attributes table.

### Infrastructure

- **Test bootstrap + migration coverage + pilot pillar (#54)** —
  `tests/` directory, `pyproject.toml`, `requirements_test.txt`,
  `.github/workflows/ci.yml`, plus the three phases of #54 (infra,
  migration tests, `p_power` pilot pillar).
- **`CONTRIBUTING.md` refresh** — Tests now mandatory, CI checks
  documented, `vol.Exclusive("fixable")` trap noted.

---

## Planned

### Stale-sensor detection (v2.4)

**Problem:** Sensors can fail silently — they stop reporting but Home
Assistant keeps showing the last valid value. The current zombie
detector only catches `unavailable` / `unknown`, so this class of
failure goes unnoticed.

**Approach — hybrid design (Option D from the v2.3 design session):**

- **Always-on, passive layer:** A new `stale_candidates` state
  attribute lists every entity whose `state.last_reported` is older
  than a configurable threshold (default 24 h). No score impact, no
  penalty — pure transparency, no false-positive risk for unmodified
  setups.
- **Opt-in, score-impacting layer:** A new `stale_watch_labels` option
  mirrors the existing multi-label `ignore_labels` pattern. Entities
  carrying any of these labels and exceeding the threshold contribute
  to a new penalty bucket. Zero false positives by design — the user
  explicitly marks which sensors must keep reporting.

**Why not auto-detect by device class:** Every commonly cited "safe"
device class (`temperature`, `humidity`, `pressure`, `power`,
`illuminance`, …) has legitimate long-quiet scenarios (climate-stable
rooms, idle devices, nighttime). No single threshold works across
them, and a magic default would violate the "no obfuscated thresholds"
rule from `HAGHS_PHILOSOPHY.md`.

**Technical primitive:** `state.last_reported` (HA Core 2024.4+).
Updates on every backend message regardless of whether the value or
attributes changed, so it survives Zigbee2MQTT's `force_update=False`
default — which `state.last_updated` does not.

**Prerequisite:** Bump `hacs.json` min HA version to ≥ 2024.4
(already on the v2.3 pre-release checklist to raise to 2024.10+).

---

### Bug Fix: Unregistered Ghost Zombie Entities (#61)

**Problem:** Entities that exist in HA's state machine but have no entry in the entity registry are correctly detected as zombies but are completely invisible in the HA UI. Users cannot identify or resolve them, and there is no indication in the `zombie_entities` attribute that these entities are unregistered.

**Solution:**
- Mark unregistered zombie entities with an `[unregistered]` prefix in the `zombie_entities` attribute.
- Emit a `WARNING` log entry so users can locate the entity ID via Settings > System > Logs.

**Scope:** `__init__.py` (`_calc_zombies()`). No attribute renames, no scoring changes.

### Bug Fix: Config Bonus Masking Zombie Penalty (#61)

**Problem:** The recorder configuration bonus (`config_bonus`, up to +10 pts) can fully negate the ratio-based zombie penalty on large instances. Result: a score of 100 is returned even when zombies are detected — violating the accuracy principle.

**Example:** 3 zombies / 300 total entities → p_zombie = 7 → app_score = min(100, 100 − 7 + 10) = 100.

**Solution:** Enforce a hard cap: when `zombie_count > 0`, `app_final` is capped at 99. Score 100 is only achievable with zero detected issues.

**Scope:** `__init__.py` (`_async_calc_application()`). One additional line after the existing `app_final` calculation.

---

## Planned

### PSI-Aware Recommendation Text

**Problem:** Two separate users confused PSI stall time with classic CPU utilization because the Advisor message `"CPU load is impacting score (6.5%)"` gives no indication that 6.5% refers to PSI stall time, not utilization percentage. Users who see 38% in System Monitor and 6.5% in the Advisor assume HAGHS is reacting to the wrong value.

**Solution:** Split `REC_CPU_LOAD` in `_build_recommendations` into two context-aware variants:
- PSI active: `"PSI CPU stall time is impacting score (X%)"` — makes the metric type explicit
- Classic sensor: `"CPU utilization is impacting score (X%)"` — unchanged behavior

Same pattern should be applied to the RAM and I/O recommendation strings for consistency.

**Scope:** Backend only (`__init__.py` + `const.py` + `strings.json`). No scoring logic changes, no breaking changes to sensor attributes.

### Smarter Zombie Grace Period for Battery-Class Sensors (#62)

**Problem:** Battery sensors (`device_class: battery`) and operating voltage sensors
(e.g., Homematic *Betriebsspannungspegel*) go `unavailable` when a Zigbee or Homematic
coordinator restarts.

Additionally, a user reported (2026-05-08) that battery sensors reappear in the zombie list after a full system restart even when the `haghs_ignore` label is correctly assigned. Likely cause: HAGHS evaluates zombie entities at startup before Home Assistant has fully loaded the entity registry, meaning labels are not yet available at the time of the first scan. This is a separate issue from the grace period fix.

**Solution:** Apply a separate, extended grace period for entities with
`device_class: battery` and measurement-type voltage sensors. Candidates:
- Increase the grace period to 60 minutes for `device_class: battery` entities.

**Scope:** `__init__.py` (`_calc_zombies()`). No attribute renames, no scoring formula
changes.

### Bug Fix: Denominator in `_calc_zombies`

**Problem:** `hass.states.async_all()` returns all states, including `automation`, `script`, `person`, `zone`, `input_boolean` etc., which can never be zombies. The zombie detection only runs over `ZOMBIE_DOMAINS` (9 specific domains), but the total entity count used as the denominator includes all domains.

**Result:** An artificially small ratio — an instance with many automations and few sensor entities is penalized far less for the same number of zombies compared to a pure sensor setup.

**Solution:** Count only entities from `ZOMBIE_DOMAINS` as the denominator, consistent with zombie detection logic.

**Scope:** `__init__.py` (`_calc_zombies()`).

### Bug Fix: HA Restart and `last_changed` (Zombie Grace Period)

**Problem:** After a HA restart, states are restored from the recorder database including their historical `last_changed` timestamp. An entity that was `unavailable` for 2 hours before shutdown will have `last_changed = "2+ hours ago"` after restart — HAGHS counts it as a zombie immediately instead of waiting for the 15-minute grace period.

**Solution:** Apply an extended grace period after a HA restart, since `last_changed` timestamps restored from the database are historical and cannot be used as a reliable baseline.

**Scope:** `__init__.py` (`_calc_zombies()`).

### Recommendation Flags as Boolean Attributes

**Problem:** Dashboard cards and external integrations must parse the `recommendations` string to react to specific advisor states. This is brittle and version-sensitive.

**Solution:** Expose individual boolean attributes alongside the existing `recommendations` string:

```
rec_backup_stale: true
rec_updates_pending: true
rec_zombie: false
```

Cards and automations can check `state_attr(e, 'rec_backup_stale')` directly. Intended as the interface standard for all HA Pulse integrations.

**Scope:** `__init__.py` + sensor attribute definitions. No changes to existing attributes.

### Update Grace Period (7 Days)

**Problem:** The `update_count` penalty deducts 5 points per pending update entity immediately when an update becomes available. This penalises normal user behaviour — most updates are installed within a few days — and causes score fluctuations that do not reflect a genuine health issue.

**Solution:** Introduce a 7-day grace period for `update_count`. An update entity only contributes to the penalty if it has been in the `available` state for more than 7 days. This requires persisting the first-seen timestamp per update entity across coordinator runs (e.g., in `hass.data`). The `p_core_lag` penalty (20 pts for HA Core ≥ 3 minor versions behind) is unaffected.

**Scope:** `__init__.py` (`_calc_updates()`). Persistent timestamp tracking in coordinator state. No changes to scoring formula, thresholds, or attributes.

### Config Audit Bonus Visibility

**Problem:** Users with a score below 100 and no active Advisor warnings have no way to understand why their score is not higher. The Advisor only flags active health issues, not missed bonus opportunities.

**Example (#67):** Application score 90, no warnings. Cause: no entity filter active (missing +5), purge threshold possibly not met (missing +5). No explanation in the card.

**Solution:** A separate "Tips" section in the dashboard card (visually distinct from warnings) that explains which Config Audit bonus points are not being earned. E.g.: "Enable entity filters in your recorder configuration to earn +5 bonus points."

**Scope:** Dashboard card template only. No backend changes required.

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

### Check Entities URL Filtering

**Status:** Not implementable within HAGHS.

**Reasoning:** HA does not support URL-based filtering of the entity list by status. `/config/entities/edit/ENTITY_ID` is not a valid route. The `?domain=` URL parameter is ignored by HA's entity configuration page. Markdown links inside HTML `<summary>` tags are not rendered as clickable links. This would require a feature request to HA Core.

---

*Last updated: 2026-05-21*
