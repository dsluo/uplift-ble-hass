"""Tests for the Uplift desk connection manager."""

from __future__ import annotations

from datetime import timedelta

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import async_fire_time_changed
from uplift_ble import DeskEventType
from uplift_ble.desk_enums import DeskUnit

from custom_components.uplift_ble.manager import UpliftDeskManager

from .conftest import FakeDesk, make_entry, make_service_info, setup_entry


async def test_setup_primes_state(hass: HomeAssistant, fake_desk: FakeDesk) -> None:
    entry = make_entry()
    await setup_entry(hass, entry)

    assert entry.state is ConfigEntryState.LOADED
    controller = fake_desk.controller
    controller.start.assert_awaited_once()
    controller.request_units.assert_awaited_once()
    controller.request_height_limits.assert_awaited_once()
    assert entry.runtime_data.connected


async def test_setup_retries_when_desk_unreachable(
    hass: HomeAssistant, fake_desk: FakeDesk
) -> None:
    fake_desk.fail_connect = True
    entry = make_entry()
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    assert entry.state is ConfigEntryState.SETUP_RETRY


async def test_unload_disconnects(hass: HomeAssistant, fake_desk: FakeDesk) -> None:
    entry = make_entry()
    await setup_entry(hass, entry)
    client = fake_desk.client

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    fake_desk.controller.stop.assert_awaited()
    client.disconnect.assert_awaited()


async def test_persistent_reconnects_after_drop(
    hass: HomeAssistant, fake_desk: FakeDesk
) -> None:
    entry = make_entry()
    await setup_entry(hass, entry)
    manager: UpliftDeskManager = entry.runtime_data

    fake_desk.client.drop()
    await hass.async_block_till_done()
    assert len(fake_desk.clients) == 2
    assert manager.connected
    assert manager.available


async def test_persistent_does_not_reconnect_after_unload(
    hass: HomeAssistant, fake_desk: FakeDesk
) -> None:
    entry = make_entry()
    await setup_entry(hass, entry)
    await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    assert len(fake_desk.clients) == 1


async def test_on_demand_disconnects_when_idle_and_reconnects_for_commands(
    hass: HomeAssistant, fake_desk: FakeDesk
) -> None:
    entry = make_entry(connection_mode="on_demand", idle_timeout=30)
    await setup_entry(hass, entry)
    manager: UpliftDeskManager = entry.runtime_data
    fake_desk.controller.emit(DeskEventType.HEIGHT, 700.0)
    assert manager.connected

    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=31))
    await hass.async_block_till_done()
    assert not manager.connected
    assert manager.available
    assert manager.state.height_mm == 700.0

    fake_desk.client.drop()
    await hass.async_block_till_done()
    assert len(fake_desk.clients) == 1

    await manager.async_run(lambda c: c.move_up())
    assert len(fake_desk.clients) == 2
    fake_desk.controller.move_up.assert_awaited_once()
    assert manager.connected


async def test_command_failure_raises_ha_error(
    hass: HomeAssistant, fake_desk: FakeDesk
) -> None:
    entry = make_entry(connection_mode="on_demand")
    await setup_entry(hass, entry)
    manager: UpliftDeskManager = entry.runtime_data
    await manager._async_disconnect()

    fake_desk.fail_connect = True
    with pytest.raises(HomeAssistantError):
        await manager.async_run(lambda c: c.move_up())


async def test_events_update_state(hass: HomeAssistant, fake_desk: FakeDesk) -> None:
    entry = make_entry()
    await setup_entry(hass, entry)
    manager: UpliftDeskManager = entry.runtime_data
    controller = fake_desk.controller

    controller.emit(DeskEventType.UNIT, DeskUnit.INCHES)
    controller.emit(DeskEventType.HEIGHT_LIMITS_CONFIGURATION, 1200, 600)
    controller.emit(DeskEventType.HEIGHT_LIMIT_MIN, 650)
    controller.emit(DeskEventType.HEIGHT, 700.0)
    controller.emit(DeskEventType.HEIGHT, 710.0)

    state = manager.state
    assert state.unit is DeskUnit.INCHES
    assert state.min_height_mm == 650
    assert state.max_height_mm == 1200
    assert state.moving_direction == 1

    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=3))
    await hass.async_block_till_done()
    assert state.moving_direction == 0


async def test_advertisement_cuts_reconnect_backoff_short(
    hass: HomeAssistant, fake_desk: FakeDesk
) -> None:
    entry = make_entry()
    await setup_entry(hass, entry)
    manager: UpliftDeskManager = entry.runtime_data

    fake_desk.fail_connect = True
    fake_desk.client.drop()
    await hass.async_block_till_done()
    assert not manager.connected

    fake_desk.fail_connect = False
    manager._async_on_advertisement(make_service_info(), None)
    await hass.async_block_till_done()
    assert manager.connected
