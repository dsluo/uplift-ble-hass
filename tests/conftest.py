"""Fixtures for Uplift Desk (BLE) tests."""

from __future__ import annotations

import time
from collections.abc import Generator
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from bleak.backends.device import BLEDevice
from bleak.backends.scanner import AdvertisementData
from homeassistant.components.bluetooth import BluetoothServiceInfoBleak
from homeassistant.const import CONF_ADDRESS
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry
from uplift_ble import DeskEventType
from uplift_ble.desk_configs import DESK_CONFIGS_BY_SERVICE

from custom_components.uplift_ble.const import (
    CONF_CONNECTION_MODE,
    CONF_FALLBACK_UNIT,
    CONF_IDLE_TIMEOUT,
    CONF_SERVICE_UUID,
    DOMAIN,
)

ADDRESS = "AA:BB:CC:DD:EE:FF"
SERVICE_UUID = "0000fe60-0000-1000-8000-00805f9b34fb"
DESK_CONFIG = DESK_CONFIGS_BY_SERVICE[SERVICE_UUID]

COMMANDS = (
    "request_units",
    "request_height_limits",
    "move_up",
    "move_down",
    "stop_movement",
    "move_to_height_preset_1",
    "move_to_height_preset_2",
    "move_to_height_preset_3",
    "move_to_height_preset_4",
    "save_height_preset_1",
    "save_height_preset_2",
    "move_to_specified_height",
    "set_units",
    "set_touch_mode",
    "set_height_limit_max",
    "set_calibration_offset",
    "set_current_height_as_height_limit_max",
    "set_current_height_as_height_limit_min",
    "clear_height_limit",
    "reset",
)


@pytest.fixture(autouse=True)
def auto_enable(enable_custom_integrations: None, enable_bluetooth: None) -> None:
    """Enable custom integrations and a mocked Bluetooth stack."""


def make_service_info(
    address: str = ADDRESS,
    name: str = "UPLIFT-1234",
    service_uuids: list[str] | None = None,
) -> BluetoothServiceInfoBleak:
    service_uuids = [SERVICE_UUID] if service_uuids is None else service_uuids
    return BluetoothServiceInfoBleak(
        name=name,
        address=address,
        rssi=-60,
        manufacturer_data={},
        service_data={},
        service_uuids=service_uuids,
        source="local",
        device=BLEDevice(address, name, None),
        advertisement=AdvertisementData(
            local_name=name,
            manufacturer_data={},
            service_data={},
            service_uuids=service_uuids,
            tx_power=None,
            rssi=-60,
            platform_data=(),
        ),
        connectable=True,
        time=time.monotonic(),
        tx_power=None,
    )


class FakeClient:
    """Stands in for a connected BleakClientWithServiceCache."""

    def __init__(self, disconnected_callback: Any = None) -> None:
        self.is_connected = True
        self._disconnected_callback = disconnected_callback
        self.disconnect = AsyncMock(side_effect=self._disconnect)

    async def _disconnect(self) -> None:
        self.is_connected = False

    def drop(self) -> None:
        """Simulate the desk going out of range."""
        self.is_connected = False
        if self._disconnected_callback is not None:
            self._disconnected_callback(self)


class FakeController:
    """Records commands and lets tests emit library events."""

    def __init__(self) -> None:
        self._listeners: dict[DeskEventType, list[Any]] = {}
        self.start = AsyncMock()
        self.stop = AsyncMock()
        for name in COMMANDS:
            setattr(self, name, AsyncMock())

    def on(self, event: DeskEventType, handler: Any) -> None:
        self._listeners.setdefault(event, []).append(handler)

    def emit(self, event: DeskEventType, *args: Any) -> None:
        for handler in self._listeners.get(event, []):
            handler(*args)


class FakeDesk:
    """Holds the fakes created for each connection."""

    def __init__(self) -> None:
        self.clients: list[FakeClient] = []
        self.controllers: list[FakeController] = []
        self.fail_connect = False

    @property
    def client(self) -> FakeClient:
        return self.clients[-1]

    @property
    def controller(self) -> FakeController:
        return self.controllers[-1]

    async def establish_connection(
        self, client_class: Any, device: Any, name: str, **kwargs: Any
    ) -> FakeClient:
        if self.fail_connect:
            raise TimeoutError
        client = FakeClient(kwargs.get("disconnected_callback"))
        self.clients.append(client)
        return client

    def create_controller(self, client: Any, **kwargs: Any) -> FakeController:
        controller = FakeController()
        self.controllers.append(controller)
        return controller


@pytest.fixture
def fake_desk() -> Generator[FakeDesk]:
    desk = FakeDesk()
    discovered = MagicMock()
    discovered.return_value.create_controller.side_effect = desk.create_controller
    with (
        patch(
            "custom_components.uplift_ble.manager.establish_connection",
            side_effect=desk.establish_connection,
        ),
        patch(
            "custom_components.uplift_ble.manager.find_desk_config",
            return_value=DESK_CONFIG,
        ),
        patch("custom_components.uplift_ble.manager.DiscoveredDesk", discovered),
        patch(
            "custom_components.uplift_ble.manager.bluetooth.async_ble_device_from_address",
            return_value=BLEDevice(ADDRESS, "UPLIFT-1234", None),
        ),
    ):
        yield desk


def make_entry(**options: Any) -> MockConfigEntry:
    return MockConfigEntry(
        domain=DOMAIN,
        title="UPLIFT-1234",
        unique_id=ADDRESS,
        data={CONF_ADDRESS: ADDRESS, CONF_SERVICE_UUID: SERVICE_UUID},
        options={
            CONF_CONNECTION_MODE: "persistent",
            CONF_FALLBACK_UNIT: "none",
            CONF_IDLE_TIMEOUT: 30,
            **options,
        },
    )


async def setup_entry(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
