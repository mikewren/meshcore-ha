"""Sensor platform for MeshCore integration."""
from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo, EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
)

from .const import (
    DOMAIN,
    NODE_TYPE_CLIENT,
    NODE_TYPE_REPEATER,
)

_LOGGER = logging.getLogger(__name__)

# Battery voltage constants
MIN_BATTERY_VOLTAGE = 3.2  # Minimum LiPo voltage
MAX_BATTERY_VOLTAGE = 4.2  # Maximum LiPo voltage

# Define sensors for the main device
SENSORS = [
    SensorEntityDescription(
        key="node_status",
        name="Node Status",
        icon="mdi:radio-tower",
    ),
    SensorEntityDescription(
        key="battery_voltage",
        name="Battery Voltage",
        device_class=SensorDeviceClass.VOLTAGE,
        native_unit_of_measurement="V",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:battery",
    ),
    SensorEntityDescription(
        key="battery_percentage",
        name="Battery Percentage",
        device_class=SensorDeviceClass.BATTERY,
        native_unit_of_measurement="%",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:battery",
    ),
    SensorEntityDescription(
        key="node_count",
        name="Node Count",
        icon="mdi:account-group",
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorEntityDescription(
        key="tx_power",
        name="TX Power",
        device_class=SensorDeviceClass.POWER,
        native_unit_of_measurement="dBm",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:power",
    ),
    SensorEntityDescription(
        key="latitude",
        name="Latitude",
        icon="mdi:map-marker",
    ),
    SensorEntityDescription(
        key="longitude",
        name="Longitude",
        icon="mdi:map-marker",
    ),
    SensorEntityDescription(
        key="frequency",
        name="Frequency",
        native_unit_of_measurement="MHz",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:radio",
    ),
    SensorEntityDescription(
        key="bandwidth",
        name="Bandwidth",
        native_unit_of_measurement="kHz",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:radio",
    ),
    SensorEntityDescription(
        key="spreading_factor",
        name="Spreading Factor",
        icon="mdi:radio",
    ),
]

# Sensors for remote nodes/contacts
CONTACT_SENSORS = [
    SensorEntityDescription(
        key="status",
        name="Status",
        icon="mdi:radio-tower",
    ),
    SensorEntityDescription(
        key="battery",
        name="Battery",
        device_class=SensorDeviceClass.VOLTAGE,
        native_unit_of_measurement="V",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:battery",
    ),
    SensorEntityDescription(
        key="battery_percentage",
        name="Battery Percentage",
        device_class=SensorDeviceClass.BATTERY,
        native_unit_of_measurement="%",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:battery",
    ),
    SensorEntityDescription(
        key="last_rssi",
        name="Last RSSI",
        native_unit_of_measurement="dBm",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:signal",
    ),
    SensorEntityDescription(
        key="last_snr",
        name="Last SNR",
        native_unit_of_measurement="dB",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:signal",
    ),
    SensorEntityDescription(
        key="last_message",
        name="Last Message",
        icon="mdi:message-text",
    ),
    SensorEntityDescription(
        key="last_message_time",
        name="Last Message Time",
        device_class=SensorDeviceClass.TIMESTAMP,
        icon="mdi:clock",
    ),
]

# Additional sensors only for repeaters (type 2)
REPEATER_SENSORS = [
    SensorEntityDescription(
        key="uptime",
        name="Uptime",
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement="s",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:clock",
    ),
    SensorEntityDescription(
        key="airtime",
        name="Airtime",
        native_unit_of_measurement="s",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:radio",
    ),
    SensorEntityDescription(
        key="nb_sent",
        name="Messages Sent",
        state_class=SensorStateClass.TOTAL_INCREASING,
        icon="mdi:message-arrow-right",
    ),
    SensorEntityDescription(
        key="nb_recv",
        name="Messages Received",
        state_class=SensorStateClass.TOTAL_INCREASING,
        icon="mdi:message-arrow-left",
    ),
    SensorEntityDescription(
        key="tx_queue_len",
        name="TX Queue Length",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:playlist-edit",
    ),
    SensorEntityDescription(
        key="free_queue_len",
        name="Free Queue Length",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:playlist-plus",
    ),
    SensorEntityDescription(
        key="sent_flood",
        name="Sent Flood Messages",
        state_class=SensorStateClass.TOTAL_INCREASING,
        icon="mdi:message-arrow-right-outline",
    ),
    SensorEntityDescription(
        key="sent_direct",
        name="Sent Direct Messages",
        state_class=SensorStateClass.TOTAL_INCREASING,
        icon="mdi:message-arrow-right",
    ),
    SensorEntityDescription(
        key="recv_flood",
        name="Received Flood Messages",
        state_class=SensorStateClass.TOTAL_INCREASING,
        icon="mdi:message-arrow-left-outline",
    ),
    SensorEntityDescription(
        key="recv_direct",
        name="Received Direct Messages",
        state_class=SensorStateClass.TOTAL_INCREASING,
        icon="mdi:message-arrow-left",
    ),
    SensorEntityDescription(
        key="full_evts",
        name="Full Events",
        state_class=SensorStateClass.TOTAL_INCREASING,
        icon="mdi:alert-circle",
    ),
    SensorEntityDescription(
        key="direct_dups",
        name="Direct Duplicates",
        state_class=SensorStateClass.TOTAL_INCREASING,
        icon="mdi:content-duplicate",
    ),
    SensorEntityDescription(
        key="flood_dups",
        name="Flood Duplicates",
        state_class=SensorStateClass.TOTAL_INCREASING,
        icon="mdi:content-duplicate",
    ),
]


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up MeshCore sensors from a config entry."""
    coordinator = hass.data[DOMAIN][entry.entry_id]
    
    _LOGGER.debug("Setting up MeshCore sensors")
    
    entities = []
    
    # Create sensors for the main device
    for description in SENSORS:
        _LOGGER.debug("Adding sensor: %s", description.key)
        entities.append(MeshCoreSensor(coordinator, description))
    
    # Add a contact list sensor to track all contacts
    entities.append(MeshCoreContactListSensor(coordinator))
    
    # Add a global message tracking sensor
    entities.append(MeshCoreMessageTrackingSensor(coordinator))
    
    # Add per-client message tracking sensors for existing contacts
    # (new contacts will get sensors when they're discovered)
    contacts = coordinator.data.get("contacts", [])
    if contacts:
        for contact in contacts:
            if not isinstance(contact, dict):
                continue
                
            contact_name = contact.get("adv_name", "")
            if contact_name:
                entities.append(MeshCoreClientMessageSensor(
                    coordinator, 
                    contact_name,
                    contact.get("public_key", "")
                ))
    
    # Create a diagnostic sensor for each contact
    contacts = coordinator.data.get("contacts", [])
    if contacts:
        _LOGGER.debug("Creating diagnostic sensors for %d contacts", len(contacts))
        
        for contact in contacts:
            if not isinstance(contact, dict):
                continue
                
            try:
                name = contact.get("adv_name", "Unknown")
                public_key = contact.get("public_key", "")
                node_type = contact.get("type")
                
                if not public_key:
                    continue
                    
                # Create a unique ID for this contact
                contact_id = f"{entry.entry_id}_contact_{public_key[:10]}"
                
                # Create diagnostic sensor for this contact
                sensor = MeshCoreContactDiagnosticSensor(
                    coordinator, 
                    name,
                    public_key,
                    contact_id
                )
                
                # Initialize attributes, icon, and name based on node type
                sensor._update_attributes()
                entities.append(sensor)
                
            except Exception as ex:
                _LOGGER.error("Error setting up contact diagnostic sensor: %s", ex)
    
    async_add_entities(entities)


class MeshCoreSensor(CoordinatorEntity, SensorEntity):
    """Representation of a MeshCore sensor."""

    def __init__(
        self,
        coordinator: DataUpdateCoordinator,
        description: SensorEntityDescription,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self.entity_description = description
        
        # Set unique ID
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_{description.key}"
        
        # Set name
        self._attr_name = description.name
        
        # Set device info
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.config_entry.entry_id)},
            name=f"MeshCore {coordinator.data.get('name', 'Node')}",
            manufacturer="MeshCore",
            model="Mesh Radio",
            sw_version=coordinator.data.get("version", "Unknown"),
        )

    @property
    def native_value(self) -> Any:
        """Return the state of the sensor."""
        if self.coordinator.data is None:
            return None

        key = self.entity_description.key
        
        if key == "node_status":
            if getattr(self.coordinator, "last_update_success", False):
                return "online"
            return "offline"
            
        elif key == "battery_voltage":
            bat_value = self.coordinator.data.get("bat", 0)
            if isinstance(bat_value, (int, float)) and bat_value > 0:
                return bat_value / 10  # Convert to voltage
            return None
            
        elif key == "battery_percentage":
            bat_value = self.coordinator.data.get("bat", 0)
            if isinstance(bat_value, (int, float)) and bat_value > 0:
                voltage = bat_value / 10  # Convert to voltage
                # Calculate percentage based on min/max voltage range
                percentage = ((voltage - MIN_BATTERY_VOLTAGE) / 
                             (MAX_BATTERY_VOLTAGE - MIN_BATTERY_VOLTAGE)) * 100
                
                # Ensure percentage is within 0-100 range
                percentage = max(0, min(100, percentage))
                return round(percentage, 1)  # Round to 1 decimal place
            return None
            
        elif key == "node_count":
            contacts = self.coordinator.data.get("contacts", [])
            return len(contacts) + 1
            
        elif key == "tx_power":
            return self.coordinator.data.get("tx_power")
            
        elif key == "latitude":
            return self.coordinator.data.get("adv_lat")
            
        elif key == "longitude":
            return self.coordinator.data.get("adv_lon")
            
        elif key == "frequency":
            freq = self.coordinator.data.get("radio_freq")
            if freq is not None:
                return freq / 1000
            return None
            
        elif key == "bandwidth":
            bw = self.coordinator.data.get("radio_bw") 
            if bw is not None:
                # Check if already in kHz
                if bw < 1000:
                    return bw  # Already in kHz
                else:
                    return bw / 1_000  # Convert Hz to kHz
            return None
            
        elif key == "spreading_factor":
            return self.coordinator.data.get("radio_sf")
        
        return None


class MeshCoreContactListSensor(CoordinatorEntity, SensorEntity):
    """A sensor to track all MeshCore contacts in a single entity."""

    def __init__(self, coordinator: DataUpdateCoordinator) -> None:
        """Initialize the contact list sensor."""
        super().__init__(coordinator)
        
        # Set unique ID and name
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_contacts"
        self._attr_name = "MeshCore Contacts"
        
        # Set device info to link to the main device
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.config_entry.entry_id)},
        )
        
        # Set entity category to diagnostic
        self._attr_entity_category = EntityCategory.DIAGNOSTIC
        
        # Use a custom icon
        self._attr_icon = "mdi:account-group"

    @property
    def native_value(self) -> str:
        """Return the current number of contacts as the state."""
        if not self.coordinator.data:
            return "0"
            
        contacts = self.coordinator.data.get("contacts", [])
        return str(len(contacts))
        
    @property
    def extra_state_attributes(self) -> Dict[str, Any]:
        """Return details about all contacts as attributes."""
        if not self.coordinator.data:
            return {}
            
        contacts = self.coordinator.data.get("contacts", [])
        if not contacts:
            return {"contacts": []}
            
        contact_list = []
        for contact in contacts:
            if not isinstance(contact, dict):
                continue
                
            # Extract the key info we want to display
            contact_info = {
                "name": contact.get("adv_name", "Unknown"),
                "type": "Repeater" if contact.get("type") == NODE_TYPE_REPEATER else "Client",
                "public_key": contact.get("public_key", "")[:16] + "...",  # Truncate for display
                "last_seen": contact.get("last_advert", 0),
            }
            
            # Add location if available
            if "adv_lat" in contact and "adv_lon" in contact:
                contact_info["location"] = f"{contact.get('adv_lat')}, {contact.get('adv_lon')}"
                
            contact_list.append(contact_info)
            
        # Sort by name
        contact_list.sort(key=lambda x: x.get("name", ""))
        
        return {
            "contacts": contact_list,
            "last_updated": datetime.now().isoformat(),
        }
        

class MeshCoreContactDiagnosticSensor(CoordinatorEntity, SensorEntity):
    """A diagnostic sensor for a single MeshCore contact."""

    def __init__(
        self,
        coordinator: DataUpdateCoordinator,
        contact_name: str,
        public_key: str,
        contact_id: str,
    ) -> None:
        """Initialize the contact diagnostic sensor."""
        super().__init__(coordinator)
        
        self.contact_name = contact_name
        self.public_key = public_key
        
        # Set unique ID
        self._attr_unique_id = contact_id
        
        # Initial name (will be updated in _update_attributes)
        self._attr_name = contact_name
        
        # Set device info to link to the main device
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.config_entry.entry_id)},
        )
        
        # Set entity category to diagnostic
        self._attr_entity_category = EntityCategory.DIAGNOSTIC
        
        # Icon will be set dynamically in the _update_attributes method

    def _get_contact_data(self) -> Dict[str, Any]:
        """Get the data for this contact from the coordinator."""
        if not self.coordinator.data or not isinstance(self.coordinator.data, dict):
            return {}
            
        contacts = self.coordinator.data.get("contacts", [])
        if not contacts:
            return {}
            
        # Find this contact by name or by public key
        for contact in contacts:
            if not isinstance(contact, dict):
                continue
                
            # Match by name
            if contact.get("adv_name") == self.contact_name:
                return contact
                
            # Match by public key prefix
            if contact.get("public_key", "").startswith(self.public_key):
                return contact
                
        return {}

    def _update_attributes(self) -> Dict[str, Any]:
        """Update the attributes and icon based on contact data."""
        contact = self._get_contact_data()
        if not contact:
            # If contact not found, use default icon
            self._attr_icon = "mdi:radio-tower"
            self._attr_name = f"{self.contact_name}"
            return {"status": "unknown"}
            
        # Create a copy of the contact data for attributes
        attributes = {}
        
        # Add all contact properties directly as attributes
        for key, value in contact.items():
            attributes[key] = value
            
        # Get the node type and set icon accordingly
        node_type = contact.get("type")
        
        # Set different icons and names based on node type
        if node_type == NODE_TYPE_CLIENT:  # Client
            self._attr_icon = "mdi:account"
            self._attr_name = f"{self.contact_name} (Client)"
            attributes["node_type_str"] = "Client"
        elif node_type == NODE_TYPE_REPEATER:  # Repeater
            self._attr_icon = "mdi:radio-tower"
            self._attr_name = f"{self.contact_name} (Repeater)"
            attributes["node_type_str"] = "Repeater"
        else:
            # Default icon if type is unknown
            self._attr_icon = "mdi:help-network"
            self._attr_name = f"{self.contact_name} (Unknown)"
            attributes["node_type_str"] = "Unknown"
        
        # Format last advertisement time if available
        if "last_advert" in attributes and attributes["last_advert"] > 0:
            last_advert_time = datetime.fromtimestamp(attributes["last_advert"])
            attributes["last_advert_formatted"] = last_advert_time.isoformat()
            
        return attributes
        
    @property
    def native_value(self) -> str:
        """Return the contact's status as the state."""
        contact = self._get_contact_data()
        if not contact:
            return "unknown"
            
        # Check last advertisement time for contact status
        last_advert = contact.get("last_advert", 0)
        if last_advert > 0:
            # Calculate time since last advert
            time_since = time.time() - last_advert
            # If less than 1 hour, consider online
            if time_since < 3600:
                return "online"
        
        return "offline"
        
    @property
    def extra_state_attributes(self) -> Dict[str, Any]:
        """Return the raw contact data as attributes."""
        return self._update_attributes()


class MeshCoreMessageTrackingSensor(CoordinatorEntity, SensorEntity):
    """Sensor that tracks all mesh network messages."""

    def __init__(self, coordinator: DataUpdateCoordinator) -> None:
        """Initialize the message tracking sensor."""
        super().__init__(coordinator)
        
        # Set unique ID and name
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_message_tracking"
        self._attr_name = "MeshCore Messages"
        
        # Set device info to link to the main device
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.config_entry.entry_id)},
        )
        
        # Set icon
        self._attr_icon = "mdi:message-text"
        
    @property
    def native_value(self) -> str:
        """Return the number of messages in history."""
        if hasattr(self.coordinator, "_message_history"):
            return str(len(self.coordinator._message_history))
        return "0"
            
    @property
    def extra_state_attributes(self) -> Dict[str, Any]:
        """Return the message history as attributes."""
        if hasattr(self.coordinator, "_message_history"):
            return {
                "messages": self.coordinator._message_history,
                "last_updated": datetime.now().isoformat(),
            }
        return {
            "messages": [],
            "last_updated": datetime.now().isoformat(),
        }


class MeshCoreClientMessageSensor(CoordinatorEntity, SensorEntity):
    """Sensor that tracks messages for a specific mesh network client."""

    def __init__(
        self, 
        coordinator: DataUpdateCoordinator, 
        client_name: str,
        public_key: str = "",
    ) -> None:
        """Initialize the client message tracking sensor."""
        super().__init__(coordinator)
        
        self.client_name = client_name
        self.public_key = public_key
        
        # Set unique ID and name
        safe_name = client_name.lower().replace(" ", "_")
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_client_{safe_name}"
        self._attr_name = f"{client_name} Messages"
        
        # Set device info to link to the main device
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.config_entry.entry_id)},
        )
        
        # Set icon
        self._attr_icon = "mdi:message-text-outline"
        
    @property
    def native_value(self) -> str:
        """Return the number of messages for this client."""
        if hasattr(self.coordinator, "_client_message_history"):
            if self.client_name in self.coordinator._client_message_history:
                return str(len(self.coordinator._client_message_history[self.client_name]))
        return "0"
            
    @property
    def extra_state_attributes(self) -> Dict[str, Any]:
        """Return the client's message history as attributes."""
        if hasattr(self.coordinator, "_client_message_history"):
            if self.client_name in self.coordinator._client_message_history:
                return {
                    "messages": self.coordinator._client_message_history[self.client_name],
                    "client_name": self.client_name,
                    "public_key": self.public_key,
                    "last_updated": datetime.now().isoformat(),
                }
        
        return {
            "messages": [],
            "client_name": self.client_name,
            "public_key": self.public_key,
            "last_updated": datetime.now().isoformat(),
        }
