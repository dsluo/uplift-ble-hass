"""Cover for the Uplift Desk (BLE) integration."""

from __future__ import annotations

from typing import Any

from homeassistant.components.cover import (
    ATTR_POSITION,
    CoverEntity,
    CoverEntityDescription,
    CoverEntityFeature,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import UpliftConfigEntry
from .entity import UpliftDeskEntity

PARALLEL_UPDATES = 0

DESK_COVER = CoverEntityDescription(key="desk", name=None)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: UpliftConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    async_add_entities([UpliftDeskCover(entry.runtime_data, DESK_COVER)])


class UpliftDeskCover(UpliftDeskEntity, CoverEntity):
    """The desk as a cover: open is up, closed is at the lowest height.

    Position is the height as a percentage of the desk's limits, so it is
    only offered once the limits are known.
    """

    @property
    def _limits(self) -> tuple[int, int] | None:
        state = self.manager.state
        low, high = state.min_height_mm, state.max_height_mm
        if low is None or high is None or high <= low:
            return None
        return low, high

    @property
    def supported_features(self) -> CoverEntityFeature:
        features = (
            CoverEntityFeature.OPEN | CoverEntityFeature.CLOSE | CoverEntityFeature.STOP
        )
        if self._limits is not None:
            features |= CoverEntityFeature.SET_POSITION
        return features

    @property
    def current_cover_position(self) -> int | None:
        limits, height = self._limits, self.manager.state.height_mm
        if limits is None or height is None:
            return None
        low, high = limits
        return max(0, min(100, round((height - low) * 100 / (high - low))))

    @property
    def is_closed(self) -> bool | None:
        position = self.current_cover_position
        return None if position is None else position == 0

    @property
    def is_opening(self) -> bool:
        return self.manager.state.moving_direction > 0

    @property
    def is_closing(self) -> bool:
        return self.manager.state.moving_direction < 0

    async def async_open_cover(self, **kwargs: Any) -> None:
        if (limits := self._limits) is not None:
            await self._async_move_to(limits[1])
        else:
            await self.manager.async_run(lambda c: c.move_up())

    async def async_close_cover(self, **kwargs: Any) -> None:
        if (limits := self._limits) is not None:
            await self._async_move_to(limits[0])
        else:
            await self.manager.async_run(lambda c: c.move_down())

    async def async_stop_cover(self, **kwargs: Any) -> None:
        await self.manager.async_run(lambda c: c.stop_movement())

    async def async_set_cover_position(self, **kwargs: Any) -> None:
        limits = self._limits
        assert limits is not None
        low, high = limits
        await self._async_move_to(
            round(low + (high - low) * kwargs[ATTR_POSITION] / 100)
        )

    async def _async_move_to(self, height_mm: int) -> None:
        await self.manager.async_run(lambda c: c.move_to_specified_height(height_mm))
