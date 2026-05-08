"""Common fixtures for the HAGHS test suite."""
from __future__ import annotations

from collections.abc import Generator

import pytest


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(
    enable_custom_integrations: None,
) -> Generator[None, None, None]:
    """Enable loading of the HAGHS custom integration in every test."""
    yield
