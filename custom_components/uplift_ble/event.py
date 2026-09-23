"""Events for the Uplift Desk (BLE) integration."""

from __future__ import annotations

from homeassistant.components.event import EventEntity, EventEntityDescription
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from uplift_ble.desk_enums import DeskErrorCode

from . import UpliftConfigEntry
from .entity import UpliftDeskEntity

PARALLEL_UPDATES = 0

EVENT_TYPES = [code.value.lower() for code in DeskErrorCode] + ["reset"]

DESK_EVENT = EventEntityDescription(
    key="desk_event", translation_key="desk_event", event_types=EVENT_TYPES
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: UpliftConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    async_add_entities([UpliftDeskEvent(entry.runtime_data, DESK_EVENT)])


class UpliftDeskEvent(UpliftDeskEntity, EventEntity):
    """Fires when the desk reports an error code or needs a manual reset."""

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.async_on_remove(self.manager.async_add_event_listener(self._on_event))

    def _on_event(self, event_type: str) -> None:
        self._trigger_event(event_type)
        self.async_write_ha_state()
