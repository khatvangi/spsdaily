# SPS Daily - Onboarding & Setup Guide

Complete setup instructions so we never repeat this cycle again.

## Overview

SPS Daily is a curated digest of science, philosophy, and society articles. The system:
1. Collects articles from RSS feeds (6 PM daily)
2. Sends to Telegram for manual curation
3. Auto-approves top articles if no curation within 1 hour (7 PM)

---

## Prerequisites

```bash
# python dependencies
pip install requests feedparser beautifulsoup4

# ollama for TLDR generation (optional but recommended)
# install from https://ollama.ai
ollama pull llama3.2:3b
```

---

## Directory Structure

```
/storage/spsdaily/
├── index.html                  # website
├── articles.json               # live articles (displayed on site)
├── pending_articles.json       # articles awaiting review
├── archive.json                # permanent archive
├── config/
│   ├── feeds.txt               # RSS sources (plain text)
│   ├── blocklist.txt           # blocked domains
│   ├── spsdaily_quality.json   # word count thresholds
│   └── spsdaily_source_weights.json  # source reputation scores
├── scripts/
│   ├── feed_collector.py       # fetches and filters RSS
│   ├── telegram_curator.py     # telegram bot + auto-approve
│   ├── auto_approve.sh         # wrapper for systemd
│   ├── run_collector.sh        # main runner script
│   └── weekly_cleanup.sh       # removes old articles
├── data/
│   └── articles.db             # sqlite (seen articles, archive)
└── logs/
    ├── collector.log           # collector output
    └── curator.log             # bot output
```

---

## Telegram Bot Setup

### 1. Create Bot
1. Message @BotFather on Telegram
2. Send `/newbot`
3. Name it (e.g., "SPS Daily Curator")
4. Get the token

### 2. Get Chat ID
1. Message your new bot
2. Visit: `https://api.telegram.org/bot<TOKEN>/getUpdates`
3. Find your chat ID in the response

### 3. Update Scripts
Edit `scripts/telegram_curator.py`:
```python
BOT_TOKEN = "your-token-here"
CHAT_ID = "your-chat-id-here"
```

Or use environment variables:
```bash
export SPSDAILY_BOT_TOKEN="your-token"
export SPSDAILY_CHAT_ID="your-chat-id"
```

---

## Systemd Services Setup

### Collector Service (runs the feed collector)

```bash
sudo tee /etc/systemd/system/spsdaily-collector.service << 'EOF'
[Unit]
Description=SPS Daily Feed Collector
After=network.target

[Service]
Type=oneshot
User=kiran
WorkingDirectory=/storage/spsdaily
ExecStart=/storage/spsdaily/scripts/run_collector.sh
EOF
```

### Collector Timer (6 PM daily)

```bash
sudo tee /etc/systemd/system/spsdaily-collector.timer << 'EOF'
[Unit]
Description=Run SPS Daily Feed Collector once daily

[Timer]
OnCalendar=*-*-* 18:00:00
Persistent=true
RandomizedDelaySec=300

[Install]
WantedBy=timers.target
EOF
```

### Auto-Approve Service (fallback if no manual curation)

```bash
sudo tee /etc/systemd/system/spsdaily-autoapprove.service << 'EOF'
[Unit]
Description=SPS Daily Auto-Approve (fallback if no manual curation)

[Service]
Type=oneshot
User=kiran
WorkingDirectory=/storage/spsdaily
ExecStart=/storage/spsdaily/scripts/auto_approve.sh
EOF
```

### Auto-Approve Timer (7 PM daily, 1 hour after collector)

```bash
sudo tee /etc/systemd/system/spsdaily-autoapprove.timer << 'EOF'
[Unit]
Description=Run SPS Daily Auto-Approve 1 hour after collector

[Timer]
OnCalendar=*-*-* 19:00:00
Persistent=true

[Install]
WantedBy=timers.target
EOF
```

### Enable All Timers

```bash
sudo systemctl daemon-reload
sudo systemctl enable spsdaily-collector.timer
sudo systemctl enable spsdaily-autoapprove.timer
sudo systemctl start spsdaily-collector.timer
sudo systemctl start spsdaily-autoapprove.timer

# verify
systemctl list-timers | grep spsdaily
```

---

## Cron Job for Weekly Cleanup

```bash
# add to crontab
crontab -e

# add this line (Sunday 6 AM)
0 6 * * 0 /storage/spsdaily/scripts/weekly_cleanup.sh
```

---

## Start Telegram Bot (for button presses)

The bot needs to run continuously to receive button presses:

```bash
# start bot
nohup /home/kiran/miniconda3/bin/python3 /storage/spsdaily/scripts/telegram_curator.py > /storage/spsdaily/logs/curator.log 2>&1 &

# check if running
ps aux | grep telegram_curator | grep -v grep

# check logs
tail -f /storage/spsdaily/logs/curator.log
```

### Auto-start Bot on Reboot (optional)

```bash
sudo tee /etc/systemd/system/spsdaily-bot.service << 'EOF'
[Unit]
Description=SPS Daily Telegram Bot
After=network.target

[Service]
Type=simple
User=kiran
WorkingDirectory=/storage/spsdaily
ExecStart=/home/kiran/miniconda3/bin/python3 /storage/spsdaily/scripts/telegram_curator.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable spsdaily-bot.service
sudo systemctl start spsdaily-bot.service
```

---

## Manual Commands

```bash
# run collector manually
/home/kiran/miniconda3/bin/python3 scripts/feed_collector.py

# send articles to telegram
/home/kiran/miniconda3/bin/python3 scripts/telegram_curator.py send

# auto-approve (select top articles)
/home/kiran/miniconda3/bin/python3 scripts/telegram_curator.py auto

# check status
/home/kiran/miniconda3/bin/python3 scripts/telegram_curator.py status

# start bot for button presses
/home/kiran/miniconda3/bin/python3 scripts/telegram_curator.py

# weekly cleanup
/storage/spsdaily/scripts/weekly_cleanup.sh
```

---

## Telegram Bot Commands

From Telegram, send these to the bot:
- `/review` - send articles for review
- `/status` - show live article counts
- `/cleanup` - remove articles older than 7 days
- `/help` - show help

---

## Editing Configuration

### Add/Remove RSS Sources
Edit `config/feeds.txt`:
```
[science]
Quanta Magazine | https://api.quantamagazine.org/feed/
New Source | https://example.com/feed/

[philosophy]
Aeon | https://aeon.co/feed.rss
```

### Block Domains
Edit `config/blocklist.txt`:
```
psychologytoday.com
wired.com
medium.com
```

### Adjust Quality Thresholds
Edit `config/spsdaily_quality.json`:
```json
{
  "min_words": {
    "science": 600,
    "philosophy": 800,
    "society": 700,
    "books": 600,
    "essays": 1000
  }
}
```

### Adjust Source Reputation
Edit `config/spsdaily_source_weights.json`:
```json
{
  "aeon.co": 3,
  "quantamagazine.org": 3,
  "nautil.us": 2,
  "phys.org": -1
}
```

---

## Troubleshooting

### Bot not responding to buttons
```bash
# check if bot is running
ps aux | grep telegram_curator | grep -v grep

# if not running, start it
nohup /home/kiran/miniconda3/bin/python3 scripts/telegram_curator.py > logs/curator.log 2>&1 &
```

### Multiple bot instances
```bash
# kill all and restart
pkill -f telegram_curator
nohup /home/kiran/miniconda3/bin/python3 scripts/telegram_curator.py > logs/curator.log 2>&1 &
```

### Check timer status
```bash
systemctl list-timers | grep spsdaily
journalctl -u spsdaily-collector.service -n 50
journalctl -u spsdaily-autoapprove.service -n 50
```

### Reset seen articles (get fresh articles)
```bash
sqlite3 data/articles.db "DELETE FROM seen_articles;"
```

### Check logs
```bash
tail -100 logs/collector.log
tail -100 logs/curator.log
```

---

## Key Design Decisions

1. **Quality by FORM not CONTENT** - filter by word count, source reputation, not keywords
2. **Single instance lock** - `fcntl.flock` prevents multiple bot instances
3. **No versioned file names** - `feed_collector.py` not `feed_collector_v2.py`
4. **Plain text config** - easy to edit feeds.txt and blocklist.txt
5. **Auto-approve fallback** - site always has fresh content even without curation
6. **TLDR via local AI** - Ollama llama3.2:3b, slow but free and private

---

## Current Bot Credentials

```
Bot: @Spsdaily_curator_bot
Token: 7834236484:AAEoCiumnN_93-y6LwFIMLuq3zRgOUwW_BY
Chat ID: 5314021805
```

---

## Daily Schedule

| Time | Action |
|------|--------|
| 6 PM | Collector fetches RSS, sends to Telegram |
| 6-7 PM | Manual curation window (approve/reject/pick) |
| 7 PM | Auto-approve if no manual curation |
| Sunday 6 AM | Weekly cleanup (remove articles > 7 days) |
