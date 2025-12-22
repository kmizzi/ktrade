#!/bin/bash
# Setup KTrade Auto-Optimizer on VPS (run from local machine)

VPS_HOST="ktrade"
REMOTE_DIR="/home/ktrade/ktrade"

echo "Setting up auto-optimizer on VPS ($VPS_HOST)..."
ssh $VPS_HOST "cd $REMOTE_DIR && ./scripts/setup-auto-optimize.sh"
