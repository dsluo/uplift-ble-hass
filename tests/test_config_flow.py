"""Tests for the Uplift Desk (BLE) config flow."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from bleak.exc import BleakError
from homeassistant.config_entries import SOURCE_BLUETOOTH, SOURCE_USER
from homeassistant.const import CONF_ADDRESS
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from custom_components.uplift_ble.const import (
    CONF_CONNECTION_MODE,
    CONF_FALLBACK_UNIT,
    CONF_IDLE_TIMEOUT,
    CONF_SERVICE_UUID,
    DOMAIN,
)
from custom_components.uplift_ble.manager import UnsupportedDeskError

from .conftest import ADDRESS, DESK_CONFIG, SERVICE_UUID, make_entry, make_service_info

SETTINGS = {
    CONF_CONNECTION_MODE: "on_demand",
    CONF_FALLBACK_UNIT: "inches",
    CONF_IDLE_TIMEOUT: 45.0,
}


@pytest.fixture
def mock_probe() -> AsyncMock:
    with patch(
        "custom_components.uplift_ble.config_flow.async_probe_desk",
        return_value=DESK_CONFIG,
    ) as probe:
        yield probe


@pytest.fixture(autouse=True)
def mock_setup_entry() -> AsyncMock:
    with patch(
        "custom_components.uplift_ble.async_setup_entry", return_value=True
    ) as setup:
        yield setup


async def test_bluetooth_discovery(hass: HomeAssistant, mock_probe: AsyncMock) -> None:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_BLUETOOTH}, data=make_service_info()
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "bluetooth_confirm"

    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["step_id"] == "settings"

    result = await hass.config_entries.flow.async_configure(result["flow_id"], SETTINGS)
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "UPLIFT-1234 (EEFF)"
    assert result["data"] == {CONF_ADDRESS: ADDRESS, CONF_SERVICE_UUID: SERVICE_UUID}
    assert result["options"] == {**SETTINGS, CONF_IDLE_TIMEOUT: 45}
    assert result["result"].unique_id == ADDRESS


async def test_bluetooth_discovery_unsupported_service(hass: HomeAssistant) -> None:
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": SOURCE_BLUETOOTH},
        data=make_service_info(service_uuids=["0000180a-0000-1000-8000-00805f9b34fb"]),
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "not_supported"


async def test_bluetooth_discovery_already_configured(hass: HomeAssistant) -> None:
    make_entry().add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_BLUETOOTH}, data=make_service_info()
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_user_flow(hass: HomeAssistant, mock_probe: AsyncMock) -> None:
    other = make_service_info(
        address="11:22:33:44:55:66",
        name="Headphones",
        service_uuids=["0000180a-0000-1000-8000-00805f9b34fb"],
    )
    with patch(
        "custom_components.uplift_ble.config_flow.async_discovered_service_info",
        return_value=[make_service_info(), other],
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": SOURCE_USER}
        )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"
    schema_addresses = result["data_schema"].schema[CONF_ADDRESS].container
    assert list(schema_addresses) == [ADDRESS]

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_ADDRESS: ADDRESS}
    )
    assert result["step_id"] == "settings"
    result = await hass.config_entries.flow.async_configure(result["flow_id"], SETTINGS)
    assert result["type"] is FlowResultType.CREATE_ENTRY
    mock_probe.assert_awaited_once()


async def test_user_flow_no_devices(hass: HomeAssistant) -> None:
    with patch(
        "custom_components.uplift_ble.config_flow.async_discovered_service_info",
        return_value=[],
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": SOURCE_USER}
        )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "no_devices_found"


async def test_settings_cannot_connect_then_recovers(
    hass: HomeAssistant, mock_probe: AsyncMock
) -> None:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_BLUETOOTH}, data=make_service_info()
    )
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})

    mock_probe.side_effect = BleakError("boom")
    result = await hass.config_entries.flow.async_configure(result["flow_id"], SETTINGS)
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "cannot_connect"}

    mock_probe.side_effect = None
    result = await hass.config_entries.flow.async_configure(result["flow_id"], SETTINGS)
    assert result["type"] is FlowResultType.CREATE_ENTRY


async def test_settings_unsupported_desk(
    hass: HomeAssistant, mock_probe: AsyncMock
) -> None:
    mock_probe.side_effect = UnsupportedDeskError
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_BLUETOOTH}, data=make_service_info()
    )
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], SETTINGS)
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "not_supported"


async def test_options_flow(hass: HomeAssistant) -> None:
    entry = make_entry()
    entry.add_to_hass(hass)

    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] is FlowResultType.FORM
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], SETTINGS
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.options == {**SETTINGS, CONF_IDLE_TIMEOUT: 45}
