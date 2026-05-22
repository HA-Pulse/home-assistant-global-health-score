# HAGHS Test Suite

Bootstrapped per issue [#54](https://github.com/d-n91/home-assistant-global-health-score/issues/54).

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
```

## Linting

```bash
ruff check .
ruff format --check .
```

## Layout

- `tests/conftest.py` — global fixtures (auto-enables `custom_integrations`).
- `tests/test_*.py` — one file per concern (migration, scoring pillars, …).

## Roadmap

Per issue #54 the suite grows in three phases:

1. Infrastructure (this commit).
2. Migration tests covering every branch of `_migrate_ignore_label_value` and
   `async_migrate_entry`.
3. Scoring-pillar pilot test (suggested: `p_power` / power supply detection).
