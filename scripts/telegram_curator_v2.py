#!/usr/bin/env python3
"""
SPS Daily Telegram Curator v2
- Supports 5 categories: science, philosophy, society, books, essays
- Displays word count and quality score in review messages
- Immediate publish on approve (no batch mode)
"""

import json
import requests
import time
import sqlite3
import html
import os
from pathlib import Path
from datetime import date, timedelta

# telegram config (env vars with fallback)
BOT_TOKEN = os.getenv("SPSDAILY_BOT_TOKEN", "7834236484:AAEoCiumnN_93-y6LwFIMLuq3zRgOUwW_BY").strip()
CHAT_ID = os.getenv("SPSDAILY_CHAT_ID", "5314021805").strip()
API_URL = f"https://api.telegram.org/bot{BOT_TOKEN}"

# all categories (v2 adds essays)
CATEGORIES = ["science", "philosophy", "society", "books", "essays"]

# paths
SPSDAILY_DIR = Path("/storage/spsdaily")
ARTICLES_FILE = SPSDAILY_DIR / "articles.json"
PENDING_FILE = SPSDAILY_DIR / "pending_articles.json"
APPROVED_FILE = SPSDAILY_DIR / "approved_articles.json"
ARCHIVE_FILE = SPSDAILY_DIR / "archive.json"
DB_PATH = SPSDAILY_DIR / "data" / "articles.db"


def add_to_archive(article, category):
    """add approved article to archive database"""
    conn = sqlite3.connect(DB_PATH)
    conn.execute('''
        CREATE TABLE IF NOT EXISTS archive (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            url TEXT UNIQUE,
            headline TEXT,
            teaser TEXT,
            source TEXT,
            category TEXT,
            word_count INTEGER,
            approved_date DATE DEFAULT CURRENT_DATE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.execute('''
        INSERT OR REPLACE INTO archive (url, headline, teaser, source, category, word_count, approved_date)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', (
        article['url'],
        article['headline'],
        article.get('teaser', ''),
        article.get('source', ''),
        category,
        article.get('word_count', 0),
        date.today().isoformat()
    ))
    conn.commit()
    conn.close()


def generate_archive_json():
    """generate archive.json grouped by date"""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.execute('''
        SELECT approved_date, category, headline, teaser, source, url
        FROM archive
        ORDER BY approved_date DESC, category, id DESC
    ''')

    archive = {}
    for row in cur.fetchall():
        date_str = row[0]
        if date_str not in archive:
            archive[date_str] = {cat: [] for cat in CATEGORIES}

        category = row[1]
        if category in archive[date_str]:
            archive[date_str][category].append({
                "headline": row[2],
                "teaser": row[3],
                "source": row[4],
                "url": row[5]
            })

    with open(ARCHIVE_FILE, 'w') as f:
        json.dump(archive, f, indent=2)

    conn.close()
    return archive


def cleanup_old_articles():
    """remove articles older than 7 days from live site (they stay in archive)"""
    if not ARTICLES_FILE.exists():
        return 0

    cutoff = (date.today() - timedelta(days=7)).isoformat()
    live_articles = json.load(open(ARTICLES_FILE))
    removed = 0

    for category in CATEGORIES:
        if category not in live_articles:
            continue
        original_count = len(live_articles[category])
        live_articles[category] = [
            a for a in live_articles[category]
            if not a.get('approvedDate') or a.get('approvedDate') >= cutoff
        ]
        removed += original_count - len(live_articles[category])

    if removed > 0:
        with open(ARTICLES_FILE, 'w') as f:
            json.dump(live_articles, f, indent=2)

    return removed


def send_message(text, reply_markup=None):
    """send a message to the curator"""
    data = {
        "chat_id": CHAT_ID,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": False
    }
    if reply_markup:
        data["reply_markup"] = json.dumps(reply_markup)

    response = requests.post(f"{API_URL}/sendMessage", data=data, timeout=30)
    return response.json()


def send_article_for_review(article, category, index):
    """send an article with approve/reject buttons, showing quality metrics"""
    headline = html.escape(article.get('headline', ''))
    teaser = html.escape(article.get('teaser', '')[:280])
    source = html.escape(article.get('source', ''))
    url = article.get('url', '')

    # quality metrics from collector v2
    wc = article.get('word_count', 0)
    rmin = article.get('reading_min', 0)
    score = article.get('score', 0)

    # format metrics line
    metrics = []
    if wc:
        metrics.append(f"{wc} words")
    if rmin:
        metrics.append(f"~{rmin} min")
    if score:
        metrics.append(f"score: {score}")
    metrics_line = f"<i>{' | '.join(metrics)}</i>\n" if metrics else ""

    # archive link if available
    archive_url = article.get('archiveUrl')
    links = f'<a href="{url}">Original</a>'
    if archive_url:
        links += f' | <a href="{archive_url}">Archive</a>'

    text = f"""<b>{category.upper()}</b>
{metrics_line}
<b>{headline}</b>

{teaser}

<i>Source: {source}</i>
{links}"""

    keyboard = {
        "inline_keyboard": [
            [
                {"text": "Approve", "callback_data": f"approve:{category}:{index}"},
                {"text": "Reject", "callback_data": f"reject:{category}:{index}"},
            ],
            [
                {"text": "Editor's Pick", "callback_data": f"pick:{category}:{index}"}
            ]
        ]
    }

    return send_message(text, keyboard)


def get_updates(offset=None):
    """get updates from telegram"""
    params = {"timeout": 30}
    if offset:
        params["offset"] = offset
    response = requests.get(f"{API_URL}/getUpdates", params=params, timeout=35)
    return response.json()


def load_pending():
    """load pending articles"""
    if PENDING_FILE.exists():
        return json.load(open(PENDING_FILE))
    return {}


def save_pending(pending):
    """save pending articles"""
    with open(PENDING_FILE, 'w') as f:
        json.dump(pending, f, indent=2)


def load_approved():
    """load approved articles"""
    if APPROVED_FILE.exists():
        return json.load(open(APPROVED_FILE))
    return {"editorsPick": None, **{cat: [] for cat in CATEGORIES}}


def save_approved(approved):
    """save approved articles"""
    with open(APPROVED_FILE, 'w') as f:
        json.dump(approved, f, indent=2)


def git_push():
    """commit and push to github"""
    import subprocess
    try:
        subprocess.run(
            ["git", "add", "articles.json", "archive.json"],
            cwd=SPSDAILY_DIR, check=True, capture_output=True
        )
        subprocess.run(
            ["git", "commit", "-m", "Curator update"],
            cwd=SPSDAILY_DIR, check=True, capture_output=True
        )
        subprocess.run(
            ["git", "push"],
            cwd=SPSDAILY_DIR, check=True, capture_output=True
        )
        return True
    except subprocess.CalledProcessError:
        return False


def send_articles_for_review():
    """send all collected articles for review"""
    if not PENDING_FILE.exists():
        print("No pending_articles.json found")
        send_message("No pending articles. Run feed_collector_v2.py first.")
        return

    articles = json.load(open(PENDING_FILE))
    pending = {}

    # count totals
    totals = {cat: len(articles.get(cat, [])) for cat in CATEGORIES}
    total = sum(totals.values())

    send_message(f"<b>SPS Daily - {total} Articles for Review</b>\n\n"
                 f"Science: {totals['science']} | Philosophy: {totals['philosophy']}\n"
                 f"Society: {totals['society']} | Books: {totals['books']} | Essays: {totals['essays']}\n\n"
                 f"Tap buttons to approve/reject. Approved articles go live immediately.")
    time.sleep(1)

    for category in CATEGORIES:
        category_articles = articles.get(category, [])
        if not category_articles:
            continue

        pending[category] = category_articles
        send_message(f"<b>{category.upper()}</b> ({len(category_articles)} articles)")
        time.sleep(0.5)

        for i, article in enumerate(category_articles):
            send_article_for_review(article, category, i)
            time.sleep(0.3)

    save_pending(pending)
    send_message("All articles sent. Approved articles publish immediately.")


def handle_callback(callback_data, pending, approved):
    """handle button callbacks - immediately updates articles.json"""
    parts = callback_data.split(":")
    action = parts[0]
    category = parts[1]
    index = int(parts[2])

    if category not in pending or index >= len(pending[category]):
        return "Article not found"

    article = pending[category][index]

    # load current live articles
    if ARTICLES_FILE.exists():
        live_articles = json.load(open(ARTICLES_FILE))
    else:
        live_articles = {"lastUpdated": "", "editorsPick": None, **{cat: [] for cat in CATEGORIES}}

    changed = False

    if action == "approve":
        if category not in live_articles:
            live_articles[category] = []

        # check if already there
        existing_urls = {a.get('url') for a in live_articles[category]}
        if article['url'] in existing_urls:
            return "Already live"

        article['approvedDate'] = date.today().isoformat()
        live_articles[category].insert(0, article)

        # auto-set editor's pick if none today
        today = date.today().isoformat()
        if live_articles.get("lastUpdated") != today or not live_articles.get("editorsPick"):
            live_articles["editorsPick"] = article
            live_articles["lastUpdated"] = today
            result = f"LIVE + PICK: {article['headline'][:35]}..."
        else:
            result = f"LIVE: {article['headline'][:40]}..."

        with open(ARTICLES_FILE, 'w') as f:
            json.dump(live_articles, f, indent=2)
        add_to_archive(article, category)
        generate_archive_json()
        changed = True

    elif action == "reject":
        if category in live_articles:
            live_articles[category] = [
                a for a in live_articles[category]
                if a.get('url') != article.get('url')
            ]
            with open(ARTICLES_FILE, 'w') as f:
                json.dump(live_articles, f, indent=2)
            changed = True
        result = f"Removed: {article['headline'][:40]}..."

    elif action == "pick":
        if category not in live_articles:
            live_articles[category] = []

        existing_urls = {a.get('url') for a in live_articles[category]}
        if article['url'] not in existing_urls:
            article['approvedDate'] = date.today().isoformat()
            live_articles[category].insert(0, article)
            add_to_archive(article, category)
            generate_archive_json()

        live_articles["editorsPick"] = article
        live_articles["lastUpdated"] = date.today().isoformat()

        with open(ARTICLES_FILE, 'w') as f:
            json.dump(live_articles, f, indent=2)
        changed = True
        result = f"PICK: {article['headline'][:40]}..."

    else:
        return "Unknown action"

    # auto-push to github
    if changed:
        if git_push():
            result += " [pushed]"
        else:
            result += " [push pending]"

    return result


def run_curator():
    """main curator loop"""
    print("SPS Daily Curator v2 started")
    print(f"  Listening on chat {CHAT_ID}")

    # cleanup old articles at startup
    removed = cleanup_old_articles()
    if removed > 0:
        print(f"  Cleaned {removed} old articles")
        git_push()

    offset = None
    pending = {}
    approved = load_approved()

    while True:
        try:
            updates = get_updates(offset)

            if not updates.get("ok"):
                print(f"Error: {updates}")
                time.sleep(5)
                continue

            for update in updates.get("result", []):
                offset = update["update_id"] + 1

                # handle commands
                if "message" in update:
                    text = update["message"].get("text", "")

                    if text in ["/start", "/review"]:
                        send_articles_for_review()
                        pending = load_pending()

                    elif text == "/status":
                        if ARTICLES_FILE.exists():
                            live = json.load(open(ARTICLES_FILE))
                            counts = {cat: len(live.get(cat, [])) for cat in CATEGORIES}
                            pick = live.get("editorsPick", {}).get("headline", "None")[:40]
                            send_message(
                                f"<b>Live Articles</b>\n\n"
                                f"Science: {counts['science']}\n"
                                f"Philosophy: {counts['philosophy']}\n"
                                f"Society: {counts['society']}\n"
                                f"Books: {counts['books']}\n"
                                f"Essays: {counts['essays']}\n\n"
                                f"<b>Pick:</b> {pick}"
                            )
                        else:
                            send_message("No articles.json found")

                    elif text == "/help":
                        send_message(
                            "<b>SPS Daily Curator v2</b>\n\n"
                            "/review - Send articles for review\n"
                            "/status - Show live article counts\n"
                            "/help - This message"
                        )

                # handle callbacks (button presses)
                elif "callback_query" in update:
                    callback = update["callback_query"]
                    callback_data = callback.get("data", "")

                    pending = load_pending()
                    result = handle_callback(callback_data, pending, approved)

                    requests.post(f"{API_URL}/answerCallbackQuery", data={
                        "callback_query_id": callback["id"],
                        "text": result
                    }, timeout=10)

        except KeyboardInterrupt:
            print("\nStopping curator...")
            break
        except Exception as e:
            print(f"Error: {e}")
            time.sleep(5)


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1:
        if sys.argv[1] == "send":
            send_articles_for_review()
        elif sys.argv[1] == "status":
            if ARTICLES_FILE.exists():
                live = json.load(open(ARTICLES_FILE))
                for cat in CATEGORIES:
                    print(f"{cat}: {len(live.get(cat, []))}")
    else:
        run_curator()
