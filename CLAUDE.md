# HAGHS: notes for developers and coding agents

Read `HAGHS_PHILOSOPHY.md` (vision and alignment) and `DEVELOPMENT_GUIDELINES.md`
(coding rules) before changing code. `CONTRIBUTING.md` and `RELEASING.md` describe the
full workflow.

## Repository facts
- Integration code lives in `custom_components/haghs/`, tests in `tests/` (pytest,
  dependencies in `requirements_test.txt`).
- CI runs Ruff (`ruff check`, `ruff format --check`), Pytest with the coverage limits
  in `.github/workflows/ci.yml`, hassfest and HACS validation.
- The runtime is local-only: no outbound network calls and no external APIs.
- User-facing text belongs in `strings.json` and `translations/*.json`, never
  hardcoded in Python.
- Verify Home Assistant APIs against the current HA Core documentation and check the
  HA release notes (https://www.home-assistant.io/blog/) for breaking changes before
  relying on config flows, coordinators, entity platforms or selectors. If something is
  not possible in Home Assistant, say so and describe the workaround.

## Workflow
- Branch from `dev` (`feat/*`, `fix/*`, `chore/*`, `release/*`). Every change lands via a
  pull request into `dev` (squash merge). `main` only receives release PRs from `dev`
  (merge commit). Never push to `dev` or `main` directly.
- Update the active changelog for the next release in the same PR.
- Merges and releases need the maintainer's explicit OK.
- `README.md`, `HAGHS_PHILOSOPHY.md` and `DEVELOPMENT_GUIDELINES.md` are maintained by the
  owner; propose changes instead of committing them.
- Write GitHub comments and community responses in English.
