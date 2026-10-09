"""Tests for the config, reconfigure and options flows."""

from datetime import timedelta
from typing import Any

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.reiseverlauftracker.config_flow_handler.validators import (
    InvalidOutputDirError,
    normalize_output_dir,
)
from custom_components.reiseverlauftracker.const import (
    CONF_END_DELAY,
    CONF_OUTPUT_DIR,
    CONF_TRACKER_ENTITY,
    DOMAIN,
    SECTION_DETECTION,
    SECTION_EXPORT,
    SECTION_THRESHOLDS,
)
from homeassistant.config_entries import SOURCE_USER, ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

TRACKER = "device_tracker.camper_gps"


async def test_user_flow_creates_entry_named_after_tracker(hass: HomeAssistant, entry_data: dict[str, Any]) -> None:
    hass.states.async_set(TRACKER, "not_home", {"friendly_name": "Camper GPS"})
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    assert result["type"] is FlowResultType.FORM

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {**entry_data, CONF_OUTPUT_DIR: "/reiseverlauf/2026/"}
    )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Camper GPS"
    assert result["data"][CONF_OUTPUT_DIR] == "reiseverlauf/2026"
    assert result["result"].unique_id == TRACKER


async def test_user_flow_rejects_output_dir_outside_media(hass: HomeAssistant, entry_data: dict[str, Any]) -> None:
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {**entry_data, CONF_OUTPUT_DIR: "../config"}
    )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {CONF_OUTPUT_DIR: "invalid_output_dir"}


async def test_same_tracker_cannot_be_set_up_twice(
    hass: HomeAssistant, config_entry: MockConfigEntry, entry_data: dict[str, Any]
) -> None:
    config_entry.add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], entry_data)

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_reconfigure_changes_tracker_and_unique_id(
    hass: HomeAssistant, init_integration: MockConfigEntry, entry_data: dict[str, Any]
) -> None:
    result = await init_integration.start_reconfigure_flow(hass)
    assert result["type"] is FlowResultType.FORM

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {**entry_data, CONF_TRACKER_ENTITY: "device_tracker.new_gps"}
    )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert init_integration.unique_id == "device_tracker.new_gps"
    assert init_integration.data[CONF_TRACKER_ENTITY] == "device_tracker.new_gps"


async def test_options_flow_stores_sections_and_reloads(hass: HomeAssistant, init_integration: MockConfigEntry) -> None:
    result = await hass.config_entries.options.async_init(init_integration.entry_id)
    assert result["type"] is FlowResultType.FORM

    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {
            SECTION_DETECTION: {"end_delay": 30, "merge_window": 0, "min_movement": 200},
            SECTION_EXPORT: {"title_format": "date", "place_names": False, "scale": 2, "margin": 5},
            SECTION_THRESHOLDS: {
                "standstill_speed": 3,
                "max_accuracy": 50,
                "min_point_distance": 15,
                "elevation_hysteresis": 10,
            },
        },
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert init_integration.options[SECTION_DETECTION][CONF_END_DELAY] == 30
    assert init_integration.state is ConfigEntryState.LOADED
    settings = init_integration.runtime_data.settings
    assert settings.end_delay == timedelta(minutes=30)
    assert settings.merge_window == timedelta(0)
    assert settings.title_format == "date"
    assert not settings.place_names


async def test_defaults_apply_without_options(hass: HomeAssistant, init_integration: MockConfigEntry) -> None:
    settings = init_integration.runtime_data.settings

    assert settings.end_delay == timedelta(minutes=60)
    assert settings.merge_window == timedelta(hours=6)
    assert settings.min_movement_m == 100
    assert settings.title_format == "date_place"
    assert settings.place_names
    assert settings.is_dplus_on("on")
    assert not settings.is_dplus_on("unavailable")


async def test_unload_entry(hass: HomeAssistant, init_integration: MockConfigEntry) -> None:
    assert await hass.config_entries.async_unload(init_integration.entry_id)
    assert init_integration.state is ConfigEntryState.NOT_LOADED


@pytest.mark.parametrize(
    ("value", "expected"),
    [("reiseverlauf", "reiseverlauf"), ("/a/b/", "a/b"), (" ./a ", "a"), ("a\\b", "a/b")],
)
def test_normalize_output_dir(value: str, expected: str) -> None:
    assert normalize_output_dir(value) == expected


@pytest.mark.parametrize("value", ["", "/", "..", "a/../b"])
def test_normalize_output_dir_rejects(value: str) -> None:
    with pytest.raises(InvalidOutputDirError):
        normalize_output_dir(value)
