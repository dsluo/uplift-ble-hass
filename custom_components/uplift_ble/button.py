"""Buttons for the Uplift Desk (BLE) integration."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.button import (
    ButtonDeviceClass,
    ButtonEntity,
    ButtonEntityDescription,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from uplift_ble import DeskController
from uplift_ble.desk_enums import DeskClearHeightLimit

from . import UpliftConfigEntry
from .entity import UpliftDeskEntity

PARALLEL_UPDATES = 0


@dataclass(frozen=True, kw_only=True)
class UpliftButtonEntityDescription(ButtonEntityDescription):
    """Describes an Uplift desk button."""

    press_fn: Callable[[DeskController], Awaitable[Any]]


async def _refresh(controller: DeskController) -> None:
    await controller.request_units()
    await controller.request_height_limits()


BUTTONS: tuple[UpliftButtonEntityDescription, ...] = (
    *(
        UpliftButtonEntityDescription(
            key=f"move_to_preset_{n}",
            translation_key="move_to_preset",
            translation_placeholders={"preset": str(n)},
            press_fn=lambda c, n=n: getattr(c, f"move_to_height_preset_{n}")(),
        )
        for n in range(1, 5)
    ),
    UpliftButtonEntityDescription(
        key="move_up", translation_key="move_up", press_fn=lambda c: c.move_up()
    ),
    UpliftButtonEntityDescription(
        key="move_down", translation_key="move_down", press_fn=lambda c: c.move_down()
    ),
    UpliftButtonEntityDescription(
        key="stop", translation_key="stop", press_fn=lambda c: c.stop_movement()
    ),
    *(
        UpliftButtonEntityDescription(
            key=f"save_preset_{n}",
            translation_key="save_preset",
            translation_placeholders={"preset": str(n)},
            entity_category=EntityCategory.CONFIG,
            entity_registry_enabled_default=False,
            press_fn=lambda c, n=n: getattr(c, f"save_height_preset_{n}")(),
        )
        for n in range(1, 3)
    ),
    UpliftButtonEntityDescription(
        key="set_current_height_as_max_limit",
        translation_key="set_current_height_as_max_limit",
        entity_category=EntityCategory.CONFIG,
        entity_registry_enabled_default=False,
        press_fn=lambda c: c.set_current_height_as_height_limit_max(),
    ),
    UpliftButtonEntityDescription(
        key="set_current_height_as_min_limit",
        translation_key="set_current_height_as_min_limit",
        entity_category=EntityCategory.CONFIG,
        entity_registry_enabled_default=False,
        press_fn=lambda c: c.set_current_height_as_height_limit_min(),
    ),
    UpliftButtonEntityDescription(
        key="clear_max_limit",
        translation_key="clear_max_limit",
        entity_category=EntityCategory.CONFIG,
        entity_registry_enabled_default=False,
        press_fn=lambda c: c.clear_height_limit(DeskClearHeightLimit.MAX),
    ),
    UpliftButtonEntityDescription(
        key="clear_min_limit",
        translation_key="clear_min_limit",
        entity_category=EntityCategory.CONFIG,
        entity_registry_enabled_default=False,
        press_fn=lambda c: c.clear_height_limit(DeskClearHeightLimit.MIN),
    ),
    UpliftButtonEntityDescription(
        key="reset",
        translation_key="reset",
        device_class=ButtonDeviceClass.RESTART,
        entity_category=EntityCategory.CONFIG,
        entity_registry_enabled_default=False,
        press_fn=lambda c: c.reset(),
    ),
    UpliftButtonEntityDescription(
        key="refresh",
        translation_key="refresh",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        press_fn=_refresh,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: UpliftConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    async_add_entities(
        UpliftDeskButton(entry.runtime_data, description) for description in BUTTONS
    )


class UpliftDeskButton(UpliftDeskEntity, ButtonEntity):
    """A button that sends a single desk command."""

    entity_description: UpliftButtonEntityDescription

    async def async_press(self) -> None:
        await self.manager.async_run(self.entity_description.press_fn)
