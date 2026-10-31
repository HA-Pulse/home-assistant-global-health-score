# HAGHS Roadmap

This document outlines completed, planned, and declined features for the
Home Assistant Global Health Score. It lives next to the active changelog
file and is refreshed whenever a release lands.

---

## Completed in v2.4

All work below is committed on `dev` and described in detail in
[`v2.4.0_CHANGELOG.md`](./v2.4.0_CHANGELOG.md).

### Features

- **Repairs count in the application score (#97)**: 5 points per open repair
  (cap 10), application score capped at 99 while a repair is open; HAGHS's own
  repairs are excluded, HA's "Ignore" takes a repair out of the count.
- **Integration entries**: individual config entries can be excluded from
  Integration Health; the counted entries are listed by name
  (`integration_unhealthy_entries`, #134) and the recommendation names config
  entries, not integrations.
- **Zombies explained (#154)**: grouped by integration, since when each zombie
  is unavailable, and why it is reported (`config_entry_missing`,
  `integration_not_loaded`, `not_provided`, `unavailable`).
- **Dead devices (#120) and empty devices (#93)**: informational markers for
  devices whose monitored entities are all unavailable and for devices without
  any entity, from registry facts only.
- **Stale reporting (discussion #79)**: passive candidates and opt-in watch
  labels for entities that stopped reporting.
- **Ignore labels on areas (discussion #96)** and **conditional ignore labels**
  that apply only while a helper is on (vacation mode without Spook).
- **Translations (#114, #138, #163)**: recommendation texts translatable;
  Brazilian Portuguese and German.
- **Unregistered entities informational (#98)** and **calculation failures
  visible (#135)**.
- **Dashboard cards v1.4**: zombie reasons and since on the Pro card, stale
  reporting, calculation status lines and a link to every entity, device and
  settings page; dead and empty devices link to their device page through
  `dead_device_ids` and `empty_device_ids` (#172). Every card link is checked
  in a browser before a release.

### Bug fixes

- **Every missing score point explained (#92)**: Config-Audit bonus and
  Integration Health produce a recommendation line and a `rec_*` flag.
- **Coordinator safety net (#103)**, **dead-device false positives (#143)**,
  **PSI fallback gate (#123)**, **Spook named for the label actions (#99)**,
  **punctuation (#136)**.
- **Recorder attribute size (#159)**: entity lists are excluded from recorder
  history, so large instances stay below the 16 KB limit.
- **Informational checks isolated**: a failure in dead devices, empty devices
  or zombie reasons no longer takes the score down.
- **No deprecated device registry access**: the device registry is read the way
  Home Assistant supports from 2026.9 on.

### Infrastructure

- **Pillar test coverage and CI (#107, #117, #128)**: `coordinator.py` at 100 %
  statement and branch coverage; CI runs on Python 3.14 and gates the package at
  90 % and `coordinator.py` at 80 %. The suite holds 550 tests.

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

*Last updated: 2026-10-31*