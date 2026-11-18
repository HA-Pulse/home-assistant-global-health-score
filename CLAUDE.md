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
  (merge commit) and, while no code waits on `dev`
  (`git diff origin/main..origin/dev -- custom_components/` is empty), documentation merges
  from `dev` (merge commit). Never push to `dev` or `main` directly.
- Roadmap: when the maintainer commits something to a version (issue comment, decision in
  a session, planning card), set the milestone `vX.Y.Z` on its issue and add one line under
  `ROADMAP.md` "Planned" > `vX.Y` (issue number and one sentence of benefit) in a docs PR
  into `dev` in the same session; one PR may carry the decisions of a day. Moved means the
  line and the milestone move; declined means an entry under "Declined" with the reason.
  While no code waits on `dev`, a dev → main merge PR follows. At the release the finished
  lines move to "Completed in vX.Y" (see `RELEASING.md`).
- Pure documentation PRs change only `.md` files and `docs/`, and none of
  `custom_components/`, `tests/`, `.github/`, `CLAUDE.md`, `AGENTS.md`, `CONTRIBUTING.md`
  or `RELEASING.md`. Once CI is green and the review is clean, one maintainer OK covers the
  squash merge into `dev` and, while no code waits on `dev`, the dev → main merge PR (merge
  commit) and its merge. A red CI, a conflict, a review that is not clean or code waiting on
  `dev` stops the flow. Releases keep their own OKs; any other PR follows the normal flow.
- Update the active changelog for the next release in the same PR.
- Merges and releases need the maintainer's explicit OK.
- `README.md`, `HAGHS_PHILOSOPHY.md` and `DEVELOPMENT_GUIDELINES.md` are maintained by the
  owner; propose changes instead of committing them.
- Write GitHub comments and community responses in English.
