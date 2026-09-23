"""Numbers for the Uplift Desk (BLE) integration."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.number import (
    NumberDeviceClass,
    NumberEntity,
    NumberEntityDescription,
    NumberMode,
)
from homeassistant.const import EntityCategory, UnitOfLength
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from uplift_ble import DeskController

from . import UpliftConfigEntry
from .entity import UpliftDeskEntity
from .manager import DeskState, height_bounds

PARALLEL_UPDATES = 0


@dataclass(frozen=True, kw_only=True)
class UpliftNumberEntityDescription(NumberEntityDescription):
    """Describes an Uplift desk number."""

    value_fn: Callable[[DeskState], float | None]
    set_fn: Callable[[DeskController, int], Awaitable[Any]]
    bounds_fn: Callable[[DeskState], tuple[int, int]] | None = None


NUMBERS: tuple[UpliftNumberEntityDescription, ...] = (
    UpliftNumberEntityDescription(
        key="target_height",
        translation_key="target_height",
        device_class=NumberDeviceClass.DISTANCE,
        native_unit_of_measurement=UnitOfLength.MILLIMETERS,
        native_step=1,
        mode=NumberMode.SLIDER,
        value_fn=lambda s: s.height_mm,
        set_fn=lambda c, v: c.move_to_specified_height(v),
        bounds_fn=height_bounds,
    ),
    UpliftNumberEntityDescription(
        key="height_limit_max",
        translation_key="height_limit_max",
        device_class=NumberDeviceClass.DISTANCE,
        native_unit_of_measurement=UnitOfLength.MILLIMETERS,
        native_min_value=0,
        native_max_value=0xFFFF,
        native_step=1,
        mode=NumberMode.BOX,
        entity_category=EntityCategory.CONFIG,
        entity_registry_enabled_default=False,
        value_fn=lambda s: s.max_height_mm,
        set_fn=lambda c, v: c.set_height_limit_max(v),
    ),
    UpliftNumberEntityDescription(
        # The desk does not report the offset back, so this stays unknown.
        key="calibration_offset",
        translation_key="calibration_offset",
        device_class=NumberDeviceClass.DISTANCE,
        native_unit_of_measurement=UnitOfLength.MILLIMETERS,
        native_min_value=0,
        native_max_value=0xFFFF,
        native_step=1,
        mode=NumberMode.BOX,
        entity_category=EntityCategory.CONFIG,
        entity_registry_enabled_default=False,
        value_fn=lambda s: None,
        set_fn=lambda c, v: c.set_calibration_offset(v),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: UpliftConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    async_add_entities(
        UpliftDeskNumber(entry.runtime_data, description) for description in NUMBERS
    )


class UpliftDeskNumber(UpliftDeskEntity, NumberEntity):
    """A number that sends a desk command when set."""

    entity_description: UpliftNumberEntityDescription

    @property
    def native_value(self) -> float | None:
        return self.entity_description.value_fn(self.manager.state)

    @property
    def native_min_value(self) -> float:
        if self.entity_description.bounds_fn is not None:
            return self.entity_description.bounds_fn(self.manager.state)[0]
        return super().native_min_value

    @property
    def native_max_value(self) -> float:
        if self.entity_description.bounds_fn is not None:
            return self.entity_description.bounds_fn(self.manager.state)[1]
        return super().native_max_value

    async def async_set_native_value(self, value: float) -> None:
        await self.manager.async_run(
            lambda c: self.entity_description.set_fn(c, round(value))
        )
