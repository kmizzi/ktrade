#!/bin/bash
# Health check script for ktrade-bot
# This script checks if the bot is healthy and restarts it if hung
# Run via cron every 5 minutes: */5 * * * * /home/ktrade/ktrade/scripts/health_check.sh

HEARTBEAT_FILE="/home/ktrade/ktrade/data/bot_heartbeat"
MAX_AGE_SECONDS=600  # 10 minutes - if heartbeat is older, restart
LOG_FILE="/home/ktrade/ktrade/logs/health_check.log"

log() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') - $1" >> "$LOG_FILE"
}

# Check if service is running
if ! systemctl is-active --quiet ktrade-bot; then
    log "ERROR: Bot service not running. Starting..."
    sudo systemctl start ktrade-bot
    log "Bot service started"
    exit 0
fi

# Check heartbeat file exists
if [ ! -f "$HEARTBEAT_FILE" ]; then
    log "WARNING: Heartbeat file not found. Bot may be starting up or stuck."
    # Give it some grace time on first run
    exit 0
fi

# Get heartbeat timestamp
HEARTBEAT_TIME=$(cat "$HEARTBEAT_FILE" 2>/dev/null)
if [ -z "$HEARTBEAT_TIME" ]; then
    log "WARNING: Heartbeat file is empty"
    exit 0
fi

# Calculate age
CURRENT_TIME=$(date +%s)
HEARTBEAT_INT=${HEARTBEAT_TIME%.*}  # Remove decimal part
AGE=$((CURRENT_TIME - HEARTBEAT_INT))

# Check if heartbeat is too old
if [ "$AGE" -gt "$MAX_AGE_SECONDS" ]; then
    log "ERROR: Bot heartbeat is ${AGE}s old (max: ${MAX_AGE_SECONDS}s). Restarting..."
    sudo systemctl restart ktrade-bot
    log "Bot service restarted due to stale heartbeat"
else
    # Optional: log healthy status (comment out if too verbose)
    log "OK: Bot is healthy. Heartbeat age: ${AGE}s"
fi
