"""Tests for Uplift desk entities."""

from __future__ import annotations

from homeassistant.const import STATE_OFF, STATE_ON, STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from uplift_ble import DeskEventType
from uplift_ble.desk_enums import (
    DeskErrorCode,
    DeskLockStatus,
    DeskTouchMode,
    DeskUnit,
)

from .conftest import FakeDesk, make_entry, setup_entry

DEVICE = "uplift_1234"


async def _setup(hass: HomeAssistant, fake_desk: FakeDesk):
    entry = make_entry()
    await setup_entry(hass, entry)
    return fake_desk.controller


async def test_height_sensor(hass: HomeAssistant, fake_desk: FakeDesk) -> None:
    controller = await _setup(hass, fake_desk)
    assert hass.states.get(f"sensor.{DEVICE}_height").state == STATE_UNKNOWN

    controller.emit(DeskEventType.HEIGHT, 723.9)
    await hass.async_block_till_done()
    state = hass.states.get(f"sensor.{DEVICE}_height")
    assert float(state.state) == 72.39
    assert state.attributes["unit_of_measurement"] == "cm"


async def test_unavailable_when_persistent_connection_drops(
    hass: HomeAssistant, fake_desk: FakeDesk
) -> None:
    await _setup(hass, fake_desk)
    fake_desk.fail_connect = True
    fake_desk.client.drop()
    await hass.async_block_till_done()
    assert hass.states.get(f"sensor.{DEVICE}_height").state == STATE_UNAVAILABLE


async def test_buttons(hass: HomeAssistant, fake_desk: FakeDesk) -> None:
    controller = await _setup(hass, fake_desk)
    for entity, method in (
        ("move_to_preset_1", "move_to_height_preset_1"),
        ("move_to_preset_4", "move_to_height_preset_4"),
        ("move_up", "move_up"),
        ("move_down", "move_down"),
        ("stop", "stop_movement"),
    ):
        await hass.services.async_call(
            "button",
            "press",
            {"entity_id": f"button.{DEVICE}_{entity}"},
            blocking=True,
        )
        getattr(controller, method).assert_awaited_once()


async def test_dangerous_entities_disabled_by_default(
    hass: HomeAssistant, fake_desk: FakeDesk, entity_registry: er.EntityRegistry
) -> None:
    await _setup(hass, fake_desk)
    for entity_id in (
        f"button.{DEVICE}_reset_desk",
        f"button.{DEVICE}_save_current_height_as_preset_1",
        f"button.{DEVICE}_clear_max_height_limit",
        f"button.{DEVICE}_set_current_height_as_min_limit",
        f"number.{DEVICE}_calibration_offset",
        f"number.{DEVICE}_max_height_limit",
    ):
        entry = entity_registry.async_get(entity_id)
        assert entry is not None, entity_id
        assert entry.disabled_by is er.RegistryEntryDisabler.INTEGRATION
        assert hass.states.get(entity_id) is None


async def test_target_height_number(hass: HomeAssistant, fake_desk: FakeDesk) -> None:
    controller = await _setup(hass, fake_desk)
    controller.emit(DeskEventType.HEIGHT_LIMITS_CONFIGURATION, 1250, 640)
    controller.emit(DeskEventType.HEIGHT, 700.0)
    await hass.async_block_till_done()

    state = hass.states.get(f"number.{DEVICE}_target_height")
    assert float(state.state) == 700.0
    assert state.attributes["min"] == 640
    assert state.attributes["max"] == 1250

    await hass.services.async_call(
        "number",
        "set_value",
        {"entity_id": f"number.{DEVICE}_target_height", "value": 900.4},
        blocking=True,
    )
    controller.move_to_specified_height.assert_awaited_once_with(900)


async def test_cover(hass: HomeAssistant, fake_desk: FakeDesk) -> None:
    controller = await _setup(hass, fake_desk)
    entity_id = f"cover.{DEVICE}"

    await hass.services.async_call(
        "cover", "open_cover", {"entity_id": entity_id}, blocking=True
    )
    controller.move_up.assert_awaited_once()

    controller.emit(DeskEventType.HEIGHT_LIMITS_CONFIGURATION, 1200, 600)
    controller.emit(DeskEventType.HEIGHT, 900.0)
    await hass.async_block_till_done()
    assert hass.states.get(entity_id).attributes["current_position"] == 50

    await hass.services.async_call(
        "cover",
        "set_cover_position",
        {"entity_id": entity_id, "position": 25},
        blocking=True,
    )
    controller.move_to_specified_height.assert_awaited_once_with(750)

    await hass.services.async_call(
        "cover", "close_cover", {"entity_id": entity_id}, blocking=True
    )
    controller.move_to_specified_height.assert_awaited_with(600)

    await hass.services.async_call(
        "cover", "stop_cover", {"entity_id": entity_id}, blocking=True
    )
    controller.stop_movement.assert_awaited_once()

    controller.emit(DeskEventType.HEIGHT, 890.0)
    await hass.async_block_till_done()
    assert hass.states.get(entity_id).state == "closing"


async def test_selects(hass: HomeAssistant, fake_desk: FakeDesk) -> None:
    controller = await _setup(hass, fake_desk)
    controller.emit(DeskEventType.UNIT, DeskUnit.CENTIMETERS)
    controller.emit(DeskEventType.TOUCH_MODE, DeskTouchMode.ONE_TOUCH)
    await hass.async_block_till_done()
    assert hass.states.get(f"select.{DEVICE}_display_unit").state == "centimeters"
    assert hass.states.get(f"select.{DEVICE}_touch_mode").state == "one_touch"

    await hass.services.async_call(
        "select",
        "select_option",
        {"entity_id": f"select.{DEVICE}_display_unit", "option": "inches"},
        blocking=True,
    )
    controller.set_units.assert_awaited_once_with(DeskUnit.INCHES)


async def test_lock_sensor(hass: HomeAssistant, fake_desk: FakeDesk) -> None:
    controller = await _setup(hass, fake_desk)
    entity_id = f"binary_sensor.{DEVICE}_lock"
    controller.emit(DeskEventType.LOCK_STATUS, DeskLockStatus.LOCKED)
    await hass.async_block_till_done()
    assert hass.states.get(entity_id).state == STATE_OFF
    controller.emit(DeskEventType.LOCK_STATUS, DeskLockStatus.UNLOCKED)
    await hass.async_block_till_done()
    assert hass.states.get(entity_id).state == STATE_ON


async def test_desk_alert_event(hass: HomeAssistant, fake_desk: FakeDesk) -> None:
    controller = await _setup(hass, fake_desk)
    entity_id = f"event.{DEVICE}_desk_alert"
    assert hass.states.get(entity_id).state == STATE_UNKNOWN

    controller.emit(DeskEventType.ERROR_CODE, DeskErrorCode.H01)
    await hass.async_block_till_done()
    assert hass.states.get(entity_id).attributes["event_type"] == "h01"

    controller.emit(DeskEventType.RESET)
    await hass.async_block_till_done()
    assert hass.states.get(entity_id).attributes["event_type"] == "reset"
