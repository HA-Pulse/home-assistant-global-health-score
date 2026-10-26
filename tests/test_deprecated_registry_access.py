"""No deprecated device registry access in the integration code.

HA reports `DeviceRegistry.devices` used as a mapping (removal in 2027.9) and the
`DeviceEntry` reads `config_entries`, `config_entries_subentries` and
`primary_config_entry` (warning from 2026.10, removal in 2027.10). The one allowed
exception is the marked fallback for HA versions without `config_entry_id`.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

SOURCE = Path(__file__).resolve().parents[1] / "custom_components" / "haghs"
MARKER = "# deprecated-fallback: HA < 2026.9 has no config_entry_id"
DEVICES_AS_MAPPING = re.compile(r"\.devices(\.(values|items|keys|get|get_entry)\(|\[)")
DEVICE_ENTRY_READS = re.compile(r"\.(config_entries_subentries|primary_config_entry)\b")
CONFIG_ENTRIES = re.compile(r"(?<!hass)(?<!homeassistant)\.config_entries\b")


def _findings(text: str) -> list[str]:
    findings = []
    for number, line in enumerate(text.splitlines(), 1):
        if DEVICES_AS_MAPPING.search(line):
            findings.append(f"{number}: devices used as a mapping")
        if DEVICE_ENTRY_READS.search(line):
            findings.append(f"{number}: deprecated DeviceEntry read")
        if CONFIG_ENTRIES.search(line) and MARKER not in line:
            findings.append(f"{number}: DeviceEntry.config_entries")
    return findings


def test_integration_code_has_no_deprecated_registry_access() -> None:
    findings = {
        path.name: _findings(path.read_text(encoding="utf-8"))
        for path in sorted(SOURCE.glob("*.py"))
    }
    assert {name: found for name, found in findings.items() if found} == {}
    markers = sum(path.read_text(encoding="utf-8").count(MARKER) for path in SOURCE.glob("*.py"))
    assert markers == 1


@pytest.mark.parametrize(
    "snippet",
    [
        "devices = list(dev_reg.devices.values())",
        "entry = registry.devices[device_id]",
        "found = dev_reg.devices.get(device_id)",
        "ids = device.config_entries",
        "subs = device.config_entries_subentries",
        "primary = device.primary_config_entry",
    ],
)
def test_each_forbidden_pattern_is_found(snippet: str) -> None:
    assert _findings(snippet)


@pytest.mark.parametrize(
    "snippet",
    [
        "for device in dev_reg.devices:",
        "entry = self.hass.config_entries.async_get_entry(entry_id)",
        "from homeassistant.config_entries import ConfigEntry",
        f"legacy = device.config_entries  {MARKER}",
        "entry_id = device.config_entry_id",
    ],
)
def test_allowed_forms_pass(snippet: str) -> None:
    assert _findings(snippet) == []
