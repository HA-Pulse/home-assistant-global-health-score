# HAGHS Roadmap

This document outlines planned features and improvements for the Home Assistant Global Health Score.

## In Progress (dev branch)

### Power Supply Status Detection (#21)

Auto-detect under-voltage conditions on Raspberry Pi devices via `binary_sensor.rpi_power_status`. A `Problem` state applies a flat 20-point penalty to the hardware score. No configuration needed — the check is skipped automatically on non-RPi hardware.

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

Additionally, a user reported (2026-05-08) that battery sensors reappear in the zombie list after a system restart even when the `haghs_ignore` label is correctly assigned. The relationship between this and the grace period fix is still under investigation.

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

---

## Declined

### CPU Temperature Monitoring (#21)

**Status:** Will not be implemented.

**Reasoning:** CPU temperature is a predictive hardware metric, not a current health indicator. If thermal throttling occurs, it already surfaces through elevated PSI stall values, which HAGHS captures. Adding temperature as a scoring component would dilute the existing hardware score without adding actionable health information. The required user configuration (sensor selection, threshold definition per hardware platform) conflicts with the pragmatism principle.

### Check Entities URL Filtering

**Status:** Not implementable within HAGHS.

**Reasoning:** HA does not support URL-based filtering of the entity list by status. `/config/entities/edit/ENTITY_ID` is not a valid route. The `?domain=` URL parameter is ignored by HA's entity configuration page. Markdown links inside HTML `<summary>` tags are not rendered as clickable links. This would require a feature request to HA Core.

---

*Last updated: 2026-05-08*
