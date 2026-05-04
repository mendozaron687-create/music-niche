"""
Upload an already-rendered video to YouTube without generating new music.
Usage: python _upload_existing.py
"""
import os
import json
from dotenv import load_dotenv
load_dotenv()

OUT = r"C:\Users\onel_\Desktop\Music Niche\faceless-video-automation\output\hugot_opm_pop_20260503_184436"

final_path     = os.path.join(OUT, "final.mp4")
thumbnail_path = os.path.join(OUT, "thumbnail.png")
ass_path       = os.path.join(OUT, "lyrics.ass")
lyrics_path    = os.path.join(OUT, "lyrics.txt")

song_title   = "Aangat Tayo, Bes"
upload_title = '"Mas Galit Sila Sa Hirap Ko Kaysa Sa Nakaw Nila" 💔😭 | OPM Hugot'
genre_key    = "hugot_opm_pop"

lyrics = open(lyrics_path, encoding="utf-8").read()

# Build description
from main import _generate_description, upload_to_youtube
from music_topics import get_genre
from music_video import extract_chapters_from_ass

genre_dict = get_genre(genre_key)
chapters   = extract_chapters_from_ass(ass_path, song_title)
description = _generate_description(upload_title, genre_dict, lyrics, is_opm=True, chapters=chapters)

tags = genre_dict.get("youtube_tags", []) + ["music", "aimusic", "OPM", "Tagalog", "PinoyMusic"]

print(f"Title   : {upload_title}")
print(f"Tags    : {tags[:6]}...")
print(f"Desc    :\n{description[:300]}\n")

# Save metadata
meta = {
    "title": upload_title,
    "song_title": song_title,
    "description": description,
    "tags": tags,
    "genre": genre_key,
}
with open(os.path.join(OUT, "metadata.json"), "w", encoding="utf-8") as f:
    json.dump(meta, f, indent=2, ensure_ascii=False)
print("[meta] metadata.json saved")

# Upload
from main import upload_to_youtube
url = upload_to_youtube(
    video_path=final_path,
    thumbnail_path=thumbnail_path,
    title=upload_title,
    description=description,
    tags=tags,
    first_comment="💔 Nakaka-relate ka ba? I-share mo ito sa mga kaibigan mo na kailangan marinig ito ngayon 👇",
    genre_key=genre_key,
)
print(f"\n✅ Uploaded: {url}")
