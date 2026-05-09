"""
Regenerate ONLY the ASS caption file for an existing output folder, then
optionally do a full re-render.  No API calls — uses existing music.mp3 and
lyrics.txt.

Usage:
    # Step 1 — regenerate ASS only (fast, inspect timing)
    python _rerender_captions.py [folder_name]

    # Step 2 — full video re-render (downloads Pexels clips again)
    python _rerender_captions.py [folder_name] --video

Example:
    python _rerender_captions.py opm_rnb_hugot_20260509_085939
    python _rerender_captions.py opm_rnb_hugot_20260509_085939 --video
"""
import sys, os, json, glob, subprocess
sys.path.insert(0, '.')
from dotenv import load_dotenv
load_dotenv()

do_video = "--video" in sys.argv
args = [a for a in sys.argv[1:] if not a.startswith("--")]

# ── Select output folder ──────────────────────────────────────────────────────
if args:
    folder_name = args[0]
else:
    folders = sorted(glob.glob("output/*/music.mp3"))
    if not folders:
        print("No output folders with music.mp3 found.")
        sys.exit(1)
    folder_name = os.path.basename(os.path.dirname(folders[-1]))
    print(f"[rerender] No folder specified — using most recent: {folder_name}")

out_dir     = os.path.join("output", folder_name)
audio_path  = os.path.join(out_dir, "music.mp3")
lyrics_path = os.path.join(out_dir, "lyrics.txt")
meta_path   = os.path.join(out_dir, "metadata.json")

for p in (audio_path, lyrics_path):
    if not os.path.exists(p):
        print(f"[rerender] Not found: {p}")
        sys.exit(1)

# ── Load content ──────────────────────────────────────────────────────────────
with open(lyrics_path, encoding="utf-8") as f:
    lyrics = f.read()

meta = {}
if os.path.exists(meta_path):
    with open(meta_path, encoding="utf-8") as f:
        meta = json.load(f)

genre_key   = meta.get("genre", "hugot_ballad")
song_title  = meta.get("song_title", "OPM Song")
yt_title    = meta.get("title", song_title)
story_cards = meta.get("story_cards", [])
pull_quotes = meta.get("pull_quotes", [])

print(f"[rerender] Folder  : {out_dir}")
print(f"[rerender] Genre   : {genre_key}")
print(f"[rerender] Title   : {song_title}")

# ── Get audio duration via ffprobe ────────────────────────────────────────────
ffprobe = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".venv", "Scripts", "ffprobe.exe")
if not os.path.exists(ffprobe):
    ffprobe = "ffprobe"
r = subprocess.run(
    [ffprobe, "-v", "quiet", "-show_entries", "format=duration",
     "-of", "default=noprint_wrappers=1:nokey=1", audio_path],
    capture_output=True, text=True,
)
duration = float(r.stdout.strip()) if r.stdout.strip() else 270.0
print(f"[rerender] Duration: {duration:.1f}s")

# ── Regenerate ASS ────────────────────────────────────────────────────────────
from music_video import _build_ass
from music_topics import GENRES

genre_dict = GENRES.get(genre_key, GENRES.get("hugot_ballad", {}))
ass_path   = os.path.join(out_dir, "lyrics_new.ass")

print("[rerender] Regenerating ASS with fixed sync ...")
_build_ass(
    lyrics=lyrics,
    duration=duration,
    vstyle=genre_dict,
    output_path=ass_path,
    story_cards=story_cards,
    pull_quotes=pull_quotes,
    audio_path=audio_path,
    story_segments=None,
    song_title=song_title,
)

# ── Print caption timing for inspection ───────────────────────────────────────
print("\n── Caption timing preview ──────────────────────────────────────────")
with open(ass_path, encoding="utf-8-sig") as f:
    for line in f:
        if line.startswith("Dialogue:") and ",Lyric," in line:
            parts = line.split(",", 9)
            start, end = parts[1], parts[2]
            text = parts[9].strip() if len(parts) > 9 else ""
            # Strip ASS override tags for display
            import re as _re
            text = _re.sub(r"\{[^}]*\}", "", text)
            print(f"  {start} → {end}  {text[:70]}")

print(f"\n[rerender] New ASS saved: {ass_path}")
print("[rerender] Inspect the timing above. To do a full re-render, run:")
print(f"  python _rerender_captions.py {folder_name} --video")

if not do_video:
    sys.exit(0)

# ── Full video re-render (downloads Pexels clips) ─────────────────────────────
from music_video import build_music_video

pexels_key  = os.getenv("PEXELS_API_KEY", "")
output_path = os.path.join(out_dir, "final_rerendered.mp4")

print("\n[rerender] Building full video with fixed captions ...")
result = build_music_video(
    audio_path=audio_path,
    lyrics=lyrics,
    title=song_title,
    genre_dict=genre_dict,
    output_path=output_path,
    pexels_key=pexels_key,
    hook_text=yt_title,
    story_cards=story_cards,
    pull_quotes=pull_quotes,
    story_segments=None,
    song_title=song_title,
)
print(f"\n[rerender] Done -> {result}")
