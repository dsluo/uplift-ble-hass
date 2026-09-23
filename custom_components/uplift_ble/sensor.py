"""Sensors for the Uplift Desk (BLE) integration."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import EntityCategory, UnitOfLength
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import UpliftConfigEntry
from .entity import UpliftDeskEntity
from .manager import DeskState

PARALLEL_UPDATES = 0


@dataclass(frozen=True, kw_only=True)
class UpliftSensorEntityDescription(SensorEntityDescription):
    """Describes an Uplift desk sensor."""

    value_fn: Callable[[DeskState], float | int | None]


def _distance(
    key: str, value_fn: Callable[[DeskState], float | int | None], **kwargs
) -> UpliftSensorEntityDescription:
    return UpliftSensorEntityDescription(
        key=key,
        translation_key=key,
        device_class=SensorDeviceClass.DISTANCE,
        native_unit_of_measurement=UnitOfLength.MILLIMETERS,
        suggested_unit_of_measurement=UnitOfLength.CENTIMETERS,
        suggested_display_precision=1,
        value_fn=value_fn,
        **kwargs,
    )


SENSORS: tuple[UpliftSensorEntityDescription, ...] = (
    _distance(
        "height",
        lambda s: s.height_mm,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    _distance(
        "height_limit_min",
        lambda s: s.min_height_mm,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    _distance(
        "height_limit_max",
        lambda s: s.max_height_mm,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    *(
        UpliftSensorEntityDescription(
            # Preset units vary by firmware, so the raw value is exposed as-is.
            key=f"height_preset_{n}_raw",
            translation_key="height_preset_raw",
            translation_placeholders={"preset": str(n)},
            entity_category=EntityCategory.DIAGNOSTIC,
            entity_registry_enabled_default=False,
            value_fn=lambda s, n=n: getattr(s, f"height_preset_{n}"),
        )
        for n in range(1, 5)
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: UpliftConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    async_add_entities(
        UpliftDeskSensor(entry.runtime_data, description) for description in SENSORS
    )


class UpliftDeskSensor(UpliftDeskEntity, SensorEntity):
    """A sensor reading a value from the desk state."""

    entity_description: UpliftSensorEntityDescription

    @property
    def native_value(self) -> float | int | None:
        return self.entity_description.value_fn(self.manager.state)
