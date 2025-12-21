#!/bin/bash
# Remove KTrade Auto-Optimizer Cron Schedule
# Run this script to disable automatic bot optimization

# Auto-detect directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
KTRADE_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

CRON_ID="# KTRADE-AUTO-OPTIMIZER"

echo "Removing KTrade Auto-Optimizer schedule..."

# Get current crontab, filter out our entries, and reinstall
(crontab -l 2>/dev/null | grep -v "$CRON_ID") | crontab - 2>/dev/null || true

echo ""
echo "✅ Auto-optimizer schedule removed!"
echo ""
echo "The following were removed:"
echo "  • Daily optimization at market close"
echo "  • Health check every 6 hours"
echo ""
echo "To re-enable: $SCRIPT_DIR/setup-auto-optimize.sh"
echo ""

# Verify removal
echo "Remaining cron entries:"
crontab -l 2>/dev/null || echo "(no crontab)"
