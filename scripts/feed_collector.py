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
import subprocess

# Ollama configuration
OLLAMA_MODEL_FILTER = "qwen2.5:0.5b"  # Tiny model for YES/NO filtering
OLLAMA_MODEL_TRANSLATE = "qwen3:latest"  # Larger model for translation
USE_AI_FILTER = True  # Set to False to disable AI filtering
USE_WORLD_COLLECTION = True  # Set to False to disable international feeds

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


def ai_translate(text, source_lang, target_lang="English"):
    """Use Ollama to translate text to English."""
    if not text or not text.strip():
        return text

    prompt = f"""Translate the following {source_lang} text to {target_lang}.
Only output the translation, nothing else.

Text: {text}
/no_think"""

    try:
        result = subprocess.run(
            ["ollama", "run", OLLAMA_MODEL_TRANSLATE, prompt],
            capture_output=True,
            text=True,
            timeout=60
        )
        translated = result.stdout.strip()
        # Clean up any thinking tags if present
        if "<think>" in translated:
            translated = translated.split("</think>")[-1].strip()
        return translated if translated else text
    except Exception as e:
        print(f"    Translation error: {e}")
        return text

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

# RSS Feeds organized by category (expanded from Arts & Letters Daily sources)
FEEDS = {
    "science": [
        # Major Science Publications
        ("Scientific American", "https://www.scientificamerican.com/feed/"),
        ("New Scientist", "https://www.newscientist.com/feed/home/"),
        ("Nautilus", "https://nautil.us/feed/"),
        ("Quanta Magazine", "https://www.quantamagazine.org/feed/"),
        ("Nature News", "https://www.nature.com/nature.rss"),
        ("Science Magazine", "https://www.science.org/rss/news_current.xml"),
        ("MIT Tech Review", "https://www.technologyreview.com/feed/"),
        ("Ars Technica Science", "https://feeds.arstechnica.com/arstechnica/science"),
        ("Wired Science", "https://www.wired.com/feed/category/science/latest/rss"),
        # Science Blogs & Magazines
        ("Big Think", "https://bigthink.com/feed/"),
        ("Science Daily", "https://www.sciencedaily.com/rss/all.xml"),
        ("Discover Magazine", "https://www.discovermagazine.com/rss"),
        ("Smithsonian", "https://www.smithsonianmag.com/rss/science-nature/"),
        ("Popular Science", "https://www.popsci.com/feed/"),
        ("Live Science", "https://www.livescience.com/feeds/all"),
        ("Phys.org", "https://phys.org/rss-feed/"),
        ("Science News", "https://www.sciencenews.org/feed"),
        # Edge & Long-form Science
        ("Edge", "https://www.edge.org/feed"),
        ("Knowable Magazine", "https://knowablemagazine.org/rss"),
        ("Undark", "https://undark.org/feed/"),
        ("Massive Science", "https://massivesci.com/feed/"),
    ],
    "philosophy": [
        # Philosophy Magazines
        ("Aeon", "https://aeon.co/feed.rss"),
        ("Philosophy Now", "https://philosophynow.org/rss"),
        ("The New Atlantis", "https://www.thenewatlantis.com/rss"),
        ("IAI News", "https://iai.tv/rss/articles"),
        # Academic Philosophy
        ("Daily Nous", "https://dailynous.com/feed/"),
        ("The Philosophers' Magazine", "https://www.philosophersmag.com/feed"),
        ("Blog of the APA", "https://blog.apaonline.org/feed/"),
        # Ideas & Essays
        ("3 Quarks Daily", "https://3quarksdaily.com/feed/"),
        ("The Point", "https://thepointmag.com/feed/"),
        ("Public Domain Review", "https://publicdomainreview.org/rss.xml"),
        ("Hedgehog Review", "https://hedgehogreview.com/feed"),
        ("The Drift", "https://www.thedriftmag.com/feed/"),
        ("Liberties Journal", "https://libertiesjournal.com/feed/"),
        ("The Marginalia Review", "https://marginalia.lareviewofbooks.org/feed/"),
        # Psyche (Aeon's sister)
        ("Psyche", "https://psyche.co/feed.rss"),
    ],
    "society": [
        # Major Essay Magazines
        ("The Atlantic", "https://www.theatlantic.com/feed/all/"),
        ("The New Yorker", "https://www.newyorker.com/feed/everything"),
        ("The Guardian Long Read", "https://www.theguardian.com/news/series/the-long-read/rss"),
        ("Harper's Magazine", "https://harpers.org/feed/"),
        ("The New Republic", "https://newrepublic.com/rss.xml"),
        ("Slate", "https://slate.com/feeds/all.rss"),
        ("Salon", "https://www.salon.com/feed/"),
        ("Vox", "https://www.vox.com/rss/index.xml"),
        # Ideas & Commentary
        ("Noema Magazine", "https://www.noemamag.com/feed/"),
        ("Boston Review", "https://www.bostonreview.net/feed/"),
        ("The Baffler", "https://thebaffler.com/feed"),
        ("n+1", "https://www.nplusonemag.com/feed/"),
        ("Dissent", "https://www.dissentmagazine.org/feed"),
        ("The American Scholar", "https://theamericanscholar.org/feed/"),
        ("The Conversation", "https://theconversation.com/us/articles.rss"),
        ("JSTOR Daily", "https://daily.jstor.org/feed/"),
        # UK Publications
        ("Prospect UK", "https://www.prospectmagazine.co.uk/feed"),
        ("New Statesman", "https://www.newstatesman.com/feed"),
        ("The Spectator", "https://www.spectator.co.uk/feed"),
        ("UnHerd", "https://unherd.com/feed/"),
        # Commentary & Analysis
        ("Project Syndicate", "https://www.project-syndicate.org/rss"),
        ("Foreign Affairs", "https://www.foreignaffairs.com/rss.xml"),
        ("Foreign Policy", "https://foreignpolicy.com/feed/"),
        ("The Economist 1843", "https://www.economist.com/1843/rss.xml"),
    ],
    "books": [
        # Major Book Reviews
        ("NY Review of Books", "https://www.nybooks.com/feed/"),
        ("London Review of Books", "https://www.lrb.co.uk/feed"),
        ("The TLS", "https://www.the-tls.co.uk/feed/"),
        ("LA Review of Books", "https://lareviewofbooks.org/feed/"),
        ("Literary Hub", "https://lithub.com/feed/"),
        # More Book Reviews
        ("Public Books", "https://www.publicbooks.org/feed/"),
        ("The Paris Review", "https://www.theparisreview.org/feed/"),
        ("Bookforum", "https://www.bookforum.com/feed"),
        ("The Millions", "https://themillions.com/feed"),
        ("Literary Review UK", "https://literaryreview.co.uk/feed"),
        ("Open Letters Review", "https://www.openlettersreview.com/feed"),
        ("The Rumpus", "https://therumpus.net/feed/"),
        # Arts & Culture
        ("Art in America", "https://www.artnews.com/c/art-in-america/feed/"),
        ("Artforum", "https://www.artforum.com/feed/"),
        ("Hyperallergic", "https://hyperallergic.com/feed/"),
    ]
}

# International feeds organized by country/language
# Format: (name, url, language, country)
WORLD_FEEDS = [
    # Germany (German)
    ("Der Spiegel", "https://www.spiegel.de/wissenschaft/index.rss", "German", "Germany"),
    ("Die Zeit Wissen", "https://newsfeed.zeit.de/wissen/index", "German", "Germany"),
    ("FAZ Feuilleton", "https://www.faz.net/rss/aktuell/feuilleton/", "German", "Germany"),

    # France (French)
    ("Le Monde Ideas", "https://www.lemonde.fr/idees/rss_full.xml", "French", "France"),
    ("Philosophie Magazine", "https://www.philomag.com/feed", "French", "France"),
    ("La Vie des Idées", "https://laviedesidees.fr/spip.php?page=backend", "French", "France"),

    # Spain (Spanish)
    ("El País Cultura", "https://feeds.elpais.com/mrss-s/pages/ep/site/elpais.com/section/cultura/portada", "Spanish", "Spain"),
    ("La Vanguardia Cultura", "https://www.lavanguardia.com/rss/cultura.xml", "Spanish", "Spain"),

    # Italy (Italian)
    ("La Repubblica Cultura", "https://www.repubblica.it/rss/cultura/rss2.0.xml", "Italian", "Italy"),
    ("Il Post", "https://www.ilpost.it/feed/", "Italian", "Italy"),

    # Netherlands (Dutch)
    ("NRC", "https://www.nrc.nl/rss/", "Dutch", "Netherlands"),
    ("De Correspondent", "https://decorrespondent.nl/feed", "Dutch", "Netherlands"),

    # Japan (Japanese)
    ("Asahi Shimbun", "https://www.asahi.com/rss/asahi/newsheadlines.rdf", "Japanese", "Japan"),
    ("Nikkei Asia", "https://asia.nikkei.com/rss/feed/nar", "English", "Japan"),

    # China
    ("Caixin Global", "https://www.caixinglobal.com/rss.html", "English", "China"),
    ("Sixth Tone", "https://www.sixthtone.com/rss", "English", "China"),

    # India (English)
    ("The Hindu Opinion", "https://www.thehindu.com/opinion/feeder/default.rss", "English", "India"),
    ("Scroll.in", "https://scroll.in/rss/all", "English", "India"),
    ("The Caravan", "https://caravanmagazine.in/rss-feeds/rss.xml", "English", "India"),

    # Brazil (Portuguese)
    ("Folha de S.Paulo", "https://feeds.folha.uol.com.br/mundo/rss091.xml", "Portuguese", "Brazil"),
    ("Piauí", "https://piaui.folha.uol.com.br/feed/", "Portuguese", "Brazil"),

    # Argentina (Spanish)
    ("La Nación Ideas", "https://www.lanacion.com.ar/arcio/rss/category/ideas/", "Spanish", "Argentina"),

    # Mexico (Spanish)
    ("Letras Libres", "https://letraslibres.com/feed/", "Spanish", "Mexico"),
    ("Nexos", "https://www.nexos.com.mx/?feed=rss2", "Spanish", "Mexico"),

    # Middle East
    ("Al Jazeera Opinion", "https://www.aljazeera.com/xml/rss/all.xml", "English", "Qatar"),
    ("Haaretz", "https://www.haaretz.com/srv/haaretz-latest-headlines", "English", "Israel"),

    # Africa
    ("Mail & Guardian", "https://mg.co.za/feed/", "English", "South Africa"),
    ("Daily Maverick", "https://www.dailymaverick.co.za/feed/", "English", "South Africa"),

    # Australia
    ("The Conversation AU", "https://theconversation.com/au/articles.rss", "English", "Australia"),
    ("Sydney Review of Books", "https://sydneyreviewofbooks.com/feed/", "English", "Australia"),

    # South Korea (Korean)
    ("Hankyoreh", "https://www.hani.co.kr/rss/", "Korean", "South Korea"),

    # Poland (Polish)
    ("Gazeta Wyborcza", "https://wyborcza.pl/0,0.html?disableRedirects=true", "Polish", "Poland"),

    # Czech Republic (Czech)
    ("Respekt", "https://www.respekt.cz/rss", "Czech", "Czech Republic"),

    # Russia (Russian) - independent media
    ("Meduza", "https://meduza.io/rss/all", "Russian", "Russia"),
]

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

def collect_world_feeds():
    """Collect and translate articles from international feeds."""
    if not USE_WORLD_COLLECTION:
        return []

    print("\n🌍 Collecting WORLD feeds...")
    world_articles = []
    seen_headlines = set()

    for name, url, language, country in WORLD_FEEDS:
        print(f"  → {name} ({country})")
        try:
            feed = feedparser.parse(url)
            cutoff = datetime.now() - timedelta(days=7)
            added = 0

            for entry in feed.entries[:5]:  # Limit per source
                published = None
                if hasattr(entry, 'published_parsed') and entry.published_parsed:
                    published = datetime(*entry.published_parsed[:6])
                elif hasattr(entry, 'updated_parsed') and entry.updated_parsed:
                    published = datetime(*entry.updated_parsed[:6])

                if published and published < cutoff:
                    continue

                headline = clean_html(entry.get('title', ''))
                teaser = truncate_teaser(entry.get('summary', entry.get('description', '')))
                link = entry.get('link', '')

                if not headline or not link:
                    continue

                # Skip duplicates
                headline_lower = headline.lower().strip()
                if headline_lower in seen_headlines:
                    continue
                seen_headlines.add(headline_lower)

                # Translate if not English
                if language != "English":
                    print(f"    Translating: {headline[:40]}...")
                    headline = ai_translate(headline, language)
                    if teaser:
                        teaser = ai_translate(teaser, language)

                world_articles.append({
                    "headline": headline,
                    "teaser": teaser,
                    "source": f"{name} ({country})",
                    "url": link,
                    "country": country,
                    "language": language,
                    "published": published.isoformat() if published else None
                })
                added += 1

            print(f"    Added {added} articles")

        except Exception as e:
            print(f"    Error: {e}")

    return world_articles


def collect_all_feeds():
    """Collect articles from all feeds"""
    all_articles = {
        "science": [],
        "philosophy": [],
        "society": [],
        "books": [],
        "world": []
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

    # Add world if we have any
    if selected.get('world'):
        output["world"] = selected['world']

    return output

def main():
    print("🗞️  SPS Daily Feed Collector")
    print("=" * 40)

    # Collect from all feeds
    all_articles = collect_all_feeds()

    # Collect world feeds (with translation)
    world_articles = collect_world_feeds()
    all_articles["world"] = world_articles

    # Select best articles (15 per category - front page shows 6, category pages show all)
    print("\n✨ Selecting articles...")
    selected = select_articles(all_articles, per_category=15)

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
    print(f"   Books: {len(output.get('books', []))} articles")
    print(f"   World: {len(output.get('world', []))} articles")

if __name__ == "__main__":
    main()
