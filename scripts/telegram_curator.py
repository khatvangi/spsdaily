#!/usr/bin/env python3
"""
SPS Daily Telegram Curator
Sends collected articles to Telegram for manual curation
"""

import json
import requests
import time
from pathlib import Path

# Telegram Bot Configuration
BOT_TOKEN = "8516392118:AAEIybKb68Gfl0kTpzKkbCKtUl1OtRqMwtY"
CHAT_ID = "5314021805"
API_URL = f"https://api.telegram.org/bot{BOT_TOKEN}"

# Paths
SPSDAILY_DIR = Path("/storage/spsdaily")
ARTICLES_FILE = SPSDAILY_DIR / "articles.json"
PENDING_FILE = SPSDAILY_DIR / "pending_articles.json"
APPROVED_FILE = SPSDAILY_DIR / "approved_articles.json"

def send_message(text, reply_markup=None):
    """Send a message to the curator"""
    data = {
        "chat_id": CHAT_ID,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True
    }
    if reply_markup:
        data["reply_markup"] = json.dumps(reply_markup)

    response = requests.post(f"{API_URL}/sendMessage", data=data)
    return response.json()

def send_article_for_review(article, category, index):
    """Send an article with approve/reject buttons"""
    text = f"""<b>{category.upper()}</b>

<b>{article['headline']}</b>

{article.get('teaser', '')[:300]}

<i>Source: {article['source']}</i>
<a href="{article['url']}">Read full article</a>"""

    keyboard = {
        "inline_keyboard": [
            [
                {"text": "✅ Approve", "callback_data": f"approve:{category}:{index}"},
                {"text": "❌ Reject", "callback_data": f"reject:{category}:{index}"},
            ],
            [
                {"text": "⭐ Editor's Pick", "callback_data": f"pick:{category}:{index}"}
            ]
        ]
    }

    return send_message(text, keyboard)

def get_updates(offset=None):
    """Get updates from Telegram"""
    params = {"timeout": 30}
    if offset:
        params["offset"] = offset
    response = requests.get(f"{API_URL}/getUpdates", params=params)
    return response.json()

def load_pending():
    """Load pending articles"""
    if PENDING_FILE.exists():
        return json.load(open(PENDING_FILE))
    return {}

def save_pending(pending):
    """Save pending articles"""
    with open(PENDING_FILE, 'w') as f:
        json.dump(pending, f, indent=2)

def load_approved():
    """Load approved articles"""
    if APPROVED_FILE.exists():
        return json.load(open(APPROVED_FILE))
    return {"editorsPick": None, "science": [], "philosophy": [], "society": [], "books": []}

def save_approved(approved):
    """Save approved articles"""
    with open(APPROVED_FILE, 'w') as f:
        json.dump(approved, f, indent=2)

def publish_approved():
    """Publish approved articles to the main articles.json"""
    approved = load_approved()

    if not any(approved.get(cat) for cat in ["science", "philosophy", "society", "books"]):
        print("No approved articles to publish")
        return False

    from datetime import datetime

    # Get editor's pick - use selected one, or first from any category
    editors_pick = approved.get("editorsPick")
    if not editors_pick:
        for cat in ["science", "philosophy", "society", "books"]:
            if approved.get(cat):
                editors_pick = approved[cat][0]
                break

    output = {
        "lastUpdated": datetime.now().strftime("%Y-%m-%d"),
        "editorsPick": editors_pick or {},
        "science": approved.get("science", []),
        "philosophy": approved.get("philosophy", []),
        "society": approved.get("society", []),
        "books": approved.get("books", [])
    }

    with open(ARTICLES_FILE, 'w') as f:
        json.dump(output, f, indent=2)

    print(f"Published: Science={len(output['science'])}, Philosophy={len(output['philosophy'])}, Society={len(output['society'])}, Books={len(output['books'])}")
    return True

def send_articles_for_review():
    """Send all collected articles for review"""
    # Load collected articles from pending file
    if not PENDING_FILE.exists():
        print("No pending_articles.json found")
        send_message("❌ No pending articles. Run the collector first.")
        return

    articles = json.load(open(PENDING_FILE))
    pending = {}

    send_message("🗞️ <b>SPS Daily - Articles for Review</b>\n\nReview the following articles. Tap ✅ to approve, ❌ to reject, or ⭐ to make it Editor's Pick.")
    time.sleep(1)

    for category in ["science", "philosophy", "society", "books"]:
        category_articles = articles.get(category, [])
        if not category_articles:
            continue

        pending[category] = category_articles
        send_message(f"📂 <b>{category.upper()}</b> ({len(category_articles)} articles)")
        time.sleep(0.5)

        for i, article in enumerate(category_articles):
            send_article_for_review(article, category, i)
            time.sleep(0.3)  # Rate limiting

    save_pending(pending)

    send_message("✅ All articles sent! When done reviewing, send /publish to publish approved articles.")

def git_push():
    """Commit and push articles.json to GitHub"""
    import subprocess
    try:
        subprocess.run(
            ["git", "add", "articles.json"],
            cwd=SPSDAILY_DIR, check=True, capture_output=True
        )
        subprocess.run(
            ["git", "commit", "-m", "📰 Curator update"],
            cwd=SPSDAILY_DIR, check=True, capture_output=True
        )
        subprocess.run(
            ["git", "push"],
            cwd=SPSDAILY_DIR, check=True, capture_output=True
        )
        return True
    except subprocess.CalledProcessError:
        return False

def handle_callback(callback_data, pending, approved):
    """Handle button callbacks - immediately updates articles.json and pushes"""
    parts = callback_data.split(":")
    action = parts[0]
    category = parts[1]
    index = int(parts[2])

    if category not in pending or index >= len(pending[category]):
        return "Article not found"

    article = pending[category][index]

    # Load current live articles
    live_articles = json.load(open(ARTICLES_FILE))
    changed = False

    if action == "approve":
        # Add to live articles immediately
        if category not in live_articles:
            live_articles[category] = []
        if article not in live_articles[category]:
            live_articles[category].insert(0, article)  # Add to top
            with open(ARTICLES_FILE, 'w') as f:
                json.dump(live_articles, f, indent=2)
            changed = True
            result = f"✅ LIVE: {article['headline'][:40]}..."
        else:
            return "Already live"

    elif action == "reject":
        # Remove from live articles if present
        if category in live_articles:
            live_articles[category] = [a for a in live_articles[category] if a.get('url') != article.get('url')]
            with open(ARTICLES_FILE, 'w') as f:
                json.dump(live_articles, f, indent=2)
            changed = True
        result = f"❌ Removed: {article['headline'][:40]}..."

    elif action == "pick":
        # Set as editor's pick immediately
        live_articles["editorsPick"] = article
        # Also add to category if not there
        if category not in live_articles:
            live_articles[category] = []
        if article not in live_articles[category]:
            live_articles[category].insert(0, article)
        with open(ARTICLES_FILE, 'w') as f:
            json.dump(live_articles, f, indent=2)
        changed = True
        result = f"⭐ PICK SET: {article['headline'][:40]}..."
    else:
        return "Unknown action"

    # Auto-push to GitHub
    if changed:
        if git_push():
            result += " 🚀"
        else:
            result += " (push pending)"

    return result

def run_curator():
    """Main curator loop - listens for commands and callbacks"""
    print("🤖 SPS Daily Curator Bot started")
    print(f"   Listening for commands from chat {CHAT_ID}")

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

                # Handle messages (commands)
                if "message" in update:
                    msg = update["message"]
                    text = msg.get("text", "")

                    if text == "/start" or text == "/review":
                        send_articles_for_review()
                        pending = load_pending()

                    elif text == "/publish":
                        if publish_approved():
                            send_message("✅ Articles published to SPS Daily!\n\nRun 'git push' on server to update the website.")
                        else:
                            send_message("❌ No approved articles to publish. Review articles first with /review")

                    elif text == "/status":
                        approved = load_approved()
                        counts = {cat: len(approved.get(cat, [])) for cat in ["science", "philosophy", "society", "books"]}
                        pick = approved.get("editorsPick", {}).get("headline", "Not set")[:40]
                        send_message(f"📊 <b>Status</b>\n\nApproved:\n• Science: {counts['science']}\n• Philosophy: {counts['philosophy']}\n• Society: {counts['society']}\n• Books: {counts['books']}\n\nEditor's Pick: {pick}")

                    elif text == "/help":
                        send_message("""<b>SPS Daily Curator Commands</b>

/review - Send articles for review
/status - Show approved counts
/publish - Publish approved articles
/help - Show this help""")

                # Handle callbacks (button presses)
                elif "callback_query" in update:
                    callback = update["callback_query"]
                    callback_data = callback.get("data", "")

                    pending = load_pending()
                    approved = load_approved()

                    result = handle_callback(callback_data, pending, approved)

                    # Answer the callback
                    requests.post(f"{API_URL}/answerCallbackQuery", data={
                        "callback_query_id": callback["id"],
                        "text": result
                    })

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
            # Just send articles for review (non-interactive)
            send_articles_for_review()
        elif sys.argv[1] == "publish":
            # Publish approved articles
            publish_approved()
    else:
        # Run interactive curator
        run_curator()
