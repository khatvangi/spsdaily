#!/bin/bash
# Weekly cleanup - removes articles older than 7 days from front page
# Add to crontab: 0 6 * * 0 /storage/spsdaily/scripts/weekly_cleanup.sh

cd /storage/spsdaily

# run cleanup via python
/home/kiran/miniconda3/bin/python3 -c "
import json
from datetime import date, timedelta
from pathlib import Path

ARTICLES_FILE = Path('articles.json')
CATEGORIES = ['science', 'philosophy', 'society', 'books', 'essays']

if ARTICLES_FILE.exists():
    cutoff = (date.today() - timedelta(days=7)).isoformat()
    live = json.load(open(ARTICLES_FILE))
    removed = 0

    for cat in CATEGORIES:
        if cat not in live:
            continue
        before = len(live[cat])
        live[cat] = [a for a in live[cat] if not a.get('approvedDate') or a.get('approvedDate') >= cutoff]
        removed += before - len(live[cat])

    if removed > 0:
        with open(ARTICLES_FILE, 'w') as f:
            json.dump(live, f, indent=2)
        print(f'Cleaned {removed} old articles')
    else:
        print('No old articles to clean')
"

# push if changes
if git diff --quiet articles.json; then
    echo "No changes to push"
else
    git add articles.json
    git commit -m "Weekly cleanup"
    git push
fi
