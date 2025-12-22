#!/bin/bash
# Remove KTrade Auto-Optimizer from VPS (run from local machine)

VPS_HOST="ktrade"
REMOTE_DIR="/home/ktrade/ktrade"

echo "Removing auto-optimizer from VPS ($VPS_HOST)..."
ssh $VPS_HOST "cd $REMOTE_DIR && ./scripts/remove-auto-optimize.sh"
