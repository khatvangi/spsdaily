# SPS Daily

Curated digest of the best writing on science, philosophy, and society. Inspired by Arts & Letters Daily.

**Live site:** https://spsdaily.thebeakers.com

## Architecture

```
/storage/spsdaily/
├── index.html              # Main page (5 columns: Science, Philosophy, Society, Books, Essays)
├── articles.json           # Live articles (this week only)
├── archive.json            # All approved articles (permanent)
├── config/
│   ├── feeds.txt           # RSS sources (plain text, easy to edit)
│   ├── blocklist.txt       # Blocked domains
│   ├── spsdaily_quality.json      # Word count thresholds
│   └── spsdaily_source_weights.json  # Source reputation
├── scripts/
│   ├── feed_collector.py       # Quality-gated collector
│   ├── telegram_curator.py     # Telegram bot
│   └── weekly_cleanup.sh       # Cron job for 7-day rotation
├── pending_articles.json   # Articles awaiting review
└── data/articles.db        # SQLite (seen articles, archive)
```

## Workflow

1. **Collector** fetches RSS, applies quality gates (word count, reputation, clickbait filter)
2. **Telegram bot** sends filtered articles for review
3. **Curator** taps buttons:
   - ✅ Approve → article goes live immediately
   - ❌ Reject → article removed
   - ⭐ Editor's Pick → sets featured article
4. **Weekly cleanup** removes articles older than 7 days (keeps in archive)

## Quality Gates

- **Word count:** 600-1000 minimum by category (the real filter)
- **Source reputation:** Aeon +3, Phys.org -1, etc.
- **Blocklist:** psychologytoday.com, wired.com, medium.com, etc.
- **Clickbait patterns:** "10 ways to...", "you won't believe", etc.

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
```

## Telegram Bot

- **Bot:** @Spsdaily_curator_bot
- **Token:** 7834236484:AAEoCiumnN_93-y6LwFIMLuq3zRgOUwW_BY
- **Chat ID:** 5314021805

### Bot Commands
- `/review` - Send articles for review
- `/status` - Show live article counts
- `/cleanup` - Remove articles older than 7 days
- `/help` - Show help

## Editing Feeds

Plain text files - just edit directly:

**config/feeds.txt** - Add/remove sources:
```
[science]
Quanta Magazine | https://api.quantamagazine.org/feed/
```

**config/blocklist.txt** - Block domains:
```
psychologytoday.com
wired.com
```

## RSS Sources

- **Science:** 14 sources (Quanta, Nautilus, Nature, Science, C&EN, etc.)
- **Philosophy:** 16 sources (Aeon, NDPR, Daily Nous, Hedgehog Review, etc.)
- **Society:** 20 sources (Noema, Atlantic, New Yorker, Foreign Affairs, etc.)
- **Books:** 11 sources (NYRB, LRB, TLS, LA Review of Books, etc.)
- **Essays:** 12 sources (Granta, Paris Review, Guernica, etc.)

## Cron Jobs

```bash
# Weekly cleanup (Sunday 6 AM)
0 6 * * 0 /storage/spsdaily/scripts/weekly_cleanup.sh

# Check crontab
crontab -l | grep spsdaily
```

## See Also

- `LESSONS_LEARNED.md` - Design decisions and insights
