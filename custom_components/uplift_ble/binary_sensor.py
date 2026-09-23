"""Binary sensors for the Uplift Desk (BLE) integration."""

from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from uplift_ble.desk_enums import DeskLockStatus

from . import UpliftConfigEntry
from .entity import UpliftDeskEntity

PARALLEL_UPDATES = 0

LOCK = BinarySensorEntityDescription(
    key="lock", device_class=BinarySensorDeviceClass.LOCK
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: UpliftConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    async_add_entities([UpliftDeskLockSensor(entry.runtime_data, LOCK)])


class UpliftDeskLockSensor(UpliftDeskEntity, BinarySensorEntity):
    """Keypad lock state. On means unlocked, per the lock device class."""

    @property
    def is_on(self) -> bool | None:
        lock_status = self.manager.state.lock_status
        if lock_status is None:
            return None
        return lock_status is DeskLockStatus.UNLOCKED
