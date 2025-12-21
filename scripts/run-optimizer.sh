#!/bin/bash
# KTrade Auto-Optimizer Runner
# This script is called by cron to run the Claude Code optimizer

set -e

# Configuration
KTRADE_DIR="/Users/kalvin/code/ktrade"
LOG_DIR="$KTRADE_DIR/logs"
REPORT_DIR="$LOG_DIR/optimization-reports"
PROMPT_FILE="$KTRADE_DIR/scripts/bot-optimize-prompt.md"
TODAY=$(date +%Y-%m-%d)
TIMESTAMP=$(date +%Y-%m-%d_%H-%M-%S)

# Ensure directories exist
mkdir -p "$LOG_DIR"
mkdir -p "$REPORT_DIR"

# Log start
echo "[$TIMESTAMP] Starting KTrade optimization run..." >> "$LOG_DIR/optimizer.log"

# Change to project directory
cd "$KTRADE_DIR"

# Read the prompt file
PROMPT=$(cat "$PROMPT_FILE")

# Run Claude Code with full autonomy
# --dangerously-skip-permissions: Skip all permission prompts
# --print: Output to stdout (for logging)
# -p: Pass the prompt

claude --dangerously-skip-permissions --print -p "$PROMPT" >> "$LOG_DIR/optimizer-$TODAY.log" 2>&1

EXIT_CODE=$?

# Log completion
TIMESTAMP=$(date +%Y-%m-%d_%H-%M-%S)
if [ $EXIT_CODE -eq 0 ]; then
    echo "[$TIMESTAMP] Optimization run completed successfully" >> "$LOG_DIR/optimizer.log"
else
    echo "[$TIMESTAMP] Optimization run failed with exit code $EXIT_CODE" >> "$LOG_DIR/optimizer.log"
    # Send alert on failure
    "$KTRADE_DIR/scripts/send-alert.sh" "Optimizer Failed" "The auto-optimizer failed with exit code $EXIT_CODE. Check logs at $LOG_DIR/optimizer-$TODAY.log"
fi

exit $EXIT_CODE
