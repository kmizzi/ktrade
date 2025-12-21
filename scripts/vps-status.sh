#!/bin/bash
# Check KTrade status on VPS (run from local machine)

VPS_HOST="karb"
REMOTE_DIR="/root/code/ktrade"

echo "=== KTrade VPS Status ==="
echo ""

echo "Bot process:"
ssh $VPS_HOST "ps aux | grep run_bot.py | grep -v grep || echo '  (not running)'"
echo ""

echo "Cron schedule:"
ssh $VPS_HOST "crontab -l 2>/dev/null | grep KTRADE || echo '  (no schedule)'"
echo ""

echo "Recent log:"
ssh $VPS_HOST "tail -5 $REMOTE_DIR/logs/bot.log 2>/dev/null || echo '  (no log)'"
