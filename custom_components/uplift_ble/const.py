"""Constants for the Uplift Desk (BLE) integration."""

from enum import StrEnum

DOMAIN = "uplift_ble"

CONF_SERVICE_UUID = "service_uuid"
CONF_CONNECTION_MODE = "connection_mode"
CONF_FALLBACK_UNIT = "fallback_unit"
CONF_IDLE_TIMEOUT = "idle_timeout"


class ConnectionMode(StrEnum):
    """How the integration holds the BLE connection."""

    PERSISTENT = "persistent"
    ON_DEMAND = "on_demand"


FALLBACK_UNIT_NONE = "none"

DEFAULT_CONNECTION_MODE = ConnectionMode.PERSISTENT
DEFAULT_FALLBACK_UNIT = FALLBACK_UNIT_NONE
DEFAULT_IDLE_TIMEOUT = 30

# Used for the target height slider until the desk reports its limits.
DEFAULT_MIN_HEIGHT_MM = 500
DEFAULT_MAX_HEIGHT_MM = 1300

# The desk stops reporting height once it stops moving, so treat it as
# stationary after this many seconds without a height change.
MOVEMENT_SETTLE_SECONDS = 2.0

RECONNECT_BACKOFF_SECONDS = (5, 10, 30, 60, 120, 300)
