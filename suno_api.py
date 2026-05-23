"""
Suno API wrapper — generate lyrics, then music, poll until done, download mp3.
API docs: https://docs.kie.ai/suno-api/quickstart
Base URL: https://api.kie.ai

Note: in customMode=True the `prompt` field is STRICTLY used as lyrics verbatim.
"""
import os
import random
import re
import time
import requests


BASE_URL = "https://api.kie.ai/api/v1"
POLL_INTERVAL = 15   # seconds between status checks
MAX_WAIT = 600       # 10 minutes


def _headers() -> dict:
    key = os.getenv("KIE_API_KEY") or os.getenv("SUNO_API_KEY", "")
    if not key:
        raise RuntimeError("KIE_API_KEY not set in .env")
    return {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}


# ── Lyrics ─────────────────────────────────────────────────────────────────

def generate_lyrics(prompt: str) -> str:
    """Generate AI lyrics for a given prompt. Returns the lyrics text."""
    resp = requests.post(
        f"{BASE_URL}/lyrics",
        headers=_headers(),
        json={"prompt": prompt[:200], "callBackUrl": "https://example.com/callback"},
        timeout=30,
    )
    resp.raise_for_status()
    task_id = resp.json()["data"]["taskId"]
    print(f"[suno] Lyrics task: {task_id}")

    deadline = time.time() + MAX_WAIT
    while time.time() < deadline:
        time.sleep(POLL_INTERVAL)
        info = _get_task(task_id, "lyrics")
        status = info.get("status", "")
        if status == "SUCCESS":
            items = info.get("response", {}).get("data", [])
            if items:
                text = items[0].get("text", "")
                print(f"[suno] Lyrics ready ({len(text)} chars)")
                return text
        elif status == "FAILED":
            raise RuntimeError(f"[suno] Lyrics generation failed: {info}")
        print(f"[suno] Lyrics status: {status}")
    raise TimeoutError("[suno] Lyrics generation timed out")


# ── Style sanitizer ──────────────────────────────────────────────────────────

# KIE.ai Suno rejects styles that reference specific artist names.
# This list covers all artists mentioned across music_topics.py / lyrics_generator.py.
_ARTIST_PATTERNS = re.compile(
    r'\b('
    r'Rivermaya|Bamboo|Eraserheads|Arthur Nery|Kyle Echarri|'
    r'Freddie Aguilar|Noel Cabangon|APO Hiking Society|APO|'
    r'Juan dela Cruz|Ben&Ben|December Avenue|I Belong to the Zoo|'
    r'Parokya ni Edgar|Sandwich|Sponge Cola|Hale|Orange and Lemons|'
    r'Sugarfree|Rico Blanco|Ebe Dancel|Chad Borja|'
    r'Adele|Ed Sheeran|Taylor Swift|Billie Eilish|Bruno Mars|'
    r'Drake|Kendrick Lamar|Post Malone|The Weeknd|Justin Bieber'
    r')\b',
    re.IGNORECASE,
)
# Also strip "X inspired", "X style", "X-style" phrases
_ARTIST_PHRASE_PATTERNS = re.compile(
    r'\b\w[\w\s]+?\s+(?:inspired|style|influenced)\b',
    re.IGNORECASE,
)

def _sanitize_style(style: str) -> str:
    """Remove artist name references that KIE.ai Suno rejects."""
    # Remove known artist names
    cleaned = _ARTIST_PATTERNS.sub("", style)
    # Collapse multiple commas/spaces left behind
    cleaned = re.sub(r',\s*,', ',', cleaned)
    cleaned = re.sub(r'\s{2,}', ' ', cleaned)
    cleaned = cleaned.strip(", ")
    return cleaned


# ── Extra production style (applied randomly ~50% of the time) ──────────────
# Set to "" to disable entirely. Change EXTRA_STYLE_CHANCE to adjust frequency.
EXTRA_STYLE_CHANCE = 0.0   # Style is now set directly per-genre in GENRE_PROMPTS; no random appending
EXTRA_STYLE_PROMPT = (
    "A catchy, feel-good love song with a smooth funky pop style inspired by modern "
    "retro R&B. Upbeat groove, warm bassline, clean guitar riffs, soft synth layers, "
    "and a danceable rhythm. The vibe is romantic, playful, and slightly flirtatious—"
    "like falling in love unexpectedly. Male vocals with soulful delivery, light "
    "falsetto moments, and catchy melodic hooks. Chorus is addictive and easy to sing "
    "along to. Tempo is mid-to-upbeat, perfect for dancing or cruising at night. "
    "Overall mood: joyful, charming, and uplifting love energy."
)

# ── Music generation ────────────────────────────────────────────────────────

def generate_music(
    lyrics: str,
    style: str,
    title: str,
    instrumental: bool = False,
    model: str = "V5_5",
) -> dict:
    """
    Generate music using Suno. Returns task info dict with taskId and tracks list.
    Each track has: id, audio_url, title, duration.

    Lyrics are passed exactly as provided — customMode=True ensures Suno uses
    our lyrics verbatim without AI rewriting.
    """
    # Ensure section labels are present so Suno follows the structure
    # If lyrics already have [Verse] markers, keep as-is; otherwise wrap
    has_markers = bool(re.search(r'^\[.+\]', lyrics, re.MULTILINE))
    if not has_markers and not instrumental:
        # Add minimal structure markers so Suno doesn't freestyle
        lyrics = "[Verse 1]\n" + lyrics

    # KIE.ai rejects style strings with artist name references
    clean_style = _sanitize_style(style)
    if clean_style != style:
        print(f"[suno] Style sanitized (removed artist refs): {clean_style[:120]}")

    # Randomly append extra production notes
    if EXTRA_STYLE_PROMPT and random.random() < EXTRA_STYLE_CHANCE:
        clean_style = f"{clean_style}, {EXTRA_STYLE_PROMPT}"
        print(f"[suno] Extra style appended ({len(clean_style)} chars total)")
    else:
        print("[suno] Extra style skipped (random)")

    payload = {
        "customMode": True,
        "instrumental": instrumental,
        "model": model,
        "style": clean_style[:1000],
        "title": title[:80],
        "callBackUrl": "https://example.com/callback",
    }
    if not instrumental:
        # Pass lyrics directly — customMode+prompt is the correct Suno API contract
        # for exact-lyrics generation (no AI paraphrasing)
        payload["prompt"] = lyrics[:5000]

    resp = requests.post(
        f"{BASE_URL}/generate",
        headers=_headers(),
        json=payload,
        timeout=30,
    )
    resp.raise_for_status()
    body = resp.json()
    if not body.get("data"):
        raise RuntimeError(
            f"[suno] generate_music failed: code={body.get('code')} msg={body.get('msg')}"
        )
    task_id = body["data"]["taskId"]
    print(f"[suno] Music task: {task_id}")

    deadline = time.time() + MAX_WAIT
    while time.time() < deadline:
        time.sleep(POLL_INTERVAL)
        info = _get_task(task_id, "generate")
        status = info.get("status", "")
        # FIRST_SUCCESS = at least one track ready; SUCCESS = all tracks ready
        if status in ("SUCCESS", "FIRST_SUCCESS", "TEXT_SUCCESS"):
            response = info.get("response") or {}
            # API returns sunoData (camelCase), normalize to snake_case for callers
            raw = response.get("sunoData") or response.get("data") or []
            tracks = []
            for t in raw:
                audio_url = (
                    t.get("audioUrl") or
                    t.get("streamAudioUrl") or
                    t.get("sourceStreamAudioUrl") or
                    t.get("sourceAudioUrl") or ""
                )
                if not audio_url:
                    continue
                tracks.append({
                    "id": t.get("id", ""),
                    "audio_url": audio_url,
                    "title": t.get("title", ""),
                    "duration": t.get("duration", 0),
                    "image_url": t.get("imageUrl") or t.get("sourceImageUrl") or "",
                    "suno_lyrics": t.get("prompt", ""),  # what Suno logged (our lyrics)
                })
            if tracks:
                print(f"[suno] Music ready — {len(tracks)} track(s)")
                return {"taskId": task_id, "tracks": tracks}
            # sunoData present but no audio URL yet — keep polling
        elif status in ("CREATE_TASK_FAILED", "GENERATE_AUDIO_FAILED", "SENSITIVE_WORD_ERROR", "FAILED"):
            err = info.get("errorMessage") or status
            raise RuntimeError(f"[suno] Music generation failed ({status}): {err}")
        elif status == "CALLBACK_EXCEPTION":
            # Non-fatal — log and keep polling; tracks may still arrive
            print(f"[suno] Warning: callback exception, continuing to poll...")
        print(f"[suno] Music status: {status}")
    raise TimeoutError("[suno] Music generation timed out")


# ── Status polling ──────────────────────────────────────────────────────────

def _get_task(task_id: str, kind: str = "generate") -> dict:
    """Poll task status. kind: 'generate' | 'lyrics'."""
    if kind == "lyrics":
        url = f"{BASE_URL}/lyrics/record-info"
    else:
        url = f"{BASE_URL}/generate/record-info"
    resp = requests.get(
        url,
        headers=_headers(),
        params={"taskId": task_id},
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json().get("data", {})


# ── Download ────────────────────────────────────────────────────────────────

def download_audio(audio_url: str, output_path: str) -> str:
    """Download generated mp3 to output_path. Returns output_path."""
    os.makedirs(os.path.dirname(output_path) if os.path.dirname(output_path) else ".", exist_ok=True)
    print(f"[suno] Downloading audio → {output_path}")
    r = requests.get(audio_url, stream=True, timeout=120)
    r.raise_for_status()
    with open(output_path, "wb") as f:
        for chunk in r.iter_content(chunk_size=8192):
            f.write(chunk)
    print(f"[suno] Audio saved: {output_path}")
    return output_path


# ── Credits ─────────────────────────────────────────────────────────────────

def get_credits() -> int:
    try:
        resp = requests.get(f"{BASE_URL}/generate/credit", headers=_headers(), timeout=10)
        resp.raise_for_status()
        data = resp.json().get("data", {})
        # kie.ai returns {credits: N} or a plain int
        if isinstance(data, dict):
            return int(data.get("credits") or data.get("balance") or 0)
        return int(data or 0)
    except Exception as e:
        print(f"[suno] Could not fetch credits: {e}")
        return -1
