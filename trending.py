"""
trending.py – Fetch real-time trending topics scored for high YouTube Shorts CTR.

Free sources (no API key required):
  • Google Trends  via pytrends  (daily trending searches)
  • Reddit hot posts             (public JSON, no auth)
  • HackerNews top stories       (official free API)

Optional keyed sources (add to .env for more signal):
  • GNEWS_API_KEY    → GNews   (100 free req/day,  https://gnews.io)
  • NEWSDATA_API_KEY → NewsData (200 free req/day, https://newsdata.io)
"""

import os
import re
import requests
from dotenv import load_dotenv

load_dotenv()

# ── CTR power-word list ───────────────────────────────────────────────────────
# These words consistently drive higher click-through on YouTube Shorts
POWER_WORDS = [
    "how", "why", "secret", "truth", "mistake", "never", "always",
    "exposed", "revealed", "shocking", "surprising", "warning", "stop",
    "best", "worst", "banned", "hidden", "hack", "trick", "instantly",
    "fast", "easy", "free", "money", "rich", "broke", "fired", "quit",
    "viral", "trending", "ai", "chatgpt", "nobody", "every", "real",
    "actually", "wrong", "scary", "danger", "illegal", "million", "billionaire",
]

# ── Niche → scoring keywords ──────────────────────────────────────────────────
NICHE_KEYWORDS = {
    "finance":         ["money", "invest", "stock", "crypto", "budget", "debt",
                        "salary", "income", "passive", "savings", "wealth", "bank",
                        "tax", "credit", "loan", "retire", "rich", "broke"],
    "health_wellness": ["health", "fitness", "diet", "workout", "sleep", "stress",
                        "weight", "fat", "muscle", "mental", "anxiety", "calories",
                        "food", "eating", "running", "exercise", "vitamin"],
    "technology":      ["ai", "tech", "robot", "app", "software", "hack", "cyber",
                        "openai", "chatgpt", "phone", "data", "startup", "google",
                        "apple", "meta", "tesla", "chip", "quantum"],
    "business":        ["business", "startup", "entrepreneur", "profit", "client",
                        "brand", "market", "sales", "freelance", "revenue", "boss",
                        "employee", "ceo", "founder", "passive income"],
    "motivation":      ["success", "mindset", "habit", "discipline", "focus",
                        "goal", "hustle", "grind", "winner", "failure", "rich",
                        "broke", "confidence", "fear", "lazy"],
    "productivity":    ["productivity", "routine", "morning", "habit", "time",
                        "focus", "distraction", "organize", "efficient", "task",
                        "schedule", "procrastinate", "deep work", "dopamine"],
    "ai_tools":        ["ai", "chatgpt", "openai", "gpt", "automation", "tool",
                        "free", "prompt", "generate", "workflow", "midjourney",
                        "claude", "gemini", "agent", "llm"],
    "relationships":   ["relationship", "dating", "partner", "love", "toxic",
                        "trust", "communication", "breakup", "marriage", "red flag",
                        "attachment", "narcissist", "boundaries"],
}

# ── Niche → best subreddits ───────────────────────────────────────────────────
NICHE_SUBREDDITS = {
    "finance":         ["personalfinance", "investing", "financialindependence", "wallstreetbets"],
    "health_wellness": ["fitness", "loseit", "nutrition", "HealthyFood"],
    "technology":      ["technology", "Futurology", "gadgets"],
    "business":        ["entrepreneur", "smallbusiness", "startups"],
    "motivation":      ["GetMotivated", "selfimprovement", "decidingtobebetter"],
    "productivity":    ["productivity", "getdisciplined", "nosurf"],
    "ai_tools":        ["artificial", "ChatGPT", "singularity", "MachineLearning"],
    "relationships":   ["relationship_advice", "psychology", "socialskills"],
}


# ── Scoring ───────────────────────────────────────────────────────────────────

def _ctr_score(title: str, niche: str) -> int:
    """Return a CTR potential score for a title (higher = better for Shorts)."""
    lower = title.lower()
    words = lower.split()
    score = 0

    # Power words (each hit = +2)
    for w in POWER_WORDS:
        if re.search(r'\b' + re.escape(w) + r'\b', lower):
            score += 2

    # Numbers in title ("5 mistakes", "3 secrets") = strong CTR signal
    if re.search(r'\b\d+\b', title):
        score += 3

    # Niche keyword relevance
    for kw in NICHE_KEYWORDS.get(niche, []):
        if kw in lower:
            score += 2

    # Ideal length for Shorts title (5–12 words)
    if 5 <= len(words) <= 12:
        score += 2
    elif len(words) > 16:
        score -= 2

    # Question format ("Why do…?") — strong curiosity gap
    if title.strip().endswith("?"):
        score += 2

    return score


def _clean_title(title: str) -> str:
    """Remove URLs, subreddit tags, and excessive whitespace."""
    title = re.sub(r'https?://\S+', '', title)
    title = re.sub(r'\[.*?\]', '', title)
    title = re.sub(r'\(.*?\)', '', title)
    title = re.sub(r'\s+', ' ', title).strip()
    # Remove trailing punctuation clutter except ? and !
    title = re.sub(r'[,;:\-–—]+$', '', title).strip()
    return title[:120]


# ── Data sources ──────────────────────────────────────────────────────────────

def _fetch_google_trends(niche: str) -> list:
    """Daily trending searches from Google Trends (pytrends, no key needed)."""
    try:
        from pytrends.request import TrendReq
        pt = TrendReq(hl='en-US', tz=360, timeout=(10, 25), retries=2, backoff_factor=0.5)
        df = pt.trending_searches(pn='united_states')
        raw = df[0].tolist()[:25]
        print(f"[trending] Google Trends: {len(raw)} results")
        return raw
    except Exception as e:
        print(f"[trending] Google Trends error: {e}")
        return []


def _fetch_reddit(niche: str) -> list:
    """Hot post titles from niche-relevant subreddits (no auth needed)."""
    subreddits = NICHE_SUBREDDITS.get(niche, ["popular"])
    titles = []
    headers = {"User-Agent": "faceless-shorts-bot/1.0"}
    for sub in subreddits:
        try:
            r = requests.get(
                f"https://www.reddit.com/r/{sub}/hot.json?limit=20",
                headers=headers, timeout=10
            )
            if r.status_code == 200:
                posts = r.json().get("data", {}).get("children", [])
                for p in posts:
                    t = p["data"].get("title", "")
                    if t:
                        titles.append(_clean_title(t))
        except Exception as e:
            print(f"[trending] Reddit r/{sub} error: {e}")
    print(f"[trending] Reddit: {len(titles)} results")
    return titles


def _fetch_hackernews() -> list:
    """Top HackerNews story titles (best for technology / ai_tools niches)."""
    try:
        ids_r = requests.get(
            "https://hacker-news.firebaseio.com/v0/topstories.json",
            timeout=10
        )
        ids = ids_r.json()[:20]
        titles = []
        for story_id in ids:
            try:
                item = requests.get(
                    f"https://hacker-news.firebaseio.com/v0/item/{story_id}.json",
                    timeout=5
                ).json()
                if item and item.get("title"):
                    titles.append(_clean_title(item["title"]))
            except Exception:
                pass
        print(f"[trending] HackerNews: {len(titles)} results")
        return titles
    except Exception as e:
        print(f"[trending] HackerNews error: {e}")
        return []


def _fetch_gnews(niche: str) -> list:
    """GNews headlines (requires GNEWS_API_KEY – 100 free req/day at gnews.io)."""
    key = os.getenv("GNEWS_API_KEY", "")
    if not key:
        return []
    niche_query = {
        "finance":         "money finance investing",
        "health_wellness": "health fitness wellness",
        "technology":      "technology AI startup",
        "business":        "business entrepreneur startup",
        "motivation":      "success mindset self improvement",
        "productivity":    "productivity habits routine",
        "ai_tools":        "artificial intelligence AI tools ChatGPT",
        "relationships":   "relationships dating psychology",
    }.get(niche, niche.replace("_", " "))
    try:
        r = requests.get(
            "https://gnews.io/api/v4/search",
            params={"q": niche_query, "lang": "en", "max": 10, "token": key},
            timeout=10
        )
        if r.status_code == 200:
            articles = r.json().get("articles", [])
            titles = [_clean_title(a["title"]) for a in articles]
            print(f"[trending] GNews: {len(titles)} results")
            return titles
    except Exception as e:
        print(f"[trending] GNews error: {e}")
    return []


def _fetch_newsdata(niche: str) -> list:
    """NewsData.io headlines (requires NEWSDATA_API_KEY – 200 free req/day at newsdata.io)."""
    key = os.getenv("NEWSDATA_API_KEY", "")
    if not key:
        return []
    niche_query = {
        "finance":         "money investing",
        "health_wellness": "health fitness",
        "technology":      "technology AI",
        "business":        "business startup",
        "motivation":      "success mindset",
        "productivity":    "productivity",
        "ai_tools":        "artificial intelligence",
        "relationships":   "relationships",
    }.get(niche, niche.replace("_", " "))
    try:
        r = requests.get(
            "https://newsdata.io/api/1/news",
            params={"apikey": key, "q": niche_query, "language": "en"},
            timeout=10
        )
        if r.status_code == 200:
            results = r.json().get("results", [])
            titles = [_clean_title(a["title"]) for a in results if a.get("title")]
            print(f"[trending] NewsData: {len(titles)} results")
            return titles
    except Exception as e:
        print(f"[trending] NewsData error: {e}")
    return []


# ── Main entry point ──────────────────────────────────────────────────────────

def get_trending_topic(niche: str = "finance", top_n: int = 1):
    """
    Fetch real-time trending topics, score each for CTR potential, return the best.

    Returns:
        str  if top_n == 1  (best single topic)
        list if top_n  > 1  (top N topics, scored)
        None if all sources fail (caller should fall back to static topics)
    """
    print(f"[trending] Searching trends for niche: {niche}")
    candidates = []

    # Always-on free sources
    candidates += _fetch_google_trends(niche)
    candidates += _fetch_reddit(niche)

    # Tech-specific boost from HackerNews
    if niche in ("technology", "ai_tools"):
        candidates += _fetch_hackernews()

    # Optional keyed sources
    candidates += _fetch_gnews(niche)
    candidates += _fetch_newsdata(niche)

    if not candidates:
        print("[trending] No candidates found – falling back to static topic.")
        return None

    # Deduplicate (case-insensitive, first 60 chars)
    seen = set()
    unique = []
    for c in candidates:
        key = c.lower()[:60]
        if key not in seen and len(c.strip()) > 8:
            seen.add(key)
            unique.append(c)

    # Score and rank by CTR potential
    scored = sorted(unique, key=lambda t: _ctr_score(t, niche), reverse=True)

    if top_n == 1:
        best = scored[0]
        print(f"[trending] Top topic (CTR score={_ctr_score(best, niche)}): {best}")
        return best

    top = scored[:top_n]
    for t in top:
        print(f"[trending]  score={_ctr_score(t, niche):>3}  {t}")
    return top


def get_trending_suggestions(niche: str, count: int = 8) -> list:
    """Return multiple scored trending suggestions for dashboard display."""
    results = get_trending_topic(niche, top_n=count * 3)  # fetch more, filter down
    if not results:
        return []
    return [
        {"title": t, "score": _ctr_score(t, niche)}
        for t in (results if isinstance(results, list) else [results])
    ][:count]
