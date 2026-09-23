"""The Uplift Desk (BLE) integration."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_ADDRESS, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady

from uplift_ble.desk_enums import DeskUnit

from .const import (
    CONF_CONNECTION_MODE,
    CONF_FALLBACK_UNIT,
    CONF_IDLE_TIMEOUT,
    DEFAULT_CONNECTION_MODE,
    DEFAULT_FALLBACK_UNIT,
    DEFAULT_IDLE_TIMEOUT,
    FALLBACK_UNIT_NONE,
    ConnectionMode,
)
from .manager import DeskNotFoundError, UnsupportedDeskError, UpliftDeskManager

PLATFORMS = [
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.COVER,
    Platform.EVENT,
    Platform.NUMBER,
    Platform.SELECT,
    Platform.SENSOR,
]

type UpliftConfigEntry = ConfigEntry[UpliftDeskManager]


async def async_setup_entry(hass: HomeAssistant, entry: UpliftConfigEntry) -> bool:
    """Set up an Uplift desk from a config entry."""
    fallback_unit = entry.options.get(CONF_FALLBACK_UNIT, DEFAULT_FALLBACK_UNIT)
    manager = UpliftDeskManager(
        hass,
        address=entry.data[CONF_ADDRESS],
        name=entry.title,
        connection_mode=ConnectionMode(
            entry.options.get(CONF_CONNECTION_MODE, DEFAULT_CONNECTION_MODE)
        ),
        fallback_unit=None
        if fallback_unit == FALLBACK_UNIT_NONE
        else DeskUnit(fallback_unit),
        idle_timeout=entry.options.get(CONF_IDLE_TIMEOUT, DEFAULT_IDLE_TIMEOUT),
    )
    try:
        await manager.async_start()
    except (DeskNotFoundError, UnsupportedDeskError, ConnectionError) as err:
        await manager.async_shutdown()
        raise ConfigEntryNotReady(str(err) or type(err).__name__) from err

    entry.runtime_data = manager
    entry.async_on_unload(manager.async_shutdown)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: UpliftConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
