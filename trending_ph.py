"""
trending_ph.py — Fetch real-time trending topics in the Philippines.

Sources (all free, no API key required):
  1. Reddit r/Philippines + r/PHCelebrity hot posts (public JSON, no auth)
  2. Google Trends daily trending searches (direct API, no pytrends)
  3. Rappler RSS feed (entertainment/news)

Returns a ranked list of trending stories with context for hugot lyrics.
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

def _get_reddit_ph(subreddits: list[str] = None, limit: int = 20) -> list[dict]:
    """Fetch hot posts from Philippine subreddits. No auth required."""
    if subreddits is None:
        subreddits = ["Philippines", "phlgbt", "OFW", "OffMyChestPH"]

    stories = []
    for sub in subreddits:
        try:
            url = f"https://www.reddit.com/r/{sub}/hot.json?limit={limit}"
            resp = requests.get(url, headers={"User-Agent": _REDDIT_UA}, timeout=10)
            resp.raise_for_status()
            posts = resp.json()["data"]["children"]
            for p in posts:
                d = p["data"]
                if d.get("stickied") or d.get("pinned"):
                    continue
                title = d.get("title", "")
                selftext = (d.get("selftext", "") or "")[:300]
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
        subreddits=["Philippines", "OFW", "phlgbt"],
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
    "OffMyChestPH",
    "relationship_advice",
    "phlgbt",
    "BreakUps",
    "TrueOffMyChest",
    "heartbreak",
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
                if d.get("stickied") or d.get("pinned"):
                    continue
                title = d.get("title", "")
                selftext = (d.get("selftext", "") or "").strip()
                if len(selftext) < 100:
                    continue  # skip link-only or very short posts
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
    # For Reddit love stories with rich selftext, pass the actual story
    if "reddit" in source and len(desc) > 100:
        sub = source.split("/")[-1]
        context = f'Real story shared by a Filipino on r/{sub}:\n\nTitle: "{title}"\n\n{desc[:600]}'
    else:
        context = f'Trending in the Philippines ({cat}): "{title}"'
        if desc and desc.strip() and desc.strip() != title:
            context += f" — {desc[:200]}"
    return context


if __name__ == "__main__":
    print("Fetching trending PH stories...\n")
    stories = get_trending_ph(max_results=20)
    print(f"\nTop {len(stories)} trending stories:\n")
    for i, s in enumerate(stories, 1):
        print(f"{i:2}. [{s['hugot_score']:2d}★] [{s['category']:20s}] {s['title'][:65]}")
    print()
    best = pick_hugot_story(stories)
    print(f"Best for hugot: {best['title']}")
    print(f"Context: {format_story_context(best)}")
