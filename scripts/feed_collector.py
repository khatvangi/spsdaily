#!/usr/bin/env python3
"""SPS Daily Feed Collector v2

Quality gates based on FORM (word count, depth, source reputation)
not CONTENT (topic keywords). A rigorous 2000-word analysis of any
serious topic is worth reading. A 300-word hot take isn't.

Config files:
  - config/spsdaily_feeds.json      (RSS sources by category)
  - config/spsdaily_quality.json    (word counts, patterns, blocklist)
  - config/spsdaily_source_weights.json (reputation weighting)
"""

from __future__ import annotations

import os
import re
import json
import math
import html
import sqlite3
import socket
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlparse

import feedparser
import requests

# paths
ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
CONFIG_DIR = ROOT / "config"
DATA_DIR.mkdir(parents=True, exist_ok=True)

DB_PATH = DATA_DIR / "articles.db"
PENDING_FILE = ROOT / "pending_articles.json"  # keep at root for compatibility

FEEDS_FILE = CONFIG_DIR / "spsdaily_feeds.json"
FEEDS_TXT = CONFIG_DIR / "feeds.txt"
BLOCKLIST_TXT = CONFIG_DIR / "blocklist.txt"
QUALITY_FILE = CONFIG_DIR / "spsdaily_quality.json"
WEIGHTS_FILE = CONFIG_DIR / "spsdaily_source_weights.json"

# telegram config (env vars with fallback)
BOT_TOKEN = os.getenv("SPSDAILY_BOT_TOKEN", "7834236484:AAEoCiumnN_93-y6LwFIMLuq3zRgOUwW_BY").strip()
CHAT_ID = os.getenv("SPSDAILY_CHAT_ID", "5314021805").strip()
TELEGRAM_API = f"https://api.telegram.org/bot{BOT_TOKEN}"

# defaults if config files missing
DEFAULT_FEEDS = {
    "science": [["Quanta Magazine", "https://api.quantamagazine.org/feed/"]],
    "philosophy": [["Aeon", "https://aeon.co/feed.rss"]],
    "society": [["Noema", "https://www.noemamag.com/feed/"]],
    "books": [["NYRB", "https://www.nybooks.com/feed/"]],
    "essays": [["Granta", "https://granta.com/feed/"]]
}

DEFAULT_QUALITY = {
    "max_age_days": 7,
    "select_per_category": 15,
    "overfetch_factor": 4,
    "timeout_sec": 20,
    "user_agent": "SPSDailyCollector/2.0",
    "min_words": {"science": 600, "philosophy": 800, "society": 700, "books": 600, "essays": 1000},
    "domain_min_words": {},
    "domain_blocklist": ["medium.com", "substack.com"],
    "clickbait_patterns": [r"^\s*\d+\s+(ways|things|reasons)\b"],
    "min_teaser_length": 60
}

DEFAULT_WEIGHTS = {"domain_weight": {}, "source_weight": {}}


def load_json(path: Path, fallback: dict) -> dict:
    """load json config with fallback"""
    if path.exists():
        try:
            return json.loads(path.read_text())
        except Exception as e:
            print(f"  warning: failed to load {path}: {e}")
    return fallback


def load_feeds_txt(path: Path) -> dict:
    """load feeds from simple text file format"""
    feeds = {}
    current_cat = None

    if not path.exists():
        return {}

    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        if line.startswith('[') and line.endswith(']'):
            current_cat = line[1:-1].lower()
            feeds[current_cat] = []
        elif current_cat and '|' in line:
            name, url = line.split('|', 1)
            feeds[current_cat].append([name.strip(), url.strip()])

    return feeds


def load_blocklist_txt(path: Path) -> set:
    """load blocklist from simple text file"""
    if not path.exists():
        return set()

    blocked = set()
    for line in path.read_text().splitlines():
        line = line.strip().lower()
        if line and not line.startswith('#'):
            blocked.add(line)
    return blocked


def normalize_domain(url: str) -> str:
    """extract domain from url, strip www."""
    try:
        d = urlparse(url).netloc.lower()
        return d[4:] if d.startswith("www.") else d
    except Exception:
        return ""


def clean_text(s: str) -> str:
    """clean html entities and whitespace"""
    s = html.unescape(s or "")
    s = re.sub(r"<[^>]+>", " ", s)  # strip html tags
    return re.sub(r"\s+", " ", s).strip()


def parse_entry_date(entry) -> datetime | None:
    """extract datetime from feed entry"""
    for key in ("published_parsed", "updated_parsed"):
        t = getattr(entry, key, None)
        if t:
            try:
                return datetime(*t[:6], tzinfo=timezone.utc)
            except Exception:
                pass
    return None


def looks_clickbaity(text: str, patterns: list[str]) -> bool:
    """check if text matches clickbait patterns (FORM not CONTENT)"""
    t = (text or "").lower()
    return any(re.search(p, t, flags=re.IGNORECASE) for p in patterns)


def generate_tldr(headline: str, teaser: str, category: str) -> str | None:
    """generate 'why this might interest you' using Ollama"""
    import subprocess

    prompt = f"""Article: {headline}
Summary: {teaser[:150]}

Write ONE sentence (max 12 words) saying why this matters. Start with a verb.

BANNED words: groundbreaking, innovative, transformative, revolutionary, cutting-edge, game-changing, fascinating, intriguing, compelling, remarkable, unprecedented, paradigm, synergy, leverage, holistic, deep dive, unpack, explore, delve, journey, landscape, robust, scalable, ecosystem

Good examples:
- Overturns a century of physics assumptions.
- Shows how bacteria communicate like neurons.
- Connects ancient philosophy to modern ethics.

Bad examples (DO NOT write like this):
- Offers fascinating insights into...
- Explores the compelling landscape of...
- Presents a groundbreaking approach to...

Your sentence (plain, direct, no fluff):"""

    try:
        result = subprocess.run(
            ["ollama", "run", "llama3.2:3b", prompt],
            capture_output=True,
            text=True,
            timeout=30
        )
        tldr = result.stdout.strip()
        # clean up
        tldr = tldr.strip('"\'.-').strip()
        # remove common preambles
        for prefix in ["This article ", "The article ", "It ", "This "]:
            if tldr.startswith(prefix):
                tldr = tldr[len(prefix):]
                tldr = tldr[0].upper() + tldr[1:] if tldr else tldr
        # truncate if too long (take first sentence)
        if '.' in tldr:
            tldr = tldr.split('.')[0].strip()
        # final length check
        if tldr and 10 < len(tldr) < 120:
            return tldr
    except Exception:
        pass
    return None


def extract_image_url(entry) -> str | None:
    """extract image URL from RSS entry - tries multiple sources"""
    # 1. media:content
    if hasattr(entry, 'media_content') and entry.media_content:
        for mc in entry.media_content:
            url = mc.get('url', '')
            if url and ('image' in mc.get('type', '') or url.endswith(('.jpg', '.png', '.webp'))):
                return url
    # 2. media:thumbnail
    if hasattr(entry, 'media_thumbnail') and entry.media_thumbnail:
        for mt in entry.media_thumbnail:
            if mt.get('url'):
                return mt['url']
    # 3. enclosures
    if hasattr(entry, 'enclosures') and entry.enclosures:
        for enc in entry.enclosures:
            if 'image' in enc.get('type', ''):
                return enc.get('href') or enc.get('url')
    # 4. links with image type
    if hasattr(entry, 'links'):
        for link in entry.links:
            if 'image' in link.get('type', ''):
                return link.get('href')
    # 5. parse content for img tag
    content = getattr(entry, 'content', [{}])
    if content and len(content) > 0:
        html_content = content[0].get('value', '')
        img_match = re.search(r'<img[^>]+src=["\']([^"\']+)["\']', html_content)
        if img_match:
            return img_match.group(1)
    # 6. summary img tag
    summary = getattr(entry, 'summary', '')
    if summary:
        img_match = re.search(r'<img[^>]+src=["\']([^"\']+)["\']', summary)
        if img_match:
            return img_match.group(1)
    return None


# --- database ---

def init_db() -> sqlite3.Connection:
    """init sqlite db for tracking seen articles"""
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS seen_articles (
            url TEXT PRIMARY KEY,
            headline TEXT,
            category TEXT,
            seen_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    return conn


def already_seen(conn: sqlite3.Connection, url: str) -> bool:
    return conn.execute("SELECT 1 FROM seen_articles WHERE url=?", (url,)).fetchone() is not None


def mark_seen(conn: sqlite3.Connection, url: str, headline: str, category: str):
    conn.execute(
        "INSERT OR IGNORE INTO seen_articles (url, headline, category) VALUES (?, ?, ?)",
        (url, headline, category)
    )
    conn.commit()


# --- word count fetcher ---

def check_archive_url(url: str, timeout_sec: int = 5) -> str | None:
    """check if article exists on archive.org"""
    try:
        api_url = f"https://archive.org/wayback/available?url={url}"
        resp = requests.get(api_url, timeout=timeout_sec)
        data = resp.json()
        snapshot = data.get("archived_snapshots", {}).get("closest", {})
        if snapshot.get("available"):
            return snapshot.get("url")
    except Exception:
        pass
    return None


def fetch_wordcount(url: str, timeout_sec: int, user_agent: str) -> int:
    """fetch actual article page and count words (the real quality gate)"""
    try:
        headers = {"User-Agent": user_agent}
        r = requests.get(url, timeout=timeout_sec, headers=headers)
        if r.status_code >= 400 or not r.text:
            return 0

        # strip scripts, styles, navs
        h = re.sub(r"(?is)<(script|style|noscript|nav|footer|header)[^>]*>.*?</\1>", " ", r.text)
        txt = re.sub(r"(?is)<[^>]+>", " ", h)
        txt = re.sub(r"\s+", " ", html.unescape(txt)).strip()

        # count actual words
        return len(re.findall(r"[A-Za-z][A-Za-z'\-]{2,}", txt))
    except Exception:
        return 0


# --- telegram ---

def telegram_send(msg: str):
    """send notification to telegram"""
    if not (BOT_TOKEN and CHAT_ID):
        return
    try:
        requests.post(
            f"{TELEGRAM_API}/sendMessage",
            json={
                "chat_id": CHAT_ID,
                "text": msg,
                "parse_mode": "HTML",
                "disable_web_page_preview": True
            },
            timeout=10
        )
    except Exception:
        pass


# --- candidate scoring ---

@dataclass
class Candidate:
    category: str
    source: str
    url: str
    domain: str
    headline: str
    teaser: str
    published: str
    base_score: float
    word_count: int = 0
    final_score: float = 0.0
    image_url: str = ""


def compute_base_score(c: Candidate, weights: dict, min_teaser: int) -> float:
    """compute initial score from source reputation and teaser quality"""
    # domain reputation
    dw = weights.get("domain_weight", {}).get(c.domain, 0)
    # source name override
    sw = weights.get("source_weight", {}).get(c.source, 0)
    # penalize missing/short teasers (suggests low-effort entry)
    teaser_pen = 0 if (c.teaser and len(c.teaser) >= min_teaser) else -0.5
    return float(dw + sw + teaser_pen)


def compute_final_score(base: float, word_count: int) -> float:
    """final score incorporates word count (depth signal)"""
    # log scale rewards depth without being exponential
    return base + (math.log(max(word_count, 100), 10) if word_count else 0.0)


# --- main ---

def main():
    print("SPS Daily Feed Collector v2")
    print("=" * 50)
    print("Quality gates: word count, source reputation, form patterns")
    print("=" * 50)

    # load configs - prefer simple text files, fall back to JSON
    feeds = load_feeds_txt(FEEDS_TXT) or load_json(FEEDS_FILE, DEFAULT_FEEDS)
    quality = load_json(QUALITY_FILE, DEFAULT_QUALITY)
    weights = load_json(WEIGHTS_FILE, DEFAULT_WEIGHTS)

    # load blocklist from text file (merged with JSON blocklist)
    txt_blocklist = load_blocklist_txt(BLOCKLIST_TXT)

    # extract quality settings
    cutoff = datetime.now(timezone.utc) - timedelta(days=int(quality.get("max_age_days", 7)))
    select_n = int(quality.get("select_per_category", 15))
    overfetch = int(quality.get("overfetch_factor", 4))
    timeout = int(quality.get("timeout_sec", 20))
    ua = str(quality.get("user_agent", DEFAULT_QUALITY["user_agent"]))
    min_words = dict(quality.get("min_words", DEFAULT_QUALITY["min_words"]))
    domain_min = dict(quality.get("domain_min_words", {}))
    blocklist = set(d.lower().strip() for d in quality.get("domain_blocklist", []))
    blocklist.update(txt_blocklist)  # merge text file blocklist
    patterns = list(quality.get("clickbait_patterns", []))
    min_teaser = int(quality.get("min_teaser_length", 60))

    # init db
    conn = init_db()

    # phase 1: collect candidates from all feeds
    print("\n[Phase 1] Collecting from RSS feeds...")
    candidates = {cat: [] for cat in feeds.keys()}
    stats = {"feeds": 0, "entries": 0, "blocked": 0, "clickbait": 0, "old": 0, "seen": 0}

    for category, feed_list in feeds.items():
        print(f"\n  {category.upper()} ({len(feed_list)} sources)")
        for source, feed_url in feed_list:
            stats["feeds"] += 1
            try:
                fp = feedparser.parse(feed_url)
                entries = getattr(fp, "entries", []) or []
            except Exception as e:
                print(f"    {source}: ERROR {e}")
                continue

            added = 0
            for e in entries[:15]:  # limit per feed
                stats["entries"] += 1
                url = clean_text(getattr(e, "link", "") or "")
                if not url:
                    continue

                domain = normalize_domain(url)

                # gate: blocked domain
                if not domain or domain in blocklist:
                    stats["blocked"] += 1
                    continue

                title = clean_text(getattr(e, "title", "") or "")
                summary = clean_text(getattr(e, "summary", "") or getattr(e, "description", "") or "")

                # gate: clickbait form (not content keywords)
                if looks_clickbaity(title, patterns) or looks_clickbaity(summary, patterns):
                    stats["clickbait"] += 1
                    continue

                # gate: too old
                dt = parse_entry_date(e)
                if dt and dt < cutoff:
                    stats["old"] += 1
                    continue

                # gate: already seen
                if already_seen(conn, url):
                    stats["seen"] += 1
                    continue

                # extract image from RSS entry
                image_url = extract_image_url(e) or ""

                c = Candidate(
                    category=category,
                    source=source,
                    url=url,
                    domain=domain,
                    headline=title,
                    teaser=summary[:300],
                    published=dt.isoformat() if dt else "",
                    base_score=0.0,
                    image_url=image_url
                )
                c.base_score = compute_base_score(c, weights, min_teaser)
                candidates[category].append(c)
                added += 1

            if added > 0:
                print(f"    {source}: {added} candidates")

    print(f"\n  Stats: {stats['feeds']} feeds, {stats['entries']} entries")
    print(f"         blocked={stats['blocked']}, clickbait={stats['clickbait']}, old={stats['old']}, seen={stats['seen']}")

    # phase 2: stage top candidates by base score
    print("\n[Phase 2] Staging top candidates by reputation...")
    staged = {}
    for cat, items in candidates.items():
        items.sort(key=lambda x: x.base_score, reverse=True)
        staged[cat] = items[:max(select_n * overfetch, select_n)]
        print(f"  {cat}: {len(staged[cat])} staged (from {len(items)} candidates)")

    # phase 3: fetch word counts (the real quality gate)
    print("\n[Phase 3] Fetching word counts (this takes a while)...")
    kept = {cat: [] for cat in feeds.keys()}
    dropped_short = 0
    total_to_check = sum(len(items) for items in staged.values())
    checked = 0

    for cat, items in staged.items():
        cat_min = int(min_words.get(cat, 700))
        print(f"\n  {cat.upper()} (min {cat_min} words):")

        for c in items:
            checked += 1
            # domain-specific minimum
            required = int(domain_min.get(c.domain, cat_min))
            c.word_count = fetch_wordcount(c.url, timeout, ua)

            if c.word_count < required:
                dropped_short += 1
                if c.word_count > 0:
                    print(f"    [{checked}/{total_to_check}] SKIP {c.word_count}w < {required}w: {c.headline[:40]}...")
                continue

            c.final_score = compute_final_score(c.base_score, c.word_count)

            # check archive.org
            archive_url = check_archive_url(c.url)

            # generate TLDR "why this might interest you"
            tldr = generate_tldr(c.headline, c.teaser, cat)

            article_data = {
                "headline": c.headline,
                "teaser": c.teaser,
                "url": c.url,
                "source": c.source,
                "domain": c.domain,
                "published": c.published,
                "word_count": c.word_count,
                "reading_min": max(1, int(round(c.word_count / 220))),
                "score": round(c.final_score, 2)
            }
            if c.image_url:
                article_data["imageUrl"] = c.image_url
            if archive_url:
                article_data["archiveUrl"] = archive_url
            if tldr:
                article_data["tldr"] = tldr

            kept[cat].append(article_data)
            extras = []
            if archive_url:
                extras.append("archived")
            if tldr:
                extras.append("tldr")
            extras_note = f" [{', '.join(extras)}]" if extras else ""
            print(f"    [{checked}/{total_to_check}] KEEP {c.word_count}w{extras_note}: {c.headline[:40]}...")

        # sort by final score and limit
        kept[cat].sort(key=lambda x: x.get("score", 0), reverse=True)
        kept[cat] = kept[cat][:select_n]

        # mark as seen
        for item in kept[cat]:
            mark_seen(conn, item["url"], item["headline"], cat)

    conn.close()

    # save pending
    PENDING_FILE.write_text(json.dumps(kept, indent=2))

    # summary
    total = sum(len(v) for v in kept.values())
    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    print("\n" + "=" * 50)
    print(f"DONE at {now}")
    print(f"Total pending: {total} articles (dropped {dropped_short} short)")
    for cat in ["science", "philosophy", "society", "books", "essays"]:
        if cat in kept:
            print(f"  {cat}: {len(kept[cat])}")
    print(f"\nPending file: {PENDING_FILE}")

    # telegram notification
    host = socket.gethostname()
    msg = (
        f"<b>SPS Daily Collector v2</b>\n"
        f"<b>Host:</b> {html.escape(host)}\n"
        f"<b>Time:</b> {html.escape(now)}\n"
        f"<b>Pending:</b> {total} articles\n"
        f"  Science: {len(kept.get('science', []))}\n"
        f"  Philosophy: {len(kept.get('philosophy', []))}\n"
        f"  Society: {len(kept.get('society', []))}\n"
        f"  Books: {len(kept.get('books', []))}\n"
        f"  Essays: {len(kept.get('essays', []))}\n"
        f"<b>Dropped (short):</b> {dropped_short}\n\n"
        f"Run <code>telegram_curator_v2.py</code> to review."
    )
    telegram_send(msg)


if __name__ == "__main__":
    main()
