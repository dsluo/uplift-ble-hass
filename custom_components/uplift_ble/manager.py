"""Connection and state management for an Uplift BLE desk."""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import Awaitable, Callable
from dataclasses import asdict, dataclass
from typing import Any

from bleak.backends.device import BLEDevice
from bleak.exc import BleakError
from bleak_retry_connector import BleakClientWithServiceCache, establish_connection
from homeassistant.components import bluetooth
from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.event import async_call_later

from uplift_ble import DeskController, DeskEventType, DiscoveredDesk
from uplift_ble.ble_helpers import gatt_characteristics_to_uuids
from uplift_ble.desk_configs import DESK_CONFIGS_BY_SERVICE, DeskConfig
from uplift_ble.desk_enums import (
    DeskErrorCode,
    DeskLockStatus,
    DeskTouchMode,
    DeskUnit,
)

from .const import (
    DEFAULT_MAX_HEIGHT_MM,
    DEFAULT_MIN_HEIGHT_MM,
    MOVEMENT_SETTLE_SECONDS,
    RECONNECT_BACKOFF_SECONDS,
    ConnectionMode,
)

_LOGGER = logging.getLogger(__name__)

BLEAK_EXCEPTIONS = (BleakError, TimeoutError, EOFError, OSError)


class DeskNotFoundError(Exception):
    """The desk is not currently reachable by any Bluetooth adapter."""


class UnsupportedDeskError(Exception):
    """The device does not expose a supported desk GATT profile."""


@dataclass
class DeskState:
    """Last known desk state, kept across on-demand disconnects."""

    height_mm: float | None = None
    unit: DeskUnit | None = None
    touch_mode: DeskTouchMode | None = None
    lock_status: DeskLockStatus | None = None
    height_limit_min_mm: int | None = None
    height_limit_max_mm: int | None = None
    height_limit_config_min_mm: int | None = None
    height_limit_config_max_mm: int | None = None
    height_preset_1: int | None = None
    height_preset_2: int | None = None
    height_preset_3: int | None = None
    height_preset_4: int | None = None
    moving_direction: int = 0

    @property
    def min_height_mm(self) -> int | None:
        if self.height_limit_min_mm is not None:
            return self.height_limit_min_mm
        return self.height_limit_config_min_mm

    @property
    def max_height_mm(self) -> int | None:
        if self.height_limit_max_mm is not None:
            return self.height_limit_max_mm
        return self.height_limit_config_max_mm


def find_desk_config(client: BleakClientWithServiceCache) -> DeskConfig:
    """Return the desk profile matching a connected client's GATT services.

    Mirrors ``uplift_ble.DeskValidator`` but works on an already connected
    client, since Home Assistant owns connection establishment.
    """
    for service in client.services:
        desk_config = DESK_CONFIGS_BY_SERVICE.get(service.uuid)
        if desk_config is None:
            continue
        required = {
            desk_config.input_char_uuid,
            desk_config.output_char_uuid,
            desk_config.name_char_uuid,
        }
        if required <= gatt_characteristics_to_uuids(service.characteristics):
            return desk_config
    raise UnsupportedDeskError


async def async_probe_desk(ble_device: BLEDevice) -> DeskConfig:
    """Connect once to confirm the device is a supported desk."""
    client = await establish_connection(
        BleakClientWithServiceCache, ble_device, ble_device.name or ble_device.address
    )
    try:
        return find_desk_config(client)
    finally:
        await client.disconnect()


class UpliftDeskManager:
    """Owns the BLE connection, desk controller, and last known state."""

    def __init__(
        self,
        hass: HomeAssistant,
        address: str,
        name: str,
        connection_mode: ConnectionMode,
        fallback_unit: DeskUnit | None,
        idle_timeout: float,
    ) -> None:
        self.hass = hass
        self.address = address
        self.name = name
        self.connection_mode = connection_mode
        self.fallback_unit = fallback_unit
        self.idle_timeout = idle_timeout
        self.state = DeskState()
        self.desk_config: DeskConfig | None = None

        self._client: BleakClientWithServiceCache | None = None
        self._controller: DeskController | None = None
        self._lock = asyncio.Lock()
        self._listeners: list[Callable[[], None]] = []
        self._event_listeners: list[Callable[[str], None]] = []
        self._present = True
        self._shutting_down = False
        self._expected_disconnect = False
        self._reconnect_attempt = 0
        self._reconnect_task: asyncio.Task[None] | None = None
        self._advertised = asyncio.Event()
        self._cancel_idle: CALLBACK_TYPE | None = None
        self._cancel_settle: CALLBACK_TYPE | None = None
        self._unsubs: list[CALLBACK_TYPE] = []

    @property
    def connected(self) -> bool:
        return self._client is not None and self._client.is_connected

    @property
    def available(self) -> bool:
        if self.connection_mode is ConnectionMode.PERSISTENT:
            return self.connected
        return self.connected or self._present

    async def async_start(self) -> None:
        """Connect for the first time and start watching advertisements."""
        self._unsubs.append(
            bluetooth.async_register_callback(
                self.hass,
                self._async_on_advertisement,
                bluetooth.BluetoothCallbackMatcher(address=self.address),
                bluetooth.BluetoothScanningMode.PASSIVE,
            )
        )
        self._unsubs.append(
            bluetooth.async_track_unavailable(
                self.hass, self._async_on_unavailable, self.address, connectable=True
            )
        )
        async with self._lock:
            await self._async_connect()
        self._async_touch()

    async def async_shutdown(self) -> None:
        """Disconnect and release all resources."""
        self._shutting_down = True
        for unsub in self._unsubs:
            unsub()
        self._unsubs.clear()
        if self._reconnect_task is not None:
            self._reconnect_task.cancel()
            self._reconnect_task = None
        self._cancel_timers()
        async with self._lock:
            await self._async_disconnect()

    @callback
    def async_add_listener(self, update_callback: Callable[[], None]) -> CALLBACK_TYPE:
        """Listen for state or availability changes."""
        self._listeners.append(update_callback)
        return lambda: self._listeners.remove(update_callback)

    @callback
    def async_add_event_listener(
        self, event_callback: Callable[[str], None]
    ) -> CALLBACK_TYPE:
        """Listen for desk error and reset events."""
        self._event_listeners.append(event_callback)
        return lambda: self._event_listeners.remove(event_callback)

    async def async_run(
        self, command: Callable[[DeskController], Awaitable[Any]]
    ) -> None:
        """Run a controller command, connecting first if needed."""
        async with self._lock:
            try:
                await self._async_connect()
                assert self._controller is not None
                await command(self._controller)
            except DeskNotFoundError as err:
                raise HomeAssistantError(f"{self.name} is not in range") from err
            except UnsupportedDeskError as err:
                raise HomeAssistantError(
                    f"{self.name} does not look like a supported desk"
                ) from err
            except (ConnectionError, *BLEAK_EXCEPTIONS) as err:
                raise HomeAssistantError(
                    f"Failed to communicate with {self.name}: {err}"
                ) from err
        self._async_touch()

    def diagnostics(self) -> dict[str, Any]:
        return {
            "connected": self.connected,
            "available": self.available,
            "connection_mode": self.connection_mode,
            "desk_variant": self.desk_config.desk_variant.value
            if self.desk_config
            else None,
            "state": asdict(self.state),
        }

    async def _async_connect(self) -> None:
        """Establish the connection. Caller must hold the lock."""
        if self.connected:
            return
        ble_device = bluetooth.async_ble_device_from_address(
            self.hass, self.address, connectable=True
        )
        if ble_device is None:
            raise DeskNotFoundError(f"Desk {self.address} is not in range")

        _LOGGER.debug("Connecting to %s", self.address)
        self._expected_disconnect = False
        try:
            client = await establish_connection(
                BleakClientWithServiceCache,
                ble_device,
                self.name,
                disconnected_callback=self._on_disconnected,
                ble_device_callback=lambda: (
                    bluetooth.async_ble_device_from_address(
                        self.hass, self.address, connectable=True
                    )
                    or ble_device
                ),
            )
        except BLEAK_EXCEPTIONS as err:
            raise ConnectionError(f"Failed to connect to {self.address}") from err

        try:
            self.desk_config = find_desk_config(client)
            controller = DiscoveredDesk(
                address=self.address, name=self.name, desk_config=self.desk_config
            ).create_controller(client, fallback_unit=self.fallback_unit)
            self._register_controller_events(controller)
            await controller.start()
            self._client = client
            self._controller = controller
            await controller.request_units()
            await controller.request_height_limits()
        except BaseException:
            self._client = None
            self._controller = None
            self._expected_disconnect = True
            await client.disconnect()
            raise

        _LOGGER.debug("Connected to %s", self.address)
        self._reconnect_attempt = 0
        self._async_notify()

    async def _async_disconnect(self) -> None:
        """Tear down the connection. Caller must hold the lock."""
        controller, client = self._controller, self._client
        self._controller = None
        self._client = None
        self._expected_disconnect = True
        if controller is not None:
            await _async_stop_quietly(controller)
        if client is not None:
            try:
                await client.disconnect()
            except BLEAK_EXCEPTIONS:
                _LOGGER.debug("Error disconnecting", exc_info=True)
        self._async_notify()

    def _on_disconnected(self, client: BleakClientWithServiceCache) -> None:
        if client is not self._client:
            return
        _LOGGER.debug("Disconnected from %s", self.address)
        controller = self._controller
        self._controller = None
        self._client = None
        if controller is not None:
            self.hass.async_create_task(
                _async_stop_quietly(controller), eager_start=False
            )
        self._async_notify()
        if not self._expected_disconnect and not self._shutting_down:
            self._schedule_reconnect()

    def _schedule_reconnect(self) -> None:
        if (
            self.connection_mode is not ConnectionMode.PERSISTENT
            or self._shutting_down
            or self._reconnect_task is not None
        ):
            return
        self._reconnect_task = self.hass.async_create_background_task(
            self._async_reconnect_loop(), f"uplift_ble reconnect {self.address}"
        )

    async def _async_reconnect_loop(self) -> None:
        try:
            while not self._shutting_down and not self.connected:
                delay = RECONNECT_BACKOFF_SECONDS[
                    min(self._reconnect_attempt, len(RECONNECT_BACKOFF_SECONDS) - 1)
                ]
                self._reconnect_attempt += 1
                try:
                    async with self._lock:
                        await self._async_connect()
                except (DeskNotFoundError, ConnectionError, UnsupportedDeskError):
                    _LOGGER.debug(
                        "Reconnect to %s failed, retrying in %ss",
                        self.address,
                        delay,
                        exc_info=True,
                    )
                    self._advertised.clear()
                    with contextlib.suppress(TimeoutError):
                        await asyncio.wait_for(self._advertised.wait(), delay)
        finally:
            self._reconnect_task = None

    @callback
    def _async_on_advertisement(
        self,
        service_info: bluetooth.BluetoothServiceInfoBleak,
        change: bluetooth.BluetoothChange,
    ) -> None:
        if not self._present:
            self._present = True
            self._async_notify()
        if not self.connected:
            self._advertised.set()
            self._schedule_reconnect()

    @callback
    def _async_on_unavailable(
        self, service_info: bluetooth.BluetoothServiceInfoBleak
    ) -> None:
        self._present = False
        self._async_notify()

    @callback
    def _async_touch(self) -> None:
        """Restart the on-demand idle disconnect timer."""
        if self.connection_mode is not ConnectionMode.ON_DEMAND:
            return
        if self._cancel_idle is not None:
            self._cancel_idle()
        self._cancel_idle = async_call_later(
            self.hass, self.idle_timeout, self._async_idle_timeout
        )

    async def _async_idle_timeout(self, _now: Any) -> None:
        self._cancel_idle = None
        async with self._lock:
            await self._async_disconnect()

    def _cancel_timers(self) -> None:
        if self._cancel_idle is not None:
            self._cancel_idle()
            self._cancel_idle = None
        if self._cancel_settle is not None:
            self._cancel_settle()
            self._cancel_settle = None

    @callback
    def _async_notify(self) -> None:
        for listener in list(self._listeners):
            listener()

    @callback
    def _async_fire_event(self, event_type: str) -> None:
        for listener in list(self._event_listeners):
            listener(event_type)

    def _register_controller_events(self, controller: DeskController) -> None:
        def update(**changes: Any) -> Callable[..., None]:
            def handler(*values: Any) -> None:
                for field, index in changes.items():
                    setattr(self.state, field, values[index])
                self._async_notify()

            return handler

        controller.on(DeskEventType.HEIGHT, self._on_height)
        controller.on(DeskEventType.UNIT, update(unit=0))
        controller.on(DeskEventType.TOUCH_MODE, update(touch_mode=0))
        controller.on(DeskEventType.LOCK_STATUS, update(lock_status=0))
        controller.on(DeskEventType.HEIGHT_LIMIT_MAX, update(height_limit_max_mm=0))
        controller.on(DeskEventType.HEIGHT_LIMIT_MIN, update(height_limit_min_mm=0))
        controller.on(
            DeskEventType.HEIGHT_LIMITS_CONFIGURATION,
            update(height_limit_config_max_mm=0, height_limit_config_min_mm=1),
        )
        controller.on(DeskEventType.HEIGHT_PRESET_1, update(height_preset_1=0))
        controller.on(DeskEventType.HEIGHT_PRESET_2, update(height_preset_2=0))
        controller.on(DeskEventType.HEIGHT_PRESET_3, update(height_preset_3=0))
        controller.on(DeskEventType.HEIGHT_PRESET_4, update(height_preset_4=0))
        controller.on(DeskEventType.ERROR_CODE, self._on_error_code)
        controller.on(DeskEventType.RESET, self._on_reset)

    def _on_height(self, height_mm: float) -> None:
        previous = self.state.height_mm
        self.state.height_mm = height_mm
        if previous is not None and height_mm != previous:
            self.state.moving_direction = 1 if height_mm > previous else -1
            if self._cancel_settle is not None:
                self._cancel_settle()
            self._cancel_settle = async_call_later(
                self.hass, MOVEMENT_SETTLE_SECONDS, self._async_settled
            )
        self._async_notify()
        # Keep on-demand connections open while the desk is still moving so
        # the final height is captured.
        self._async_touch()

    @callback
    def _async_settled(self, _now: Any) -> None:
        self._cancel_settle = None
        self.state.moving_direction = 0
        self._async_notify()

    def _on_error_code(self, error_code: DeskErrorCode) -> None:
        self._async_fire_event(error_code.value.lower())

    def _on_reset(self) -> None:
        self._async_fire_event("reset")


async def _async_stop_quietly(controller: DeskController) -> None:
    try:
        await controller.stop()
    except BLEAK_EXCEPTIONS:
        _LOGGER.debug("Error stopping desk notifications", exc_info=True)


def height_bounds(state: DeskState) -> tuple[int, int]:
    """Return the usable height range, falling back to typical desk limits."""
    return (
        state.min_height_mm or DEFAULT_MIN_HEIGHT_MM,
        state.max_height_mm or DEFAULT_MAX_HEIGHT_MM,
    )
