## Summary

1-3 bullets describing what this PR does and why.

## Motivation

Link to issue, community thread, or short rationale.

## Changes

ist of files/areas changed and the nature of the change.

## Test plan

Manual steps taken to validate. Once the test suite exists, list the
pytest commands you ran.

## Checklist

- [ ] Target branch is `dev`
- [ ] I have read `HAGHS_PHILOSOPHY.md` and `DEVELOPMENT_GUIDELINES.md`
- [ ] `v2.3_CHANGELOG.md` updated (with file-level notes and any
      user-visible behavior change called out)
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
