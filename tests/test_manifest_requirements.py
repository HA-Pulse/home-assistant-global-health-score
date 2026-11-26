"""psutil is declared in the manifest with a lower bound only (#238, HAGHS-20261124-007).

An exact pin could make Home Assistant reinstall psutil under its own integrations; a lower bound is always met by the
psutil Home Assistant already installs.
"""

from __future__ import annotations

import json
from importlib.metadata import version
from pathlib import Path

from packaging.requirements import Requirement
from packaging.version import Version

MANIFEST = Path(__file__).parent.parent / "custom_components" / "haghs" / "manifest.json"


def _requirements() -> list[Requirement]:
    return [
        Requirement(r) for r in json.loads(MANIFEST.read_text(encoding="utf-8"))["requirements"]
    ]


def test_psutil_is_the_only_requirement_with_a_lower_bound_only() -> None:
    requirements = _requirements()
    assert [r.name for r in requirements] == ["psutil"]
    specs = list(requirements[0].specifier)
    assert [s.operator for s in specs] == [">="]


def test_the_installed_psutil_meets_the_requirement() -> None:
    requirement = _requirements()[0]
    assert Version(version("psutil")) in requirement.specifier
