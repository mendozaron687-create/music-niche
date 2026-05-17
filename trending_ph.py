"""
trending_ph.py — Fetch real-time trending topics in the Philippines.

Sources (all free, no API key required):
  1. YouTube trending PH (YouTube Data API v3 if YOUTUBE_DATA_API_KEY set,
     else pytrends gprop='youtube', else Google Trends daily)
  2. Google Trends daily trending searches in PH (direct API, no auth)
  3. Reddit r/Philippines hot posts (fallback for love stories)

Genre auto-classification:
  - political/government keywords → 'pinoy_rant'
  - love/heartbreak → 'hugot_ballad' / 'hugot_opm_pop'
  - celebrity/entertainment → 'hugot_opm_pop'
  - default → random hugot genre

Returns a ranked list of trending stories with context for music lyrics.
"""

import os
import re
import json
import time
import random
import requests
from datetime import datetime

_USED_STORIES_FILE = os.path.join(os.path.dirname(__file__), "used_stories.json")


def _story_key(story: dict) -> str:
    """Stable dedup key — Reddit post ID from permalink, else title slug."""
    link = story.get("link", "")
    if "/comments/" in link:
        # e.g. https://reddit.com/r/Philippines/comments/abc123/title/
        return link.split("/comments/")[1].split("/")[0]
    return re.sub(r"\W+", "", story.get("title", "").lower())[:40]


def _load_used_ids() -> set:
    if not os.path.exists(_USED_STORIES_FILE):
        return set()
    try:
        with open(_USED_STORIES_FILE) as f:
            return set(json.load(f).get("used", []))
    except Exception:
        return set()


def _mark_story_used(story: dict):
    used = _load_used_ids()
    used.add(_story_key(story))
    try:
        with open(_USED_STORIES_FILE, "w") as f:
            json.dump({"used": list(used)}, f, indent=2)
    except Exception as e:
        print(f"[trending_ph] Could not save used_stories.json: {e}")


_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )
}

_REDDIT_UA = "PH-Hugot-MusicBot/1.0 (music automation)"


_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )
}

_REDDIT_UA = "PH-Hugot-MusicBot/1.0 (music automation)"

# Keywords that score a story higher for hugot music relevance
HUGOT_KEYWORDS = [
    # High-value breakup/love keywords (score 3)
    "breakup", "break up", "split", "annulment", "hiwalay", "third party",
    "kabit", "cheated", "heartbreak", "sawi", "nag-break", "naghiwalay", "iniwan",
    # Medium-value love/emotion keywords (score 2)
    "separation", "ex", "kilig", "selos", "jealous", "puso", "mahal",
    "nabigo", "nasaktan", "loneliness", "nagtanan", "umalis",
    # Celebrity/viral drama (score 2)
    "scandal", "viral", "issue", "kontrobersya", "artista", "celebrity",
    "bashers", "netizens", "fans", "relationship",
    # Relatable Filipino struggles (score 1)
    "OFW", "utang", "trabaho", "jobless", "stress", "pagod", "gipit",
    "inflation", "gastos", "hanapbuhay", "moving on", "alone", "lonely",
    "naiyak", "malungkot", "nag-iisa", "sakit", "luha", "pag-ibig",
]

_HIGH_SCORE_KW = {
    "breakup", "break up", "split", "annulment", "hiwalay", "third party",
    "kabit", "cheated", "heartbreak", "sawi", "nag-break", "naghiwalay", "iniwan",
}


def _hugot_score(text: str) -> int:
    lower = text.lower()
    score = 0
    for kw in HUGOT_KEYWORDS:
        if kw in lower:
            score += 3 if kw in _HIGH_SCORE_KW else (2 if len(kw) > 5 else 1)
    return score


# ── Source 1: Reddit ─────────────────────────────────────────────────────────

# Keywords that indicate NSFW/sensitive content — skip these stories entirely
# to avoid YouTube age-restriction, self-harm flags, or content suppression.
_NSFW_BLOCKLIST = [
    # Sexual
    "sex", "nakipagtalik", "ginalaw", "nilasog", "sexual", "rape", "molestation",
    "harrassed", "nude", "nudes", "onlyfans", "porn", "kantot",
    # Self-harm / suicide (YouTube sensitive topics policy)
    "suicide", "nagpakamatay", "self-harm", "self harm", "nagputol", "gusto na mamatay",
    "buhay mo", "pumatay", "magpakamatay",
    # Extreme violence
    "murder", "pinatay", "napatay", "dismember",
]


def _is_safe_story(title: str, selftext: str = "") -> bool:
    """Return False if a Reddit story contains NSFW or policy-sensitive content."""
    combined = (title + " " + selftext).lower()
    return not any(kw in combined for kw in _NSFW_BLOCKLIST)


def _get_reddit_ph(subreddits: list[str] = None, limit: int = 20) -> list[dict]:
    """Fetch hot posts from Philippine subreddits. No auth required."""
    if subreddits is None:
        # Only safe, family-friendly PH subreddits — avoids age-restriction on YouTube
        subreddits = ["Philippines", "OFW", "phtrending"]

    stories = []
    for sub in subreddits:
        try:
            url = f"https://www.reddit.com/r/{sub}/hot.json?limit={limit}"
            resp = requests.get(url, headers={"User-Agent": _REDDIT_UA}, timeout=10)
            resp.raise_for_status()
            posts = resp.json()["data"]["children"]
            for p in posts:
                d = p["data"]
                if d.get("stickied") or d.get("pinned") or d.get("over_18"):
                    continue
                title = d.get("title", "")
                selftext = (d.get("selftext", "") or "")[:300]
                if not _is_safe_story(title, selftext):
                    print(f"[trending_ph] Skipped NSFW/sensitive post: {title[:60]}")
                    continue
                combined = f"{title} {selftext}"
                stories.append({
                    "title": title,
                    "description": selftext[:200],
                    "link": f"https://reddit.com{d.get('permalink', '')}",
                    "published": datetime.fromtimestamp(d.get("created_utc", 0)).strftime(
                        "%a, %d %b %Y %H:%M:%S +0800"
                    ),
                    "category": f"reddit_r/{sub}",
                    "source": f"reddit/{sub}",
                    "hugot_score": _hugot_score(combined),
                    "upvotes": d.get("score", 0),
                })
            time.sleep(0.5)
        except Exception as e:
            print(f"[trending_ph] Reddit r/{sub} failed: {e}")
    return stories


# ── Source 2: Google Trends PH (direct API) ───────────────────────────────────

def _get_google_trends_ph(count: int = 15) -> list[dict]:
    """
    Fetch daily trending searches in PH via Google Trends unofficial API.
    No API key or pytrends needed.
    """
    try:
        url = (
            "https://trends.google.com/trends/api/dailytrends"
            "?hl=en-US&tz=-480&geo=PH&ns=15"
        )
        resp = requests.get(url, headers=_HEADERS, timeout=12)
        if resp.status_code != 200:
            raise RuntimeError(f"HTTP {resp.status_code}")

        # Response is JSONP — strip the leading ")]}'\n"
        raw = resp.text
        json_start = raw.find("{")
        data = json.loads(raw[json_start:])

        days = data.get("default", {}).get("trendingSearchesDays", [])
        results = []
        for day in days[:2]:  # Today + yesterday
            for trend in day.get("trendingSearches", [])[:count]:
                query = trend.get("title", {}).get("query", "")
                articles = trend.get("articles", [])
                snippet = articles[0].get("snippet", "") if articles else ""
                combined = f"{query} {snippet}"
                results.append({
                    "title": query,
                    "description": snippet[:200],
                    "link": trend.get("title", {}).get("exploreLink", ""),
                    "published": datetime.now().strftime("%a, %d %b %Y %H:%M:%S +0800"),
                    "category": "google_trends",
                    "source": "google_trends",
                    "hugot_score": _hugot_score(combined),
                    "upvotes": int(trend.get("formattedTraffic", "0+").replace("+", "").replace("K", "000")),
                })
        return results
    except Exception as e:
        print(f"[trending_ph] Google Trends PH error: {e}")
        return []


# ── Main functions ────────────────────────────────────────────────────────────

def get_trending_ph(max_results: int = 15) -> list[dict]:
    """
    Fetch trending stories/topics from the Philippines.
    Returns list of dicts sorted by hugot_score (desc).
    """
    all_stories = []

    print("[trending_ph] Fetching Google Trends PH...")
    all_stories.extend(_get_google_trends_ph(count=15))

    print("[trending_ph] Fetching Reddit r/Philippines...")
    all_stories.extend(_get_reddit_ph(
        subreddits=["Philippines", "OFW", "phtrending"],
        limit=20,
    ))

    # Deduplicate by title (first 35 chars, normalized)
    seen = set()
    unique = []
    for s in all_stories:
        key = re.sub(r"\W+", "", s["title"].lower())[:35]
        if key not in seen and s["title"].strip():
            seen.add(key)
            unique.append(s)

    unique.sort(key=lambda x: x["hugot_score"], reverse=True)
    return unique[:max_results]


# ── Love story sources (for hugot genres) ────────────────────────────────────

_LOVE_STORY_SUBREDDITS = [
    "relationship_advice",
    "BreakUps",
    "TrueOffMyChest",
    "heartbreak",
    "Philippines",
]

_LOVE_KEYWORDS = [
    "love", "heartbreak", "breakup", "sawi", "mahal", "ex", "crush",
    "relationship", "boyfriend", "girlfriend", "asawa", "karelasyon",
    "nasaktan", "iniwan", "cheated", "kabit", "kilig", "miss",
    "long distance", "ldr", "unrequited", "pag-ibig", "nag-iisa",
    "hiwalay", "naghiwalay", "third party", "broken",
]


def _get_reddit_love_stories(limit: int = 25) -> list[dict]:
    """
    Fetch real personal love stories from PH Reddit communities.
    Only includes posts with actual story content (selftext >= 100 chars).
    """
    stories = []
    for sub in _LOVE_STORY_SUBREDDITS:
        try:
            url = f"https://www.reddit.com/r/{sub}/hot.json?limit={limit}"
            resp = requests.get(url, headers={"User-Agent": _REDDIT_UA}, timeout=10)
            resp.raise_for_status()
            posts = resp.json()["data"]["children"]
            for p in posts:
                d = p["data"]
                if d.get("stickied") or d.get("pinned") or d.get("over_18"):
                    continue
                title = d.get("title", "")
                selftext = (d.get("selftext", "") or "").strip()
                if len(selftext) < 100:
                    continue  # skip link-only or very short posts
                if not _is_safe_story(title, selftext):
                    print(f"[trending_ph] Skipped NSFW love story: {title[:60]}")
                    continue
                combined = f"{title} {selftext}"
                score = _hugot_score(combined)
                love_hits = sum(1 for kw in _LOVE_KEYWORDS if kw in combined.lower())
                if love_hits == 0:
                    continue  # skip posts with zero love/relationship keywords
                score += love_hits
                stories.append({
                    "title": title,
                    "description": selftext[:600],  # richer story context
                    "link": f"https://reddit.com{d.get('permalink', '')}",
                    "published": datetime.fromtimestamp(d.get("created_utc", 0)).strftime(
                        "%a, %d %b %Y %H:%M:%S +0800"
                    ),
                    "category": f"reddit_r/{sub}",
                    "source": f"reddit/{sub}",
                    "hugot_score": score,
                    "upvotes": d.get("score", 0),
                })
            time.sleep(0.5)
        except Exception as e:
            print(f"[trending_ph] Reddit r/{sub} failed: {e}")

    stories.sort(
        key=lambda x: x["hugot_score"] * 3 + min(x["upvotes"] // 10, 30),
        reverse=True,
    )
    return stories


def get_ph_love_stories(max_results: int = 10) -> list[dict]:
    """
    Fetch real Filipino love/heartbreak stories from Reddit for hugot lyrics inspiration.
    Filters out already-used stories (dedup via used_stories.json).
    Falls back to get_trending_ph() if no stories with selftext are found.
    """
    print("[trending_ph] Fetching PH love stories from Reddit...")
    stories = _get_reddit_love_stories(limit=30)
    if stories:
        used = _load_used_ids()
        fresh = [s for s in stories if _story_key(s) not in used]
        if len(fresh) >= 3:
            stories = fresh
            print(f"[trending_ph] Found {len(stories)} fresh (unused) love stories")
        else:
            print(f"[trending_ph] Found {len(stories)} love stories (few unused, reusing pool)")
        return stories[:max_results]
    print("[trending_ph] No story posts found, falling back to trending topics...")
    return get_trending_ph(max_results=max_results)


def pick_hugot_story(stories: list[dict]) -> dict:
    """
    Pick the best story for hugot music inspiration.
    Prefers high hugot_score; adds randomness from top-5 to avoid repetition.
    """
    if not stories:
        return {
            "title": "Pagmamahal na Walang Katumbas",
            "description": "A love story that was never meant to be",
            "category": "entertainment",
            "hugot_score": 0,
        }
    top = stories[:5]
    story = random.choice(top)
    _mark_story_used(story)
    return story


def format_story_context(story: dict) -> str:
    """Format a story dict into a context string for the LLM prompt."""
    title = story.get("title", "")
    desc = story.get("description", "")
    source = story.get("source", "")
    cat = story.get("category", "")
    if "reddit" in source and len(desc) > 100:
        sub = source.split("/")[-1]
        context = f'Real story shared by a Filipino on r/{sub}:\n\nTitle: "{title}"\n\n{desc[:600]}'
    else:
        context = f'Trending in the Philippines ({cat}): "{title}"'
        if desc and desc.strip() and desc.strip() != title:
            context += f" — {desc[:200]}"
    return context


# ── YouTube PH Trending ───────────────────────────────────────────────────────

# Keywords for political/rant classification
_POLITICS_KEYWORDS = [
    "duterte", "marcos", "bbm", "sara", "leni", "pangulo", "presidente",
    "senado", "senador", "kongreso", "batasang pambansa", "halalan",
    "eleksyon", "gobyerno", "government", "politician", "politics",
    "corruption", "kurakot", "plunder", "bribe", "scandal", "impeach",
    "resign", "nalaman", "pork barrel", "pdaf", "cha-cha", "federalism",
    "budget", "dpwh", "doh", "deped", "military", "afp", "pnp",
    "akap", "makabayan", "ayuda", "subsidy", "tax", "buwis",
    "red-tag", "communist", "npa", "drug war", "ejtf", "pcso",
    "laglag bala", "coast guard", "china", "west philippine sea",
    "south china sea", "spratly", "panatag", "kalayaan", "rotc",
]

_ENTERTAINMENT_KEYWORDS = [
    "celebrity", "artista", "singer", "actor", "actress", "showbiz",
    "abs-cbn", "gma", "tv5", "kapamilya", "kapuso", "kapuso",
    "opm", "concert", "fans", "bashers", "issue", "kontrobersya",
    "viral", "trending", "tiktok", "instagram", "youtube",
    "bb pilipinas", "ms universe", "miss world", "gilas", "pba",
    "kathniel", "jadine", "lizquen", "aldub", "donbelle",
]

_RANT_TOPIC_SCORE_KEYWORDS = _POLITICS_KEYWORDS + [
    "inflation", "presyo", "mahal", "gastos", "taas ng presyo",
    "traffic", "trapik", "baha", "flood", "brownout", "water shortage",
    "no water", "no electricity", "poverty", "kahirapan", "gutom",
]


def _rant_score(text: str) -> int:
    lower = text.lower()
    return sum(3 for kw in _RANT_TOPIC_SCORE_KEYWORDS if kw in lower)


def classify_topic_genre(title: str, description: str = "") -> str:
    """
    Classify a trending topic into a music genre key.
    Returns one of: 'pinoy_rant', 'hugot_ballad', 'hugot_opm_pop',
                    'pinoy_rap_hugot', 'opm_rnb_hugot', 'pamana_folk_opm'
    """
    combined = (title + " " + description).lower()

    # Political / social issue → rant music
    if any(kw in combined for kw in _POLITICS_KEYWORDS):
        return "pinoy_rant"

    # Strong heartbreak/love signals → hugot ballad
    high_love = [
        "breakup", "break up", "hiwalay", "third party", "kabit",
        "cheated", "heartbreak", "sawi", "annulment",
    ]
    if any(kw in combined for kw in high_love):
        return "hugot_ballad"

    # Entertainment/celebrity drama → OPM pop (lighter hugot)
    if any(kw in combined for kw in _ENTERTAINMENT_KEYWORDS):
        return "hugot_opm_pop"

    # General love/relationship → randomly pick a hugot variant
    love_general = ["love", "pag-ibig", "mahal", "ex", "kilig", "selos", "relationship"]
    if any(kw in combined for kw in love_general):
        return random.choice(["hugot_ballad", "hugot_opm_pop", "opm_rnb_hugot"])

    # Default: random OPM genre
    return random.choice(["hugot_opm_pop", "hugot_ballad", "pamana_folk_opm"])


def get_youtube_trending_ph(max_results: int = 20) -> list[dict]:
    """
    Fetch trending YouTube topics/searches in the Philippines.

    Priority:
      1. YouTube Data API v3 (most popular videos — requires YOUTUBE_DATA_API_KEY in .env)
      2. pytrends gprop='youtube' (YouTube-specific search trends, no key needed)
      3. Google Trends daily PH (general trending fallback)

    Returns list of story dicts with 'genre_key' field set.
    """
    results = []

    # ── 1. YouTube Data API v3 ────────────────────────────────────────────
    yt_key = os.getenv("YOUTUBE_DATA_API_KEY", "")
    if yt_key:
        try:
            print("[trending_yt] Fetching YouTube trending PH via Data API v3...")
            # News & Politics (25), Entertainment (24), Music (10)
            for cat_id, cat_name in [("25", "politics"), ("24", "entertainment"), ("10", "music")]:
                resp = requests.get(
                    "https://www.googleapis.com/youtube/v3/videos",
                    params={
                        "part": "snippet",
                        "chart": "mostPopular",
                        "regionCode": "PH",
                        "videoCategoryId": cat_id,
                        "maxResults": 10,
                        "key": yt_key,
                    },
                    timeout=15,
                )
                if resp.status_code != 200:
                    continue
                for item in resp.json().get("items", []):
                    snippet = item.get("snippet", {})
                    title = snippet.get("title", "")
                    desc = snippet.get("description", "")[:300]
                    channel = snippet.get("channelTitle", "")
                    genre_key = classify_topic_genre(title, desc)
                    rant = _rant_score(title + " " + desc)
                    results.append({
                        "title": title,
                        "description": desc,
                        "link": f"https://youtube.com/watch?v={item.get('id', '')}",
                        "published": snippet.get("publishedAt", ""),
                        "category": f"youtube_{cat_name}",
                        "source": "youtube_trending",
                        "channel": channel,
                        "hugot_score": _hugot_score(title + " " + desc),
                        "rant_score": rant,
                        "genre_key": genre_key,
                    })
            if results:
                print(f"[trending_yt] Got {len(results)} YouTube trending videos (Data API)")
                return results[:max_results]
        except Exception as e:
            print(f"[trending_yt] YouTube Data API failed: {e}")

    # ── 2. pytrends — YouTube-specific search trends ──────────────────────
    try:
        from pytrends.request import TrendReq
        print("[trending_yt] Fetching YouTube search trends (PH) via pytrends...")
        pt = TrendReq(hl="en-PH", tz=480, timeout=(10, 25))
        # Get trending searches on YouTube in PH using realtime_trending_searches
        df = pt.realtime_trending_searches(pn="PH")
        if df is not None and not df.empty:
            for _, row in df.head(max_results).iterrows():
                title = str(row.get("title", "")).strip()
                if not title:
                    continue
                desc = str(row.get("entityNames", "")).strip()[:200]
                genre_key = classify_topic_genre(title, desc)
                rant = _rant_score(title + " " + desc)
                results.append({
                    "title": title,
                    "description": desc,
                    "link": "",
                    "published": datetime.now().strftime("%a, %d %b %Y %H:%M:%S +0800"),
                    "category": "youtube_trends",
                    "source": "pytrends_youtube",
                    "hugot_score": _hugot_score(title + " " + desc),
                    "rant_score": rant,
                    "genre_key": genre_key,
                })
            if results:
                print(f"[trending_yt] Got {len(results)} YouTube trends (pytrends realtime)")
                return results[:max_results]
    except ImportError:
        print("[trending_yt] pytrends not installed — pip install pytrends")
    except Exception as e:
        print(f"[trending_yt] pytrends failed: {e}")

    # ── 3. pytrends daily trending (YouTube gprop) ────────────────────────
    try:
        from pytrends.request import TrendReq
        pt = TrendReq(hl="en-PH", tz=480, timeout=(10, 25))
        df_daily = pt.trending_searches(pn="philippines")
        if df_daily is not None and not df_daily.empty:
            for row in df_daily[0].tolist()[:max_results]:
                title = str(row).strip()
                genre_key = classify_topic_genre(title)
                rant = _rant_score(title)
                results.append({
                    "title": title,
                    "description": "",
                    "link": "",
                    "published": datetime.now().strftime("%a, %d %b %Y %H:%M:%S +0800"),
                    "category": "google_trends_ph",
                    "source": "pytrends_daily",
                    "hugot_score": _hugot_score(title),
                    "rant_score": rant,
                    "genre_key": genre_key,
                })
            if results:
                print(f"[trending_yt] Got {len(results)} daily PH trends (pytrends)")
                return results[:max_results]
    except Exception:
        pass

    # ── 4. Google Trends daily PH (no key) — final fallback ──────────────
    print("[trending_yt] Falling back to Google Trends daily PH...")
    gtrends = _get_google_trends_ph(count=max_results)
    for s in gtrends:
        genre_key = classify_topic_genre(s["title"], s.get("description", ""))
        rant = _rant_score(s["title"] + " " + s.get("description", ""))
        s["genre_key"] = genre_key
        s["rant_score"] = rant
    return gtrends[:max_results]


def pick_trending_story(stories: list[dict]) -> tuple[dict, str]:
    """
    Pick the best story from YouTube/Google trending for music inspiration.
    Returns (story_dict, genre_key).

    - Political topics → pinoy_rant
    - Love/celebrity → hugot variants
    - Prefers high rant_score or hugot_score depending on topic
    """
    if not stories:
        return (
            {
                "title": "Pagod na Pagod Na Ako sa Sistemang Ito",
                "description": "Filipino frustration with daily struggles",
                "category": "social",
                "genre_key": "pinoy_rant",
            },
            "pinoy_rant",
        )

    # Sort: political stories first (by rant_score), then hugot
    rant_stories = sorted(
        [s for s in stories if s.get("rant_score", 0) >= 3],
        key=lambda x: x.get("rant_score", 0),
        reverse=True,
    )
    hugot_stories = sorted(
        [s for s in stories if s.get("rant_score", 0) < 3],
        key=lambda x: x.get("hugot_score", 0),
        reverse=True,
    )

    # Pick from the top candidates (with some randomness)
    pool = (rant_stories[:3] if rant_stories else []) + (hugot_stories[:3] if hugot_stories else [])
    if not pool:
        pool = stories[:5]

    story = random.choice(pool[:5])
    _mark_story_used(story)
    genre_key = story.get("genre_key", classify_topic_genre(story["title"]))
    return story, genre_key


def format_trending_context(story: dict) -> str:
    """Format a YouTube/Google trending story for the LLM prompt."""
    title = story.get("title", "")
    desc = story.get("description", "")
    source = story.get("source", "youtube_trending")
    cat = story.get("category", "trending")
    channel = story.get("channel", "")

    if "youtube" in source:
        src_label = f"YouTube PH trending video"
        if channel:
            src_label += f" from {channel}"
    else:
        src_label = f"Trending in the Philippines"

    context = f'{src_label}: "{title}"'
    if desc and desc.strip() and desc.strip()[:50] != title[:50]:
        context += f"\n\n{desc[:400]}"
    return context


# ── PH News RSS ────────────────────────────────────────────────────────────

_PH_NEWS_RSS_FEEDS = [
    ("Rappler",         "https://www.rappler.com/feed/"),
    ("GMA News",        "https://data.gmanetwork.com/gno/rss/news/feed.xml"),
    ("Inquirer",        "https://newsinfo.inquirer.net/feed"),
    ("Philippine Star", "https://www.philstar.com/rss/headlines"),
    ("ABS-CBN",         "https://news.abs-cbn.com/rss/news"),
]


def _get_ph_news_rss(max_per_feed: int = 8) -> list[dict]:
    """Fetch latest PH headlines from news RSS feeds. No API key needed."""
    import xml.etree.ElementTree as ET
    stories = []
    for source_name, url in _PH_NEWS_RSS_FEEDS:
        try:
            resp = requests.get(url, headers=_HEADERS, timeout=12)
            if resp.status_code != 200:
                print(f"[news_rss] {source_name}: HTTP {resp.status_code}")
                continue
            root = ET.fromstring(resp.content)
            # Standard RSS <item> tags
            items = root.findall(".//item")
            # Atom feed fallback
            if not items:
                items = (
                    root.findall(".//entry")
                    or root.findall(".//{http://www.w3.org/2005/Atom}entry")
                )
            count = 0
            for item in items:
                title_el = item.find("title")
                _desc = item.find("description")
                if _desc is None:
                    _desc = item.find("summary")
                if _desc is None:
                    _desc = item.find("{http://www.w3.org/2005/Atom}summary")
                desc_el = _desc
                link_el = item.find("link")
                _pub = item.find("pubDate")
                if _pub is None:
                    _pub = item.find("published")
                pub_el = _pub
                title = (title_el.text or "").strip() if title_el is not None else ""
                desc = (desc_el.text or "").strip() if desc_el is not None else ""
                # Strip HTML tags from description
                desc = re.sub(r"<[^>]+>", " ", desc).strip()[:400]
                link_text = (link_el.text or "").strip() if link_el is not None else ""
                if not title:
                    continue
                combined = f"{title} {desc}"
                genre_key = classify_topic_genre(title, desc)
                stories.append({
                    "title": title,
                    "description": desc,
                    "link": link_text,
                    "published": (pub_el.text or "") if pub_el is not None else "",
                    "category": source_name.lower().replace(" ", "_"),
                    "source": source_name,
                    "hugot_score": _hugot_score(combined),
                    "rant_score": _rant_score(combined),
                    "genre_key": genre_key,
                })
                count += 1
                if count >= max_per_feed:
                    break
            if count:
                print(f"[news_rss] {source_name}: {count} headlines")
        except Exception as e:
            print(f"[news_rss] {source_name} failed: {e}")
    return stories


def get_ph_news_trending(max_results: int = 20) -> list[dict]:
    """
    Fetch trending news stories in the Philippines.

    Priority:
      1. PH news RSS feeds (Rappler, GMA, Inquirer, PhilStar, ABS-CBN) — no key needed
      2. Google Trends daily PH (fallback if RSS fails)

    Returns list of story dicts compatible with pick_trending_story().
    """
    print("[news] Fetching PH news RSS feeds...")
    stories = _get_ph_news_rss(max_per_feed=8)

    if stories:
        # Deduplicate by normalized title slug
        seen = set()
        unique = []
        for s in stories:
            key = re.sub(r"\W+", "", s["title"].lower())[:35]
            if key not in seen and s["title"].strip():
                seen.add(key)
                unique.append(s)
        # Sort: political/rant news first, then by freshness (preserve RSS order = newest first)
        unique.sort(key=lambda x: x.get("rant_score", 0) * 2 + x.get("hugot_score", 0), reverse=True)
        print(f"[news] {len(unique)} unique headlines ready")
        return unique[:max_results]

    # Fallback: Google Trends PH daily
    print("[news] RSS feeds unavailable — falling back to Google Trends PH...")
    gtrends = _get_google_trends_ph(count=max_results)
    for s in gtrends:
        if "genre_key" not in s:
            s["genre_key"] = classify_topic_genre(s["title"], s.get("description", ""))
        if "rant_score" not in s:
            s["rant_score"] = _rant_score(s["title"] + " " + s.get("description", ""))
    return gtrends[:max_results]


if __name__ == "__main__":
    print("Fetching PH trending news...\n")
    stories = get_ph_news_trending(max_results=20)
    print(f"\nTop {len(stories)} news stories:\n")
    for i, s in enumerate(stories, 1):
        print(f"{i:2}. [{s.get('rant_score',0):2d}🔥|{s['hugot_score']:2d}💔] "
              f"[{s.get('genre_key','?'):20s}] {s['title'][:60]}")
    print()
    best, genre = pick_trending_story(stories)
    print(f"Best pick ({genre}): {best['title']}")
    print(f"Context:\n{format_trending_context(best)}")
