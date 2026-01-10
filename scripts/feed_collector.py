#!/usr/bin/env python3
"""
SPS Daily Feed Collector
Fetches articles from RSS feeds and generates pending_articles.json
"""

import feedparser
import json
import re
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
import html
import random
import subprocess
import socket
import requests
import time
from bs4 import BeautifulSoup

# Set network timeout to prevent hanging on slow feeds
socket.setdefaulttimeout(15)

# telegram bot config for auto-sending articles
BOT_TOKEN = "8516392118:AAEIybKb68Gfl0kTpzKkbCKtUl1OtRqMwtY"
CHAT_ID = "5314021805"
TELEGRAM_API = f"https://api.telegram.org/bot{BOT_TOKEN}"

# Database for tracking seen articles
DB_PATH = Path(__file__).parent.parent / "data" / "articles.db"

def init_db():
    """Initialize the articles database"""
    DB_PATH.parent.mkdir(exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute('''
        CREATE TABLE IF NOT EXISTS seen_articles (
            url TEXT PRIMARY KEY,
            headline TEXT,
            category TEXT,
            status TEXT DEFAULT 'pending',
            first_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            reviewed TIMESTAMP
        )
    ''')
    # Archive table for approved articles
    conn.execute('''
        CREATE TABLE IF NOT EXISTS archive (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            url TEXT UNIQUE,
            headline TEXT,
            teaser TEXT,
            source TEXT,
            category TEXT,
            approved_date DATE DEFAULT CURRENT_DATE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    return conn

def is_article_seen(conn, url):
    """Check if article URL has been seen before"""
    cur = conn.execute("SELECT 1 FROM seen_articles WHERE url = ?", (url,))
    return cur.fetchone() is not None

def mark_article_seen(conn, url, headline, category):
    """Mark an article as seen"""
    conn.execute(
        "INSERT OR IGNORE INTO seen_articles (url, headline, category) VALUES (?, ?, ?)",
        (url, headline, category)
    )
    conn.commit()

def add_to_archive(conn, article, category):
    """Add an approved article to the archive"""
    conn.execute('''
        INSERT OR IGNORE INTO archive (url, headline, teaser, source, category)
        VALUES (?, ?, ?, ?, ?)
    ''', (article['url'], article['headline'], article.get('teaser', ''),
          article.get('source', ''), category))
    conn.commit()

def generate_archive_json(conn):
    """Generate archive.json grouped by date"""
    cur = conn.execute('''
        SELECT approved_date, category, headline, teaser, source, url
        FROM archive
        ORDER BY approved_date DESC, category, id DESC
    ''')

    archive = {}
    for row in cur.fetchall():
        date_str = row[0]
        if date_str not in archive:
            archive[date_str] = {"science": [], "philosophy": [], "society": [], "books": []}

        category = row[1]
        if category in archive[date_str]:
            archive[date_str][category].append({
                "headline": row[2],
                "teaser": row[3],
                "source": row[4],
                "url": row[5]
            })

    archive_path = Path(__file__).parent.parent / "archive.json"
    with open(archive_path, 'w') as f:
        json.dump(archive, f, indent=2)

    return archive

# Ollama configuration
OLLAMA_MODEL_FILTER = "qwen2.5:0.5b"  # Tiny model for YES/NO filtering
USE_AI_FILTER = False  # Disabled - manual curation via Telegram bot

def ai_evaluate_article(headline, teaser, category):
    """Use Ollama to evaluate if an article is worth including."""
    if not USE_AI_FILTER:
        return True, "AI filter disabled"

    prompt = f"""Evaluate this article for SPS Daily, a curated digest of substantive writing on science, philosophy, and society.

Category: {category}
Headline: {headline}
Teaser: {teaser}

Is this article intellectually substantive and worth featuring? Consider:
- Is it a thoughtful essay or long-form piece (GOOD) vs. news brief or listicle (BAD)?
- Does it explore ideas in depth (GOOD) vs. superficial hot takes (BAD)?
- Is it timeless or evergreen content (GOOD) vs. breaking news that will be stale tomorrow (BAD)?
- For books: Is it a genuine literary review (GOOD) vs. political commentary (BAD)?

Reply with ONLY one word: YES or NO
/no_think"""

    try:
        result = subprocess.run(
            ["ollama", "run", OLLAMA_MODEL_FILTER, prompt],
            capture_output=True,
            text=True,
            timeout=30
        )
        response = result.stdout.strip().upper()
        # Extract just YES or NO from response
        if "YES" in response:
            return True, "AI approved"
        elif "NO" in response:
            return False, "AI rejected"
        else:
            return True, f"AI unclear: {response[:50]}"  # Default to include if unclear
    except subprocess.TimeoutExpired:
        return True, "AI timeout"
    except Exception as e:
        return True, f"AI error: {e}"


# Political/current affairs keywords to filter from book reviews
# (we want literary/academic book reviews, not political commentary)
BOOKS_FILTER_KEYWORDS = [
    # Politicians and political figures
    'trump', 'biden', 'obama', 'clinton', 'desantis', 'pelosi', 'mcconnell',
    'aoc', 'ocasio-cortez', 'bernie', 'sanders', 'musk', 'zuckerberg',
    # Political terms
    'republican', 'democrat', 'gop', 'maga', 'liberal', 'conservative',
    'election', 'ballot', 'vote', 'campaign', 'inauguration', 'mayor',
    'governor', 'senator', 'congressman', 'parliament', 'brexit',
    # Hot button issues (keep academic discussions, filter partisan takes)
    'abortion rights', 'gun control', 'immigration policy', 'border wall',
    # Partisan language
    'collectivism', 'socialism', 'fascism', 'marxist', 'woke',
    'left-wing', 'right-wing', 'far-left', 'far-right',
]

def is_political_content(headline, teaser, category):
    """Check if content is political (only filter for books category)"""
    if category != 'books':
        return False

    text = (headline + ' ' + teaser).lower()
    for keyword in BOOKS_FILTER_KEYWORDS:
        if keyword in text:
            return True
    return False

# RSS Feeds organized by category (based on Arts & Letters Daily)
# Source: https://aldaily.com/
FEEDS = {
    "science": [
        # Science & Technology (from AL Daily Magazines list)
        ("Scientific American", "https://www.scientificamerican.com/feed/"),
        ("New Scientist", "https://www.newscientist.com/feed/home/"),
        ("Nautilus", "https://nautil.us/feed/"),
        ("Discover", "https://www.discovermagazine.com/rss"),
        ("MIT Tech Review", "https://www.technologyreview.com/feed/"),
        ("Wired", "https://www.wired.com/feed/rss"),
        ("Edge", "https://www.edge.org/feed"),
        ("American Scientist", "https://www.americanscientist.org/rss"),
        ("Smithsonian Magazine", "https://www.smithsonianmag.com/rss/articles/"),
        ("Psychology Today", "https://www.psychologytoday.com/us/front/feed"),
        ("Skeptical Inquirer", "https://skepticalinquirer.org/feed/"),
        ("Atlas Obscura", "https://www.atlasobscura.com/feeds/latest"),
        ("Quanta Magazine", "https://www.quantamagazine.org/feed/"),
    ],
    "philosophy": [
        # Philosophy, Ideas & Culture (from AL Daily Magazines list)
        ("Aeon", "https://aeon.co/feed.rss"),
        ("Philosophy Now", "https://philosophynow.org/rss"),
        ("New Atlantis", "https://www.thenewatlantis.com/rss"),
        ("Hedgehog Review", "https://hedgehogreview.com/feed"),
        ("The Point", "https://thepointmag.com/feed/"),
        ("The Drift", "https://www.thedriftmag.com/feed/"),
        ("Liberties", "https://libertiesjournal.com/feed/"),
        ("Public Domain Review", "https://publicdomainreview.org/rss.xml"),
        ("3 Quarks Daily", "https://3quarksdaily.com/feed/"),
        ("First Things", "https://www.firstthings.com/rss"),
        ("The Humanist", "https://thehumanist.com/feed/"),
        ("Commonweal", "https://www.commonwealmagazine.org/rss.xml"),
        ("Plough", "https://www.plough.com/en/rss.xml"),
        ("Tikkun", "https://www.tikkun.org/feed"),
        ("Mosaic", "https://mosaicmagazine.com/feed/"),
        ("Lapham's Quarterly", "https://www.laphamsquarterly.org/feed"),
        ("Cabinet", "https://www.cabinetmagazine.org/rss/"),
        ("The Smart Set", "https://thesmartset.com/feed/"),
        ("The New Inquiry", "https://thenewinquiry.com/feed/"),
    ],
    "society": [
        # Politics, Culture & Society (from AL Daily Magazines list)
        ("The Atlantic", "https://www.theatlantic.com/feed/all/"),
        ("The New Yorker", "https://www.newyorker.com/feed/everything"),
        ("Harper's", "https://harpers.org/feed/"),
        ("New Republic", "https://newrepublic.com/rss.xml"),
        ("Slate", "https://slate.com/feeds/all.rss"),
        ("Salon", "https://www.salon.com/feed/"),
        ("The Nation", "https://www.thenation.com/feed/"),
        ("Jacobin", "https://jacobin.com/feed/"),
        ("Dissent", "https://www.dissentmagazine.org/feed"),
        ("n+1", "https://www.nplusonemag.com/feed/"),
        ("The Baffler", "https://thebaffler.com/feed"),
        ("Current Affairs", "https://www.currentaffairs.org/feed"),
        ("American Scholar", "https://theamericanscholar.org/feed/"),
        ("Boston Review", "https://www.bostonreview.net/feed/"),
        ("JSTOR Daily", "https://daily.jstor.org/feed/"),
        ("Noema", "https://www.noemamag.com/feed/"),
        # UK & International
        ("New Statesman", "https://www.newstatesman.com/feed"),
        ("The Spectator", "https://www.spectator.co.uk/feed"),
        ("Prospect", "https://www.prospectmagazine.co.uk/feed"),
        ("Spiked", "https://www.spiked-online.com/feed/"),
        ("The Walrus", "https://thewalrus.ca/feed/"),
        ("Eurozine", "https://www.eurozine.com/feed/"),
        ("Open Democracy", "https://www.opendemocracy.net/en/rss/"),
        # Policy & Foreign Affairs
        ("Foreign Affairs", "https://www.foreignaffairs.com/rss.xml"),
        ("Foreign Policy", "https://foreignpolicy.com/feed/"),
        ("National Interest", "https://nationalinterest.org/rss.xml"),
        ("Project Syndicate", "https://www.project-syndicate.org/rss"),
        ("World Affairs", "https://www.worldaffairsjournal.org/feed"),
        ("The Globalist", "https://www.theglobalist.com/feed/"),
        # Conservative/Libertarian
        ("National Review", "https://www.nationalreview.com/feed/"),
        ("American Conservative", "https://www.theamericanconservative.com/feed/"),
        ("Reason", "https://reason.com/feed/"),
        ("City Journal", "https://www.city-journal.org/feed"),
        ("Commentary", "https://www.commentary.org/feed/"),
        ("New Criterion", "https://newcriterion.com/feed"),
        ("Claremont Review", "https://claremontreviewofbooks.com/feed/"),
        # Progressive
        ("Mother Jones", "https://www.motherjones.com/feed/"),
        ("The Progressive", "https://progressive.org/feed/"),
        ("In These Times", "https://inthesetimes.com/feed"),
        # Literary & Arts
        ("Granta", "https://granta.com/feed/"),
        ("Guernica", "https://www.guernicamag.com/feed/"),
        ("Electric Literature", "https://electricliterature.com/feed/"),
        ("Poetry", "https://www.poetryfoundation.org/feed"),
        ("The Paris Review Daily", "https://www.theparisreview.org/blog/feed/"),
        ("The White Review", "https://www.thewhitereview.org/feed/"),
        ("Threepenny Review", "https://www.threepennyreview.com/feed.xml"),
        ("Yale Review", "https://yalereview.org/feed"),
        ("Hudson Review", "https://hudsonreview.com/feed/"),
        ("Salmagundi", "https://www.salmagundi.skidmore.edu/feed/"),
        ("Arion", "https://www.bu.edu/arion/feed/"),
    ],
    "books": [
        # Book Reviews (from AL Daily Book Reviews list)
        ("NY Review of Books", "https://www.nybooks.com/feed/"),
        ("London Review of Books", "https://www.lrb.co.uk/feed"),
        ("The TLS", "https://www.the-tls.co.uk/feed/"),
        ("LA Review of Books", "https://lareviewofbooks.org/feed/"),
        ("Literary Review", "https://literaryreview.co.uk/feed"),
        ("Bookforum", "https://www.bookforum.com/feed"),
        ("The Millions", "https://themillions.com/feed"),
        ("Public Books", "https://www.publicbooks.org/feed/"),
        ("Open Letters Review", "https://www.openlettersreview.com/feed"),
        ("Sydney Review of Books", "https://sydneyreviewofbooks.com/feed/"),
        ("Dublin Review of Books", "https://drb.ie/feed/"),
        ("Jewish Review of Books", "https://jewishreviewofbooks.com/feed/"),
        ("Complete Review", "https://www.complete-review.com/new/new.xml"),
        ("Pittsburgh Review of Books", "https://pittsburghreviewofbooks.com/feed/"),
        # Newspaper Book Sections
        ("Guardian Books", "https://www.theguardian.com/books/rss"),
        ("NY Times Books", "https://rss.nytimes.com/services/xml/rss/nyt/Books.xml"),
        ("Washington Post Books", "https://www.washingtonpost.com/rss/entertainment/books"),
        ("The Hindu Books", "https://www.thehindu.com/books/feeder/default.rss"),
        ("Financial Times Books", "https://www.ft.com/books?format=rss"),
        ("Economist Books", "https://www.economist.com/books-and-arts/rss.xml"),
        # Arts & Culture
        ("Artforum", "https://www.artforum.com/feed/"),
        ("Art News", "https://www.artnews.com/feed/"),
        ("Hyperallergic", "https://hyperallergic.com/feed/"),
    ]
}


def clean_html(text):
    """Remove HTML tags and decode entities"""
    if not text:
        return ""
    text = re.sub(r'<[^>]+>', '', text)
    text = html.unescape(text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text

def truncate_teaser(text, max_len=200):
    """Truncate text to max length at word boundary"""
    text = clean_html(text)
    if len(text) <= max_len:
        return text
    truncated = text[:max_len].rsplit(' ', 1)[0]
    return truncated + "..."

def fetch_feed(name, url, max_age_days=7):
    """Fetch and parse an RSS feed"""
    articles = []
    try:
        feed = feedparser.parse(url)
        cutoff = datetime.now() - timedelta(days=max_age_days)

        for entry in feed.entries[:10]:  # Limit to recent entries
            # Try to get published date
            published = None
            if hasattr(entry, 'published_parsed') and entry.published_parsed:
                published = datetime(*entry.published_parsed[:6])
            elif hasattr(entry, 'updated_parsed') and entry.updated_parsed:
                published = datetime(*entry.updated_parsed[:6])

            # Skip old articles
            if published and published < cutoff:
                continue

            # Extract article data
            headline = clean_html(entry.get('title', ''))
            teaser = truncate_teaser(
                entry.get('summary', entry.get('description', ''))
            )
            link = entry.get('link', '')

            if headline and link:
                articles.append({
                    "headline": headline,
                    "teaser": teaser,
                    "source": name,
                    "url": link,
                    "published": published.isoformat() if published else None
                })
    except Exception as e:
        print(f"  Error fetching {name}: {e}")

    return articles

def fetch_hacker_news(max_articles=20):
    """fetch top stories from hacker news, filtered for science/philosophy"""
    HN_KEYWORDS = {
        # science
        'science', 'scientific', 'physics', 'biology', 'chemistry', 'astronomy',
        'quantum', 'evolution', 'research', 'discovery', 'nature', 'universe',
        'space', 'cosmos', 'neural', 'cognitive', 'brain', 'dna', 'climate',
        # philosophy & society
        'philosophy', 'ethics', 'consciousness', 'moral', 'existence',
        'democracy', 'society', 'culture', 'human', 'humanity', 'history',
        'psychology', 'theory', 'mathematical', 'logic', 'truth',
        # broader science-adjacent
        'ai', 'artificial intelligence', 'machine learning', 'algorithm',
        'energy', 'solar', 'nuclear', 'medical', 'health', 'disease'
    }

    articles = []
    try:
        # get best stories (quality-filtered by HN)
        resp = requests.get('https://hacker-news.firebaseio.com/v0/beststories.json', timeout=10)
        story_ids = resp.json()[:100]  # check top 100

        for sid in story_ids:
            if len(articles) >= max_articles:
                break
            item = requests.get(f'https://hacker-news.firebaseio.com/v0/item/{sid}.json', timeout=5).json()
            if not item or item.get('type') != 'story' or not item.get('url'):
                continue

            title = item.get('title', '').lower()
            # check if any keyword matches (word boundary)
            if any(re.search(r'\b' + kw + r'\b', title) for kw in HN_KEYWORDS):
                articles.append({
                    "headline": item.get('title', ''),
                    "teaser": f"Discussed on Hacker News with {item.get('score', 0)} points",
                    "source": "Hacker News",
                    "url": item.get('url'),
                    "published": datetime.fromtimestamp(item.get('time', 0)).isoformat()
                })
    except Exception as e:
        print(f"  Error fetching Hacker News: {e}")

    return articles

def check_archive_url(url):
    """check if article is archived on archive.org, return archive url or None"""
    try:
        api_url = f"https://archive.org/wayback/available?url={url}"
        resp = requests.get(api_url, timeout=5)
        data = resp.json()
        snapshot = data.get("archived_snapshots", {}).get("closest", {})
        if snapshot.get("available"):
            return snapshot.get("url")
    except Exception:
        pass
    return None


def fetch_og_image(url, timeout=5):
    """fetch og:image from article url"""
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (compatible; SPSDaily/1.0)'}
        resp = requests.get(url, headers=headers, timeout=timeout)
        soup = BeautifulSoup(resp.content, 'html.parser')

        # try og:image first
        og_image = soup.find('meta', property='og:image')
        if og_image and og_image.get('content'):
            return og_image['content']

        # fallback to twitter:image
        tw_image = soup.find('meta', attrs={'name': 'twitter:image'})
        if tw_image and tw_image.get('content'):
            return tw_image['content']

    except Exception:
        pass
    return None


def send_article_to_telegram(article, category, index):
    """send single article to telegram for review immediately"""
    # build message with image preview
    img_info = ""
    if article.get('imageUrl'):
        img_info = f"\n🖼️ <i>Has image</i>"

    text = f"""<b>{category.upper()}</b>{img_info}

<b>{article['headline']}</b>

{article.get('teaser', '')[:280]}

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

    data = {
        "chat_id": CHAT_ID,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": False,
        "reply_markup": json.dumps(keyboard)
    }

    try:
        requests.post(f"{TELEGRAM_API}/sendMessage", data=data, timeout=10)
        time.sleep(0.35)  # rate limit
    except Exception as e:
        print(f"    ⚠ Telegram error: {e}")

def add_archive_urls(selected):
    """add archive.org urls to selected articles"""
    print("\n📚 Checking Archive.org availability...")
    total = sum(len(articles) for articles in selected.values())
    checked = 0
    found = 0

    for category, articles in selected.items():
        for article in articles:
            checked += 1
            archive_url = check_archive_url(article['url'])
            if archive_url:
                article['archiveUrl'] = archive_url
                found += 1
            time.sleep(0.1)  # rate limit: ~10 req/sec

            # progress indicator every 10 articles
            if checked % 10 == 0:
                print(f"    Checked {checked}/{total}...")

    print(f"    Found {found}/{total} archived articles")
    return selected

def collect_all_feeds():
    """Collect articles from all feeds"""
    all_articles = {
        "science": [],
        "philosophy": [],
        "society": [],
        "books": []
    }

    # Track seen headlines globally to avoid duplicates across all categories
    seen_headlines = set()

    # Collect all candidates first, then AI filter
    candidates = {cat: [] for cat in all_articles.keys()}

    for category, feeds in FEEDS.items():
        print(f"\n📚 Collecting {category}...")
        for name, url in feeds:
            print(f"  → {name}")
            articles = fetch_feed(name, url)
            added = 0
            filtered = 0
            dupes = 0

            for article in articles:
                headline_lower = article['headline'].lower().strip()

                # Skip duplicates
                if headline_lower in seen_headlines:
                    dupes += 1
                    continue

                # Skip political content in books (keyword filter)
                if is_political_content(article['headline'], article['teaser'], category):
                    filtered += 1
                    print(f"    ⚠ Filtered (political): {article['headline'][:50]}...")
                    continue

                seen_headlines.add(headline_lower)
                candidates[category].append(article)
                added += 1

            status = f"Added {added}"
            if dupes > 0:
                status += f", {dupes} dupes"
            if filtered > 0:
                status += f", {filtered} filtered"
            print(f"    {status}")

    # fetch from hacker news
    print(f"\n📚 Collecting from Hacker News...")
    hn_articles = fetch_hacker_news()
    hn_added = 0
    for article in hn_articles:
        headline_lower = article['headline'].lower().strip()
        if headline_lower not in seen_headlines:
            seen_headlines.add(headline_lower)
            candidates['science'].append(article)
            hn_added += 1
    print(f"    Added {hn_added} from HN")

    # AI filtering pass
    if USE_AI_FILTER:
        print("\n🤖 AI filtering articles...")
        for category, articles in candidates.items():
            print(f"  {category}: evaluating {len(articles)} articles...")
            ai_approved = 0
            ai_rejected = 0
            for article in articles:
                approved, reason = ai_evaluate_article(
                    article['headline'],
                    article['teaser'],
                    category
                )
                if approved:
                    all_articles[category].append(article)
                    ai_approved += 1
                else:
                    ai_rejected += 1
                    print(f"    ✗ {article['headline'][:60]}...")
            print(f"    ✓ {ai_approved} approved, ✗ {ai_rejected} rejected")
    else:
        all_articles = candidates

    return all_articles

def select_articles(all_articles, per_category=3):
    """Select diverse articles for each category"""
    selected = {}

    for category, articles in all_articles.items():
        if not articles:
            selected[category] = []
            continue

        # Sort by freshness (if available)
        articles.sort(key=lambda x: x.get('published') or '', reverse=True)

        # Try to pick from different sources, avoid duplicates
        sources_used = set()
        urls_used = set()
        picks = []

        for article in articles:
            if len(picks) >= per_category:
                break
            # Skip if URL already used or same source
            if article['url'] in urls_used:
                continue
            if article['source'] not in sources_used:
                picks.append({
                    "headline": article['headline'],
                    "teaser": article['teaser'],
                    "source": article['source'],
                    "url": article['url']
                })
                sources_used.add(article['source'])
                urls_used.add(article['url'])

        # Fill remaining slots if needed (allow same source but not same URL)
        for article in articles:
            if len(picks) >= per_category:
                break
            if article['url'] not in urls_used:
                picks.append({
                    "headline": article['headline'],
                    "teaser": article['teaser'],
                    "source": article['source'],
                    "url": article['url']
                })
                urls_used.add(article['url'])

        selected[category] = picks

    return selected

def generate_json(selected):
    """Generate the articles.json file"""
    # Pick editor's choice from science or philosophy
    all_picks = selected.get('science', []) + selected.get('philosophy', [])
    editors_pick = random.choice(all_picks) if all_picks else {
        "headline": "Welcome to SPS Daily",
        "teaser": "Your daily digest of science, philosophy, and society.",
        "source": "SPS Daily",
        "url": "https://spsdaily.thebeakers.com"
    }

    output = {
        "lastUpdated": datetime.now().strftime("%Y-%m-%d"),
        "editorsPick": editors_pick,
        "science": selected.get('science', []),
        "philosophy": selected.get('philosophy', []),
        "society": selected.get('society', [])
    }

    # Add books if we have any
    if selected.get('books'):
        output["books"] = selected['books']

    return output

def save_pending(pending_data, pending_path):
    """save pending articles to file (for callback handler)"""
    with open(pending_path, 'w') as f:
        json.dump(pending_data, f, indent=2)


def main():
    print("🗞️  SPS Daily Feed Collector")
    print("=" * 40)

    # Initialize database
    conn = init_db()

    # Collect from all feeds
    all_articles = collect_all_feeds()

    # Filter out already-seen articles
    print("\n🔍 Filtering seen articles...")
    new_articles = {}
    seen_count = 0
    for category, articles in all_articles.items():
        new_articles[category] = []
        for article in articles:
            if is_article_seen(conn, article['url']):
                seen_count += 1
            else:
                new_articles[category].append(article)
                mark_article_seen(conn, article['url'], article['headline'], category)

    print(f"   Skipped {seen_count} already-seen articles")
    conn.close()

    # Check if we have any new articles
    total_new = sum(len(arts) for arts in new_articles.values())
    if total_new == 0:
        print("\n✨ No new articles to review!")
        return

    # Select articles (no strict limit - 1 week retention handles cleanup)
    print("\n✨ Selecting articles...")
    selected = select_articles(new_articles, per_category=50)

    # Prepare pending structure - will be saved incrementally
    pending_path = Path(__file__).parent.parent / "pending_articles.json"
    pending_data = {
        "lastUpdated": datetime.now().strftime("%Y-%m-%d"),
        "editorsPick": None,
        "science": [],
        "philosophy": [],
        "society": [],
        "books": []
    }

    # Send start notification
    try:
        requests.post(f"{TELEGRAM_API}/sendMessage", data={
            "chat_id": CHAT_ID,
            "text": f"🗞️ <b>SPS Daily - {total_new} new articles incoming!</b>\n\nReview each one: ✅ Approve, ❌ Reject, ⭐ Pick",
            "parse_mode": "HTML"
        }, timeout=10)
    except Exception:
        pass

    # Process each article: fetch image, archive url, send to telegram
    print("\n📤 Processing and sending to Telegram...")
    processed = 0

    for category in ["science", "philosophy", "society", "books"]:
        articles = selected.get(category, [])
        if not articles:
            continue

        print(f"\n  📂 {category.upper()} ({len(articles)} articles)")

        for i, article in enumerate(articles):
            processed += 1
            headline_short = article['headline'][:40] + "..." if len(article['headline']) > 40 else article['headline']
            print(f"    [{processed}] {headline_short}")

            # fetch og:image
            img_url = fetch_og_image(article['url'])
            if img_url:
                article['imageUrl'] = img_url
                print(f"        🖼️ image found")

            # check archive.org
            archive_url = check_archive_url(article['url'])
            if archive_url:
                article['archiveUrl'] = archive_url
                print(f"        📚 archived")

            # add to pending data
            pending_data[category].append(article)

            # save pending file incrementally (so callbacks work)
            save_pending(pending_data, pending_path)

            # send to telegram immediately
            index = len(pending_data[category]) - 1
            send_article_to_telegram(article, category, index)

    # Set default editor's pick (first science or philosophy article)
    for cat in ["science", "philosophy", "society", "books"]:
        if pending_data.get(cat):
            pending_data["editorsPick"] = pending_data[cat][0]
            break
    save_pending(pending_data, pending_path)

    # Send completion notification
    try:
        requests.post(f"{TELEGRAM_API}/sendMessage", data={
            "chat_id": CHAT_ID,
            "text": f"✅ <b>All {processed} articles sent!</b>\n\nTap buttons to curate. Articles go live immediately.",
            "parse_mode": "HTML"
        }, timeout=10)
    except Exception:
        pass

    print(f"\n✅ Done! {processed} articles sent to Telegram")
    print(f"   Science: {len(pending_data['science'])}")
    print(f"   Philosophy: {len(pending_data['philosophy'])}")
    print(f"   Society: {len(pending_data['society'])}")
    print(f"   Books: {len(pending_data['books'])}")

if __name__ == "__main__":
    main()
