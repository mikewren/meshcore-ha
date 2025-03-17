#!/bin/bash

# Configuration
REMOTE_USER="awolden"
REMOTE_HOST="server.local.com"
REMOTE_PATH="/opt/homeassistant/config/custom_components"
LOCAL_PATH="./custom_components/meshcore"
REMOTE_COMPONENT_PATH="$REMOTE_PATH/meshcore"

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Parse command-line arguments
RESTART_HA=false
while getopts ":r" opt; do
  case ${opt} in
    r )
      RESTART_HA=true
      ;;
    \? )
      echo "Invalid option: -$OPTARG" 1>&2
      exit 1
      ;;
  esac
done

echo -e "${YELLOW}Syncing MeshCore integration to Home Assistant server...${NC}"

# Ensure target directory exists
ssh $REMOTE_USER@$REMOTE_HOST "mkdir -p $REMOTE_COMPONENT_PATH"

# Sync files using rsync
rsync -avz --delete \
    --exclude '*.pyc' \
    --exclude '__pycache__' \
    --exclude '.DS_Store' \
    $LOCAL_PATH/ $REMOTE_USER@$REMOTE_HOST:$REMOTE_COMPONENT_PATH/

# Restart Home Assistant if requested
if [ "$RESTART_HA" = true ]; then
  echo -e "${YELLOW}Restarting Home Assistant...${NC}"
  ssh $REMOTE_USER@$REMOTE_HOST "sudo docker restart homeassistant" || {
    echo -e "${RED}Failed to restart Home Assistant${NC}"
    exit 1
  }
  echo -e "${GREEN}Home Assistant restart initiated${NC}"
else
  # Provide instructions for restarting/reloading
  echo -e "${YELLOW}To apply changes:${NC}"
  echo -e "  1. ${YELLOW}For most changes: Reload the integration${NC}"
  echo -e "     - Go to Developer Tools → Services"
  echo -e "     - Select service: ${GREEN}homeassistant.reload_config_entry${NC}"
  echo -e "     - Click 'Call Service'"
  echo -e ""
  echo -e "  2. ${YELLOW}For structural changes (changes to __init__.py, config_flow.py, or new dependencies):${NC}"
  echo -e "     - Go to Configuration → Server Controls"
  echo -e "     - Click 'Restart'"
  echo -e ""
  echo -e "  3. ${YELLOW}For complete reinstallation:${NC}"
  echo -e "     - Uninstall the integration from Home Assistant"
  echo -e "     - Restart Home Assistant"
  echo -e "     - Re-add the integration"
  echo -e ""
  echo -e "  4. ${YELLOW}To automatically restart Home Assistant:${NC}"
  echo -e "     - Run this script with the -r flag: ${GREEN}./sync-to-ha.sh -r${NC}"
fi

echo -e "${GREEN}Sync complete!${NC}"