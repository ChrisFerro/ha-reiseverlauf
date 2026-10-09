"""Fixtures for the service action tests, some of which run the recorder."""

from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def media_dir(tmp_path: Path) -> Path:
    """
    Return the media folder without touching `hass`.

    The recorder fixtures must run before `hass` is created, so `setup()` assigns the folder instead.
    """
    return tmp_path


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(recorder_db_url: str, enable_custom_integrations: None) -> None:
    """Prepare the recorder database before `hass` exists, then load custom integrations."""
