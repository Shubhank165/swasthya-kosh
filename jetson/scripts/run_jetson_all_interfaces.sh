#!/usr/bin/env bash
# Launch MediKiosk FastAPI & Display servers bound to 0.0.0.0
# Accessible over Tailscale (100.104.251.40), USB tether (192.168.191.75), and localhost
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"
export PYTHONPATH="$ROOT_DIR/src"

# Bind to 0.0.0.0 so all networks can connect
export MEDIKIOSK_HOST=0.0.0.0
export MEDIKIOSK_PORT=8000
export PANEL_ENABLED=true
export PANEL_TARGET=tablet
export PANEL_PORT=8800

echo "=========================================================="
echo " Starting MediKiosk on Jetson Orin Nano (All Interfaces)"
echo " API:     http://0.0.0.0:8000"
echo " WS:      ws://0.0.0.0:8000/ws/session"
echo " Display: http://0.0.0.0:8800"
echo "=========================================================="

python3 -m uvicorn medikiosk.app:app --host 0.0.0.0 --port 8000
