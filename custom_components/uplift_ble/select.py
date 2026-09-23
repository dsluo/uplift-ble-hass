"""Selects for the Uplift Desk (BLE) integration."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from enum import Enum
from typing import Any

from homeassistant.components.select import SelectEntity, SelectEntityDescription
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from uplift_ble import DeskController
from uplift_ble.desk_enums import DeskTouchMode, DeskUnit

from . import UpliftConfigEntry
from .entity import UpliftDeskEntity
from .manager import DeskState

PARALLEL_UPDATES = 0


@dataclass(frozen=True, kw_only=True)
class UpliftSelectEntityDescription(SelectEntityDescription):
    """Describes an Uplift desk select backed by a library enum."""

    enum: type[Enum]
    value_fn: Callable[[DeskState], Enum | None]
    select_fn: Callable[[DeskController, Any], Awaitable[Any]]


SELECTS: tuple[UpliftSelectEntityDescription, ...] = (
    UpliftSelectEntityDescription(
        key="display_unit",
        translation_key="display_unit",
        entity_category=EntityCategory.CONFIG,
        options=[unit.value for unit in DeskUnit],
        enum=DeskUnit,
        value_fn=lambda s: s.unit,
        select_fn=lambda c, v: c.set_units(v),
    ),
    UpliftSelectEntityDescription(
        key="touch_mode",
        translation_key="touch_mode",
        entity_category=EntityCategory.CONFIG,
        options=[mode.value for mode in DeskTouchMode],
        enum=DeskTouchMode,
        value_fn=lambda s: s.touch_mode,
        select_fn=lambda c, v: c.set_touch_mode(v),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: UpliftConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    async_add_entities(
        UpliftDeskSelect(entry.runtime_data, description) for description in SELECTS
    )


class UpliftDeskSelect(UpliftDeskEntity, SelectEntity):
    """A select for a desk setting."""

    entity_description: UpliftSelectEntityDescription

    @property
    def current_option(self) -> str | None:
        value = self.entity_description.value_fn(self.manager.state)
        return None if value is None else value.value

    async def async_select_option(self, option: str) -> None:
        value = self.entity_description.enum(option)
        await self.manager.async_run(
            lambda c: self.entity_description.select_fn(c, value)
        )
