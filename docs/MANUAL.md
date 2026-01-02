# SPS Daily - Complete Setup & Operations Manual

**Last Updated:** January 2026  
**For:** Non-technical users who want to run SPS Daily

---

## Table of Contents

1. [What is SPS Daily?](#what-is-sps-daily)
2. [System Requirements](#system-requirements)
3. [Directory Structure](#directory-structure)
4. [How It Works](#how-it-works)
5. [Running the Collector Manually](#running-the-collector-manually)
6. [Setting Up Automatic Updates](#setting-up-automatic-updates)
7. [Configuration Options](#configuration-options)
8. [Adding New RSS Feeds](#adding-new-rss-feeds)
9. [Troubleshooting](#troubleshooting)
10. [Checking Logs](#checking-logs)
11. [Common Tasks](#common-tasks)

---

## What is SPS Daily?

SPS Daily is a curated news digest website that automatically:
1. **Collects articles** from 70+ RSS feeds (science, philosophy, society, books)
2. **Collects international articles** from 35+ sources in different languages
3. **Translates** non-English articles to English using AI (Ollama)
4. **Filters** out low-quality content using AI
5. **Publishes** to your website via GitHub Pages

The website is at: https://spsdaily.thebeakers.com

---

## System Requirements

Your server needs:
- **Linux** (Ubuntu/Debian recommended)
- **Python 3.8+** with pip
- **Git** (for pushing to GitHub)
- **Ollama** (for AI filtering and translation)
- **Internet connection**

### Check if everything is installed:

```bash
# Check Python
python3 --version

# Check Git
git --version

# Check Ollama
ollama --version

# Check required Python packages
pip3 show feedparser
```

---

## Directory Structure

```
/storage/spsdaily/
├── index.html              # Main website page
├── science.html            # Science category page
├── philosophy.html         # Philosophy category page
├── society.html            # Society category page
├── books.html              # Books category page
├── world.html              # World (international) category page
├── about.html              # About page
├── privacy.html            # Privacy policy
├── terms.html              # Terms of use
├── articles.json           # THE DATA FILE - all articles go here
├── scripts/
│   ├── feed_collector.py   # Main collector script
│   ├── requirements.txt    # Python dependencies
│   ├── run_collector.sh    # Runner script for automation
│   ├── spsdaily-collector.service  # Systemd service file
│   └── spsdaily-collector.timer    # Systemd timer file
├── logs/
│   └── collector.log       # Log file for debugging
└── docs/
    └── MANUAL.md           # This file
```

---

## How It Works

### Step-by-Step Process:

1. **RSS Collection**
   - The script reads RSS feeds from ~100 sources
   - It downloads recent articles (last 7 days)
   - It removes duplicates

2. **Political Filtering (Books only)**
   - For the "books" category, it filters out political content
   - Uses keyword matching (e.g., "Trump", "Biden", "election")

3. **AI Quality Filtering**
   - Each article is evaluated by Ollama AI
   - Removes listicles, quizzes, breaking news, hot takes
   - Keeps substantive essays and long-form pieces

4. **World Collection & Translation**
   - Collects from international sources
   - Translates headlines and teasers to English
   - Uses Ollama for high-quality translation

5. **JSON Generation**
   - Creates `articles.json` with all selected articles
   - Selects 15 per category (6 shown on front page)

6. **Git Push**
   - Commits changes to GitHub
   - GitHub Pages automatically updates the website

---

## Running the Collector Manually

### Simple Run:

```bash
cd /storage/spsdaily
python3 scripts/feed_collector.py
```

### What you'll see:

```
🗞️  SPS Daily Feed Collector
========================================

📚 Collecting science...
  → Scientific American
    Added 10
  → New Scientist
    Added 8
  ...

🤖 AI filtering articles...
  science: evaluating 124 articles...
    ✓ 102 approved, ✗ 22 rejected
  ...

🌍 Collecting WORLD feeds...
  → Der Spiegel (Germany)
    Translating: ...
    Added 5 articles
  ...

✅ Generated /storage/spsdaily/articles.json
   Science: 15 articles
   Philosophy: 15 articles
   Society: 15 articles
   Books: 12 articles
   World: 15 articles
```

### Run and Push to Website:

```bash
cd /storage/spsdaily
./scripts/run_collector.sh
```

This will:
1. Run the collector
2. Commit changes
3. Push to GitHub (website updates automatically)

---

## Setting Up Automatic Updates

### Option 1: Systemd Timer (Recommended)

This runs the collector automatically at 6 AM and 6 PM every day.

**Step 1: Copy service files**

```bash
sudo cp /storage/spsdaily/scripts/spsdaily-collector.service /etc/systemd/system/
sudo cp /storage/spsdaily/scripts/spsdaily-collector.timer /etc/systemd/system/
```

**Step 2: Reload systemd**

```bash
sudo systemctl daemon-reload
```

**Step 3: Enable and start the timer**

```bash
sudo systemctl enable spsdaily-collector.timer
sudo systemctl start spsdaily-collector.timer
```

**Step 4: Verify it's running**

```bash
# Check timer status
sudo systemctl status spsdaily-collector.timer

# List all timers
systemctl list-timers

# See next run time
systemctl list-timers | grep spsdaily
```

**Step 5: Test it manually**

```bash
sudo systemctl start spsdaily-collector.service
```

### Option 2: Cron Job (Alternative)

If you prefer cron:

```bash
# Edit crontab
crontab -e

# Add this line (runs at 6 AM and 6 PM):
0 6,18 * * * /storage/spsdaily/scripts/run_collector.sh
```

---

## Configuration Options

Edit `/storage/spsdaily/scripts/feed_collector.py` to change settings:

### At the top of the file:

```python
# Ollama configuration
OLLAMA_MODEL_FILTER = "qwen2.5:0.5b"    # Model for YES/NO filtering
OLLAMA_MODEL_TRANSLATE = "qwen3:latest"  # Model for translation
USE_AI_FILTER = True                     # Set to False to disable AI filtering
USE_WORLD_COLLECTION = True              # Set to False to disable international feeds
```

### To disable AI (runs much faster):

```python
USE_AI_FILTER = False
USE_WORLD_COLLECTION = False
```

### To change number of articles:

Find this line in the `main()` function:

```python
selected = select_articles(all_articles, per_category=15)
```

Change `15` to however many you want per category.

---

## Adding New RSS Feeds

### Adding English Feeds:

Edit `feed_collector.py` and find the `FEEDS` dictionary:

```python
FEEDS = {
    "science": [
        ("Source Name", "https://example.com/feed.rss"),
        # Add your new feed here
    ],
    "philosophy": [...],
    "society": [...],
    "books": [...]
}
```

**Example - Adding a new science source:**

```python
"science": [
    ("Scientific American", "https://www.scientificamerican.com/feed/"),
    ("My New Source", "https://mynewsource.com/rss"),  # <-- Add here
    ...
]
```

### Adding International Feeds:

Find the `WORLD_FEEDS` list:

```python
WORLD_FEEDS = [
    # Format: (name, url, language, country)
    ("Der Spiegel", "https://www.spiegel.de/wissenschaft/index.rss", "German", "Germany"),
    # Add your new feed here
]
```

**Example - Adding a Swedish source:**

```python
("Dagens Nyheter", "https://www.dn.se/rss/", "Swedish", "Sweden"),
```

### Testing your new feed:

```bash
# Test the RSS URL
curl -s "https://example.com/feed.rss" | head -50

# Run collector to see if it works
python3 scripts/feed_collector.py 2>&1 | grep "Your Source Name"
```

---

## Troubleshooting

### Problem: "Ollama not found"

**Solution:** Make sure Ollama is installed and running:

```bash
# Check if Ollama is running
ollama list

# If not, start it
ollama serve &

# Or check the service
sudo systemctl status ollama
```

### Problem: "Permission denied"

**Solution:** Fix file permissions:

```bash
chmod +x /storage/spsdaily/scripts/run_collector.sh
sudo chown -R kiran:kiran /storage/spsdaily
```

### Problem: "Git push failed"

**Solution:** Check GitHub authentication:

```bash
cd /storage/spsdaily
git remote -v          # See remote URL
gh auth status         # Check GitHub CLI auth
git push               # Try manual push
```

### Problem: "No articles found"

**Possible causes:**
1. RSS feed URL changed or broken
2. Network issues
3. Website blocking your requests

**Solution:** Test the feed manually:

```bash
curl -s "https://example.com/feed.rss" | head -20
```

### Problem: "AI filtering too slow"

**Solution:** Disable AI filtering for faster runs:

Edit `feed_collector.py`:
```python
USE_AI_FILTER = False
```

### Problem: "Translations not working"

**Solution:** Check Ollama model:

```bash
# List models
ollama list

# Pull the translation model if missing
ollama pull qwen3:latest

# Test translation
echo "Bonjour le monde" | ollama run qwen3 "Translate to English:"
```

---

## Checking Logs

### View the log file:

```bash
# See last 50 lines
tail -50 /storage/spsdaily/logs/collector.log

# Follow log in real-time
tail -f /storage/spsdaily/logs/collector.log

# Search for errors
grep -i error /storage/spsdaily/logs/collector.log
```

### Check systemd logs:

```bash
# View service logs
sudo journalctl -u spsdaily-collector.service

# View recent entries
sudo journalctl -u spsdaily-collector.service --since "1 hour ago"
```

---

## Common Tasks

### Task: Run collector right now

```bash
cd /storage/spsdaily
./scripts/run_collector.sh
```

### Task: Check when it last ran

```bash
tail -20 /storage/spsdaily/logs/collector.log
```

### Task: See what articles were collected

```bash
# Pretty print the JSON
cat /storage/spsdaily/articles.json | python3 -m json.tool | head -100

# Count articles per category
python3 -c "import json; d=json.load(open('/storage/spsdaily/articles.json')); print({k:len(v) for k,v in d.items() if isinstance(v,list)})"
```

### Task: Temporarily disable automatic updates

```bash
sudo systemctl stop spsdaily-collector.timer
```

### Task: Re-enable automatic updates

```bash
sudo systemctl start spsdaily-collector.timer
```

### Task: Update the website manually

```bash
cd /storage/spsdaily
git add -A
git commit -m "Manual update"
git push
```

### Task: Pull latest code changes

```bash
cd /storage/spsdaily
git pull
```

### Task: Check website status

Visit: https://spsdaily.thebeakers.com

Or check GitHub Pages:
```bash
gh api repos/khatvangi/spsdaily/pages
```

---

## Quick Reference Card

| What you want to do | Command |
|---------------------|---------|
| Run collector now | `./scripts/run_collector.sh` |
| Check logs | `tail -50 /storage/spsdaily/logs/collector.log` |
| Check timer | `systemctl list-timers \| grep spsdaily` |
| Stop automation | `sudo systemctl stop spsdaily-collector.timer` |
| Start automation | `sudo systemctl start spsdaily-collector.timer` |
| Test Ollama | `ollama list` |
| Manual git push | `cd /storage/spsdaily && git add -A && git commit -m "update" && git push` |

---

## Support

If you have issues:
1. Check the logs first
2. Make sure Ollama is running
3. Try running manually to see errors
4. Check your internet connection

---

*This manual was generated for SPS Daily by Claude Code.*
