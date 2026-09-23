"""Config flow for the Uplift Desk (BLE) integration."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from bluetooth_data_tools import human_readable_name
from homeassistant.components.bluetooth import (
    BluetoothServiceInfoBleak,
    async_discovered_service_info,
)
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlowWithReload,
)
from homeassistant.const import CONF_ADDRESS
from homeassistant.core import callback
from homeassistant.helpers.selector import (
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
)

from uplift_ble.desk_configs import DESK_SERVICE_UUIDS

from .const import (
    CONF_CONNECTION_MODE,
    CONF_FALLBACK_UNIT,
    CONF_IDLE_TIMEOUT,
    CONF_SERVICE_UUID,
    DEFAULT_CONNECTION_MODE,
    DEFAULT_FALLBACK_UNIT,
    DEFAULT_IDLE_TIMEOUT,
    DOMAIN,
    FALLBACK_UNIT_NONE,
    ConnectionMode,
)
from .manager import BLEAK_EXCEPTIONS, UnsupportedDeskError, async_probe_desk

_LOGGER = logging.getLogger(__name__)


def _desk_service_uuid(service_info: BluetoothServiceInfoBleak) -> str | None:
    return next(
        (uuid for uuid in service_info.service_uuids if uuid in DESK_SERVICE_UUIDS),
        None,
    )


def _settings_schema(defaults: dict[str, Any]) -> vol.Schema:
    return vol.Schema(
        {
            vol.Required(
                CONF_CONNECTION_MODE,
                default=defaults.get(CONF_CONNECTION_MODE, DEFAULT_CONNECTION_MODE),
            ): SelectSelector(
                SelectSelectorConfig(
                    options=[mode.value for mode in ConnectionMode],
                    translation_key=CONF_CONNECTION_MODE,
                    mode=SelectSelectorMode.LIST,
                )
            ),
            vol.Required(
                CONF_FALLBACK_UNIT,
                default=defaults.get(CONF_FALLBACK_UNIT, DEFAULT_FALLBACK_UNIT),
            ): SelectSelector(
                SelectSelectorConfig(
                    options=[FALLBACK_UNIT_NONE, "centimeters", "inches"],
                    translation_key=CONF_FALLBACK_UNIT,
                    mode=SelectSelectorMode.DROPDOWN,
                )
            ),
            vol.Required(
                CONF_IDLE_TIMEOUT,
                default=defaults.get(CONF_IDLE_TIMEOUT, DEFAULT_IDLE_TIMEOUT),
            ): NumberSelector(
                NumberSelectorConfig(
                    min=5,
                    max=3600,
                    step=1,
                    unit_of_measurement="s",
                    mode=NumberSelectorMode.BOX,
                )
            ),
        }
    )


def _normalize_settings(user_input: dict[str, Any]) -> dict[str, Any]:
    return {**user_input, CONF_IDLE_TIMEOUT: int(user_input[CONF_IDLE_TIMEOUT])}


class UpliftDeskConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Uplift desks."""

    VERSION = 1

    def __init__(self) -> None:
        self._discovery_info: BluetoothServiceInfoBleak | None = None
        self._discovered_devices: dict[str, BluetoothServiceInfoBleak] = {}

    async def async_step_bluetooth(
        self, discovery_info: BluetoothServiceInfoBleak
    ) -> ConfigFlowResult:
        """Handle a desk found by Bluetooth discovery."""
        if _desk_service_uuid(discovery_info) is None:
            return self.async_abort(reason="not_supported")
        await self.async_set_unique_id(discovery_info.address)
        self._abort_if_unique_id_configured()
        self._discovery_info = discovery_info
        self.context["title_placeholders"] = {"name": self._title(discovery_info)}
        return await self.async_step_bluetooth_confirm()

    async def async_step_bluetooth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Confirm a discovered desk."""
        assert self._discovery_info is not None
        if user_input is not None:
            return await self.async_step_settings()
        self._set_confirm_only()
        return self.async_show_form(
            step_id="bluetooth_confirm",
            description_placeholders={"name": self._title(self._discovery_info)},
        )

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Pick a desk from those currently advertising."""
        if user_input is not None:
            address = user_input[CONF_ADDRESS]
            await self.async_set_unique_id(address, raise_on_progress=False)
            self._abort_if_unique_id_configured()
            self._discovery_info = self._discovered_devices[address]
            return await self.async_step_settings()

        current_addresses = self._async_current_ids(include_ignore=False)
        for service_info in async_discovered_service_info(self.hass):
            if (
                service_info.address in current_addresses
                or _desk_service_uuid(service_info) is None
            ):
                continue
            self._discovered_devices[service_info.address] = service_info

        if not self._discovered_devices:
            return self.async_abort(reason="no_devices_found")

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_ADDRESS): vol.In(
                        {
                            address: f"{self._title(info)} ({address})"
                            for address, info in self._discovered_devices.items()
                        }
                    )
                }
            ),
        )

    async def async_step_settings(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Choose connection settings, then verify the desk responds."""
        assert self._discovery_info is not None
        discovery_info = self._discovery_info
        errors: dict[str, str] = {}

        if user_input is not None:
            try:
                await async_probe_desk(discovery_info.device)
            except UnsupportedDeskError:
                return self.async_abort(reason="not_supported")
            except BLEAK_EXCEPTIONS:
                errors["base"] = "cannot_connect"
            except Exception:
                _LOGGER.exception("Unexpected error probing desk")
                errors["base"] = "unknown"
            else:
                return self.async_create_entry(
                    title=self._title(discovery_info),
                    data={
                        CONF_ADDRESS: discovery_info.address,
                        CONF_SERVICE_UUID: _desk_service_uuid(discovery_info),
                    },
                    options=_normalize_settings(user_input),
                )

        return self.async_show_form(
            step_id="settings",
            data_schema=_settings_schema(user_input or {}),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> UpliftDeskOptionsFlow:
        return UpliftDeskOptionsFlow()

    @staticmethod
    def _title(service_info: BluetoothServiceInfoBleak) -> str:
        return human_readable_name(None, service_info.name, service_info.address)


class UpliftDeskOptionsFlow(OptionsFlowWithReload):
    """Change connection settings for an existing desk."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(data=_normalize_settings(user_input))
        return self.async_show_form(
            step_id="init",
            data_schema=_settings_schema(dict(self.config_entry.options)),
        )
