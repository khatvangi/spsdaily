# SPS Daily v2 - Lessons Learned & Insights

## The Problem

v1 collector was too loose - accepting everything from 100+ feeds, resulting in:
- Low-quality clickbait reaching the curation queue
- Psychology Today, Wired, and other noisy sources polluting the feed
- No distinction between 300-word news briefs and 3000-word essays
- Curator fatigue from rejecting garbage

## The Solution: Quality Gates Based on FORM, Not CONTENT

### Key Insight: Filter by Depth, Not Topic

**Wrong approach:** Keyword blocking ("trump", "election", "politics")
- Misses the point entirely
- A rigorous 2000-word Foreign Affairs analysis of any topic is worth reading
- A 300-word hot take isn't, regardless of topic

**Right approach:** Structural quality signals
1. **Word count** - The real filter. Long-form = serious effort
2. **Source reputation** - Aeon, Quanta, NYRB have editorial standards
3. **Clickbait patterns** - "10 ways to...", "you won't believe" = low effort
4. **Domain blocklist** - Content farms (Medium, Substack, BuzzFeed)

### Word Count Thresholds (Calibrated by Category)

| Category | Minimum Words | Rationale |
|----------|---------------|-----------|
| Science | 600 | Research summaries can be shorter |
| Philosophy | 800 | Ideas need space to develop |
| Society | 700 | Analysis requires context |
| Books | 600 | Reviews vary in length |
| Essays | 1000 | Long-form by definition |

### Source Reputation Weights

```
+3 (Top tier): Aeon, Quanta, NYRB, LRB, Noema, Granta, Paris Review
+2 (Excellent): Nautilus, Hedgehog Review, Boston Review, Foreign Affairs
+1 (Good): Atlantic, New Yorker, Nature, Science, Harper's
 0 (Neutral): Most sources
-1 (Noisy): Phys.org, ScienceDaily (need higher word count to pass)
```

## Architecture

```
config/
├── feeds.txt          # Plain text - easy to edit
├── blocklist.txt      # Plain text - domains to reject
├── spsdaily_quality.json    # Word counts, patterns
└── spsdaily_source_weights.json  # Reputation scores

scripts/
├── feed_collector_v2.py     # Quality-gated collector
├── telegram_curator_v2.py   # Bot with /review, /status, /cleanup
└── weekly_cleanup.sh        # Cron job for 7-day rotation
```

## Collector Pipeline

```
Phase 1: Collect from RSS feeds
    ↓ Filter: blocked domains
    ↓ Filter: clickbait patterns
    ↓ Filter: older than 7 days
    ↓ Filter: already seen (SQLite)

Phase 2: Stage by reputation
    ↓ Sort by base_score (domain + source weight)
    ↓ Take top N × overfetch_factor

Phase 3: Word count gate (THE REAL FILTER)
    ↓ Fetch actual page, count words
    ↓ Reject if below category minimum
    ↓ Check archive.org for archived version
    ↓ Compute final_score = base + log10(word_count)

Output: pending_articles.json (sorted by quality)
```

## Telegram Bot Commands

| Command | Action |
|---------|--------|
| `/review` | Send pending articles for curation |
| `/status` | Show live article counts |
| `/cleanup` | Remove articles older than 7 days |
| `/help` | Show commands |

## Duplicate Prevention

- Checks URL across ALL categories before approving
- Returns "DUPLICATE - already live" if pressed twice
- Works for both Approve and Editor's Pick actions

## Weekly Rotation

- **Automatic:** Cron runs Sunday 6 AM
- **Manual:** `/cleanup` command
- Articles older than 7 days removed from front page
- Archive keeps everything forever

## Config Files (Plain Text for Easy Editing)

### feeds.txt
```
[science]
Quanta Magazine | https://api.quantamagazine.org/feed/
Knowable Magazine | https://knowablemagazine.org/rss
# comment out or delete to remove
```

### blocklist.txt
```
# one domain per line
psychologytoday.com
wired.com
medium.com
```

## Key Commands

```bash
# Run collector manually
/home/kiran/miniconda3/bin/python3 scripts/feed_collector_v2.py

# Start curator bot
nohup /home/kiran/miniconda3/bin/python3 scripts/telegram_curator_v2.py > logs/curator_v2.log 2>&1 &

# Send articles to Telegram
/home/kiran/miniconda3/bin/python3 scripts/telegram_curator_v2.py send

# Check bot status
ps aux | grep telegram_curator_v2
```

## Telegram Bot

- **Bot:** @Spsdaily_curator_bot
- **Token:** 7834236484:AAEoCiumnN_93-y6LwFIMLuq3zRgOUwW_BY
- **Chat ID:** 5314021805

## What We Learned

1. **Quality = Depth** - Word count is the best single proxy for article quality
2. **Reputation matters** - Trust Aeon more than Psychology Today
3. **Form over content** - Block clickbait structure, not topics
4. **Plain text configs** - JSON is annoying to edit; `Name | URL` is not
5. **Archive everything** - Front page rotates; archive is permanent
6. **Duplicate checks must be global** - Check all categories, not just current

## Future Improvements

- [ ] Add more essay sources (literary magazines)
- [ ] Tune word count thresholds based on rejection rate
- [ ] Add reading time to website display
- [ ] Consider AI summarization for teasers
- [ ] Track curator decisions to learn preferences
