"""
main.py — YouTube Music Niche Automation Pipeline

Flow:
  1. Pick genre (or use arg)
  2. Generate lyrics via Suno API
  3. Generate music (3-6 min) via Suno API
  4. Download mp3
  5. Build 1920x1080 music video (Pexels BG + effects + karaoke subtitles)
  6. Generate thumbnail (1280x720)
  7. Upload to YouTube with SEO-optimized metadata

Requirements: set in .env
  SUNO_API_KEY=...
  PEXELS_API_KEY=...
  OPENROUTER_API_KEY=...  (optional — for AI-generated description)
"""

import os
import asyncio
import json
import random
import subprocess
import shutil
from datetime import datetime
from dotenv import load_dotenv
import requests as _requests


def _trim_audio(audio_path: str, max_sec: float = 270, fade_sec: float = 5) -> float:
    """
    If audio_path is longer than max_sec, trim it in-place with a fade-out.
    Returns the actual duration after trimming.
    """
    import imageio_ffmpeg
    from music_video import get_audio_duration
    dur = get_audio_duration(audio_path)
    if dur <= max_sec:
        return dur
    tmp = audio_path + ".trimtmp.mp3"
    fade_start = max_sec - fade_sec
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    r = subprocess.run(
        [ffmpeg, "-y", "-i", audio_path,
         "-t", str(max_sec),
         "-af", f"afade=t=out:st={fade_start:.1f}:d={fade_sec}",
         "-q:a", "2", tmp],
        capture_output=True,
    )
    if r.returncode == 0:
        shutil.move(tmp, audio_path)
        print(f"[pipeline] Trimmed audio from {dur:.0f}s → {max_sec:.0f}s (fade-out {fade_sec}s)")
        return max_sec
    else:
        if os.path.exists(tmp):
            os.remove(tmp)
        print(f"[pipeline] Trim failed (non-fatal), keeping original {dur:.0f}s audio")
        return dur

load_dotenv()


# ── Pre-flight checks (run before Suno to avoid wasting credits) ────────────

def _preflight_checks(output_dir: str) -> None:
    """Raise early (before Suno is called) if any dependency will fail later."""
    import imageio_ffmpeg

    # 1. ffmpeg reachable
    try:
        ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
        r = subprocess.run([ffmpeg, "-version"], capture_output=True, timeout=10)
        if r.returncode != 0:
            raise RuntimeError("ffmpeg returned non-zero")
    except Exception as e:
        raise RuntimeError(f"[preflight] ffmpeg not working: {e}")

    # 2. Pexels API key valid (single cheap request)
    pexels_key = os.getenv("PEXELS_API_KEY", "")
    if not pexels_key:
        raise RuntimeError("[preflight] PEXELS_API_KEY not set")
    try:
        res = _requests.get(
            "https://api.pexels.com/videos/search",
            headers={"Authorization": pexels_key},
            params={"query": "nature", "per_page": 1},
            timeout=15,
        )
        if res.status_code == 401:
            raise RuntimeError("[preflight] PEXELS_API_KEY is invalid (401)")
        if res.status_code not in (200, 429):  # 429 = rate-limited but key is valid
            raise RuntimeError(f"[preflight] Pexels returned unexpected status {res.status_code}")
    except RuntimeError:
        raise
    except Exception as e:
        raise RuntimeError(f"[preflight] Pexels API check failed: {e}")

    print("[preflight] ffmpeg OK, Pexels key OK — safe to spend credits")


# ── YouTube upload ──────────────────────────────────────────────────────────

# ── Playlist helpers ────────────────────────────────────────────────────────

_PLAYLIST_CACHE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "playlist_ids.json")

def _get_or_create_playlist(youtube, genre_key: str) -> str:
    """Return playlist ID for the genre, creating it on YouTube if needed.
    IDs are cached locally in playlist_ids.json."""
    # Load cache
    cache = {}
    if os.path.exists(_PLAYLIST_CACHE_FILE):
        try:
            with open(_PLAYLIST_CACHE_FILE) as f:
                cache = json.load(f)
        except Exception:
            pass
    if genre_key in cache:
        return cache[genre_key]

    # Create playlist names per genre
    _PLAYLIST_NAMES = {
        "hugot_ballad":    "Hugot Ballads 💔 | Best OPM Heartbreak Songs 2026",
        "hugot_opm_pop":   "OPM Pop Hugot 🎵 | Trending Pinoy Love Songs 2026",
        "pinoy_rap_hugot": "Pinoy Rap Hugot 🔥 | Tagalog Trap & Hip Hop 2026",
        "opm_rnb_hugot":   "OPM R&B Hugot 🌙 | Late Night Pinoy Soul 2026",
        "pamana_folk_opm": "OPM Folk Hugot 🎸 | Heartfelt Filipino Acoustic Songs",
    }
    name = _PLAYLIST_NAMES.get(genre_key, f"OPM Music — {genre_key.replace('_', ' ').title()}")
    description = (
        f"Pinaka-magagandang hugot OPM songs na ai-generated. "
        f"Subscribe para laging updated sa bagong musika! 🇵🇭🎶 #OPM #Hugot #PinoyMusic"
    )
    try:
        resp = youtube.playlists().insert(
            part="snippet,status",
            body={
                "snippet": {"title": name, "description": description},
                "status": {"privacyStatus": "public"},
            },
        ).execute()
        playlist_id = resp["id"]
        cache[genre_key] = playlist_id
        with open(_PLAYLIST_CACHE_FILE, "w") as f:
            json.dump(cache, f, indent=2)
        print(f"[yt] Created playlist '{name}' → {playlist_id}")
        return playlist_id
    except Exception as e:
        print(f"[yt] Could not create playlist (non-fatal): {e}")
        return ""


# ── Upload ──────────────────────────────────────────────────────────────────

def upload_to_youtube(
    video_path: str,
    thumbnail_path: str,
    title: str,
    description: str,
    tags: list,
    first_comment: str = "",
    playlist_id: str = "",
    genre_key: str = "",
) -> str:
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow

    SCOPES = [
        "https://www.googleapis.com/auth/youtube.upload",
        "https://www.googleapis.com/auth/youtube",
    ]
    token_path = os.path.join(os.path.dirname(__file__), "token.json")
    creds_path = os.path.join(os.path.dirname(__file__), "credentials.json")

    creds = None
    if os.path.exists(token_path):
        creds = Credentials.from_authorized_user_file(token_path, SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            from google.auth.transport.requests import Request
            creds.refresh(Request())
            with open(token_path, "w") as f:
                f.write(creds.to_json())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(creds_path, SCOPES)
            creds = flow.run_local_server(port=0)
            with open(token_path, "w") as f:
                f.write(creds.to_json())

    youtube = build("youtube", "v3", credentials=creds)
    print("[yt] Uploading video...")

    # Resolve playlist (create if first time for this genre)
    if not playlist_id and genre_key:
        playlist_id = _get_or_create_playlist(youtube, genre_key)

    # Deduplicate tags, preserve order; YouTube allows ~500 chars total for tags
    seen = set()
    unique_tags = []
    for t in tags:
        tl = t.lower()
        if tl not in seen:
            seen.add(tl)
            unique_tags.append(t)

    # Determine content language for OPM (tells YouTube to serve to Filipino audience)
    _is_opm_lang = genre_key in {
        "hugot_ballad", "hugot_opm_pop", "pinoy_rap_hugot",
        "opm_rnb_hugot", "pamana_folk_opm", "pinoy_rant", "pinoy_protest_anthem",
    }

    insert_request = youtube.videos().insert(
        part="snippet,status",
        body={
            "snippet": {
                "title": title[:100],
                "description": description[:5000],
                "tags": unique_tags[:50],
                "categoryId": "10",  # Music category
                **({"defaultLanguage": "tl", "defaultAudioLanguage": "tl"} if _is_opm_lang else {}),
            },
            "status": {
                "privacyStatus": "public",
                "selfDeclaredMadeForKids": False,
                # Required by YouTube policy for AI-generated realistic content
                "containsSyntheticMedia": True,
            },
        },
        media_body=MediaFileUpload(video_path, chunksize=-1, resumable=True),
    )
    response = insert_request.execute()
    video_id = response["id"]

    if thumbnail_path and os.path.exists(thumbnail_path):
        print("[yt] Uploading thumbnail...")
        youtube.thumbnails().set(
            videoId=video_id,
            media_body=MediaFileUpload(thumbnail_path),
        ).execute()

    if first_comment:
        try:
            youtube.commentThreads().insert(
                part="snippet",
                body={
                    "snippet": {
                        "videoId": video_id,
                        "topLevelComment": {
                            "snippet": {"textOriginal": first_comment}
                        },
                    }
                },
            ).execute()
            print("[yt] First comment posted.")
        except Exception as e:
            print(f"[yt] Comment failed (non-fatal): {e}")

    if playlist_id:
        try:
            youtube.playlistItems().insert(
                part="snippet",
                body={
                    "snippet": {
                        "playlistId": playlist_id,
                        "resourceId": {"kind": "youtube#video", "videoId": video_id},
                    }
                },
            ).execute()
            print(f"[yt] Added to playlist {playlist_id}")
        except Exception as e:
            print(f"[yt] Playlist append failed (non-fatal): {e}")

    url = f"https://youtube.com/watch?v={video_id}"
    print(f"[yt] Live at: {url}")
    return url


# ── SEO description ─────────────────────────────────────────────────────────

def _generate_description(
    title: str,
    genre_dict: dict,
    lyrics: str,
    is_opm: bool = False,
    chapters: str = "",
    trend_topic: str = "",
) -> str:
    """Generate an SEO-optimised YouTube description via OpenRouter (or fallback)."""
    import datetime
    api_key = os.getenv("OPENROUTER_API_KEY", "")
    style = genre_dict.get("style", "music")
    year = datetime.date.today().year

    # Up to 15 hashtags — YouTube renders these as clickable links above the title
    hashtag_block = " ".join(
        f"#{t}" for t in (genre_dict.get("youtube_tags", []) + ["OPM", "PinoyMusic", "Trending"])[:15]
    )

    # Filipino-specific CTA (drives comments = strongest algorithm signal)
    if is_opm:
        topic_hook = f"Tungkol ito sa: {trend_topic}.\n" if trend_topic else ""
        cta_block = (
            f"{topic_hook}"
            "💬 Sino ang nasa isip mo habang pinapakingan ito? I-comment ka below 👇\n"
            "🔔 I-subscribe at i-on ang bell para hindi ka makaligtaan ng bagong OPM!\n"
            "❤️ I-share mo 'to sa taong kailangan marinig ito ngayon.\n"
            "👇 Buksan ang description para sa lyrics at chapters."
        )
    else:
        cta_block = (
            "🎵 New music uploaded daily — Subscribe so you never miss a track!\n"
            "🔔 Hit the bell icon to get notified!"
        )

    chapters_block = f"\n\n🎵 CHAPTERS\n{chapters}" if chapters else ""

    if api_key:
        import requests as _req
        if is_opm:
            prompt = (
                f"Write a YouTube description for this OPM music video.\n"
                f"Video title: '{title}'\n"
                f"Music style: {style}\n"
                f"Trending topic this song is about: '{trend_topic}'\n\n"
                f"RULES:\n"
                f"1. First sentence MUST contain the song title and the trending topic keyword (for YouTube search indexing).\n"
                f"2. Mention the year {year} and 'OPM' at least once each.\n"
                f"3. 120-160 words total. Tagalog/Taglish. Plain text only, no markdown, no bullet points.\n"
                f"4. Capture the main emotion (heartbreak / frustration / pag-asa / etc).\n"
                f"5. End with: 'Para sa bawat Pilipinong may nararamdaman ngayon — para ito sa inyo.' "
            )
        else:
            prompt = (
                f"Write a YouTube description for this music video.\n"
                f"Title: '{title}' | Style: {style}\n"
                f"150-200 words. Include: what the music is for, a subscribe CTA, mention AI-generated music. "
                f"Include the year {year}. Plain text only."
            )
        try:
            resp = _req.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json={"model": "google/gemini-2.0-flash-001",
                      "messages": [{"role": "user", "content": prompt}]},
                timeout=30,
            )
            if resp.status_code == 200:
                desc = resp.json()["choices"][0]["message"]["content"].strip()
                return f"{desc}\n\n{cta_block}{chapters_block}\n\n{hashtag_block}"
        except Exception as e:
            print(f"[desc] OpenRouter failed: {e}")

    # Fallback description
    first_line = lyrics.splitlines()[0] if lyrics else ""
    if is_opm:
        return (
            f"{title} — OPM {year}\n\n"
            f'"{first_line}"\n\n'
            f"Pakinggan mo ito kapag parang gusto mong mag-isa lang.\n"
            f"{('Tungkol ito sa: ' + trend_topic + chr(10)) if trend_topic else ''}"
            f"\n{cta_block}{chapters_block}\n\n{hashtag_block}"
        )
    return (
        f"{title}\n\n"
        f"Enjoy this AI-generated {style} track ({year}). Perfect for studying, relaxing, or setting the mood.\n\n"
        f'"{first_line}"\n\n'
        f"{cta_block}{chapters_block}\n\n{hashtag_block}"
    )


# ── First comment templates ─────────────────────────────────────────────────

_FIRST_COMMENTS = [
    "🎧 What are you listening to this for? Study? Work? Sleep? Drop it below 👇",
    "🎵 Let me know what genre you want next! Comment below 👇",
    "💬 This track goes hard — what's your favorite part? Comment the timestamp!",
    "🎶 Save this for your playlist! What mood does this music put you in?",
    "🔥 New music every week! Subscribe and hit the bell 🔔 so you never miss a drop!",
    "🎧 Turn up the volume and let this wash over you. What are you doing right now?",
]


OPM_GENRES = {
    "hugot_ballad", "hugot_opm_pop", "pinoy_rap_hugot",
    "opm_rnb_hugot", "pamana_folk_opm",
    "pinoy_rant", "pinoy_protest_anthem",       # political/rant genres
}

# ── Main pipeline ───────────────────────────────────────────────────────────

async def create_music_video(
    genre_key: str = None,
    output_dir: str = None,
    upload: bool = True,
    model: str = "V4_5ALL",
    instrumental: bool = False,
    resume_from: str = None,
) -> dict:
    from suno_api import generate_music, download_audio, get_credits
    from music_video import build_music_video
    from music_topics import get_random_genre, get_genre, build_video_title
    from thumbnail import generate_music_thumbnail

    # ── RESUME MODE: skip Suno entirely, reload from a previous checkpoint ──
    if resume_from:
        resume_from = os.path.abspath(resume_from)
        _ckpt_file = os.path.join(resume_from, "suno_checkpoint.json")
        if not os.path.exists(_ckpt_file):
            raise FileNotFoundError(
                f"[resume] No suno_checkpoint.json found in {resume_from}\n"
                "Make sure you point --resume at the output folder from a previous run."
            )
        with open(_ckpt_file) as _cf:
            _ckpt = json.load(_cf)
        print(f"[resume] Loaded Suno checkpoint: track='{_ckpt.get('track_title')}' "
              f"duration={_ckpt.get('track_duration')}s")

        # Infer genre_key from directory name (e.g. hugot_ballad_20260505_...)
        _dir_name = os.path.basename(resume_from)
        if not genre_key:
            for _sep in ("_202", "_"):
                if _sep in _dir_name:
                    _candidate = _dir_name.split(_sep)[0]
                    try:
                        genre_dict = get_genre(_candidate)
                        genre_key = _candidate
                        break
                    except Exception:
                        pass
        if not genre_key:
            raise RuntimeError(
                "[resume] Could not infer genre from directory name. "
                "Pass --genre explicitly (e.g. --genre hugot_ballad)."
            )
        genre_dict = get_genre(genre_key)
        print(f"[resume] Genre: {genre_key}")

        output_dir = resume_from
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        _preflight_checks(output_dir)

        # Reload lyrics
        _lyrics_suno = os.path.join(output_dir, "lyrics_suno.txt")
        _lyrics_orig = os.path.join(output_dir, "lyrics.txt")
        if os.path.exists(_lyrics_suno):
            caption_lyrics = open(_lyrics_suno, encoding="utf-8").read()
        elif os.path.exists(_lyrics_orig):
            caption_lyrics = open(_lyrics_orig, encoding="utf-8").read()
        else:
            raise FileNotFoundError("[resume] No lyrics.txt or lyrics_suno.txt found in output dir.")

        audio_url   = _ckpt["audio_url"]
        suno_task_id  = _ckpt.get("suno_task_id")
        suno_audio_id = _ckpt.get("suno_audio_id")

        # Re-download audio if missing (run may have died before download)
        audio_path = os.path.join(output_dir, "music.mp3")
        if not os.path.exists(audio_path) or os.path.getsize(audio_path) < 10_000:
            print("[resume] music.mp3 missing or incomplete — re-downloading from Suno URL...")
            download_audio(audio_url, audio_path)
        else:
            print("[resume] music.mp3 already present, skipping download.")
        actual_duration = _trim_audio(audio_path, max_sec=270, fade_sec=5)

        # Reload metadata for upload title / hook
        _meta_file = os.path.join(output_dir, "metadata.json")
        if os.path.exists(_meta_file):
            with open(_meta_file) as _mf:
                _meta = json.load(_mf)
            upload_title = _meta.get("title", genre_key)
            hook_text    = _meta.get("trend_story", "")[:70]
            song_title   = _meta.get("song_title", "")
            description  = _meta.get("description", "")
            tags         = _meta.get("tags", [])
        else:
            song_title   = _ckpt.get("track_title", "")
            title        = build_video_title(genre_dict, song_title=song_title)
            upload_title = title[:100]
            hook_text    = ""
            description  = ""
            tags         = genre_dict.get("youtube_tags", []) + ["music", "aimusic"]

        # Rebuild video
        print("[resume] Re-rendering video...")
        final_path = os.path.join(output_dir, "final.mp4")
        build_music_video(
            audio_path=audio_path,
            lyrics=caption_lyrics,
            title=song_title or upload_title,
            genre_dict=genre_dict,
            output_path=final_path,
            pexels_key=os.getenv("PEXELS_API_KEY", ""),
            hook_text=hook_text or None,
            song_title=song_title or upload_title,
        )

        # Regenerate thumbnail
        thumbnail_path = os.path.join(output_dir, "thumbnail.png")
        generate_music_thumbnail(
            title=upload_title,
            genre_key=genre_key,
            output_path=thumbnail_path,
            video_path=final_path,
            story_hook=hook_text or None,
            pexels_key=os.getenv("PEXELS_API_KEY", ""),
        )

        result = {
            "genre": genre_key,
            "title": upload_title,
            "song_title": song_title,
            "paths": {
                "audio": audio_path,
                "lyrics": _lyrics_orig if os.path.exists(_lyrics_orig) else _lyrics_suno,
                "final": final_path,
                "short": "",
                "thumbnail": thumbnail_path,
                "metadata": _meta_file if os.path.exists(_meta_file) else "",
            },
            "url": None,
            "short_url": None,
        }

        if upload:
            first_comment = random.choice(_FIRST_COMMENTS)
            result["url"] = upload_to_youtube(
                video_path=final_path,
                thumbnail_path=thumbnail_path,
                title=upload_title,
                description=description,
                tags=tags,
                first_comment=first_comment,
                genre_key=genre_key,
            )

        print(f"[resume] Done. URL: {result['url']}")
        return result
    # ── END RESUME MODE ─────────────────────────────────────────────────────

    # 1. Pick genre
    if genre_key:
        genre_dict = get_genre(genre_key)
    else:
        genre_key, genre_dict = get_random_genre()
    print(f"\n{'='*55}")
    print(f"Genre: {genre_key}")
    print(f"Style: {genre_dict['style'][:80]}")
    print(f"{'='*55}\n")

    # Check credits (kie.ai may not expose this endpoint — treat -1 as unknown/skip)
    try:
        credits = get_credits()
        if credits == -1:
            print("[suno] Credits endpoint unavailable — skipping credit check")
        else:
            print(f"[suno] Credits remaining: {credits}")
            if credits < 10:
                raise RuntimeError(f"[suno] Insufficient credits ({credits}) — need at least 10. Aborting before spending any.")
    except RuntimeError:
        raise
    except Exception as e:
        print(f"[suno] Could not fetch credits: {e}")

    # Output dir
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    if not output_dir:
        output_dir = os.path.join(os.path.dirname(__file__), "output", f"{genre_key}_{timestamp}")
    os.makedirs(output_dir, exist_ok=True)

    # --- Pre-flight checks (run BEFORE calling Suno to avoid wasting credits) ---
    _preflight_checks(output_dir)

    # 2. Generate lyrics
    song_title = ""
    trend_story = {}

    if genre_key in OPM_GENRES:
        # OPM/Rant path: fetch YouTube PH trending → classify genre → LLM lyrics
        from trending_ph import (
            get_ph_news_trending, pick_trending_story, format_trending_context,
        )
        from lyrics_generator import generate_tagalog_lyrics, generate_song_title, GENRE_PROMPTS

        print("[pipeline] Fetching PH trending news...")
        news_stories = get_ph_news_trending(max_results=20)

        # Auto-select genre from trending topic (unless genre was explicitly passed)
        if genre_key not in ("pinoy_rant", "pinoy_protest_anthem"):
            trend_story, detected_genre = pick_trending_story(news_stories)
            genre_key = detected_genre
            genre_dict = get_genre(genre_key)
            print(f"[pipeline] Auto-detected genre: {genre_key}")
        else:
            trend_story, _ = pick_trending_story(news_stories)
        trend_context = format_trending_context(trend_story)

        print(f"[pipeline] Trending topic: {trend_story['title']}")
        print(f"[pipeline] Genre: {genre_key}")

        print("[pipeline] Generating Tagalog lyrics via OpenRouter...")
        lyrics, suno_style_override = generate_tagalog_lyrics(trend_context, genre_key=genre_key)

        # Short Tagalog song title (for Suno music generation)
        print("[pipeline] Generating song title...")
        song_title = generate_song_title(lyrics, trend_story["title"], genre_key=genre_key)
        print(f"[pipeline] Song title: {song_title}")

        # Viral YouTube title — story-driven hook in Tagalog (for upload & thumbnail)
        from lyrics_generator import generate_viral_yt_title, generate_pinned_comment
        yt_title = generate_viral_yt_title(trend_story["title"], lyrics, genre_key=genre_key)
        print(f"[pipeline] YouTube title: {yt_title}")

        # Pinned first comment — LLM-generated emotional hook
        first_comment = generate_pinned_comment(trend_story["title"], lyrics)

        # Story intro cards + mid-video pull quotes
        from lyrics_generator import generate_story_cards
        _sc_data = generate_story_cards(trend_story["title"], trend_story.get("description", ""))
        story_card_list = _sc_data.get("intro", [])
        pull_quote_list = _sc_data.get("mid", [])
        print(f"[pipeline] Story cards: {len(story_card_list)} intro + {len(pull_quote_list)} mid-quotes")

        # Short story hook for video title card (first 5s retention)
        hook_text = trend_story["title"][:70]

        # Override the style from lyrics_generator (more specific than genre_dict)
        genre_dict = dict(genre_dict)
        genre_dict["style"] = suno_style_override
    else:
        # Non-OPM path: use Suno's own lyric generation
        from suno_api import generate_lyrics as suno_generate_lyrics
        print("[pipeline] Generating lyrics via Suno...")
        lyrics = suno_generate_lyrics(genre_dict["lyric_prompt"])
        yt_title = None
        hook_text = ""
        first_comment = random.choice(_FIRST_COMMENTS)
        story_card_list = []
        pull_quote_list = []

    lyrics_path = os.path.join(output_dir, "lyrics.txt")
    with open(lyrics_path, "w", encoding="utf-8") as f:
        f.write(lyrics)
    print(f"[pipeline] Lyrics saved ({len(lyrics)} chars)")

    # 3. Generate music via Suno (using lyrics from step 2)
    # yt_title   = viral story hook (YouTube, thumbnail, description)
    # song_title = short Tagalog title (Suno music generation)
    title = build_video_title(genre_dict, song_title=song_title)
    upload_title = (yt_title or title)[:100]  # what viewers see on YouTube
    print(f"[pipeline] Generating music via Suno: {upload_title}")
    music_result = generate_music(
        lyrics=lyrics,
        style=genre_dict["style"],
        title=(song_title or title)[:80],
        instrumental=instrumental,
        model=model,
    )

    tracks = music_result.get("tracks", [])
    if not tracks:
        raise RuntimeError("No tracks returned from Suno")

    # Pick the track with longest duration (guard against None duration)
    track = max(tracks, key=lambda t: t.get("duration") or 0)
    audio_url = track.get("audio_url", "")
    suno_task_id = music_result.get("taskId")
    suno_audio_id = track.get("id")
    print(f"[pipeline] Track: '{track.get('title')}'")

    # Checkpoint: save Suno result immediately so credits aren't wasted if
    # anything downstream (video render, upload) fails later.
    _checkpoint_path = os.path.join(output_dir, "suno_checkpoint.json")
    with open(_checkpoint_path, "w", encoding="utf-8") as _cf:
        json.dump({
            "audio_url": audio_url,
            "suno_task_id": suno_task_id,
            "suno_audio_id": suno_audio_id,
            "track_title": track.get("title"),
            "track_duration": track.get("duration"),
        }, _cf, indent=2)
    print(f"[pipeline] Suno checkpoint saved → {_checkpoint_path}")

    # Always use our original lyrics for captions — never Suno's modified version.
    # Suno may rewrite or paraphrase lyrics; our written lyrics are the canonical text
    # for captions/subtitles. Suno's version is saved for reference only.
    caption_lyrics = lyrics
    suno_lyrics = track.get("suno_lyrics", "").strip()
    if suno_lyrics and suno_lyrics != lyrics:
        suno_lyrics_path = os.path.join(output_dir, "lyrics_suno.txt")
        with open(suno_lyrics_path, "w", encoding="utf-8") as f:
            f.write(suno_lyrics)
        print(f"[pipeline] Suno drifted from our lyrics — saved to lyrics_suno.txt (not used for captions)")
    else:
        print("[pipeline] Suno lyrics match our input")

    # 4. Download audio then trim to max 270s (4.5 min) for watchability
    audio_path = os.path.join(output_dir, "music.mp3")
    download_audio(audio_url, audio_path)
    actual_duration = _trim_audio(audio_path, max_sec=270, fade_sec=5)

    # 4b. Story segments disabled — lyrics are shown on screen via segment-level Whisper sync.
    story_segments_list = None

    # 5. Build music video
    print("[pipeline] Building music video...")
    final_path = os.path.join(output_dir, "final.mp4")
    build_music_video(
        audio_path=audio_path,
        lyrics=caption_lyrics,
        title=song_title or title,
        genre_dict=genre_dict,
        output_path=final_path,
        pexels_key=os.getenv("PEXELS_API_KEY", ""),
        hook_text=hook_text,
        story_cards=story_card_list or None,
        pull_quotes=pull_quote_list or None,
        story_segments=None,
        song_title=song_title or title,
    )

    # 5b. Shorts removed (story-mode videos are long-form only)
    short_path = ""
    ass_path = os.path.join(output_dir, "lyrics.ass")
    is_opm = genre_key in OPM_GENRES

    # 6. Generate thumbnail (video frame + story hook as punchy big text)
    thumbnail_path = os.path.join(output_dir, "thumbnail.png")
    generate_music_thumbnail(
        title=upload_title,
        genre_key=genre_key,
        output_path=thumbnail_path,
        video_path=final_path,
        story_hook=hook_text or None,
        pexels_key=os.getenv("PEXELS_API_KEY", ""),
    )

    # 7. Build metadata (chapters from subtitle file + Filipino CTA for OPM)
    from music_video import extract_chapters_from_ass
    import datetime as _dt
    chapters = extract_chapters_from_ass(ass_path, song_title or title)
    _trend_topic = trend_story.get("title", "") if isinstance(trend_story, dict) else ""
    description = _generate_description(
        upload_title, genre_dict, lyrics,
        is_opm=is_opm, chapters=chapters,
        trend_topic=_trend_topic,
    )
    # Base tags from genre + universal music terms
    tags = genre_dict.get("youtube_tags", []) + ["music", "OPMmusic", str(_dt.date.today().year)]
    if is_opm:
        # High-volume Filipino search terms
        tags += [
            "OPM", "Tagalog", "PinoyMusic", "bagongOPM", "OPMhit",
            "HugotSongs", "pinoylovesong", "bagongkanta", "pampalipasoras",
        ]
        # Inject keywords extracted from the trending topic title
        if _trend_topic:
            _kw = [w for w in _trend_topic.split() if len(w) >= 4 and w.isalpha()]
            tags += [w.lower() for w in _kw[:6]]

    # Save metadata
    meta_path = os.path.join(output_dir, "metadata.json")
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump({
            "title": upload_title,
            "song_title": song_title,
            "description": description,
            "tags": tags,
            "genre": genre_key,
            "style": genre_dict["style"],
            "duration": actual_duration,
            "suno_task_id": suno_task_id,
            "suno_audio_id": suno_audio_id,
            "audio_url": audio_url,
            "trend_story": trend_story.get("title", ""),
            "trend_context": trend_story.get("description", ""),
        }, f, indent=2, ensure_ascii=False)

    result = {
        "genre": genre_key,
        "title": upload_title,
        "song_title": song_title,
        "paths": {
            "audio": audio_path,
            "lyrics": lyrics_path,
            "final": final_path,
            "short": short_path,
            "thumbnail": thumbnail_path,
            "metadata": meta_path,
        },
        "url": None,
        "short_url": None,
    }

    # 8. Upload to YouTube (main video + Short separately)
    if upload:
        result["url"] = upload_to_youtube(
            video_path=final_path,
            thumbnail_path=thumbnail_path,
            title=upload_title,
            description=description,
            tags=tags,
            first_comment=first_comment,
            genre_key=genre_key,
        )

        # Upload Short
        if short_path and os.path.exists(short_path):
            try:
                from googleapiclient.discovery import build as yt_build
                from google.oauth2.credentials import Credentials
                SCOPES = [
                    "https://www.googleapis.com/auth/youtube.upload",
                    "https://www.googleapis.com/auth/youtube",
                ]
                token_path = os.path.join(os.path.dirname(__file__), "token.json")
                creds = Credentials.from_authorized_user_file(token_path, SCOPES)
                youtube = yt_build("youtube", "v3", credentials=creds)
                from shorts import upload_short
                result["short_url"] = upload_short(
                    youtube=youtube,
                    short_path=short_path,
                    main_title=upload_title,
                    description=description,
                    tags=tags,
                    thumbnail_path=thumbnail_path,
                )
            except Exception as e:
                print(f"[pipeline] Short upload failed (non-fatal): {e}")

    # Save log
    log_path = os.path.join(os.path.dirname(__file__), "logs", f"{timestamp}.json")
    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    with open(log_path, "w") as f:
        json.dump({
            "date": datetime.now().isoformat(),
            "genre": genre_key,
            "title": upload_title,
            "output_dir": output_dir,
            "url": result["url"],
            "successful": 1,
            "failed": 0,
        }, f, indent=2)

    return result


# ── CLI entry ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="YouTube Music Niche Automation")
    parser.add_argument("--genre", default=None, help="Genre key (e.g. lofi_hiphop)")
    parser.add_argument("--no-upload", action="store_true", help="Skip YouTube upload")
    parser.add_argument("--model", default="V4_5ALL", help="Suno model version")
    parser.add_argument("--instrumental", action="store_true", help="Instrumental only")
    parser.add_argument("--output-dir", default=None, help="Custom output directory")
    parser.add_argument(
        "--resume", default=None, metavar="OUTPUT_DIR",
        help="Re-render video from a previous run's output folder (skips Suno, uses saved checkpoint)",
    )
    args = parser.parse_args()

    result = asyncio.run(create_music_video(
        genre_key=args.genre,
        output_dir=args.output_dir,
        upload=not args.no_upload,
        model=args.model,
        instrumental=args.instrumental,
        resume_from=args.resume,
    ))

    print("\n" + "="*55)
    print("DONE")
    print(f"  Title : {result['title']}")
    print(f"  Video : {result['paths']['final']}")
    print(f"  URL   : {result.get('url', 'Not uploaded')}")
    print("="*55)

