# Uplift Desk (BLE) for Home Assistant

A [HACS](https://hacs.xyz) custom integration that controls Uplift standing desks (and other desks built on Jiecang controllers) through the Uplift Bluetooth adapter. It uses the unofficial [`uplift-ble`](https://github.com/librick/uplift-ble) library.

> [!WARNING]
> This integration moves a large, heavy object. The Uplift adapter accepts commands from anything in Bluetooth range without pairing, and some commands exposed here (height limits, calibration offset, reset) are undocumented vendor commands that can behave differently across desk brands and hardware revisions. Keep the desk clear of people and obstacles while testing, and be ready to stop it with the keypad. See the [upstream compatibility table](https://github.com/librick/uplift-ble#compatibility) for what has been verified on which hardware.
>
> This project is not affiliated with or endorsed by UPLIFT Desk or Jiecang.

## Installation

1. In HACS, open the menu, choose **Custom repositories**, and add `https://github.com/dsluo/uplift-ble-hass` as an **Integration**.
2. Install **Uplift Desk (BLE)** and restart Home Assistant.
3. Desks advertising a supported service (`0x00FF`, `0xFE60`, `0xFF00`, `0xFF12`) are discovered automatically. You can also add one manually from **Settings > Devices & services > Add integration > Uplift Desk (BLE)**.

You need a working [Bluetooth integration](https://www.home-assistant.io/integrations/bluetooth/): a local adapter or an ESPHome Bluetooth proxy with active connections enabled.

## Configuration

These can be changed later from the integration's **Configure** button.

| Option | Description |
| --- | --- |
| Connection mode | **Persistent** stays connected, so height updates live and commands are instant, but it keeps one Bluetooth connection slot busy. **On demand** connects when a command is sent and disconnects after the idle timeout, so height only updates around commands. |
| Fallback display unit | Height reports are in the desk's display unit. Some desks never report which unit that is, so set this to whatever your keypad shows if the height sensor stays unknown. |
| Idle disconnect timeout | On demand mode only. How long to stay connected after the last command or movement. |

## Entities

Enabled by default:

| Entity | Notes |
| --- | --- |
| Cover | Open raises the desk to its max limit, close lowers it to its min limit, position is the height as a percentage between the limits. Until the desk reports its limits, open and close only nudge it up or down. |
| Height sensor | Current height. |
| Target height | Slider that moves the desk to a height in mm. |
| Move to preset 1-4 | Recall keypad presets. |
| Move up / Move down / Stop | Single movement commands. |
| Lock | On when the keypad is unlocked (Home Assistant lock semantics). |
| Desk alert | Event entity that fires on error codes (E01-E13, H01, H02, LOCK) and when the desk needs a manual reset. |
| Display unit, Touch mode | Desk settings. |
| Min/max height limit sensors | Diagnostic. |

Disabled by default. Enable these only if you know what they do on your desk:

- Save current height as preset 1 / 2
- Set current height as max / min limit, clear max / min limit, max height limit
- Calibration offset (write only; the desk does not report it back)
- Reset desk
- Refresh settings
- Raw preset value sensors (units vary by firmware)

## Development

```bash
uv sync
uv run pytest
uv run ruff check . && uv run ruff format --check .
```

## Credits

Built on [librick/uplift-ble](https://github.com/librick/uplift-ble), which builds on Bennett Wendorf's [uplift-desk-controller](https://github.com/Bennett-Wendorf/uplift-desk-controller).
