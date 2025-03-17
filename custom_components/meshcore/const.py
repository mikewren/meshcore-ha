"""Constants for the MeshCore integration."""
from typing import Final

DOMAIN: Final = "meshcore"

# Connection types
CONF_CONNECTION_TYPE: Final = "connection_type"
CONF_USB_PATH: Final = "usb_path"
CONF_BLE_ADDRESS: Final = "ble_address"
CONF_TCP_HOST: Final = "tcp_host"
CONF_TCP_PORT: Final = "tcp_port"
CONF_BAUDRATE: Final = "baudrate"
DEFAULT_BAUDRATE: Final = 115200
DEFAULT_TCP_PORT: Final = 5000

# Connection type options
CONNECTION_TYPE_USB: Final = "usb"
CONNECTION_TYPE_BLE: Final = "ble"
CONNECTION_TYPE_TCP: Final = "tcp"

# Polling settings
CONF_SCAN_INTERVAL: Final = "scan_interval"
DEFAULT_SCAN_INTERVAL: Final = 30  # seconds

# Services
SERVICE_SEND_MESSAGE: Final = "send_message"
ATTR_NODE_ID: Final = "node_id"
ATTR_MESSAGE: Final = "message"

# Node types
NODE_TYPE_CLIENT: Final = 1
NODE_TYPE_REPEATER: Final = 2

# Other constants
CONNECTION_TIMEOUT: Final = 10  # seconds