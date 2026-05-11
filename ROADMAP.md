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

*No items currently queued for v2.4. Open issues are triaged on
[GitHub](https://github.com/d-n91/home-assistant-global-health-score/issues)
and added here once a concrete scope is agreed.*

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

*Last updated: 2026-05-11*
