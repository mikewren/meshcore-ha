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
            description = f"Sent message to {data.get('receiver', 'Unknown')}"
        elif message_type == "channel" and channel:
            description = f"Channel message in {channel}"
        else:
            description = f"Message from {sender_name}"
        
        return {
            "name": sender_name,
            "message": message,
            "domain": DOMAIN,
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
        }
    
    @callback
    def process_client_message_event(event: Event) -> dict[str, str]:
        """Process MeshCore client message events for logbook."""
        data = event.data
        client_name = data.get("client_name", "Unknown")
        message = data.get("message", "")
        is_incoming = data.get("is_incoming", True)
        
        if is_incoming:
            description = f"Received message from {client_name}"
        else:
            description = f"Sent message to {client_name}"
        
        return {
            "name": client_name,
            "message": message,
            "domain": DOMAIN,
        }
        
    async_describe_event(DOMAIN, EVENT_MESHCORE_MESSAGE, process_message_event)
    async_describe_event(DOMAIN, EVENT_MESHCORE_CONTACT, process_contact_event)
    async_describe_event(DOMAIN, EVENT_MESHCORE_CLIENT_MESSAGE, process_client_message_event)

def log_message(hass: HomeAssistant, message_data: Dict[str, Any]) -> None:
    """Record message history using Home Assistant events."""
    if not message_data:
        return
        
    # Extract message data
    message_text = message_data.get("msg", "")
    sender_key = message_data.get("sender", "")
    sender_name = "Unknown"
    receiver_name = message_data.get("receiver", "Unknown")
    channel = message_data.get("channel", "")
    message_type = "direct"  # Default to direct message
    outgoing = message_data.get("outgoing", False)
    contact_public_key = None
    
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
                
    # Determine message type
    if channel:
        message_type = "channel"
    
    # First, log to the standard message event
    if outgoing:
        event_type = "send_message"
        event_name = f"Sent message to {receiver_name}"
    elif message_type == "channel" and channel:
        event_type = "channel_message"
        event_name = f"Channel message in {channel}"
    else:
        event_type = "receive_message"
        event_name = f"Message from {sender_name}"
        
    # Create general message event data
    event_data = {
        "name": event_name,
        "message": message_text,
        "message_type": message_type,
        "sender_name": sender_name,
        "entity_id": f"{DOMAIN}.message_tracking",
        "domain": DOMAIN,
        "outgoing": outgoing,
    }
    
    # Fire general message event
    hass.bus.async_fire(EVENT_MESHCORE_MESSAGE, event_data)
    
    # Then, log to client-specific event if we have client info
    if sender_name != "Unknown" or receiver_name != "Unknown":
        client_name = sender_name if not outgoing else receiver_name
        
        # Create client message event data
        client_event_data = {
            "client_name": client_name,
            "message": message_text,
            "is_incoming": not outgoing,
            "entity_id": f"{DOMAIN}.client_{client_name.lower().replace(' ', '_')}",
            "domain": DOMAIN,
            "client_public_key": contact_public_key,
            "timestamp": datetime.now().isoformat(),
        }
        
        # Fire client-specific message event
        hass.bus.async_fire(EVENT_MESHCORE_CLIENT_MESSAGE, client_event_data)
    
    # Store message in coordinator for message tracking
    if coordinator and hasattr(coordinator, "_message_history"):
        # Create history entry
        history_entry = {
            "text": message_text,
            "sender": sender_name,
            "receiver": receiver_name,
            "type": message_type,
            "channel": channel,
            "outgoing": outgoing,
            "timestamp": datetime.now().isoformat(),
        }
        
        # Add to global history
        coordinator._message_history.append(history_entry)
        
        # Keep only last 50 messages
        if len(coordinator._message_history) > 50:
            coordinator._message_history = coordinator._message_history[-50:]
        
        # Also store in per-client history 
        client_name = sender_name if not outgoing else receiver_name
        if client_name != "Unknown":
            # Initialize client history dict if needed
            if not hasattr(coordinator, "_client_message_history"):
                coordinator._client_message_history = {}
                
            # Initialize this client's history if needed
            if client_name not in coordinator._client_message_history:
                coordinator._client_message_history[client_name] = []
                
            # Add to client's history
            coordinator._client_message_history[client_name].append(history_entry)
            
            # Keep only last 50 messages per client
            if len(coordinator._client_message_history[client_name]) > 50:
                coordinator._client_message_history[client_name] = coordinator._client_message_history[client_name][-50:]
        
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
        "entity_id": f"{DOMAIN}.contact_{contact_name.lower().replace(' ', '_')}",
        "domain": DOMAIN,
    }
    
    # Fire Home Assistant event for history/logbook
    hass.bus.async_fire(EVENT_MESHCORE_CONTACT, event_data)
    
    # Create a client message for this contact - initial message
    client_event_data = {
        "client_name": contact_name,
        "message": f"New {contact_type.lower()} device discovered",
        "is_incoming": False,  # System message
        "entity_id": f"{DOMAIN}.client_{contact_name.lower().replace(' ', '_')}",
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