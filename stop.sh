#!/bin/bash
echo "Stopping ktrade bot..."
pkill -f "run_bot.py"
sleep 1

if pgrep -f "run_bot.py" > /dev/null; then
    echo "Bot still running, force killing..."
    pkill -9 -f "run_bot.py"
fi

echo "Bot stopped."
