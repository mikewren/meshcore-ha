"""API for communicating with MeshCore devices using direct import."""
import logging
import asyncio
import json
import time
import os
import sys
from typing import Any, Dict, List, Optional, Union
from pathlib import Path
from asyncio import Lock

# Import directly from the vendor module
from .vendor.mccli import (
    MeshCore, 
    BLEConnection, 
    SerialConnection, 
    TCPConnection,
    UART_SERVICE_UUID,
    UART_RX_CHAR_UUID,
    UART_TX_CHAR_UUID
)

from .const import (
    CONNECTION_TYPE_USB,
    CONNECTION_TYPE_BLE,
    CONNECTION_TYPE_TCP,
    DEFAULT_BAUDRATE,
    DEFAULT_TCP_PORT,
)

_LOGGER = logging.getLogger(__name__)

class MeshCoreAPI:
    """API for interacting with MeshCore devices by directly using the MeshCore class."""

    def __init__(
        self,
        connection_type: str,
        usb_path: Optional[str] = None,
        baudrate: int = DEFAULT_BAUDRATE,
        ble_address: Optional[str] = None,
        tcp_host: Optional[str] = None,
        tcp_port: int = DEFAULT_TCP_PORT,
    ) -> None:
        """Initialize the API."""
        self.connection_type = connection_type
        self.usb_path = usb_path
        self.baudrate = baudrate
        self.ble_address = ble_address
        self.tcp_host = tcp_host
        self.tcp_port = tcp_port
        
        self._connected = False
        self._connection = None
        self._mesh_core = None
        self._node_info = {}
        self._cached_contacts = {}
        self._cached_messages = []
        
        # Add a lock to prevent concurrent access to the device
        self._device_lock = Lock()
        
    async def connect(self) -> bool:
        """Connect to the MeshCore device using the appropriate connection type."""
        try:
            # Reset state first
            self._connected = False
            self._connection = None
            self._mesh_core = None
            
            _LOGGER.info("Connecting to MeshCore device...")
            
            # Create the appropriate connection object based on connection type
            if self.connection_type == CONNECTION_TYPE_USB and self.usb_path:
                _LOGGER.info(f"Using USB connection at {self.usb_path} with baudrate {self.baudrate}")
                self._connection = SerialConnection(self.usb_path, self.baudrate)
                
                # Establish the connection
                address = await self._connection.connect()
                
                # Add a longer delay for serial connection to stabilize
                # Increased from the original implementation for more stability
                await asyncio.sleep(0.5)
                
            elif self.connection_type == CONNECTION_TYPE_BLE:
                _LOGGER.info(f"Using BLE connection with address {self.ble_address}")
                self._connection = BLEConnection(self.ble_address if self.ble_address else "")
                
                # Establish the connection
                address = await self._connection.connect()
                
            elif self.connection_type == CONNECTION_TYPE_TCP and self.tcp_host:
                _LOGGER.info(f"Using TCP connection to {self.tcp_host}:{self.tcp_port}")
                self._connection = TCPConnection(self.tcp_host, self.tcp_port)
                
                # Establish the connection
                address = await self._connection.connect()
                
            else:
                _LOGGER.error("Invalid connection configuration")
                return False
                
            if address is None:
                _LOGGER.error("Failed to connect to MeshCore device")
                return False
                
            # Create MeshCore instance with the connection
            self._mesh_core = MeshCore(self._connection)
            
            # Wait a bit before initializing
            await asyncio.sleep(0.2)
            
            # Initialize the connection to the device
            _LOGGER.info("Initializing connection to MeshCore device...")
            try:
                init_success = await self._mesh_core.connect()
                if not init_success:
                    _LOGGER.error("Failed to initialize MeshCore connection")
                    return False
            except UnicodeDecodeError as e:
                # Special handling for decode errors which are common
                _LOGGER.error(f"Unicode decode error during initialization: {e}")
                _LOGGER.info("Attempting manual initialization sequence...")
                
                # Try a manual approach - just send APPSTART but don't expect a response
                try:
                    await self._mesh_core.send_only(b'\x01\x03      mccli')
                    
                    # Give the device time to process
                    await asyncio.sleep(0.5)
                    
                    # Assume it worked and continue
                    _LOGGER.info("Manual initialization completed")
                except Exception as manual_ex:
                    _LOGGER.error(f"Manual initialization also failed: {manual_ex}")
                    return False
            
            self._connected = True
            _LOGGER.info("Successfully connected to MeshCore device")
            return True
            
        except Exception as ex:
            _LOGGER.error("Error connecting to MeshCore device: %s", ex)
            self._connected = False
            self._connection = None
            self._mesh_core = None
            return False
    
    async def disconnect(self) -> None:
        """Disconnect from the MeshCore device."""
        self._connected = False
        self._connection = None
        self._mesh_core = None
        _LOGGER.info("Disconnected from MeshCore device")
        return
    
    async def get_node_info(self) -> Dict[str, Any]:
        """Get information about the node."""
        if not self._connected or not self._mesh_core:
            _LOGGER.error("Not connected to MeshCore device")
            return {}
            
        async with self._device_lock:
            try:
                # Retrieve node info using the MeshCore instance
                _LOGGER.debug("Getting node info...")
                success = await self._mesh_core.send_appstart()
                if not success:
                    _LOGGER.error("Failed to initialize app session")
                    return {}
                    
                # The self_info attribute is updated when appstart is called
                # We need to make a copy to avoid reference issues
                self._node_info = self._mesh_core.self_info.copy()
                return self._node_info
                
            except Exception as ex:
                _LOGGER.error("Error getting node info: %s", ex)
                return {}
    
    async def get_battery(self) -> int:
        """Get battery level (raw value)."""
        if not self._connected or not self._mesh_core:
            _LOGGER.error("Not connected to MeshCore device")
            return 0
            
        async with self._device_lock:
            try:
                _LOGGER.debug("Getting battery level...")
                battery = await self._mesh_core.get_bat()
                if battery is False:
                    _LOGGER.error("Failed to get battery level")
                    return 0
                    
                return battery
                
            except Exception as ex:
                _LOGGER.error("Error getting battery level: %s", ex)
                return 0
    
    async def get_contacts(self) -> Dict[str, Any]:
        """Get list of contacts/nodes in the mesh network."""
        if not self._connected or not self._mesh_core:
            _LOGGER.error("Not connected to MeshCore device")
            return {}
            
        async with self._device_lock:
            try:
                # Retrieve contacts using the MeshCore instance
                _LOGGER.debug("Getting contacts...")
                contacts = await self._mesh_core.get_contacts()
                
                if contacts and isinstance(contacts, dict):
                    self._cached_contacts = contacts
                    _LOGGER.debug("Retrieved %d contacts", len(contacts))
                    return contacts
                else:
                    _LOGGER.warning("No contacts found or invalid contacts format")
                    return {}
                    
            except Exception as ex:
                _LOGGER.error("Error getting contacts: %s", ex)
                return {}
    
    async def get_new_messages(self) -> List[Dict[str, Any]]:
        """Get new messages from the mesh network.
        
        This implementation matches the approach used in mccli.py's sync_msgs command.
        It repeatedly calls get_msg() until it returns False, collecting all messages.
        """
        if not self._connected or not self._mesh_core:
            _LOGGER.error("Not connected to MeshCore device")
            return []
            
        async with self._device_lock:
            try:
                messages = []
                
                _LOGGER.info("===== Syncing messages from device (like mccli.py sync_msgs) =====")
                
                # Use a very simple approach that matches the CLI tool's sync_msgs command
                res = True
                while res:
                    res = await self._mesh_core.get_msg()
                    
                    if res is False:
                        _LOGGER.debug("No more messages (received False)")
                        break
                        
                    if res:
                        # Log message details
                        if isinstance(res, dict):
                            if "msg" in res:
                                text = res.get("msg", "")
                                sender = res.get("sender", "Unknown") 
                                if hasattr(sender, "hex"):
                                    sender = sender.hex()
                                timestamp = res.get("sender_timestamp", "Unknown")
                                
                                _LOGGER.info(f"Retrieved message: '{text}' from {sender}")
                            else:
                                _LOGGER.info(f"Retrieved non-text message: {res}")
                        else:
                            _LOGGER.warning(f"Retrieved non-dict result: {res}")
                        
                        # Add to our message list
                        messages.append(res)
                        
                        # Add to cached messages
                        self._cached_messages.append(res)
                        # Keep only the latest 50 messages
                        if len(self._cached_messages) > 50:
                            self._cached_messages = self._cached_messages[-50:]
                    
                _LOGGER.info(f"===== Retrieved {len(messages)} messages from device =====")
                return messages
                
            except Exception as ex:
                _LOGGER.error(f"Error getting new messages: {ex}")
                return []
        
    async def wait_for_message(self, timeout: int = 10) -> Optional[Dict[str, Any]]:
        """Wait for a new message to arrive."""
        if not self._connected or not self._mesh_core:
            _LOGGER.error("Not connected to MeshCore device")
            return None
            
        # We'll use a shorter timeout to avoid blocking the device for too long
        actual_timeout = min(timeout, 2)
            
        async with self._device_lock:
            try:
                _LOGGER.debug(f"Waiting for messages with {actual_timeout}s timeout...")
                
                # Wait for message notification
                got_message = await self._mesh_core.wait_msg(actual_timeout)
                if not got_message:
                    # Timeout waiting for message
                    _LOGGER.debug("No messages received within timeout period")
                    return None
                    
                _LOGGER.info("Message notification received, fetching message...")
                
                # Get the message
                msg = await self._mesh_core.get_msg()
                if msg:
                    _LOGGER.info(f"Message received: {msg}")
                    
                    # Add to cached messages
                    self._cached_messages.append(msg)
                    # Keep only the latest 50 messages
                    if len(self._cached_messages) > 50:
                        self._cached_messages = self._cached_messages[-50:]
                    
                    # We won't check for additional messages here to avoid
                    # blocking the device for too long
                    return msg
                
                _LOGGER.debug("Message notification received but no message data found")
                return None
                
            except Exception as ex:
                _LOGGER.error(f"Error waiting for message: {ex}")
                return None
    
    async def request_status(self) -> Dict[str, Any]:
        """Request status from all nodes.
        
        Note: Currently disabled to avoid potential device issues.
        """
        # Skipping status requests due to device issues
        _LOGGER.debug("Status requests are disabled to avoid device issues")
        return {}  # Return empty status results
    
    async def send_message(self, node_name: str, message: str) -> bool:
        """Send message to a specific node by name."""
        if not self._connected or not self._mesh_core:
            _LOGGER.error("Not connected to MeshCore device")
            return False
            
        async with self._device_lock:
            try:
                # First ensure we have contacts
                if not self._cached_contacts:
                    # We're behind a lock, so avoid calling another locked method
                    _LOGGER.error("No cached contacts available - call get_contacts first")
                    return False
                    
                # Check if the node exists
                if node_name not in self._cached_contacts:
                    _LOGGER.error("Node %s not found in contacts", node_name)
                    return False
                    
                # Send the message using the MeshCore instance
                _LOGGER.info(f"Sending message to {node_name}: {message}")
                result = await self._mesh_core.send_msg(
                    bytes.fromhex(self._cached_contacts[node_name]["public_key"])[:6],
                    message
                )
                
                if not result:
                    _LOGGER.error(f"Failed to send message to {node_name}")
                    return False
                    
                # Wait for the message ACK with shorter timeout
                _LOGGER.debug(f"Waiting for ACK from {node_name}...")
                ack_received = await self._mesh_core.wait_ack(3)  # reduced timeout
                
                if ack_received:
                    _LOGGER.info(f"Message to {node_name} acknowledged")
                else:
                    _LOGGER.warning(f"No ACK received from {node_name}")
                
                return ack_received
                
            except Exception as ex:
                _LOGGER.error(f"Error sending message: {ex}")
                return False