"""Common fixtures for the HAGHS test suite."""

from __future__ import annotations

import pytest


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
