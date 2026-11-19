## Summary

1-3 bullets describing what this PR does and why.

## Motivation

Link to issue, community thread, or short rationale.

Use `Fixes #<number>` to link the issue; it closes when the release reaches
`main`. Use `Refs #<number>` if the PR only partially addresses the issue.

## Changes

List of files/areas changed and the nature of the change.

> **Workflow files:** changes under `.github/workflows/` go into their own
> small PR, so a failing CI run there does not hide feature failures. Pushing
> them requires the workflow permission to be granted for that PR; without it
> the maintainer applies the change via the web UI.

## Test plan

Actual pytest output (at minimum the summary line) plus any manual steps
taken to validate the change.

## Checklist

- [ ] Target branch is `dev`
- [ ] Pytest output included in the Test plan section
- [ ] I have read `HAGHS_PHILOSOPHY.md` and `DEVELOPMENT_GUIDELINES.md`
- [ ] The active changelog for the next release updated (with file-level
      notes and any user-visible behavior change called out)
- [ ] No outbound network calls / external APIs introduced
- [ ] All I/O is async or wrapped in `async_add_executor_job`
- [ ] All new user-facing text is in `strings.json`, mirrored in
      `translations/en.json`, and added to `de.json` and `pt-BR.json`
      (or the PR says which translation is missing)
- [ ] Translation keys used in code match the keys defined in
      `strings.json`
- [ ] Type hints on all new public functions / methods
- [ ] `ruff check .` and `ruff format --check .` clean locally
- [ ] Coverage limits from CI met (90 % overall, 80 % `coordinator.py`)
- [ ] Docs updated for any behaviour change; `python script/gen_docs.py`
      run if attributes or options changed
- [ ] Migration path documented for any breaking change

## Breaking changes?

"None" or a list with migration notes.
