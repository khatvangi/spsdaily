#!/bin/bash
#
# SPS Daily Feed Collector Runner
# This script runs the feed collector and pushes updates to GitHub
#

# Configuration
SPSDAILY_DIR="/storage/spsdaily"
PYTHON="/home/kiran/miniconda3/bin/python3"
LOG_FILE="/storage/spsdaily/logs/collector.log"
LOCK_FILE="/tmp/spsdaily_collector.lock"

# Create logs directory if needed
mkdir -p "$(dirname "$LOG_FILE")"

# Prevent multiple instances
if [ -f "$LOCK_FILE" ]; then
    echo "$(date): Collector already running. Exiting." >> "$LOG_FILE"
    exit 1
fi
trap "rm -f $LOCK_FILE" EXIT
touch "$LOCK_FILE"

# Log start
echo "" >> "$LOG_FILE"
echo "========================================" >> "$LOG_FILE"
echo "$(date): Starting SPS Daily Feed Collector" >> "$LOG_FILE"
echo "========================================" >> "$LOG_FILE"

# Change to project directory
cd "$SPSDAILY_DIR" || exit 1

# Pull latest changes (in case of manual edits)
echo "$(date): Pulling latest changes..." >> "$LOG_FILE"
git pull >> "$LOG_FILE" 2>&1

# Run the v2 collector (quality-gated)
echo "$(date): Running feed collector v2..." >> "$LOG_FILE"
$PYTHON scripts/feed_collector_v2.py >> "$LOG_FILE" 2>&1
COLLECTOR_STATUS=$?

if [ $COLLECTOR_STATUS -ne 0 ]; then
    echo "$(date): ERROR - Collector failed with status $COLLECTOR_STATUS" >> "$LOG_FILE"
    exit 1
fi

# Send articles to Telegram for curation
echo "$(date): Sending articles to Telegram..." >> "$LOG_FILE"
$PYTHON scripts/telegram_curator_v2.py send >> "$LOG_FILE" 2>&1

echo "$(date): Collector finished - check Telegram for articles" >> "$LOG_FILE"
