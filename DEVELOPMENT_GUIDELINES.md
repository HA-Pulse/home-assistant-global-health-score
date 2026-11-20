# HAGHS Development Guidelines (HA Core Standards)

## 1. Code Quality & Structure
- **Type Hints (PEP 484):** All Python code must be annotated with type hints, at least on all public methods and function signatures. CI does not check types; reviewers do.
- **Language & Naming:** Code, variables, class names, and comments must be written exclusively in English. Follow PEP 8 standards.
- **Linting:** The code must comply with official Home Assistant standards (using `ruff` for clean linting and formatting).

## 2. Home Assistant Core Rules
- **Async-First (Non-Blocking):** I/O must never block the event loop. HAGHS has no network I/O (see `HAGHS_PHILOSOPHY.md`, Local-Only). Blocking file and system calls (reading `/proc`, `psutil`, `os.path.getsize`) run through `hass.async_add_executor_job`, as the coordinator does for PSI, disk usage and database size. Do not add async I/O libraries such as `aiofiles` for this.
- **Setup & Configuration:** YAML configurations for integrations are deprecated. All configuration and options must be handled exclusively through a UI-based `ConfigFlow` and `OptionsFlow`.
- **Data Fetching:** Always use the `DataUpdateCoordinator` for regular updates. No isolated `time.sleep()` or custom loops.
- **Localization (I18n):** Never hardcode user-facing text or error messages in Python code. Use `strings.json`, mirrored in `translations/en.json`; `translations/de.json` and `translations/pt-BR.json` must contain every key (enforced by the translation tests, see `CONTRIBUTING.md`).
- **Compatibility:** HAGHS must run on the minimum Home Assistant version in `hacs.json` (currently 2024.10.0) and keep Python syntax compatible with `target-version` in `pyproject.toml` (py312). Use newer Home Assistant APIs only with a fallback for older versions, and act on Home Assistant deprecations before their removal release (example: #214).

## 3. Safety & Stability
- **Safety Net:** All sub-calculations must use the safety-net pattern (`_safe_calc` with timeout). A failing pillar must never crash the sensor. The coordinator itself must never raise.
- **Error Handling:** `_safe_calc` catches exceptions and timeouts of a sub-calculation: the pillar falls back to a neutral score, the fallback is counted in `pillar_fallback_count`, and a warning is logged. If the whole update cycle fails, the last valid result is kept and the failure is logged as an error with traceback (#103). Nothing is raised to Home Assistant.
- **Testing:** Every change to integration code must include tests; new scoring logic needs unit tests with known input/output pairs. CI enforces at least 90 % coverage for `custom_components/haghs` and 80 % for `coordinator.py`. This is a prerequisite for HA Core adoption.
