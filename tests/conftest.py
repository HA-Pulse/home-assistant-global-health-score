"""Common fixtures for the HAGHS test suite."""

from __future__ import annotations

import importlib
import sys

import pytest

try:
    import pytest_homeassistant  # noqa: F401
except ModuleNotFoundError:
    # The minimum-version CI job (requirements_test_min.txt, #237) uses the older package name of the same test
    # helpers; alias it, and the submodules the tests import, so every test runs unchanged there.
    for _name in (
        "",
        ".common",
        ".components",
        ".components.recorder",
        ".components.recorder.common",
    ):
        sys.modules[f"pytest_homeassistant{_name}"] = importlib.import_module(
            f"pytest_homeassistant_custom_component{_name}"
        )


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(
    enable_custom_integrations: None,
) -> None:
    """Enable loading of the HAGHS custom integration in every test."""
    return


@pytest.fixture
def hass_config_dir(hass_tmp_config_dir: str) -> str:
    """Give tests an existing, isolated Home Assistant config directory."""
    return hass_tmp_config_dir
