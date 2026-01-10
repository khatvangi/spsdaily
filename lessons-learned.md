# SPS Daily - Lessons Learned

## Do NOT Rewrite Scripts

**Rule**: Fix the specific problem, don't rewrite the whole file.

When something breaks:
1. Find the root cause (read logs, check data)
2. Fix only what's broken
3. Test the fix
4. Done

Rewriting scripts introduces new bugs and wastes time.

---

## Common Issues & Fixes

### 1. Telegram Bot Conflict Error

**Symptom:**
```
Error: {'ok': False, 'error_code': 409, 'description': 'Conflict: terminated by other getUpdates request'}
```

**Cause:** Multiple bot instances polling simultaneously (only one allowed per token)

**Fix:**
```bash
# stop everything
sudo systemctl stop spsdaily-curator
pkill -9 -f telegram_curator.py

# clear telegram queue
curl -s "https://api.telegram.org/bot8516392118:AAEIybKb68Gfl0kTpzKkbCKtUl1OtRqMwtY/getUpdates?offset=-1"

# start fresh (single instance)
sudo systemctl start spsdaily-curator
```

**Prevention:** Never run `python3 telegram_curator.py` manually while service is running.

---

### 2. Editor's Pick Not Changing

**Symptom:** Same article stays as Editor's Pick for days

**Cause:** Bot wasn't processing button callbacks (due to conflict error above)

**Fix:** Fix the bot conflict, then tap ⭐ on new article

---

### 3. Articles Not Appearing on Website

**Symptom:** Approved articles don't show up

**Check:**
```bash
# is articles.json valid?
cat articles.json | python3 -m json.tool > /dev/null && echo "valid" || echo "broken"

# was it pushed?
git status

# push if needed
git add articles.json && git commit -m "Update" && git push
```

---

### 4. Collector Not Running

**Symptom:** No new articles in Telegram

**Check:**
```bash
# timer status
systemctl list-timers | grep spsdaily

# last run logs
sudo journalctl -u spsdaily-collector -n 50

# run manually
/home/kiran/miniconda3/bin/python3 scripts/feed_collector.py
```

---

### 5. Git Push Rejected

**Symptom:** `! [rejected] main -> main (non-fast-forward)`

**Cause:** Local and remote diverged

**Fix:**
```bash
git pull --rebase
git push
# or if you're sure local is correct:
git push --force
```

---

## Service Commands Cheat Sheet

```bash
# curator bot
sudo systemctl status spsdaily-curator
sudo systemctl restart spsdaily-curator
sudo journalctl -u spsdaily-curator -f  # live logs

# collector timer
systemctl list-timers | grep spsdaily
sudo journalctl -u spsdaily-collector -n 50

# check for rogue processes
ps aux | grep telegram_curator
ps aux | grep feed_collector
```

---

## File Locations

| File | Purpose |
|------|---------|
| `articles.json` | Live articles on website |
| `pending_articles.json` | Articles awaiting review |
| `archive.json` | Historical archive |
| `scripts/feed_collector.py` | RSS collector |
| `scripts/telegram_curator.py` | Telegram bot |
| `logs/collector.log` | Collector output |

---

## Architecture (Don't Break This)

```
6AM/6PM: Timer triggers collector
    ↓
Collector fetches RSS → sends to Telegram
    ↓
You tap ✅/❌/⭐ buttons
    ↓
Curator updates articles.json → git push
    ↓
GitHub Pages serves updated site
```

Each piece works. Don't rewrite them.
