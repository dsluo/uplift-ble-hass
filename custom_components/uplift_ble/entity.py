"""Base entity for the Uplift Desk (BLE) integration."""

from __future__ import annotations

from homeassistant.helpers.device_registry import CONNECTION_BLUETOOTH, DeviceInfo
from homeassistant.helpers.entity import Entity, EntityDescription

from .manager import UpliftDeskManager


class UpliftDeskEntity(Entity):
    """An entity backed by an UpliftDeskManager."""

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(
        self, manager: UpliftDeskManager, description: EntityDescription
    ) -> None:
        self.manager = manager
        self.entity_description = description
        self._attr_unique_id = f"{manager.address}_{description.key}"
        self._attr_device_info = DeviceInfo(
            connections={(CONNECTION_BLUETOOTH, manager.address)},
            name=manager.name,
            manufacturer="Uplift Desk",
            model=f"Jiecang {manager.desk_config.desk_variant.name.split('_')[1]}"
            if manager.desk_config
            else None,
        )

    @property
    def available(self) -> bool:
        return self.manager.available

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(self.manager.async_add_listener(self._handle_update))

    def _handle_update(self) -> None:
        self.async_write_ha_state()
