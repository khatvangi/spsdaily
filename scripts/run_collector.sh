#!/bin/bash
#
# SPS Daily Feed Collector Runner
# This script runs the feed collector and pushes updates to GitHub
#

# Configuration
SPSDAILY_DIR="/storage/spsdaily"
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

# Run the collector
echo "$(date): Running feed collector..." >> "$LOG_FILE"
python3 scripts/feed_collector.py >> "$LOG_FILE" 2>&1
COLLECTOR_STATUS=$?

if [ $COLLECTOR_STATUS -ne 0 ]; then
    echo "$(date): ERROR - Collector failed with status $COLLECTOR_STATUS" >> "$LOG_FILE"
    exit 1
fi

# Check if articles.json changed
if git diff --quiet articles.json; then
    echo "$(date): No changes to articles.json" >> "$LOG_FILE"
else
    echo "$(date): Changes detected, committing..." >> "$LOG_FILE"
    
    # Commit and push
    git add articles.json
    git commit -m "📰 Update articles $(date +'%Y-%m-%d %H:%M')" >> "$LOG_FILE" 2>&1
    git push >> "$LOG_FILE" 2>&1
    
    if [ $? -eq 0 ]; then
        echo "$(date): Successfully pushed updates to GitHub" >> "$LOG_FILE"
    else
        echo "$(date): ERROR - Failed to push to GitHub" >> "$LOG_FILE"
        exit 1
    fi
fi

echo "$(date): Collector finished successfully" >> "$LOG_FILE"
