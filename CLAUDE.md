# SPS Daily

Curated digest of the best writing on science, philosophy, and society. Inspired by Arts & Letters Daily.

**Live site:** https://spsdaily.thebeakers.com

## Architecture

```
/storage/spsdaily/
├── index.html              # Main page (4 columns: Science, Philosophy, Society, Books)
├── articles.json           # Live articles data
├── scripts/
│   ├── feed_collector.py   # Fetches from 100+ RSS feeds
│   ├── telegram_curator.py # Telegram bot for curation
│   ├── run_collector.sh    # Runner script for systemd
│   └── spsdaily-collector.timer  # Runs at 6 AM & 6 PM
├── pending_articles.json   # Articles awaiting review
├── approved_articles.json  # Approved articles buffer
└── docs/MANUAL.md          # Operations manual
```

## Workflow

1. **Collector** runs twice daily (6 AM, 6 PM) via systemd timer
2. **Telegram bot** (@spsdaily_ghatoth_bot) sends articles for review
3. **Curator** taps buttons:
   - ✅ Approve → article goes live immediately
   - ❌ Reject → article removed
   - ⭐ Editor's Pick → sets featured article
4. **Git push** deploys changes to GitHub Pages

## Key Commands

```bash
# Run collector manually
/home/kiran/miniconda3/bin/python3 scripts/feed_collector.py

# Start Telegram curator bot
nohup /home/kiran/miniconda3/bin/python3 scripts/telegram_curator.py > logs/curator.log 2>&1 &

# Send articles for review
/home/kiran/miniconda3/bin/python3 scripts/telegram_curator.py send

# Check bot status
ps aux | grep telegram_curator

# Push updates to website
git add articles.json && git commit -m "Update" && git push
```

## Telegram Bot

- **Bot:** @spsdaily_ghatoth_bot
- **Token:** 8516392118:AAEIybKb68Gfl0kTpzKkbCKtUl1OtRqMwtY
- **Chat ID:** 5314021805

### Bot Commands
- `/review` - Send all articles for review
- `/status` - Show approved counts
- `/publish` - Publish approved (batch mode)
- `/help` - Show help

## Configuration

In `scripts/feed_collector.py`:
```python
USE_AI_FILTER = False  # AI filtering disabled (manual curation)
socket.setdefaulttimeout(15)  # 15-second timeout for slow feeds
```

## RSS Sources

- **Science:** 13 sources (Scientific American, Nautilus, Wired, etc.)
- **Philosophy:** 19 sources (Aeon, 3 Quarks Daily, First Things, etc.)
- **Society:** 50 sources (Atlantic, New Yorker, Foreign Affairs, etc.)
- **Books:** 23 sources (NYRB, LRB, TLS, Guardian Books, etc.)

## Systemd Timer

```bash
# Check timer status
systemctl list-timers | grep spsdaily

# View logs
sudo journalctl -u spsdaily-collector.service

# Restart timer
sudo systemctl restart spsdaily-collector.timer
```

## Newsletter

- **Platform:** Listmonk (self-hosted)
- **URL:** https://newsletter.thebeakers.com
- **List ID:** a5887db5-f279-42b5-aea6-0b3f660854dd
