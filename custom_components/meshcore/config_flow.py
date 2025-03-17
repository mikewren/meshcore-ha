"""Config flow for MeshCore integration."""
import logging
import asyncio
import os
from typing import Any, Dict, Optional

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.components import usb
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult
from homeassistant.exceptions import HomeAssistantError
import homeassistant.helpers.config_validation as cv
from bleak import BleakScanner

from .const import (
    DOMAIN,
    CONF_CONNECTION_TYPE,
    CONF_USB_PATH,
    CONF_BLE_ADDRESS,
    CONF_TCP_HOST,
    CONF_TCP_PORT,
    CONF_BAUDRATE,
    CONF_SCAN_INTERVAL,
    CONNECTION_TYPE_USB,
    CONNECTION_TYPE_BLE,
    CONNECTION_TYPE_TCP,
    DEFAULT_BAUDRATE,
    DEFAULT_TCP_PORT,
    DEFAULT_SCAN_INTERVAL,
    CONNECTION_TIMEOUT,
)
from .meshcore_api import MeshCoreAPI

_LOGGER = logging.getLogger(__name__)

class CannotConnect(HomeAssistantError):
    """Error to indicate we cannot connect."""

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_CONNECTION_TYPE): vol.In(
            [CONNECTION_TYPE_USB, CONNECTION_TYPE_BLE, CONNECTION_TYPE_TCP]
        ),
    }
)

USB_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_USB_PATH): str,
        vol.Optional(CONF_BAUDRATE, default=DEFAULT_BAUDRATE): cv.positive_int,
        vol.Optional(CONF_SCAN_INTERVAL, default=DEFAULT_SCAN_INTERVAL): cv.positive_int,
    }
)

BLE_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_BLE_ADDRESS): str,
        vol.Optional(CONF_SCAN_INTERVAL, default=DEFAULT_SCAN_INTERVAL): cv.positive_int,
    }
)

TCP_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_TCP_HOST): str,
        vol.Optional(CONF_TCP_PORT, default=DEFAULT_TCP_PORT): cv.port,
        vol.Optional(CONF_SCAN_INTERVAL, default=DEFAULT_SCAN_INTERVAL): cv.positive_int,
    }
)


async def validate_usb_input(hass: HomeAssistant, data: Dict[str, Any]) -> Dict[str, Any]:
    """Validate the user input allows us to connect to the USB device."""
    try:
        api = MeshCoreAPI(
            connection_type=CONNECTION_TYPE_USB,
            usb_path=data[CONF_USB_PATH],
            baudrate=data[CONF_BAUDRATE],
        )
        await asyncio.wait_for(api.connect(), timeout=CONNECTION_TIMEOUT)
        node_info = await api.get_node_info()
        await api.disconnect()
        
        # If we get here, the connection was successful
        return {"title": f"MeshCore Node {node_info.get('name', 'Unknown')}"}
    except asyncio.TimeoutError:
        raise CannotConnect("Connection timed out")
    except Exception as ex:
        _LOGGER.error("Validation error: %s", ex)
        raise CannotConnect(f"Failed to connect: {str(ex)}")


async def validate_ble_input(hass: HomeAssistant, data: Dict[str, Any]) -> Dict[str, Any]:
    """Validate the user input allows us to connect to the BLE device."""
    try:
        api = MeshCoreAPI(
            connection_type=CONNECTION_TYPE_BLE,
            ble_address=data[CONF_BLE_ADDRESS],
        )
        await asyncio.wait_for(api.connect(), timeout=CONNECTION_TIMEOUT)
        node_info = await api.get_node_info()
        await api.disconnect()
        
        # If we get here, the connection was successful
        return {"title": f"MeshCore Node {node_info.get('name', 'Unknown')}"}
    except asyncio.TimeoutError:
        raise CannotConnect("Connection timed out")
    except Exception as ex:
        _LOGGER.error("Validation error: %s", ex)
        raise CannotConnect(f"Failed to connect: {str(ex)}")


async def validate_tcp_input(hass: HomeAssistant, data: Dict[str, Any]) -> Dict[str, Any]:
    """Validate the user input allows us to connect to the TCP device."""
    try:
        api = MeshCoreAPI(
            connection_type=CONNECTION_TYPE_TCP,
            tcp_host=data[CONF_TCP_HOST],
            tcp_port=data[CONF_TCP_PORT],
        )
        await asyncio.wait_for(api.connect(), timeout=CONNECTION_TIMEOUT)
        node_info = await api.get_node_info()
        await api.disconnect()
        
        # If we get here, the connection was successful
        return {"title": f"MeshCore Node {node_info.get('name', 'Unknown')}"}
    except asyncio.TimeoutError:
        raise CannotConnect("Connection timed out")
    except Exception as ex:
        _LOGGER.error("Validation error: %s", ex)
        raise CannotConnect(f"Failed to connect: {str(ex)}")


class MeshCoreConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for MeshCore."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize flow."""
        self.connection_type: Optional[str] = None
        self.discovery_info: Optional[Dict[str, Any]] = None

    async def async_step_user(self, user_input: Optional[Dict[str, Any]] = None) -> FlowResult:
        """Handle the initial step."""
        errors: Dict[str, str] = {}

        if user_input is not None:
            self.connection_type = user_input[CONF_CONNECTION_TYPE]
            
            if self.connection_type == CONNECTION_TYPE_USB:
                return await self.async_step_usb()
            if self.connection_type == CONNECTION_TYPE_BLE:
                return await self.async_step_ble()
            if self.connection_type == CONNECTION_TYPE_TCP:
                return await self.async_step_tcp()

        return self.async_show_form(
            step_id="user", data_schema=STEP_USER_DATA_SCHEMA, errors=errors
        )

    async def async_step_usb(self, user_input: Optional[Dict[str, Any]] = None) -> FlowResult:
        """Handle USB configuration."""
        errors: Dict[str, str] = {}

        if user_input is not None:
            try:
                info = await validate_usb_input(self.hass, user_input)
                return self.async_create_entry(title=info["title"], data={
                    CONF_CONNECTION_TYPE: CONNECTION_TYPE_USB,
                    CONF_USB_PATH: user_input[CONF_USB_PATH],
                    CONF_BAUDRATE: user_input[CONF_BAUDRATE],
                    CONF_SCAN_INTERVAL: user_input[CONF_SCAN_INTERVAL],
                })
            except CannotConnect:
                errors["base"] = "cannot_connect"
            except Exception:  # pylint: disable=broad-except
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"

        # Always allow manual entry for USB path
        # Skip trying to detect ports completely
        return self.async_show_form(
            step_id="usb", 
            data_schema=vol.Schema({
                vol.Required(CONF_USB_PATH): str,
                vol.Optional(CONF_BAUDRATE, default=DEFAULT_BAUDRATE): cv.positive_int,
                vol.Optional(CONF_SCAN_INTERVAL, default=DEFAULT_SCAN_INTERVAL): cv.positive_int,
            }),
            errors=errors
        )

    async def async_step_ble(self, user_input: Optional[Dict[str, Any]] = None) -> FlowResult:
        """Handle BLE configuration."""
        errors: Dict[str, str] = {}

        if user_input is not None:
            try:
                info = await validate_ble_input(self.hass, user_input)
                return self.async_create_entry(title=info["title"], data={
                    CONF_CONNECTION_TYPE: CONNECTION_TYPE_BLE,
                    CONF_BLE_ADDRESS: user_input[CONF_BLE_ADDRESS],
                    CONF_SCAN_INTERVAL: user_input[CONF_SCAN_INTERVAL],
                })
            except CannotConnect:
                errors["base"] = "cannot_connect"
            except Exception:  # pylint: disable=broad-except
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"

        # Scan for BLE devices
        devices = {}
        try:
            scanner = BleakScanner()
            discovered_devices = await scanner.discover(timeout=5.0)
            for device in discovered_devices:
                if device.name and "MeshCore" in device.name:
                    devices[device.address] = f"{device.name} ({device.address})"
        except Exception as ex:
            _LOGGER.warning("Failed to scan for BLE devices: %s", ex)

        # If we have discovered devices, show them in a dropdown
        if devices:
            schema = vol.Schema(
                {
                    vol.Required(CONF_BLE_ADDRESS): vol.In(devices),
                    vol.Optional(CONF_SCAN_INTERVAL, default=DEFAULT_SCAN_INTERVAL): cv.positive_int,
                }
            )
        else:
            # Otherwise, allow manual entry
            schema = BLE_SCHEMA

        return self.async_show_form(
            step_id="ble", data_schema=schema, errors=errors
        )

    async def async_step_tcp(self, user_input: Optional[Dict[str, Any]] = None) -> FlowResult:
        """Handle TCP configuration."""
        errors: Dict[str, str] = {}

        if user_input is not None:
            try:
                info = await validate_tcp_input(self.hass, user_input)
                return self.async_create_entry(title=info["title"], data={
                    CONF_CONNECTION_TYPE: CONNECTION_TYPE_TCP,
                    CONF_TCP_HOST: user_input[CONF_TCP_HOST],
                    CONF_TCP_PORT: user_input[CONF_TCP_PORT],
                    CONF_SCAN_INTERVAL: user_input[CONF_SCAN_INTERVAL],
                })
            except CannotConnect:
                errors["base"] = "cannot_connect"
            except Exception:  # pylint: disable=broad-except
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"

        return self.async_show_form(
            step_id="tcp", data_schema=TCP_SCHEMA, errors=errors
        )