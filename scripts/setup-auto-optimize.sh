#!/bin/bash
# Setup KTrade Auto-Optimizer Cron Schedule
# Run this script to enable automatic bot optimization

set -e

# Auto-detect directory (works on both Mac and Linux)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
KTRADE_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
SCRIPTS_DIR="$KTRADE_DIR/scripts"
CRON_ID="# KTRADE-AUTO-OPTIMIZER"

echo "Setting up KTrade Auto-Optimizer..."

# Make scripts executable
chmod +x "$SCRIPTS_DIR/run-optimizer.sh"
chmod +x "$SCRIPTS_DIR/send-alert.sh"

# Create logs directory
mkdir -p "$KTRADE_DIR/logs/optimization-reports"

# Define cron schedules
# Schedule 1: Daily optimization at 4:30 PM ET (market close)
# Note: Cron uses server timezone. Adjust if needed.
# 30 16 * * 1-5 = 4:30 PM, Monday-Friday

# Schedule 2: Health check every 6 hours
# 0 */6 * * * = Every 6 hours

# Remove existing KTrade optimizer entries first
(crontab -l 2>/dev/null | grep -v "$CRON_ID") | crontab - 2>/dev/null || true

# Add new cron entries
(crontab -l 2>/dev/null; cat << EOF
$CRON_ID - Daily optimization at market close (4:30 PM ET, Mon-Fri)
30 16 * * 1-5 $SCRIPTS_DIR/run-optimizer.sh >> $KTRADE_DIR/logs/cron.log 2>&1
$CRON_ID - Health check every 6 hours
0 */6 * * * $SCRIPTS_DIR/run-optimizer.sh >> $KTRADE_DIR/logs/cron.log 2>&1
EOF
) | crontab -

echo ""
echo "✅ Auto-optimizer scheduled successfully!"
echo ""
echo "Schedule:"
echo "  • Daily optimization: 4:30 PM (Mon-Fri, after market close)"
echo "  • Health check: Every 6 hours"
echo ""
echo "Logs:"
echo "  • Cron output: $KTRADE_DIR/logs/cron.log"
echo "  • Optimizer logs: $KTRADE_DIR/logs/optimizer-YYYY-MM-DD.log"
echo "  • Reports: $KTRADE_DIR/logs/optimization-reports/"
echo ""
echo "To view current cron jobs: crontab -l"
echo "To remove: $SCRIPTS_DIR/remove-auto-optimize.sh"
echo ""

# Verify cron is set
echo "Current cron entries:"
crontab -l | grep -A1 "$CRON_ID" || echo "(none found)"
