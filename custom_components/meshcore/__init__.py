"""The MeshCore integration."""
from __future__ import annotations

import asyncio
import logging
import time
from datetime import timedelta, datetime
from typing import Any, Dict, List, Optional

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.entity_platform import EntityPlatform
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
    MAX_MESSAGES_HISTORY,
    PLATFORM_MESSAGE,
    CONF_REPEATER_SUBSCRIPTIONS,
    CONF_REPEATER_NAME,
    CONF_REPEATER_PASSWORD,
    CONF_REPEATER_UPDATE_INTERVAL,
    DEFAULT_REPEATER_UPDATE_INTERVAL,
    CONF_INFO_INTERVAL,
    CONF_MESSAGES_INTERVAL,
    DEFAULT_INFO_INTERVAL,
    DEFAULT_MESSAGES_INTERVAL,
)
from .meshcore_api import MeshCoreAPI
from .services import async_setup_services, async_unload_services
from .logbook import log_message, log_contact_seen

_LOGGER = logging.getLogger(__name__)

# List of platforms to set up
PLATFORMS = [Platform.SENSOR, Platform.BINARY_SENSOR]

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up MeshCore from a config entry."""
    # Get configuration from entry
    connection_type = entry.data[CONF_CONNECTION_TYPE]
    
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
    
    # Get the messages interval for base update frequency
    # Check options first, then data, then use default
    messages_interval = entry.options.get(
        CONF_MESSAGES_INTERVAL, 
        entry.data.get(CONF_MESSAGES_INTERVAL, DEFAULT_MESSAGES_INTERVAL)
    )
    
    # Create update coordinator with the messages interval (fastest polling rate)
    coordinator = MeshCoreDataUpdateCoordinator(
        hass,
        _LOGGER,
        name=DOMAIN,
        update_interval=timedelta(seconds=messages_interval),
        api=api,
        config_entry=entry,
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
    # Check if repeater subscriptions have changed and handle device removal
    old_subscriptions = entry.data.get(CONF_REPEATER_SUBSCRIPTIONS, [])
    
    # Reload the entry to apply the new options
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
        config_entry: ConfigEntry = None,
    ) -> None:
        """Initialize."""
        super().__init__(
            hass,
            logger,
            name=name,
            update_interval=update_interval,
        )
        self.api = api
        self.config_entry = config_entry
        self.data: Dict[str, Any] = {}
        self._current_node_info = {}
        self._contacts = []
        self._messages = []
        self._message_history = []
        self._client_message_history = {}
        
        # Repeater subscription tracking
        self._repeater_stats = {}
        self._repeater_login_times = {}
        
        # Track last update times for different data types
        self._last_info_update = 0  # Combined time for node info and contacts
        self._last_messages_update = 0
        self._last_repeater_updates = {}  # Dictionary to track per-repeater updates
        
        # Get interval settings from config (or use defaults)
        if config_entry:
            self._info_interval = config_entry.options.get(
                CONF_INFO_INTERVAL, DEFAULT_INFO_INTERVAL
            )
            self._messages_interval = config_entry.options.get(
                CONF_MESSAGES_INTERVAL, DEFAULT_MESSAGES_INTERVAL
            )
        else:
            # Use defaults if no config entry
            self._info_interval = DEFAULT_INFO_INTERVAL
            self._messages_interval = DEFAULT_MESSAGES_INTERVAL
        
        # For compatibility with older HA versions
        if not hasattr(self, "last_update_success_time"):
            import time
            self.last_update_success_time = time.time()
    
    async def _fetch_node_info(self, result_data: Dict[str, Any]) -> Dict[str, Any]:
        """Fetch basic node information and battery status from the device."""
        self.logger.info("Fetching basic node info...")
        try:
            # Fetch basic node info
            node_info = await self.api.get_node_info()
            
            if node_info and isinstance(node_info, dict):
                # Update our data with node info
                for key, value in node_info.items():
                    result_data[key] = value
                
                # Log key node parameters
                node_name = node_info.get("name", "Unknown")
                self.logger.info(f"Node info updated: {node_name}")
            else:
                self.logger.warning("Could not get node info or empty response")
                
            # Fetch battery status
            try:
                self.logger.info("Fetching battery status...")
                battery_value = await self.api.get_battery()
                
                if battery_value is not None and battery_value > 0:
                    # Store battery value in raw form (divided by 10 in sensor.py)
                    result_data["bat"] = battery_value
                    self.logger.info(f"Battery status updated: {battery_value}")
                else:
                    self.logger.warning(f"Could not get battery status or invalid value: {battery_value}")
            except Exception as bat_ex:
                self.logger.error(f"Error getting battery status: {bat_ex}")
                # Continue without battery info
                
        except Exception as ex:
            self.logger.error(f"Error getting node info: {ex}")
            # Continue rather than failing completely
        
        return result_data
        
    async def _fetch_repeater_stats(self, result_data: Dict[str, Any]) -> Dict[str, Any]:
        """Fetch stats from configured repeaters based on their individual update intervals."""
        if not self.config_entry:
            self.logger.debug("No config entry available, skipping repeater stats")
            return result_data
            
        # Get repeater subscriptions from config entry
        repeater_subscriptions = self.config_entry.data.get(CONF_REPEATER_SUBSCRIPTIONS, [])
        if not repeater_subscriptions:
            self.logger.debug("No repeater subscriptions configured, skipping repeater stats")
            return result_data
            
        self.logger.debug(f"Found {len(repeater_subscriptions)} repeater subscriptions to check")
            
        # Create a dictionary to store all repeater stats (including cached ones)
        all_repeater_stats = {}
        
        # Start with any existing stats we have
        if hasattr(self, "_repeater_stats") and self._repeater_stats:
            all_repeater_stats.update(self._repeater_stats)
        
        # Current time for interval calculations
        current_time = time.time()
        
        # Process each repeater subscription
        for repeater in repeater_subscriptions:
            # Skip disabled repeaters
            if not repeater.get("enabled", True):
                self.logger.debug(f"Skipping disabled repeater: {repeater.get('name')}")
                continue
                
            repeater_name = repeater.get("name")
            password = repeater.get("password", "")
            update_interval = repeater.get("update_interval", DEFAULT_REPEATER_UPDATE_INTERVAL)
            
            if not repeater_name:
                self.logger.warning(f"Skipping repeater with missing name: {repeater}")
                continue
                
            # Check if it's time to update this repeater based on its interval
            last_update = self._last_repeater_updates.get(repeater_name, 0)
            time_since_update = current_time - last_update
            
            # Skip update if not enough time has passed
            if time_since_update < update_interval and last_update > 0:
                self.logger.debug(
                    f"Skipping repeater {repeater_name} update - " +
                    f"last update was {time_since_update:.1f}s ago (interval: {update_interval}s)"
                )
                continue
                
            self.logger.info(
                f"Updating repeater {repeater_name} after {time_since_update:.1f}s " +
                f"(interval: {update_interval}s)"
            )
                
            # Check if we need to re-login (login times tracked per repeater)
            last_login_time = self._repeater_login_times.get(repeater_name, 0)
            # Re-login every hour (3600 seconds)
            login_interval = 3600
            time_since_login = current_time - last_login_time
            need_login = time_since_login > login_interval
            
            if need_login:
                self.logger.info(f"Login needed for {repeater_name} - last login was {time_since_login:.1f}s ago (limit: {login_interval}s)")
                # Password can be empty for guest login
                login_success = await self.api.login_to_repeater(repeater_name, password)
                
                if login_success:
                    self._repeater_login_times[repeater_name] = current_time
                    self.logger.info(f"Successfully logged in to repeater: {repeater_name}")
                else:
                    self.logger.error(f"Failed to login to repeater: {repeater_name} - using password: {'yes' if password else 'no (guest)'}")
                    # Update timestamp even on failure to avoid hammering with login attempts
                    self._last_repeater_updates[repeater_name] = current_time
                    continue
            else:
                self.logger.debug(f"No login needed for {repeater_name} - last login was {time_since_login:.1f}s ago")
            
            # Get stats from the repeater
            try:
                self.logger.info(f"Fetching stats from repeater: {repeater_name}")
                stats = await self.api.get_repeater_stats(repeater_name)
                
                if stats:
                    # Add the stats to our results
                    self._repeater_stats[repeater_name] = stats
                    all_repeater_stats[repeater_name] = stats
                    # Update last update time
                    self._last_repeater_updates[repeater_name] = current_time
                    self.logger.info(f"Successfully updated stats for repeater: {repeater_name}")
                else:
                    self.logger.warning(f"No stats received for repeater: {repeater_name}")
                    # Update timestamp even on empty results to avoid constant retries
                    self._last_repeater_updates[repeater_name] = current_time
            except Exception as ex:
                self.logger.error(f"Error fetching stats for repeater {repeater_name}: {ex}")
                # Update timestamp even on error to avoid constant retries
                self._last_repeater_updates[repeater_name] = current_time
        
        # Add all repeater stats to the result data
        if all_repeater_stats:
            result_data["repeater_stats"] = all_repeater_stats
            self.logger.debug(f"Added stats for {len(all_repeater_stats)} repeaters to result data")
            
        return result_data
    
    async def _fetch_contacts(self, result_data: Dict[str, Any], force_update: bool = False) -> Dict[str, Any]:
        """Fetch contacts list from the device.
        
        Args:
            result_data: The data dictionary to update
            force_update: Whether to force a contacts update regardless of schedule
        """
        # Decide whether to update contacts based on schedule or forced update
        should_update = (
            force_update or 
            len(self._contacts) == 0 or 
            self._update_count % 2 == 0
        )
        
        if should_update:
            self.logger.info("Fetching contacts list...")
            try:
                contacts = await self.api.get_contacts()
                
                if contacts and isinstance(contacts, dict):
                    # Convert contacts dict to list
                    contacts_list = []
                    for name, data in contacts.items():
                        if isinstance(data, dict):
                            if "adv_name" not in data:
                                data["adv_name"] = name
                            contacts_list.append(data)
                    
                    # Store the contacts in our result data
                    self._contacts = contacts_list
                    result_data["contacts"] = contacts_list
                    
                    self.logger.info(f"Retrieved {len(contacts_list)} contacts")
                else:
                    self.logger.info("No contacts found or empty response")
                    result_data["contacts"] = []
            except Exception as ex:
                self.logger.error(f"Error getting contacts: {ex}")
                # Use previously cached contacts if any
                result_data["contacts"] = self._contacts
        else:
            # Use cached contacts when we don't fetch them
            result_data["contacts"] = self._contacts
        
        return result_data
    
    async def _fetch_messages(self, result_data: Dict[str, Any]) -> Dict[str, Any]:
        """Fetch and process new messages from the device."""
        self.logger.info("Checking for new messages...")
        try:
            new_messages = await self.api.get_new_messages()
            
            if new_messages and isinstance(new_messages, list) and len(new_messages) > 0:
                # Log message count
                self.logger.info(f"Found {len(new_messages)} new message(s)")
                
                # Process each message and add to our history
                for msg in new_messages:
                    # Extract key message details for logging
                    message_text = msg.get("text", "")
                    message_type = msg.get("type", "PRIV")  # Default to private message
                    
                    if message_type == "CHAN":
                        channel_idx = msg.get('channel_idx', 'Unknown')
                        message_source = f"Channel {channel_idx}"
                    else:
                        pubkey_prefix = msg.get('pubkey_prefix', 'Unknown')
                        message_source = f"Contact {pubkey_prefix}"
                    
                    # Log with more detail
                    self.logger.info(f"Message from {message_source}: {message_text}")
                    self.logger.debug(f"Full message: {msg}")
                    
                    # Add timestamp if not present
                    if "timestamp" not in msg:
                        msg["timestamp"] = int(time.time())
                    
                    # Add to our message history
                    self._messages.append(msg)
                
                # Keep only the latest MAX_MESSAGES_HISTORY messages
                if len(self._messages) > MAX_MESSAGES_HISTORY:
                    self._messages = self._messages[-MAX_MESSAGES_HISTORY:]
                
                # Update result data with messages
                result_data["messages"] = self._messages
                
                # Log to Home Assistant logbook
                try:
                    for msg in new_messages:
                        log_message(self.hass, msg)
                except Exception as log_ex:
                    self.logger.error(f"Error logging message to logbook: {log_ex}")
            else:
                # No new messages found
                if new_messages is None or not isinstance(new_messages, list):
                    self.logger.warning("Invalid response from message check")
                else:
                    self.logger.debug("No new messages found")
                
                # Keep existing messages
                result_data["messages"] = self._messages
        except Exception as ex:
            self.logger.error(f"Error checking messages: {ex}")
            # Keep existing messages
            result_data["messages"] = self._messages
        
        return result_data
    
    async def _async_update_data(self) -> Dict[str, Any]:
        """Update data from the MeshCore node.
        
        Implementation with different polling intervals:
        1. Messages: Every update (DEFAULT_MESSAGES_INTERVAL - 10 seconds)
        2. Node info: Every _node_info_interval (60 seconds by default)
        3. Contacts: Every _contacts_interval (60 seconds by default)
        4. Repeater stats: Per-repeater based on their update_interval (300 seconds by default)
        """
        # Initialize result with previous data
        result_data = dict(self.data) if self.data else {
            "name": "MeshCore Node", 
            "contacts": [],
            "messages": []
        }
        
        # Track update count for debugging
        if not hasattr(self, "_update_count"):
            self._update_count = 0
        self._update_count += 1
        
        # Flag to track if this is the first update
        first_update = self._update_count == 1
        
        # Current time for interval calculations
        current_time = time.time()
        
        # Initialize data structures if needed
        if not hasattr(self, "_contacts"):
            self._contacts = []
        if not hasattr(self, "_messages"):
            self._messages = []
        if not hasattr(self, "_client_message_history"):
            self._client_message_history = {}
        if not hasattr(self, "_channel_message_history"):
            self._channel_message_history = {}
        
        try:
            # Reconnect if needed
            if not self.api._connected:
                self.logger.info("Connecting to device...")
                await self.api.disconnect()
                connection_success = await self.api.connect()
                if not connection_success:
                    self.logger.error("Failed to connect to MeshCore device")
                    raise UpdateFailed("Failed to connect to MeshCore device")
            
            # Always fetch on first update
            if first_update:
                self.logger.info("First update - fetching all data types")
                result_data = await self._fetch_node_info(result_data)
                result_data = await self._fetch_contacts(result_data, force_update=True)
                result_data = await self._fetch_messages(result_data)
                result_data = await self._fetch_repeater_stats(result_data)
                
                # Set initial update times
                self._last_info_update = current_time
                self._last_messages_update = current_time
                
                # Initialize repeater update tracking
                if self.config_entry:
                    repeaters = self.config_entry.data.get(CONF_REPEATER_SUBSCRIPTIONS, [])
                    for repeater in repeaters:
                        repeater_name = repeater.get("name")
                        if repeater_name:
                            self._last_repeater_updates[repeater_name] = current_time
            else:
                # Conditional updates based on intervals
                
                # 1. Always check for messages (base update interval)
                time_since_messages = current_time - self._last_messages_update
                self.logger.debug(f"Time since last messages update: {time_since_messages:.1f}s (interval: {self._messages_interval}s)")
                result_data = await self._fetch_messages(result_data)
                self._last_messages_update = current_time
                
                # 2. Check node info and contacts if interval has passed
                time_since_info = current_time - self._last_info_update
                if time_since_info >= self._info_interval:
                    self.logger.debug(f"Fetching node info and contacts after {time_since_info:.1f}s (interval: {self._info_interval}s)")
                    # Fetch node info first
                    result_data = await self._fetch_node_info(result_data)
                    # Then fetch contacts
                    result_data = await self._fetch_contacts(result_data)
                    self._last_info_update = current_time
                else:
                    self.logger.debug(f"Skipping node info and contacts update - last update was {time_since_info:.1f}s ago")
                    # Use cached contacts
                    result_data["contacts"] = self._contacts
                
                # 4. Check repeater stats only for repeaters whose interval has passed
                await self._fetch_repeater_stats(result_data)
            
            # Always update last_update_success_time 
            self.last_update_success_time = current_time
            
            return result_data
            
        except Exception as err:
            self.logger.error(f"Error during update: {err}")
            
            # If we have previous data, return that instead of failing
            if self.data:
                return self.data
                
            # Minimal fallback data
            return {
                "name": "MeshCore Node",
                "contacts": self._contacts,
                "messages": self._messages
            }