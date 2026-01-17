#!/bin/bash
#
# SPS Daily Auto-Approve
# Runs 1 hour after collector - approves top articles if no manual curation
#

SPSDAILY_DIR="/storage/spsdaily"
PYTHON="/home/kiran/miniconda3/bin/python3"
LOG_FILE="/storage/spsdaily/logs/collector.log"

cd "$SPSDAILY_DIR" || exit 1

echo "" >> "$LOG_FILE"
echo "$(date): Running auto-approve check..." >> "$LOG_FILE"
$PYTHON scripts/telegram_curator.py auto >> "$LOG_FILE" 2>&1
