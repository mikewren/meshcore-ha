"""The MeshCore integration."""
from __future__ import annotations

import asyncio
import logging
from datetime import timedelta
from typing import Any, Dict

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    DOMAIN,
    CONF_CONNECTION_TYPE,
    CONF_USB_PATH,
    CONF_BLE_ADDRESS,
    CONF_TCP_HOST,
    CONF_TCP_PORT,
    CONF_BAUDRATE,
    CONF_SCAN_INTERVAL,
    DEFAULT_SCAN_INTERVAL,
)
from .meshcore_api import MeshCoreAPI
from .services import async_setup_services, async_unload_services
from .logbook import log_message, log_contact_seen

_LOGGER = logging.getLogger(__name__)

# List of platforms to set up
PLATFORMS = [Platform.SENSOR]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up MeshCore from a config entry."""
    # Get configuration from entry
    connection_type = entry.data[CONF_CONNECTION_TYPE]
    scan_interval = entry.data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
    
    # Create API instance based on connection type
    api_kwargs = {"connection_type": connection_type}
    
    if CONF_USB_PATH in entry.data:
        api_kwargs["usb_path"] = entry.data[CONF_USB_PATH]
    if CONF_BAUDRATE in entry.data:
        api_kwargs["baudrate"] = entry.data[CONF_BAUDRATE]
    if CONF_BLE_ADDRESS in entry.data:
        api_kwargs["ble_address"] = entry.data[CONF_BLE_ADDRESS]
    if CONF_TCP_HOST in entry.data:
        api_kwargs["tcp_host"] = entry.data[CONF_TCP_HOST]
    if CONF_TCP_PORT in entry.data:
        api_kwargs["tcp_port"] = entry.data[CONF_TCP_PORT]
    
    # Initialize API
    api = MeshCoreAPI(**api_kwargs)
    
    # Create update coordinator
    coordinator = MeshCoreDataUpdateCoordinator(
        hass,
        _LOGGER,
        name=DOMAIN,
        update_interval=timedelta(seconds=scan_interval),
        api=api,
    )
    
    # Fetch initial data
    await coordinator.async_config_entry_first_refresh()
    
    # Store coordinator for this entry
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = coordinator
    
    # Set up all platforms for this device
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    
    # Set up services
    await async_setup_services(hass)
    
    # Register update listener for config entry updates
    entry.async_on_unload(entry.add_update_listener(async_update_options))
    
    return True


async def async_update_options(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Update options for a config entry."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    # Unload platforms
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    
    # Remove entry from data
    if unload_ok and entry.entry_id in hass.data[DOMAIN]:
        # Get coordinator and disconnect
        coordinator = hass.data[DOMAIN][entry.entry_id]
        await coordinator.api.disconnect()
        
        # Remove entry
        hass.data[DOMAIN].pop(entry.entry_id)
        
        # If no more entries, unload services
        if not hass.data[DOMAIN]:
            await async_unload_services(hass)
    
    return unload_ok


class MeshCoreDataUpdateCoordinator(DataUpdateCoordinator):
    """Class to manage fetching data from the MeshCore node."""

    def __init__(
        self,
        hass: HomeAssistant,
        logger: logging.Logger,
        name: str,
        update_interval: timedelta,
        api: MeshCoreAPI,
    ) -> None:
        """Initialize."""
        super().__init__(
            hass,
            logger,
            name=name,
            update_interval=update_interval,
        )
        self.api = api
        self.data: Dict[str, Any] = {}
        self._current_node_info = {}
        self._contacts = []
        self._messages = []
        self._message_history = []
        self._client_message_history = {}
        
        # For compatibility with older HA versions
        if not hasattr(self, "last_update_success_time"):
            import time
            self.last_update_success_time = time.time()
    
    async def _async_update_data(self) -> Dict[str, Any]:
        """Update data from the MeshCore node.
        
        Simplified implementation that focuses on reliability:
        1. On every 3rd update, get contacts
        2. Every update, just get new messages
        3. Skip all other operations to reduce load
        """
        # Initialize result with previous data
        result_data = dict(self.data) if self.data else {
            "name": "MeshCore Node",
            "contacts": [],
            "messages": self._messages or [],
        }
        
        # Track update count for cycling through operations
        if not hasattr(self, "_update_count"):
            self._update_count = 0
        self._update_count += 1
        
        try:
            # Reconnect only if needed or on every 5th update
            if not self.api._connected or self._update_count % 5 == 0:
                self.logger.info("Reconnecting to device...")
                await self.api.disconnect()
                connection_success = await self.api.connect()
                if not connection_success:
                    self.logger.error("Failed to connect to MeshCore device")
                    # Properly report failure instead of silently returning cached data
                    raise UpdateFailed("Failed to connect to MeshCore device")
            
            # Every 3rd update, get contacts
            if self._update_count % 3 == 0:
                try:
                    self.logger.info("Fetching contacts...")
                    contacts = await self.api.get_contacts()
                    
                    if isinstance(contacts, dict) and contacts:
                        # Convert contacts dict to list
                        contacts_list = []
                        for name, data in contacts.items():
                            if isinstance(data, dict):
                                if "adv_name" not in data:
                                    data["adv_name"] = name
                                contacts_list.append(data)
                                
                        self.logger.info(f"Found {len(contacts_list)} contacts")
                        self._contacts = contacts_list
                        result_data["contacts"] = contacts_list
                        
                        # Check for new contacts (in simplified way)
                        for contact in contacts_list:
                            if contact.get("adv_name"):
                                self.logger.info(f"Contact: {contact.get('adv_name')} (Type: {contact.get('type')})")
                    elif self._contacts:
                        # Use cached contacts
                        result_data["contacts"] = self._contacts
                        
                except Exception as ex:
                    self.logger.error(f"Error updating contacts: {ex}")
                    # Use cached contacts but count as an update failure
                    if self._contacts:
                        result_data["contacts"] = self._contacts
                    else:
                        # If this is the first update and we have no contacts, report failure
                        if self._update_count <= 3:
                            raise UpdateFailed(f"Failed to get contacts: {ex}")
            
            # EVERY update, get new messages - our primary focus
            try:
                self.logger.info("=================== CHECKING FOR MESSAGES ===================")
                new_messages = await self.api.get_new_messages()
                
                if new_messages:
                    self.logger.info(f"Found {len(new_messages)} new messages!")
                    
                    # Process each message
                    for msg in new_messages:
                        if isinstance(msg, dict):
                            text = msg.get("msg", "")
                            sender = msg.get("sender", "Unknown")
                            if hasattr(sender, "hex"):
                                sender = sender.hex()
                                
                            self.logger.info(f"Message: '{text}' from {sender}")
                            
                            # Add to our message list
                            self._messages.append(msg)
                            
                            # Log to tracking system
                            try:
                                log_message(self.hass, msg)
                            except Exception as log_ex:
                                self.logger.error(f"Failed to log message: {log_ex}")
                    
                    # Keep only the last 50 messages
                    if len(self._messages) > 50:
                        self._messages = self._messages[-50:]
                        
                    # Update result data
                    result_data["messages"] = self._messages
                
            except Exception as ex:
                self.logger.error(f"Error checking messages: {ex}")
                # Still keep our existing messages, but report this as a failure
                result_data["messages"] = self._messages
                
                # Only raise an exception if we're completely unable to get messages
                # This prevents spamming errors for minor message retrieval issues
                if self._update_count % 3 == 0:  # Only on every 3rd update to prevent spam
                    raise UpdateFailed(f"Failed to retrieve messages: {ex}")
            
            # Always update last_update_success_time 
            import time
            self.last_update_success_time = time.time()
            
            return result_data
            
        except Exception as err:
            self.logger.error(f"Error during update: {err}")
            
            # If we have previous data, return that instead of failing
            if self.data:
                return self.data
                
            # Minimal fallback data
            return {
                "name": "MeshCore Node",
                "contacts": self._contacts or [],
                "messages": self._messages or [],
            }