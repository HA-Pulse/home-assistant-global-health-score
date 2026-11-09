# Releasing HAGHS

This document describes the release flow. It builds on the branching model
in [`CONTRIBUTING.md`](./CONTRIBUTING.md): feature work lands on `dev` via
squash-merged pull requests, and `main` only receives release PRs from `dev`.

## Overview

Before step 1, the maintainer checks the repository documents (README, ROADMAP,
changelogs, templates, `hacs.json`, `manifest.json`) against the code; factual
corrections go into a separate docs PR into `dev`.

1. Prepare the release on a `release/vX.Y.Z` branch cut from `dev`.
2. Merge that branch into `dev` via PR (squash merge).
3. Open a release PR from `dev` into `main` (merge commit, not squash).
4. Publish a pre-release `vX.Y.ZbN` from `main` and announce it to beta testers.
5. After a few days without new reports, publish the stable release `vX.Y.Z`.

The merges into `dev` (step 2) and into `main` (step 3), and both release
publications (steps 4 and 5), require an explicit OK from the maintainer.
Everything else runs without further confirmation.

## 1. Prepare the release branch

- Cut `release/vX.Y.Z` from the latest `dev`.
- Bump `version` in `custom_components/haghs/manifest.json` to `X.Y.Z`.
- Finish the active changelog for this version (rename the file when the
  version number changes).
- Update `ROADMAP.md` for the release.
- Open a PR into `dev`. CI (Ruff, Pytest, Hassfest, HACS validation) must
  be green before merge.

## 2. Release PR into main

- Open a PR from `dev` into `main`, titled `Release vX.Y.Z`.
- Merge with a **merge commit** (not squash) so the `dev` history stays
  intact on `main`.
- Never push to `main` directly; the branch ruleset rejects it anyway.

## 3. Pre-release (beta)

- Publish a GitHub pre-release with tag `vX.Y.Zb1` on `main`.
  `manifest.json` already contains `X.Y.Z`; the release workflow verifies
  that the tag base fits the manifest version and allows the `bN` suffix.
- Pre-releases reach only users who opt in for the repository (off by
  default). The announcement for testers must explain both ways:
  - Home Assistant 2026.11 and later (built-in Marketplace): **Settings >
    Devices & Services > Marketplace**, the HAGHS device, enable the
    **Pre-release** entity (disabled by default) and turn it on. The
    Marketplace checks for new versions every 6 hours.
  - Up to 2026.10 (HACS): HAGHS in HACS, three-dot menu, **Redownload**,
    **Show beta versions**, pick the version, restart Home Assistant.

## 4. Stable release

- After a few days without new beta reports, publish `vX.Y.Z` (regular
  release, not marked as pre-release).
- Draft the release notes from the changelog.
- The release workflow attaches the ZIP asset (`haghs.zip`, for manual
  installs) to the release automatically. The Marketplace and HACS install
  from the repository content.
- Afterwards: close the completed issues and post the announcement
  (community forum / Reddit).

## 5. Documentation-only release

The Marketplace shows the README of the installed or latest released
version, so a documentation fix reaches its users only with a release.

- Allowed only when `git diff vX.Y.Z..dev -- custom_components/` changes
  nothing but `version` in `manifest.json`. Code waiting on `dev` blocks it.
- Patch version (`vX.Y.Z+1`), no beta.
- Slim release check: CI green, link check (`tests/test_docs_layout.py` and
  every README/docs link after the merge into `main`), and a documentation
  audit of every changed statement. No version matrix, no full reference run.
- Steps 1, 2 and 4 otherwise unchanged.

## Tag and version check

The release workflow checks the tag against the `version` field in
`custom_components/haghs/manifest.json`. The check runs after the release is
published: on mismatch the job fails and the `haghs.zip` asset is not
attached, but the release itself is already live. Verify the tag before
publishing.

- `v2.4.0` matches version `2.4.0`.
- `v2.4.0b1` matches version `2.4.0` (the beta suffix is allowed).
- `v2.4.1` against version `2.4.0` fails the check.
