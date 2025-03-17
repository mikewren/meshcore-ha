"""Logbook integration for MeshCore."""
import logging
from typing import Dict, Any, Optional, Callable, Iterable
from datetime import datetime

from homeassistant.components.logbook import (
    DOMAIN as LOGBOOK_DOMAIN,
    EVENT_LOGBOOK_ENTRY,
)
from homeassistant.const import ATTR_NAME, ATTR_ENTITY_ID
from homeassistant.core import HomeAssistant, callback, Context, Event

from .const import (
    DOMAIN,
    NODE_TYPE_CLIENT,
    NODE_TYPE_REPEATER,
    PLATFORM_MESSAGE,
    ENTITY_DOMAIN_BINARY_SENSOR,
    ENTITY_DOMAIN_SENSOR,
    MESSAGES_SUFFIX,
    CONTACT_SUFFIX,
    CHANNEL_PREFIX,
    DEFAULT_DEVICE_NAME,
)
from .utils import (
    sanitize_name,
    get_device_name,
    format_entity_id,
    get_channel_entity_id,
    get_contact_entity_id,
    extract_channel_idx,
    find_coordinator_with_device_name,
)

_LOGGER = logging.getLogger(__name__)

# Event types for message tracking
EVENT_MESHCORE_MESSAGE = "meshcore_message"
EVENT_MESHCORE_CONTACT = "meshcore_contact"
EVENT_MESHCORE_CLIENT_MESSAGE = "meshcore_client_message"

@callback
def async_describe_events(
    hass: HomeAssistant,
    async_describe_event: Callable[[str, str, Callable[[Event], dict[str, str]]], None],
) -> None:
    """Describe logbook events."""
    @callback
    def process_message_event(event: Event) -> dict[str, str]:
        """Process MeshCore message events for logbook."""
        data = event.data
        message = data.get("message", "")
        sender_name = data.get("sender_name", "Unknown")
        message_type = data.get("message_type", "message")
        channel = data.get("channel", "")
        outgoing = data.get("outgoing", False)
        
        # Determine message description
        if outgoing:
            receiver = data.get('receiver', 'Unknown')
            pub_key_short = data.get('client_public_key', '')[:6] if data.get('client_public_key') else ''
            if pub_key_short:
                description = f"Sent to {receiver} ({pub_key_short}): {message}"
            else:
                description = f"Sent to {receiver}: {message}"
            icon = "mdi:message-arrow-right-outline"
        elif message_type == "channel" and channel:
            # For channel messages, we already have sender in the message format
            description = f"<{channel}> {message}"
            icon = "mdi:message-bulleted"
        else:
            pub_key_short = data.get('client_public_key', '')[:6] if data.get('client_public_key') else ''
            if pub_key_short:
                description = f"{sender_name} ({pub_key_short}): {message}"
            else:
                description = f"{sender_name}: {message}"
            icon = "mdi:message-text"
        
        return {
            "name": sender_name,
            "message": message,
            "domain": DOMAIN,
            "icon": icon,
        }
        
    @callback
    def process_contact_event(event: Event) -> dict[str, str]:
        """Process MeshCore contact events for logbook."""
        data = event.data
        contact_name = data.get("contact_name", "Unknown")
        contact_type = data.get("contact_type", "Node")
        
        return {
            "name": contact_name,
            "message": f"New {contact_type} discovered",
            "domain": DOMAIN,
            "icon": "mdi:account-plus",
        }
    
    @callback
    def process_client_message_event(event: Event) -> dict[str, str]:
        """Process MeshCore client message events for logbook."""
        data = event.data
        client_name = data.get("client_name", "Unknown")
        message = data.get("message", "")
        is_incoming = data.get("is_incoming", True)
        
        pub_key_short = data.get('client_public_key', '')[:6] if data.get('client_public_key') else ''
        if is_incoming:
            if pub_key_short:
                description = f"{client_name} ({pub_key_short}): {message}"
            else:
                description = f"{client_name}: {message}"
            icon = "mdi:message-text"
        else:
            if pub_key_short:
                description = f"Sent to {client_name} ({pub_key_short}): {message}"
            else:
                description = f"Sent to {client_name}: {message}"
            icon = "mdi:message-arrow-right-outline"
        
        return {
            "name": client_name,
            "message": message,
            "domain": DOMAIN,
            "icon": icon,
        }
        
    async_describe_event(DOMAIN, EVENT_MESHCORE_MESSAGE, process_message_event)
    async_describe_event(DOMAIN, EVENT_MESHCORE_CONTACT, process_contact_event)
    async_describe_event(DOMAIN, EVENT_MESHCORE_CLIENT_MESSAGE, process_client_message_event)

def log_message(hass: HomeAssistant, message_data: Dict[str, Any]) -> None:
    """Record message history using Home Assistant events."""
    if not message_data:
        return
        
    # Find the coordinator and get the device name
    coordinator, device_name = find_coordinator_with_device_name(hass.data)
        
    # Extract message data
    message_text = message_data.get("text", message_data.get("msg", ""))  # Try both text and msg fields
    sender_key = message_data.get("pubkey_prefix", message_data.get("sender", ""))  # Try both formats
    sender_name = "Unknown"
    receiver_name = message_data.get("receiver", "Unknown")
    channel = message_data.get("channel_idx", message_data.get("channel", ""))  # Try both formats
    message_type = "direct"  # Default to direct message
    outgoing = message_data.get("outgoing", False)
    contact_public_key = None
    
    # Use message type if it's already specified
    if "type" in message_data:
        message_type = message_data["type"]
    
    # Find coordinator and get contact data
    coordinator = None
    for entry_id, coord in hass.data[DOMAIN].items():
        if hasattr(coord, "data") and "contacts" in coord.data:
            coordinator = coord
            break
    
    # Process sender/receiver information
    if coordinator:
        contacts = coordinator.data.get("contacts", [])
        
        # For incoming messages, look up the sender
        if not outgoing and sender_key:
            for contact in contacts:
                if not isinstance(contact, dict):
                    continue
                    
                # Check if this contact is the sender
                if isinstance(sender_key, (bytes, bytearray)) and contact.get("public_key", "").startswith(sender_key.hex()):
                    sender_name = contact.get("adv_name", "Unknown")
                    contact_public_key = contact.get("public_key")
                    break
                elif isinstance(sender_key, str) and contact.get("public_key", "").startswith(sender_key):
                    sender_name = contact.get("adv_name", "Unknown")
                    contact_public_key = contact.get("public_key")
                    break
        
        # For outgoing messages, look up the receiver
        elif outgoing and isinstance(receiver_name, str):
            for contact in contacts:
                if not isinstance(contact, dict):
                    continue
                
                # Check if contact name matches receiver
                if contact.get("adv_name") == receiver_name:
                    contact_public_key = contact.get("public_key")
                    break
                
    # Determine message type if not already set from input
    if message_type != "CHAN" and channel:
        message_type = "channel"
    elif message_type == "CHAN":
        message_type = "channel"
        
    # Try to extract sender name from channel message if it matches pattern: "Name: message"
    if message_type == "channel" and message_text and ":" in message_text:
        parts = message_text.split(":", 1)
        if len(parts) == 2 and parts[0].strip() and parts[1].strip():
            extracted_sender = parts[0].strip()
            extracted_message = parts[1].strip()
            # Only update sender if we don't already have one
            if sender_name == "Unknown":
                sender_name = extracted_sender
                _LOGGER.debug(f"Extracted sender name '{sender_name}' from channel message")
            # Update the message text to show without the sender prefix
            message_text = extracted_message
    
    # First, log to the standard message event
    if outgoing:
        event_type = "send_message"
        event_name = f"Sent message to {receiver_name}"
    elif message_type == "channel" or message_type == "CHAN":
        event_type = "channel_message"
        channel_id = channel if channel else 0  # Default to channel 0 if not specified
        event_name = f"Channel {channel_id} message"
    else:
        event_type = "receive_message"
        event_name = f"Message from {sender_name}"
        
    
    # Then, log to client-specific event if this is a direct message (not a channel message)
    # and we have client info
    if (message_type != "channel" and message_type != "CHAN") and (sender_name != "Unknown" or receiver_name != "Unknown"):
        client_name = sender_name if not outgoing else receiver_name
        
        # Format message with contact public key prefix
        formatted_message = f"<{contact_public_key[:4]}> {message_text}"

        # Create client message event data
        client_event_data = {
            "client_name": client_name,
            "message": formatted_message,
            "text": formatted_message,  # Add text field to ensure compatibility
            "is_incoming": not outgoing,
            "entity_id": get_contact_entity_id(ENTITY_DOMAIN_BINARY_SENSOR, device_name, client_name),  # Use utility function
            "domain": DOMAIN,
            "client_public_key": contact_public_key,
            "timestamp": datetime.now().isoformat(),
            "message_type": "direct",  # Explicitly mark as direct message
            "name": client_name,  # Add name for consistency
        }
        
        # Add the channel information if it's a channel message
        if message_type == "channel" and channel:
            client_event_data["channel"] = channel
            client_event_data["channel_idx"] = channel
        
        # Fire client-specific message event
        hass.bus.async_fire(EVENT_MESHCORE_CLIENT_MESSAGE, client_event_data)
    
    # Store message in coordinator for message tracking
    if coordinator and hasattr(coordinator, "_message_history"):
        # Create history entry
        history_entry = {
            "text": message_text,
            "message": message_text,  # Add for compatibility
            "sender": sender_name,
            "receiver": receiver_name,
            "type": message_type,
            "message_type": message_type,  # Add for compatibility
            "channel": channel,
            "channel_idx": channel if channel else None,  # Add for compatibility
            "outgoing": outgoing,
            "timestamp": datetime.now().isoformat(),
            "pubkey_prefix": sender_key,  # Add the sender key for reference
        }
        
        # Add to global history
        coordinator._message_history.append(history_entry)
        
        # Keep only the last MAX_MESSAGES_HISTORY messages
        from .const import MAX_MESSAGES_HISTORY
        if len(coordinator._message_history) > MAX_MESSAGES_HISTORY:
            coordinator._message_history = coordinator._message_history[-MAX_MESSAGES_HISTORY:]
        
        # For channel messages, store in channel history
        if (message_type == "channel" or message_type == "CHAN") and channel is not None:
            channel_idx = int(channel) if isinstance(channel, (int, str)) and str(channel).isdigit() else 0
            
            # Initialize channel history dict if needed
            if not hasattr(coordinator, "_channel_message_history"):
                coordinator._channel_message_history = {}
                
            # Initialize this channel's history if needed
            if channel_idx not in coordinator._channel_message_history:
                coordinator._channel_message_history[channel_idx] = []
                
            # Add to channel's history
            coordinator._channel_message_history[channel_idx].append(history_entry)
            
            # Keep only the latest messages
            if len(coordinator._channel_message_history[channel_idx]) > MAX_MESSAGES_HISTORY:
                coordinator._channel_message_history[channel_idx] = coordinator._channel_message_history[channel_idx][-MAX_MESSAGES_HISTORY:]
            
            # Create entity ID for logbook using utility function
            entity_id = get_channel_entity_id(ENTITY_DOMAIN_BINARY_SENSOR, device_name, channel_idx)
            
            # Add channel-specific info to the event data
            # Format message with channel index
            formatted_message = f"<{channel_idx}> {message_text}"
            
            channel_event_data = {
                "name": sender_name if sender_name != "Unknown" else f"Channel {channel_idx}",
                "message": formatted_message,
                "text": message_text,
                "sender": sender_name,
                "sender_name": sender_name,  # Add sender_name for consistency
                "entity_id": entity_id,
                "channel_idx": channel_idx,
                "timestamp": datetime.now().isoformat(),
                "domain": DOMAIN,
                "message_type": "channel",  # Explicitly mark as channel message
            }
            
            # Fire channel-specific event for logbook
            hass.bus.async_fire(EVENT_MESHCORE_MESSAGE, channel_event_data)
        
        # For direct messages only (not channel messages), store in client history
        elif (message_type != "channel" and message_type != "CHAN") and client_name != "Unknown":
            # Initialize client history dict if needed
            if not hasattr(coordinator, "_client_message_history"):
                coordinator._client_message_history = {}
                
            # Initialize this client's history if needed
            if client_name not in coordinator._client_message_history:
                coordinator._client_message_history[client_name] = []
                
            # Add to client's history
            coordinator._client_message_history[client_name].append(history_entry)
            
            # Keep only the last MAX_MESSAGES_HISTORY messages per client
            if len(coordinator._client_message_history[client_name]) > MAX_MESSAGES_HISTORY:
                coordinator._client_message_history[client_name] = coordinator._client_message_history[client_name][-MAX_MESSAGES_HISTORY:]
        
        # Trigger coordinator update to refresh sensors
        coordinator.async_set_updated_data(coordinator.data)
    
    # Log for debugging
    if outgoing:
        _LOGGER.debug("Logged outgoing message: %s to %s", 
            message_text, receiver_name)
    else:
        _LOGGER.debug("Logged incoming message: %s from %s", 
            message_text, sender_name)

def log_contact_seen(hass: HomeAssistant, contact_data: Dict[str, Any]) -> None:
    """Record contact discovery using Home Assistant events."""
    if not contact_data:
        return
        
    contact_name = contact_data.get("adv_name", "Unknown")
    node_type = contact_data.get("type")
    public_key = contact_data.get("public_key", "")
    
    # Determine contact type description
    contact_type = "Client" if node_type == NODE_TYPE_CLIENT else "Repeater" if node_type == NODE_TYPE_REPEATER else "Node"
    
    # Create event data for logbook
    event_data = {
        "contact_name": contact_name,
        "contact_type": contact_type,
        "public_key": public_key,
        "node_type": node_type,
        "entity_id": get_contact_entity_id(ENTITY_DOMAIN_SENSOR, DEFAULT_DEVICE_NAME, contact_name, CONTACT_SUFFIX),
        "domain": DOMAIN,
    }
    
    # Fire Home Assistant event for history/logbook
    hass.bus.async_fire(EVENT_MESHCORE_CONTACT, event_data)
    
    # Create a client message for this contact - initial message
    client_event_data = {
        "client_name": contact_name,
        "message": f"New {contact_type.lower()} device discovered",
        "is_incoming": False,  # System message
        "entity_id": get_contact_entity_id(ENTITY_DOMAIN_SENSOR, DEFAULT_DEVICE_NAME, contact_name, "message"),  # Use utility function
        "domain": DOMAIN,
        "client_public_key": public_key,
        "timestamp": datetime.now().isoformat(),
    }
    
    # Fire client-specific event
    hass.bus.async_fire(EVENT_MESHCORE_CLIENT_MESSAGE, client_event_data)
    
    # Find the coordinator
    coordinator = None
    for entry_id, coord in hass.data[DOMAIN].items():
        if hasattr(coord, "data"):
            coordinator = coord
            break
            
    # Store in coordinator message history
    if coordinator:
        # Create history entry for global tracking
        history_entry = {
            "text": f"New {contact_type.lower()} discovered: {contact_name}",
            "sender": "system",
            "type": "contact_discovery",
            "contact_name": contact_name,
            "contact_type": contact_type,
            "timestamp": datetime.now().isoformat(),
        }
        
        # Add to global history if exists
        if hasattr(coordinator, "_message_history"):
            coordinator._message_history.append(history_entry)
            
            # Keep only last 50 messages
            if len(coordinator._message_history) > 50:
                coordinator._message_history = coordinator._message_history[-50:]
        
        # Add to client-specific history
        if contact_name != "Unknown":
            # Initialize client history dict if needed
            if not hasattr(coordinator, "_client_message_history"):
                coordinator._client_message_history = {}
                
            # Initialize this client's history
            if contact_name not in coordinator._client_message_history:
                coordinator._client_message_history[contact_name] = []
            
            # Add discovery message to client history
            coordinator._client_message_history[contact_name].append(history_entry)
            
        # Trigger update to refresh UI
        coordinator.async_set_updated_data(coordinator.data)
    
    # Log for debugging
    _LOGGER.info(
        "New %s contact discovered: %s", 
        contact_type.lower(), 
        contact_name
    )