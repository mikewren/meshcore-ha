![MeshCore Banner](images/meshcore-bg.png)

# MeshCore for Home Assistant

This is a custom Home Assistant integration for MeshCore mesh radio nodes. It allows you to monitor and control MeshCore nodes via USB, BLE, or TCP connections.

> :warning: **Work in Progress**: This integration is under active development. BLE and TCP connection methods haven't been thoroughly tested yet.

Core integration is powered by [mccli.py](https://github.com/fdlamotte/mccli/blob/main/mccli.py) from fdlamotte.

## Features

- Connect to MeshCore nodes via USB, BLE, or TCP
- Monitor node status, signal strength, battery levels, and more
- View messages received by the mesh network
- Send messages to other nodes in the network
- Automatically discover nodes in the mesh network and create sensors for them
- Track and monitor repeater nodes with detailed statistics
- Configurable update intervals for different data types (messages, device info, repeaters)

## Installation

### HACS Installation (Recommended)

1. Make sure you have [HACS](https://hacs.xyz/) installed
2. Add this repository as a custom repository in HACS:
   - Go to HACS > Integrations
   - Click on the three dots in the top right corner
   - Select "Custom repositories"
   - Add the URL of this repository
   - Select "Integration" as the category
3. Click "Install" on the MeshCore integration

### Manual Installation

1. Copy the `custom_components/meshcore` directory to your Home Assistant `custom_components` directory
2. Restart Home Assistant

## Configuration

1. Go to **Settings** > **Devices & Services**
2. Click **+ Add Integration** and search for "MeshCore"
3. Follow the setup wizard:
   - Select the connection type (USB, BLE, or TCP)
   - For USB: Select the USB port and set the baud rate (default: 115200)
   - For BLE: Select your MeshCore device from the discovered devices or enter the address manually
   - For TCP: Enter the hostname/IP and port of your MeshCore device
   - Configure update intervals for different data types:
     - Messages interval: How often to poll for new messages (default: 10 seconds)
     - Device info interval: How often to update device statistics (default: 60 seconds)
     - Repeater update interval: How often to poll repeater nodes (default: 300 seconds)

## Available Sensors

For the local node:
- **Node Status**: Shows if the node is online or offline
- **Node Count**: Number of nodes in the mesh network (including the local node)
- **Signal Strength**: RSSI of the last received packet (in dBm)
- **Signal-to-Noise Ratio**: SNR of the last received packet
- **Battery**: Battery level (percentage)
- **Last Message**: The most recent message received
- **Uptime**: How long the node has been running
- **Airtime**: Total radio airtime used
- **Messages Sent**: Total number of messages sent
- **Messages Received**: Total number of messages received

For remote nodes (automatically created for each node in the network):
- **Signal Strength**: RSSI of the last received packet from that node
- **Battery**: Battery level of the remote node (if available)
- **Last Message**: Most recent message received from that node

For repeater nodes:
- **Battery Voltage**: Battery voltage in volts
- **Battery Percentage**: Estimated battery level percentage
- **Uptime**: How long the repeater has been running (in minutes)
- **Airtime**: Total radio airtime used by the repeater (in minutes)
- **Temperature**: Internal temperature of the repeater (if available)

## Services

### Send Message

Send a message to a specific node in the mesh network.

Service: `meshcore.send_message`

| Field | Type | Description |
| ----- | ---- | ----------- |
| `node_id` | string | The ID of the node to send the message to (first 8 chars of public key) |
| `message` | string | The message text to send |

Example:
```yaml
service: meshcore.send_message
data:
  node_id: "a1b2c3d4"
  message: "Hello from Home Assistant!"
```

## Troubleshooting

### Connection Issues

- **USB Connection**: Make sure the device is properly connected and the correct port is selected. Try a different baud rate if the default doesn't work.
- **BLE Connection**: Ensure Bluetooth is enabled on your Home Assistant host. Try moving closer to the device if signal strength is low.
- **TCP Connection**: Verify the hostname/IP and port are correct and that there are no firewalls blocking the connection.

### Repeater Issues

- If repeaters aren't appearing, check that your node has correct time synchronization
- Verify the public key used for repeater login is correct
- Try increasing the repeater update interval if connections are unreliable
- Check the Home Assistant logs for detailed error messages related to repeater connections

### Integration Not Working

- Check the Home Assistant logs for error messages related to the MeshCore integration
- Verify that your MeshCore device is working correctly (try using the MeshCore CLI directly)
- Make sure you have the required permissions to access the device (especially for USB devices)
- Try adjusting the update intervals if you're experiencing performance issues

## Support and Development

- Report issues on GitHub
- Contributions are welcome via pull requests

## Requirements

- Home Assistant (version 2023.8.0 or newer)
- MeshCore node with firmware that supports API commands
- For BLE: Bluetooth adapter on the Home Assistant host
- For USB: USB port on the Home Assistant host

## License

This project is licensed under the MIT License - see the LICENSE file for details.