"""
Build a music video from an already-complete Suno task (no new credits needed).
Usage: python recover_video.py
"""
import os, sys, subprocess
sys.path.insert(0, os.path.dirname(__file__))
from dotenv import load_dotenv
load_dotenv()

from suno_api import _get_task, download_audio
from music_topics import get_genre, build_video_title
from music_video import build_music_video

TASK_ID    = "54efcfbec935dc16e6c2aa7dc98ff1dc"
LYRICS_FILE = "output/hugot_ballad_20260503_120915/lyrics.txt"
SONG_TITLE  = "Bayad na Pagmamahal"
GENRE_KEY   = "hugot_ballad"
OUTPUT_DIR  = "output/hugot_ballad_20260503_120915"

# 1. Get tracks from existing task
info     = _get_task(TASK_ID, "generate")
response = info.get("response") or {}
raw      = response.get("sunoData") or []
tracks   = [
    {
        "id": t.get("id",""),
        "audio_url": (
            t.get("audioUrl") or
            t.get("streamAudioUrl") or
            t.get("sourceStreamAudioUrl") or
            t.get("sourceAudioUrl") or ""
        ),
        "duration": t.get("duration", 0),
        "title": t.get("title",""),
        "suno_lyrics": t.get("prompt", ""),  # actual lyrics Suno sang
    }
    for t in raw
    if (
        t.get("audioUrl") or t.get("streamAudioUrl") or
        t.get("sourceStreamAudioUrl") or t.get("sourceAudioUrl")
    )
]
if not tracks:
    sys.exit("No tracks found in existing task")

track = max(tracks, key=lambda t: t["duration"] or 0)
dur_str = f"{track['duration']:.0f}s" if track["duration"] else "unknown duration"
print(f"[recover] Using track {dur_str}: {track['audio_url'][:70]}")

# 2. Download audio
audio_path = os.path.join(OUTPUT_DIR, "music.mp3")
if os.path.exists(audio_path):
    print(f"[recover] Audio already exists ({os.path.getsize(audio_path)//1024} KB)")
else:
    download_audio(track["audio_url"], audio_path)

# 3. Read lyrics — prefer Suno's actual version (lyrics_suno.txt) so captions
# match what was sung. Fall back to our original lyrics.txt if not available.
suno_lyrics_file = os.path.join(OUTPUT_DIR, "lyrics_suno.txt")
lyrics_file_used = suno_lyrics_file if os.path.exists(suno_lyrics_file) else LYRICS_FILE
with open(lyrics_file_used, encoding="utf-8") as f:
    lyrics = f.read()
print(f"[recover] Lyrics: {len(lyrics)} chars (source: {os.path.basename(lyrics_file_used)})")

# Also save Suno's lyrics if returned in the task and not already saved
suno_lyrics = track.get("suno_lyrics", "").strip()
if suno_lyrics and not os.path.exists(suno_lyrics_file):
    with open(suno_lyrics_file, "w", encoding="utf-8") as f:
        f.write(suno_lyrics)
    print(f"[recover] Suno lyrics saved → lyrics_suno.txt ({len(suno_lyrics)} chars)")
    lyrics = suno_lyrics  # use the fresher source

# 4. Build video
genre_dict = get_genre(GENRE_KEY)
title      = build_video_title(genre_dict, song_title=SONG_TITLE)
print(f"[recover] Video title: {title}")

final_path = os.path.join(OUTPUT_DIR, "final.mp4")
build_music_video(
    audio_path=audio_path,
    lyrics=lyrics,
    title=SONG_TITLE,
    genre_dict=genre_dict,
    output_path=final_path,
    pexels_key=os.getenv("PEXELS_API_KEY", ""),
)

# 5. Open result
size_mb = os.path.getsize(final_path) / 1024 / 1024
print(f"[recover] Done! {final_path} ({size_mb:.1f} MB)")
subprocess.Popen(["explorer", final_path])
