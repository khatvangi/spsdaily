#!/usr/bin/env python3
"""
SPS Daily Feed Collector
Fetches articles from RSS feeds and generates articles.json
"""

import feedparser
import json
import re
from datetime import datetime, timedelta
from pathlib import Path
import html
import random

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

# RSS Feeds organized by category
FEEDS = {
    "science": [
        ("Scientific American", "https://www.scientificamerican.com/feed/"),
        ("New Scientist", "https://www.newscientist.com/feed/home/"),
        ("Nautilus", "https://nautil.us/feed/"),
        ("Quanta Magazine", "https://www.quantamagazine.org/feed/"),
        ("Ars Technica Science", "https://feeds.arstechnica.com/arstechnica/science"),
        ("MIT Tech Review", "https://www.technologyreview.com/feed/"),
        ("Nature News", "https://www.nature.com/nature.rss"),
        ("Science Daily", "https://www.sciencedaily.com/rss/all.xml"),
        ("Discover Magazine", "https://www.discovermagazine.com/rss"),
        ("Big Think", "https://bigthink.com/feed/"),
        ("Wired Science", "https://www.wired.com/feed/category/science/latest/rss"),
        ("Smithsonian", "https://www.smithsonianmag.com/rss/science-nature/"),
    ],
    "philosophy": [
        ("Aeon", "https://aeon.co/feed.rss"),
        ("The New Atlantis", "https://www.thenewatlantis.com/rss"),
        ("Philosophy Now", "https://philosophynow.org/rss"),
        ("Daily Nous", "https://dailynous.com/feed/"),
        ("3 Quarks Daily", "https://3quarksdaily.com/feed/"),
        ("The Point", "https://thepointmag.com/feed/"),
        ("Public Domain Review", "https://publicdomainreview.org/rss.xml"),
        ("Hedgehog Review", "https://hedgehogreview.com/feed"),
        ("The Drift", "https://www.thedriftmag.com/feed/"),
        ("Liberties Journal", "https://libertiesjournal.com/feed/"),
    ],
    "society": [
        ("The Atlantic Ideas", "https://www.theatlantic.com/feed/channel/ideas/"),
        ("Noema Magazine", "https://www.noemamag.com/feed/"),
        ("Boston Review", "https://www.bostonreview.net/feed/"),
        ("Jacobin", "https://jacobin.com/feed/"),
        ("The Baffler", "https://thebaffler.com/feed"),
        ("n+1", "https://www.nplusonemag.com/feed/"),
        ("Current Affairs", "https://www.currentaffairs.org/feed"),
        ("Prospect UK", "https://www.prospectmagazine.co.uk/feed"),
        ("New Statesman", "https://www.newstatesman.com/feed"),
        ("The Conversation", "https://theconversation.com/us/articles.rss"),
        ("JSTOR Daily", "https://daily.jstor.org/feed/"),
        ("Project Syndicate", "https://www.project-syndicate.org/rss"),
    ],
    "books": [
        ("LA Review of Books", "https://lareviewofbooks.org/feed/"),
        ("London Review of Books", "https://www.lrb.co.uk/feed"),
        ("NY Review of Books", "https://www.nybooks.com/feed/"),
        ("The TLS", "https://www.the-tls.co.uk/feed/"),
        ("Literary Hub", "https://lithub.com/feed/"),
        ("Public Books", "https://www.publicbooks.org/feed/"),
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

                # Skip political content in books
                if is_political_content(article['headline'], article['teaser'], category):
                    filtered += 1
                    print(f"    ⚠ Filtered (political): {article['headline'][:50]}...")
                    continue

                seen_headlines.add(headline_lower)
                all_articles[category].append(article)
                added += 1

            status = f"Added {added}"
            if dupes > 0:
                status += f", {dupes} dupes"
            if filtered > 0:
                status += f", {filtered} filtered"
            print(f"    {status}")

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

def main():
    print("🗞️  SPS Daily Feed Collector")
    print("=" * 40)

    # Collect from all feeds
    all_articles = collect_all_feeds()

    # Select best articles
    print("\n✨ Selecting articles...")
    selected = select_articles(all_articles, per_category=3)

    # Generate JSON
    output = generate_json(selected)

    # Write to file
    output_path = Path(__file__).parent.parent / "articles.json"
    with open(output_path, 'w') as f:
        json.dump(output, f, indent=2)

    print(f"\n✅ Generated {output_path}")
    print(f"   Science: {len(output['science'])} articles")
    print(f"   Philosophy: {len(output['philosophy'])} articles")
    print(f"   Society: {len(output['society'])} articles")

if __name__ == "__main__":
    main()
