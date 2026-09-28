## Summary

1-3 bullets describing what this PR does and why.

## Motivation

Link to issue, community thread, or short rationale.

Use `Fixes #<number>` to close the issue automatically on merge. Use
`Refs #<number>` if the PR only partially addresses the issue.

## Changes

List of files/areas changed and the nature of the change.

> **Workflow files:** changes under `.github/workflows/` go into their own
> small PR, so a failing CI run there does not hide feature failures. The
> automation token may push them (workflow permission added on 28.09.2026).

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
- [ ] All new user-facing text is in `strings.json` and mirrored in
      `translations/en.json`
- [ ] Translation keys used in code match the keys defined in
      `strings.json`
- [ ] Type hints on all new public functions / methods
- [ ] `ruff` clean locally
- [ ] Migration path documented for any breaking change

## Breaking changes?

"None" or a list with migration notes.
