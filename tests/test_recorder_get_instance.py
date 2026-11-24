"""The recorder is read through Home Assistant's get_instance() helper (#236, HAGHS-20261124-006)."""

from __future__ import annotations

import logging
from types import SimpleNamespace

from custom_components.haghs import coordinator as coordinator_module
from tests.factories import make_coordinator

LOGGER = "custom_components.haghs.coordinator"


def test_the_helper_provides_the_recorder(hass, monkeypatch) -> None:
    recorder = SimpleNamespace(keep_days=5, entity_filter=object())
    seen: list[object] = []

    def helper(hass_arg):
        seen.append(hass_arg)
        return recorder

    monkeypatch.setattr(coordinator_module, "get_recorder_instance", helper, raising=False)
    coord = make_coordinator(hass)
    info = coord._read_recorder_info()
    assert seen == [hass]
    assert info.available is True
    assert info.keep_days == 5
    assert info.entity_filter_active is True


def test_recorder_not_set_up_is_one_debug_line(hass, caplog) -> None:
    coord = make_coordinator(hass)
    caplog.set_level(logging.DEBUG, logger=LOGGER)
    info = coord._read_recorder_info()
    assert info.available is False
    assert info.keep_days is None
    records = [r for r in caplog.records if r.name == LOGGER and "Recorder" in r.getMessage()]
    assert len(records) == 1
    assert records[0].levelno == logging.DEBUG
    assert (
        records[0].getMessage() == "HAGHS: Recorder not set up; config audit without recorder data"
    )
