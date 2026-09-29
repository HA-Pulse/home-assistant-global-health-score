# HAGHS Test Suite

Bootstrapped per issue [#54](https://github.com/HA-Pulse/home-assistant-global-health-score/issues/54).

## Running tests locally

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements_test.txt
pytest
```

`pytest-asyncio` is configured in `auto` mode via `pyproject.toml`, so async
tests do not need a per-test marker.

## Coverage

```bash
pytest --cov=custom_components.haghs --cov-report=term-missing
coverage report --include='custom_components/haghs/coordinator.py' --fail-under=80
```

The CI gate fails below 90 % for the package (`--cov-fail-under` in
`.github/workflows/ci.yml`), and `coordinator.py` is gated at 80 % on top of
that (issue #107). Current state: `coordinator.py` 100 %, package 93 %.

## Linting

```bash
ruff check .
ruff format --check .
```

## Layout

- `tests/conftest.py` — global fixtures (auto-enables `custom_integrations`).
- `tests/factories.py`: shared factories (`make_coordinator`, `patch_psi`,
  `patch_disk`). Plain helpers, no pytest fixtures.
- `tests/test_*.py` — one file per concern (migration, scoring pillars, …).
  The pillar coverage from #107 lives in `test_hardware_tiers.py`,
  `test_hardware_disk.py`, `test_hardware_assembly.py`,
  `test_application_components.py`, `test_recommendation_branches.py` and
  `test_ignore_paths.py`.

## Manual smoke test

The pytest suite covers the scoring logic against mocked Home Assistant
objects. It cannot exercise the real runtime: the label registry, the
recorder database, PSI detection or the repair flow. Run this checklist on
a live instance before a release and after changes to `coordinator.py`,
`config_flow.py` or `repairs.py`.

**Prerequisites**

- A live Home Assistant instance with HAGHS installed (HACS or a manual
  copy of `custom_components/haghs/`).
- Access to **Settings > System > Logs** and **Developer Tools > States**.
- 10 to 15 minutes; the zombie steps must wait out the grace period
  (default 5 minutes).

**Steps** (each with its expected result)

1. **Setup (config flow):** Remove the integration and add it again
   (**Settings > Devices & Services > Add Integration > HAGHS**).
   *Expected:* the form shows the CPU/RAM fallback pickers (optional on
   hosts with PSI, required otherwise), the storage type dropdown and the
   ignore-label multi-select with `haghs_ignore` pre-selected. Finishing
   creates one sensor, **System: HA - Global Health Score** (entity id
   starts with `sensor.system_ha_global_health_score`), with a state
   between 0 and 100 and unit `%`.
2. **Score consistency:** Open the sensor in **Developer Tools > States**
   and compare the attributes.
   *Expected:* the state matches the documented formula
   `floor(hardware_score * 0.4 + application_score * 0.6)`, every `rec_*`
   flag matches the text in `recommendations`, and `db_size_mb` looks
   plausible for the database in use.
3. **Update cycle:** Watch the sensor for two update intervals (default
   60 s, adjustable in the options).
   *Expected:* state and attributes refresh; no HAGHS errors in the log.
4. **Zombie detection:** Force a real test entity to `unavailable` (unplug
   the device, or set the state via Developer Tools) and wait out the
   zombie grace period (default 5 min; battery-class entities use the
   battery grace, default 60 min).
   *Expected:* the entity appears in `zombie_entities`, `zombie_count`
   increases by one and the application score is capped at 99.
5. **Ignore labels (static):** Assign the `haghs_ignore` label to the
   zombie entity from step 4 (entity settings dialog, label picker).
   *Expected:* from the next update cycle on, the entity is excluded from
   `zombie_count` and the cap releases.
6. **Ignore labels (dynamic):** Call the native action
   `homeassistant.add_label_to_entity` with your label and the test entity
   (**Developer Tools > Actions**), then
   `homeassistant.remove_label_from_entity` again.
   *Expected:* adding the label excludes the entity without editing the
   config entry; removing it brings the entity back. This is the path
   documented in the README automation example.
7. **Repair flow (hosts without PSI only):** Leave the CPU/RAM fallback
   sensors empty in the options on a host where PSI is not available.
   *Expected:* a repair `fallback_missing` appears under **Settings >
   System > Repairs**; the fix flow lets you pick the CPU/RAM sensors and
   resumes operation without a restart. On PSI hosts (HAOS, Supervised)
   skip this step.
8. **Reload and restart:** Reload the integration, then restart Home
   Assistant.
   *Expected:* the sensor comes back with a valid score, the log shows no
   errors and no "Migration handler not found" warnings.
9. **Log check:** Search the logs for `haghs`.
   *Expected:* no ERROR entries and no tracebacks.

**Verification log**

Add one line per run, most recent on top:

| Date | HAGHS | Home Assistant | Result / notes |
|---|---|---|---|
| | | | |

## Roadmap

Per issue #54 the suite grew in three phases; all three are complete:

1. Infrastructure.
2. Migration tests covering every branch of `_migrate_ignore_label_value` and
   `async_migrate_entry` (`tests/test_migration.py`).
3. Scoring-pillar pilot test (`tests/test_hardware_power.py`, `p_power`).
