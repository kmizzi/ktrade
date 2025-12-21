#!/bin/bash
# Send Slack alert for KTrade bot
# Usage: ./send-alert.sh "Subject" "Body"

# Load from .env if SLACK_WEBHOOK_URL not set
if [ -z "$SLACK_WEBHOOK_URL" ]; then
    SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    ENV_FILE="$SCRIPT_DIR/../.env"
    if [ -f "$ENV_FILE" ]; then
        export $(grep -v '^#' "$ENV_FILE" | grep SLACK_WEBHOOK_URL | xargs)
    fi
fi

SLACK_WEBHOOK="${SLACK_WEBHOOK_URL:-}"
SUBJECT="$1"
BODY="$2"

if [ -z "$SLACK_WEBHOOK" ]; then
    echo "Error: SLACK_WEBHOOK_URL not set"
    exit 1
fi

# Format timestamp
TIMESTAMP=$(date "+%Y-%m-%d %H:%M:%S")

# Create Slack message payload
# Using blocks for better formatting
PAYLOAD=$(cat <<EOF
{
  "blocks": [
    {
      "type": "header",
      "text": {
        "type": "plain_text",
        "text": "🤖 KTrade Alert: $SUBJECT",
        "emoji": true
      }
    },
    {
      "type": "section",
      "text": {
        "type": "mrkdwn",
        "text": "$BODY"
      }
    },
    {
      "type": "context",
      "elements": [
        {
          "type": "mrkdwn",
          "text": "📅 $TIMESTAMP | 🖥️ $(hostname)"
        }
      ]
    }
  ]
}
EOF
)

# Send to Slack
RESPONSE=$(curl -s -X POST -H 'Content-type: application/json' --data "$PAYLOAD" "$SLACK_WEBHOOK")

if [ "$RESPONSE" = "ok" ]; then
    echo "Alert sent to Slack successfully"
    exit 0
else
    echo "Failed to send Slack alert: $RESPONSE"
    # Fallback: log to file
    echo "[$TIMESTAMP] ALERT: $SUBJECT - $BODY" >> /Users/kalvin/code/ktrade/logs/alerts.log
    exit 1
fi
