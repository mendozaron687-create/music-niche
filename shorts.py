"""
shorts.py — Create a 60-second YouTube Short from a finished music video.

Strategy:
  1. Find the chorus start time from the ASS subtitle file (or default to 25% into song)
  2. Clip 60 seconds starting from chorus
  3. Scale to 1080x1920 (vertical 9:16) with smart crop
  4. Burn in most emotional lyric line as large centered text
  5. Return path to short .mp4 file

The Short is uploaded separately with #Shorts in the title.
"""

import os
import re
import subprocess
import imageio_ffmpeg


def _find_chorus_start(ass_path: str, duration: float) -> float:
    """
    Parse the ASS file to find the timestamp of a line that looks like a chorus.
    Fallback to 25% into the song.
    """
    if not os.path.exists(ass_path):
        return duration * 0.25

    chorus_keywords = [
        "mahal", "puso", "iyak", "luha", "sakit", "bakit", "sana", "ikaw",
        "love", "heart", "miss", "stay", "gone", "cry", "why",
    ]
    best_time = None

    try:
        with open(ass_path, encoding="utf-8-sig") as f:
            for line in f:
                if not line.startswith("Dialogue:"):
                    continue
                parts = line.split(",", 9)
                if len(parts) < 10:
                    continue
                # ASS time format: H:MM:SS.cs
                start_str = parts[1].strip()
                text = re.sub(r"\{[^}]+\}", "", parts[9]).strip()
                text_lower = text.lower()

                # Score this line for emotional weight
                score = sum(1 for kw in chorus_keywords if kw in text_lower)
                if score >= 2 and best_time is None:
                    h, m, rest = start_str.split(":")
                    s, cs = rest.split(".")
                    best_time = int(h) * 3600 + int(m) * 60 + int(s) + int(cs) / 100
    except Exception:
        pass

    return best_time if best_time is not None else duration * 0.25


def _most_emotional_line(ass_path: str) -> str:
    """Pull the single most emotionally weighted lyric line from the ASS file."""
    if not os.path.exists(ass_path):
        return ""

    chorus_keywords = [
        "mahal", "puso", "iyak", "luha", "sakit", "bakit", "sana", "ikaw",
        "love", "heart", "miss", "stay", "gone", "cry", "why", "hindi", "wala",
    ]
    best_line = ""
    best_score = -1

    try:
        with open(ass_path, encoding="utf-8-sig") as f:
            for line in f:
                if not line.startswith("Dialogue:"):
                    continue
                parts = line.split(",", 9)
                if len(parts) < 10:
                    continue
                text = re.sub(r"\{[^}]+\}", "", parts[9]).strip()
                if not text:
                    continue
                score = sum(1 for kw in chorus_keywords if kw in text.lower())
                # Prefer lines of moderate length (not too short, not too long)
                length_ok = 10 <= len(text) <= 60
                if score > best_score and length_ok:
                    best_score = score
                    best_line = text
    except Exception:
        pass

    return best_line[:80]


def create_short(
    video_path: str,
    ass_path: str,
    output_path: str,
    duration: float = 0.0,
    hook_text: str = "",
) -> str:
    """
    Clip 60s from chorus, crop to 1080x1920, burn lyric text overlay.
    Returns output_path on success, "" on failure.
    """
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()

    if not os.path.exists(video_path):
        print("[shorts] Source video not found, skipping Short.")
        return ""

    start = _find_chorus_start(ass_path, duration or 180.0)
    clip_dur = 60.0

    # Don't start too close to end
    if duration and start + clip_dur > duration - 5:
        start = max(0, duration - clip_dur - 5)

    lyric = _most_emotional_line(ass_path) or hook_text or ""

    # Escape for ffmpeg drawtext
    def _esc(s: str) -> str:
        return (s.replace("\\", "\\\\")
                 .replace("'", "\\'")
                 .replace(":", "\\:")
                 .replace("[", "\\[")
                 .replace("]", "\\]"))

    # filter_complex:
    # 1. crop center square from 1920x1080, then scale to 1080x1920 (vertical)
    # 2. draw lyric text centered vertically
    fc_parts = [
        # Crop 1080x1080 from center of 1920x1080, then pad/scale to 1080x1920
        "[0:v]crop=1080:1080:(iw-1080)/2:(ih-1080)/2,scale=1080:1080,"
        "pad=1080:1920:0:(oh-ih)/2:black[vc]"
    ]

    cur = "[vc]"

    if lyric:
        esc_lyric = _esc(lyric)
        fc_parts.append(
            f"{cur}drawtext="
            f"text='{esc_lyric}'"
            f":fontfile='arialbd.ttf'"
            f":fontsize=64"
            f":fontcolor=white"
            f":x=(w-text_w)/2"
            f":y=h*0.72"
            f":box=1:boxcolor=black@0.68:boxborderw=20"
            f":shadowx=3:shadowy=3:shadowcolor=black@0.9"
            f"[vt]"
        )
        cur = "[vt]"

    filter_complex = ";".join(fc_parts)

    cmd = [
        ffmpeg, "-y",
        "-ss", str(start),
        "-i", video_path,
        "-t", str(clip_dur),
        "-filter_complex", filter_complex,
        "-map", cur,
        "-map", "0:a:0",
        "-c:v", "libx264", "-preset", "fast", "-crf", "22",
        "-c:a", "aac", "-b:a", "128k",
        "-pix_fmt", "yuv420p",
        "-movflags", "+faststart",
        output_path,
    ]

    print(f"[shorts] Creating Short: start={start:.0f}s lyric='{lyric[:40]}'")
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    if r.returncode != 0:
        print(f"[shorts] ffmpeg failed: {r.stderr[-800:]}")
        return ""

    print(f"[shorts] Short saved: {output_path}")
    return output_path


def upload_short(
    youtube,
    short_path: str,
    main_title: str,
    description: str,
    tags: list,
    thumbnail_path: str = "",
) -> str:
    """Upload the Short to YouTube. Returns video URL."""
    from googleapiclient.http import MediaFileUpload

    # #Shorts must be in the title for YouTube to classify it
    short_title = f"#Shorts {main_title}"[:100]
    short_desc = (
        f"💔 {main_title}\n\n"
        f"Pakinggan ang buong kanta sa aming channel! 👆\n\n"
        f"{description[:300]}\n\n"
        f"#Shorts #OPM #Hugot #PinoyMusic #TagalogSongs"
    )[:5000]

    insert_request = youtube.videos().insert(
        part="snippet,status",
        body={
            "snippet": {
                "title": short_title,
                "description": short_desc,
                "tags": (tags[:15] + ["Shorts", "YouTubeShorts", "OPMShorts"])[:30],
                "categoryId": "10",
            },
            "status": {
                "privacyStatus": "public",
                "selfDeclaredMadeForKids": False,
                "containsSyntheticMedia": True,
            },
        },
        media_body=MediaFileUpload(short_path, chunksize=-1, resumable=True),
    )
    response = insert_request.execute()
    short_id = response["id"]

    if thumbnail_path and os.path.exists(thumbnail_path):
        try:
            youtube.thumbnails().set(
                videoId=short_id,
                media_body=MediaFileUpload(thumbnail_path),
            ).execute()
        except Exception:
            pass

    url = f"https://youtube.com/watch?v={short_id}"
    print(f"[shorts] Short live: {url}")
    return url
