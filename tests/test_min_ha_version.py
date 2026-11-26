"""The minimum Home Assistant version in hacs.json is the one the minimum CI job tests (#237, HAGHS-20261124-008)."""

from __future__ import annotations

import json
from pathlib import Path

from packaging.requirements import Requirement

ROOT = Path(__file__).parent.parent


def test_hacs_minimum_equals_the_pinned_test_version() -> None:
    minimum = json.loads((ROOT / "hacs.json").read_text(encoding="utf-8"))["homeassistant"]
    pins = {}
    for line in (ROOT / "requirements_test_min.txt").read_text(encoding="utf-8").splitlines():
        line = line.split("#", 1)[0].strip()
        if line:
            requirement = Requirement(line)
            pins[requirement.name] = str(requirement.specifier)
    assert pins["homeassistant"] == f"=={minimum}"
    assert minimum == "2026.6.0"
