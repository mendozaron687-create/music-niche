"""
Suno API wrapper — generate lyrics, then music, poll until done, download mp3.
API docs: https://docs.sunoapi.org/
Base URL: https://api.sunoapi.org
"""
import os
import time
import requests


BASE_URL = "https://api.sunoapi.org/api/v1"
POLL_INTERVAL = 15   # seconds between status checks
MAX_WAIT = 600       # 10 minutes


def _headers() -> dict:
    key = os.getenv("SUNO_API_KEY", "")
    if not key:
        raise RuntimeError("SUNO_API_KEY not set in .env")
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


# ── Music generation ────────────────────────────────────────────────────────

def generate_music(
    lyrics: str,
    style: str,
    title: str,
    instrumental: bool = False,
    model: str = "V4_5ALL",
) -> dict:
    """
    Generate music using Suno. Returns task info dict with taskId and tracks list.
    Each track has: id, audio_url, title, duration.
    """
    payload = {
        "customMode": True,
        "instrumental": instrumental,
        "model": model,
        "style": style[:1000],
        "title": title[:80],
        "count": 1,  # generate exactly 1 track to conserve credits
        "callBackUrl": "https://example.com/callback",
    }
    if not instrumental:
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
        if status in ("SUCCESS", "TEXT_SUCCESS"):
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
                    "suno_lyrics": t.get("prompt", ""),  # actual lyrics Suno sang
                })
            if tracks:
                print(f"[suno] Music ready — {len(tracks)} track(s)")
                return {"taskId": task_id, "tracks": tracks}
            # sunoData present but no audio yet — keep polling
        elif status == "FAILED":
            raise RuntimeError(f"[suno] Music generation failed: {info}")
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
    resp = requests.get(f"{BASE_URL}/generate/credit", headers=_headers(), timeout=10)
    resp.raise_for_status()
    return resp.json().get("data", 0)
