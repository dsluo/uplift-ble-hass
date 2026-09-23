"""Diagnostics for the Uplift Desk (BLE) integration."""

from __future__ import annotations

from typing import Any

from homeassistant.core import HomeAssistant

from . import UpliftConfigEntry


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: UpliftConfigEntry
) -> dict[str, Any]:
    return {
        "entry": {"data": dict(entry.data), "options": dict(entry.options)},
        "manager": entry.runtime_data.diagnostics(),
    }
