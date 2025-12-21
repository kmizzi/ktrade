#!/bin/bash
# Remove KTrade Auto-Optimizer from VPS (run from local machine)

VPS_HOST="karb"
REMOTE_DIR="/root/code/ktrade"

echo "Removing auto-optimizer from VPS ($VPS_HOST)..."
ssh $VPS_HOST "cd $REMOTE_DIR && ./scripts/remove-auto-optimize.sh"
