"""
test_video.py — Build a sample music video locally WITHOUT waiting for Suno.

Generates:
  1. A 3-minute test audio (musical chord tone via ffmpeg lavfi)
  2. Tagalog hugot lyrics via OpenRouter (fast, ~5s)
  3. Full music video with all viral effects (xfade, waveform, ASS subs, etc.)
  4. Opens the result in your default video player

Usage:
    python test_video.py [--genre hugot_ballad]
"""

import os
import sys
import subprocess
import argparse
import imageio_ffmpeg
from dotenv import load_dotenv

load_dotenv()

# ── Sample lyrics fallback (in case OpenRouter is unavailable) ───────────────
SAMPLE_LYRICS = """\
[Verse 1]
Nakaupo sa sulok, TV ang kaharap
Sa screen, ika'y nagniningning, walang kapantay
Anim na taon kitang sinuportahan
Mga pangarap mo, aking inalagaan

[Pre-Chorus]
Pero sa bawat hakbang mo papalayo
May kirot sa puso, hindi ko maitago
Alam ko naman, hindi ako ang para sa'yo
Pero bakit ganito kasakit, mahal ko?

[Chorus]
Korona ng pangarap, sa ulo mo'y nakapatong
Pero puso ko'y wasak, parang basag na garapon
Ikaw ang bituin, ako'y hamak na ilaw lang
Sa mundo ng pangarap mo, ako'y iiwanan

[Verse 2]
Naalala ko pa, sa La Union tayo'y nagkita
Mga simpleng araw, puno ng saya't alaala
Ngayon, ikaw ay reyna, ako'y nasa likod mo
Nagmamahal nang tahimik, 'di na magpapakita

[Chorus]
Korona ng pangarap, sa ulo mo'y nakapatong
Pero puso ko'y wasak, parang basag na garapon
Ikaw ang bituin, ako'y hamak na ilaw lang
Sa mundo ng pangarap mo, ako'y iiwanan

[Bridge]
Uulan na naman, parang puso kong umiiyak
Sa bawat patak, mga alaala'y bumabalik
Sana'y maging masaya ka, kahit wala ako
'Yan ang tanging hiling, bago tuluyang lumayo

[Outro]
Korona ng pangarap, ika'y Reyna magpakailanman
Ako'y mananatiling tagahanga, sa'yong tagumpay nakatanaw
Paalam, mahal ko, paalam na
Sa'yong paglisan, puso ko'y magpapaalam
"""

SAMPLE_TITLE = "Korona ng Pangarap"


def generate_test_audio(output_path: str, duration: int = 180):
    """
    Generate a musical test audio using ffmpeg lavfi.
    Uses a layered chord (A2 + E3 + A3 + C#4) with soft attack,
    sounds vaguely like a slow OPM ballad pad.
    """
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    # Chord of A minor: A2 + E3 + A3 + C4, slow tremolo
    expr = (
        "0.3*sin(2*PI*110*t)*exp(-0.003*t)"    # A2 bass
        "+0.25*sin(2*PI*165*t)*exp(-0.004*t)"  # E3
        "+0.3*sin(2*PI*220*t)*exp(-0.002*t)"   # A3
        "+0.2*sin(2*PI*261.6*t)*exp(-0.003*t)" # C4
        "+0.1*sin(2*PI*330*t)*exp(-0.005*t)"   # E4
    )
    cmd = [
        ffmpeg, "-y",
        "-f", "lavfi",
        "-i", f"aevalsrc='{expr}|{expr}':c=stereo:s=44100",
        "-t", str(duration),
        "-af", "volume=0.8,afade=t=in:d=2,afade=t=out:st={fade_start}:d=3".format(
            fade_start=duration - 3
        ),
        "-c:a", "libmp3lame", "-b:a", "192k",
        output_path,
    ]
    print(f"[test] Generating {duration}s test audio...")
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    if r.returncode != 0:
        raise RuntimeError(f"Test audio generation failed:\n{r.stderr[-500:]}")
    print(f"[test] Audio -> {output_path}")


def get_lyrics_from_openrouter(genre_key: str) -> tuple[str, str]:
    """Try to fetch real Tagalog lyrics from OpenRouter. Returns (lyrics, title)."""
    try:
        from trending_ph import get_trending_ph, pick_hugot_story, format_story_context
        from lyrics_generator import generate_tagalog_lyrics, generate_song_title

        print("[test] Fetching PH trends...")
        stories = get_trending_ph(max_results=10)
        story = pick_hugot_story(stories)
        context = format_story_context(story)
        print(f"[test] Trend: {story['title']}")

        print("[test] Generating lyrics via OpenRouter...")
        lyrics, _ = generate_tagalog_lyrics(context, genre_key=genre_key)
        title = generate_song_title(lyrics, story["title"])
        return lyrics, title
    except Exception as e:
        print(f"[test] OpenRouter failed ({e}), using sample lyrics")
        return SAMPLE_LYRICS, SAMPLE_TITLE


def main():
    parser = argparse.ArgumentParser(description="Build a test music video locally")
    parser.add_argument("--genre", default="hugot_ballad",
                        help="Genre key (default: hugot_ballad)")
    parser.add_argument("--duration", type=int, default=180,
                        help="Test audio duration in seconds (default: 180)")
    parser.add_argument("--no-llm", action="store_true",
                        help="Skip OpenRouter, use built-in sample lyrics")
    parser.add_argument("--no-open", action="store_true",
                        help="Don't auto-open the video after rendering")
    args = parser.parse_args()

    pexels_key = os.getenv("PEXELS_API_KEY", "")
    if not pexels_key:
        print("ERROR: PEXELS_API_KEY not set in .env")
        sys.exit(1)

    from datetime import datetime
    from music_video import build_music_video
    from music_topics import get_genre

    genre_key = args.genre
    genre_dict = get_genre(genre_key)

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = os.path.join(os.path.dirname(__file__), "output", f"test_{genre_key}_{ts}")
    os.makedirs(out_dir, exist_ok=True)

    # 1. Generate test audio
    audio_path = os.path.join(out_dir, "test_audio.mp3")
    generate_test_audio(audio_path, duration=args.duration)

    # 2. Get lyrics
    if args.no_llm:
        lyrics, title = SAMPLE_LYRICS, SAMPLE_TITLE
        print(f"[test] Using sample lyrics: {title}")
    else:
        lyrics, title = get_lyrics_from_openrouter(genre_key)
        print(f"[test] Song: {title}")

    # Save lyrics
    lyrics_path = os.path.join(out_dir, "lyrics.txt")
    with open(lyrics_path, "w", encoding="utf-8") as f:
        f.write(f"Title: {title}\n\n{lyrics}")

    # 3. Build video
    print(f"\n[test] Building video with genre '{genre_key}' effects...")
    final_path = os.path.join(out_dir, "test_final.mp4")
    build_music_video(
        audio_path=audio_path,
        lyrics=lyrics,
        title=title,
        genre_dict=genre_dict,
        output_path=final_path,
        pexels_key=pexels_key,
    )

    print(f"\n{'='*60}")
    print(f"TEST VIDEO READY: {final_path}")
    print(f"{'='*60}")

    # 4. Open video
    if not args.no_open:
        print("[test] Opening video...")
        os.startfile(final_path)


if __name__ == "__main__":
    main()
