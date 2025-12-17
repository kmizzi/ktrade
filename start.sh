#!/bin/bash
cd "$(dirname "$0")"
source venv/bin/activate

# Start bot in background
python scripts/run_bot.py &
BOT_PID=$!

echo "Bot started (PID: $BOT_PID)"
echo "Tailing logs/ktrade.log (Ctrl+C to stop tailing, bot keeps running)"
echo "---"

sleep 2
tail -f logs/ktrade.log
