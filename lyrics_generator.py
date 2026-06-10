"""
lyrics_generator.py — Generate viral hugot Tagalog song lyrics via OpenRouter LLM.

Flow:
  1. Receive a trending PH story (title + context)
  2. Pick a genre from music_topics (hugot variants)
  3. Call OpenRouter (Gemini Flash / DeepSeek) to write structured lyrics
  4. Return lyrics string in Suno-compatible [Verse]/[Chorus]/[Bridge] format
"""

import os
import re
import requests
from dotenv import load_dotenv

load_dotenv()

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

# Models to try in order (fallback chain)
_MODELS = [
    "google/gemini-2.0-flash-001",
    "deepseek/deepseek-chat",
    "meta-llama/llama-3.3-70b-instruct",
]

# Genre-specific system instructions for OPM hugot styles
GENRE_PROMPTS = {
    "hugot_ballad": {
        "suno_style": "OPM ballad, hugot, emotional Filipino pop, slow piano, heartbreak, male/female vocals, cinematic strings",
        "instruction": (
            "Write a slow OPM hugot ballad in Tagalog/Taglish. "
            "Must have a deeply emotional, relatable chorus about heartbreak, longing, or sawi (unrequited love). "
            "Use vivid Filipino metaphors (e.g., 'ulan', 'bituin', 'daan', 'puso'). "
            "Structure: [Verse 1], [Pre-Chorus], [Chorus], [Verse 2], [Pre-Chorus], [Chorus], [Bridge], [Outro]"
        ),
    },
    "hugot_opm_pop": {
        "suno_style": "OPM pop, catchy Taglish, upbeat hugot, acoustic guitar, feel-good sad, Filipino millennial anthem",
        "instruction": (
            "Write a catchy OPM pop song in Taglish (mix of Tagalog and English). "
            "Upbeat feel but emotionally sawi — the type that goes viral on TikTok Philippines. "
            "Hook must be very quotable and shareable. Like Ben&Ben or Moira dela Torre style. "
            "Structure: [Verse 1], [Chorus], [Verse 2], [Chorus], [Bridge], [Chorus], [Outro]"
        ),
    },
    "pinoy_rap_hugot": {
        "suno_style": "Pinoy rap, trap OPM, hugot rap, Tagalog hip hop, Flow G style, emotional bars, urban Filipino",
        "instruction": (
            "Write a Pinoy rap/hip-hop song in Tagalog/Taglish. Flow G or Skusta Clee style. "
            "Hard-hitting emotional bars about heartbreak, betrayal, or moving on. "
            "Has both rap verses and a melodic sung chorus (hugot hook). "
            "Structure: [Intro], [Verse 1], [Hook], [Verse 2], [Hook], [Bridge], [Outro]"
        ),
    },
    "opm_rnb_hugot": {
        "suno_style": "OPM R&B, smooth Filipino soul, neo-soul, emotional Tagalog vocals, late night vibes, hugot",
        "instruction": (
            "Write a smooth OPM R&B/neo-soul song in Tagalog/Taglish. "
            "Late night, introspective, about missing someone, second-guessing yourself, or quiet heartbreak. "
            "Smooth vocal runs in the chorus. Inspired by Arthur Nery or Kyle Echarri style. "
            "Structure: [Verse 1], [Chorus], [Verse 2], [Chorus], [Bridge], [Chorus]"
        ),
    },
    "pamana_folk_opm": {
        "suno_style": "Filipino folk OPM, acoustic, heartfelt, Tagalog love song, Bamboo or Rivermaya inspired, storytelling",
        "instruction": (
            "Write a heartfelt Filipino folk/acoustic OPM song in Tagalog. "
            "Storytelling style — the kind that makes OFWs cry thinking of home or loved ones left behind. "
            "Inspired by Rivermaya, Bamboo, or Eraserheads. Simple imagery but deeply felt. "
            "Structure: [Verse 1], [Chorus], [Verse 2], [Chorus], [Bridge], [Final Chorus]"
        ),
    },
    "opm_funky_love": {
        "suno_style": (
            "A catchy, feel-good love song with a smooth funky pop style inspired by modern "
            "retro R&B. Upbeat groove, warm bassline, clean guitar riffs, soft synth layers, "
            "and a danceable rhythm. The vibe is romantic, playful, and slightly flirtatious—"
            "like falling in love unexpectedly. Male vocals with soulful delivery, light "
            "falsetto moments, and catchy melodic hooks. Chorus is addictive and easy to sing "
            "along to. Tempo is mid-to-upbeat, perfect for dancing or cruising at night. "
            "Overall mood: joyful, charming, and uplifting love energy."
        ),
        "instruction": (
            "Write a catchy, feel-good OPM love song in Taglish (natural Tagalog-English mix). "
            "The vibe is ROMANTIC, PLAYFUL, and FLIRTATIOUS — NOT a heartbreak or hugot song. "
            "Pure happy love energy: butterflies, laughter, dancing, late night drives, new love. "
            "The chorus must be ADDICTIVE and instantly singable — quotable on TikTok Philippines. "
            "Soulful male vocals with light falsetto moments and a warm funky feel. "
            "Opening line must be a vivid, specific romantic moment that hooks listeners immediately. "
            "Structure: [Verse 1], [Pre-Chorus], [Chorus], [Verse 2], [Pre-Chorus], [Chorus], [Bridge], [Chorus]"
        ),
    },
    "pinoy_rant": {
        "suno_style": (
            "Pinoy rant rap, angry Tagalog hip hop, social commentary, trap beat, "
            "frustrated Filipino voice, political satire, raw emotional delivery, spoken word"
        ),
        "instruction": (
            "Write a raw angry Pinoy rant rap/spoken word song in Tagalog about the trending issue. "
            "Channel the FRUSTRATION of an ordinary Filipino — rising prices, broken government promises, "
            "corruption, traffic, lack of ayuda, or whatever the trending issue is about. "
            "Be specific, sarcastic, and painfully relatable. Quotable punchlines. "
            "DO NOT sugarcoat — this is a RANT. But end with a sliver of stubborn Filipino resilience. "
            "Structure: [Intro], [Verse 1], [Hook], [Verse 2], [Hook], [Bridge], [Outro]"
        ),
    },
    "pinoy_protest_anthem": {
        "suno_style": (
            "Filipino protest anthem, OPM rock, powerful, emotional choir, "
            "Freddie Aguilar inspired, Noel Cabangon style, acoustic builds to electric, call to action"
        ),
        "instruction": (
            "Write a powerful Filipino protest anthem in Tagalog inspired by the trending issue. "
            "It should start quietly and build to a rousing, fist-raising chorus. "
            "Channel the spirit of Freddie Aguilar's 'Bayan Ko', APO's 'American Junk', or Noel Cabangon. "
            "About standing up, demanding accountability, and Filipino resilience and dignity. "
            "Structure: [Verse 1], [Chorus], [Verse 2], [Chorus], [Bridge], [Final Chorus]"
        ),
    },
}


# ── Preset romantic themes (replaces trending news as lyric inspiration) ────

_ROMANTIC_THEMES = [
    {"title": "Ang pag-ibig na hindi inaasahan", "description": "Unexpectedly falling for someone who changed everything."},
    {"title": "Ikaw ang dahilan ng aking ngiti", "description": "The person who is the reason you smile every single day."},
    {"title": "Mahal kita nang tahimik", "description": "A quiet, steady love — no grand gestures, just a constant warm presence."},
    {"title": "Crush na naging mahal sa buhay", "description": "When a simple crush slowly became the love of your life."},
    {"title": "Ang tamis ng bagong simula", "description": "The exciting, nervous sweetness of the very beginning of a love story."},
    {"title": "Gusto kitang kasama lagi", "description": "Wanting to be with someone always — every morning, every night, every moment."},
    {"title": "Pag-ibig sa unang titig", "description": "Love at first sight — that electric moment when eyes meet across a room."},
    {"title": "Hindi ako mapagod sa iyo", "description": "A love so good you never get tired — their presence is always enough."},
    {"title": "Ikaw ang sagot sa aking panalangin", "description": "You are the answer to a prayer I did not know I was making."},
    {"title": "Sa iyong tabi, ako ay kumpleto", "description": "Feeling whole and complete simply by being beside someone you love."},
    {"title": "Ang iyong ngiti ang nagpapagaan ng araw ko", "description": "Your smile makes every hard day lighter and worth living."},
    {"title": "Bago tayong matulog, ikaw ang huling iniisip ko", "description": "The person who is always the last thought before sleep."},
    {"title": "Nandito ako para sa iyo", "description": "Being fully, completely present for someone — through every moment."},
    {"title": "Ang dating mo ay biglang nag-iba", "description": "When you suddenly see a familiar person in a whole new light."},
    {"title": "Tayo ba naman ay para sa isa't isa", "description": "The beautiful uncertainty of new love — are we truly meant for each other?"},
    {"title": "Ang pag-ibig na nagbibigay inspirasyon", "description": "A love that motivates you to be the best version of yourself."},
    {"title": "First date na parang panaginip", "description": "A first date so magical it felt unreal — like living inside a dream."},
    {"title": "Ikaw lang ang nakakaintindi sa akin", "description": "You are the only one who truly understands me without any words."},
    {"title": "Ang boses mo ay musika sa aking tainga", "description": "Your voice is music — I could listen to it forever and never get tired."},
    {"title": "Sayaw tayo hanggang umaga", "description": "Dancing together until sunrise — lost in music and each other all night long."},
]



# ── Famous Tagalog songs — now loaded from famous_songs.json (400 entries) ──
# get_famous_song_theme() reads from that file and tracks usage in used_songs.csv

def get_famous_song_theme() -> dict:
    """
    Return a random famous Tagalog song that has NOT been used yet.
    Tracks usage in used_songs.csv. Resets automatically when all 400 are exhausted.
    """
    import random as _random
    import json
    import csv
    from pathlib import Path
    from datetime import date as _date

    root = Path(__file__).parent
    songs_file = root / "famous_songs.json"
    used_file = root / "used_songs.csv"

    # Load master list
    with open(songs_file, encoding="utf-8") as f:
        all_songs = json.load(f)

    # Load already-used song titles
    used_titles: set[str] = set()
    if used_file.exists():
        with open(used_file, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                used_titles.add(row.get("song", ""))

    # Filter to unused songs
    available = [s for s in all_songs if s["song"] not in used_titles]

    if not available:
        # Full cycle complete — reset and start over
        print(f"[songs] Full cycle complete ({len(all_songs)} songs used) — resetting")
        used_file.write_text("song,artist,date_used\n", encoding="utf-8")
        available = all_songs

    chosen = _random.choice(available)
    remaining = len(available) - 1

    # Append to CSV log
    write_header = not used_file.exists() or used_file.stat().st_size == 0
    with open(used_file, "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        if write_header:
            writer.writerow(["song", "artist", "date_used"])
        writer.writerow([chosen["song"], chosen["artist"], _date.today().isoformat()])

    print(f"[songs] Selected: \"{chosen['song']}\" — {remaining} songs remaining in cycle")
    return chosen


def get_romantic_theme() -> dict:
    """Return a random preset romantic theme for original love song generation."""
    import random as _random
    return _random.choice(_ROMANTIC_THEMES)


def format_famous_song_context(song: dict) -> str:
    """Build the LLM lyrics-generation context string from a famous song reference."""
    return (
        f'Song theme inspired by the emotion of the classic OPM song "{song["song"]}":\n'
        f'Core theme: {song["theme"]}\n'
        f'Emotional tone: {song["emotion"]}\n'
        f'NOTE: Write COMPLETELY ORIGINAL lyrics — do NOT copy or reference the original song. '
        f'Only the emotional theme and feeling should carry over.'
    )


def format_romantic_context(theme: dict) -> str:
    """Build the LLM lyrics-generation context string from a romantic theme."""
    return (
        f'Song theme: "{theme["title"]}"\n'
        f'Emotional context: {theme["description"]}'
    )


def _call_openrouter(messages: list[dict], model: str) -> str:
    """Call OpenRouter with a given model. Raises on failure."""
    api_key = os.getenv("OPENROUTER_API_KEY", "")
    if not api_key:
        raise RuntimeError("OPENROUTER_API_KEY not set in .env")

    resp = requests.post(
        OPENROUTER_URL,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/music-niche-automation",
        },
        json={
            "model": model,
            "messages": messages,
            "temperature": 0.9,
            "max_tokens": 1200,
        },
        timeout=45,
    )
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"].strip()


def _clean_lyrics(raw: str) -> str:
    """
    Strip LLM preamble, English-only translation lines, title lines, and markdown
    from raw LLM lyrics output. Keeps only Tagalog/Taglish lyric lines and section labels.
    """
    lines = raw.splitlines()
    result = []
    found_section = False
    _TAGALOG_MARKERS = (
        " ng ", " ko ", " mo ", " ka ", "ako", "ikaw", " sa ", " at ",
        " na ", " ang ", "siya", "niya", "namin", "natin", "nila",
        "mga ", "kung ", "bakit", "hindi", "para ", "wala", "mahal",
    )
    for line in lines:
        # Strip bold/italic markdown markers
        stripped = re.sub(r"\*+", "", line).strip()
        if not stripped:
            if found_section:
                result.append("")
            continue
        # Begin collecting from first [Section] label
        if re.match(r"^\[.+\]$", stripped):
            found_section = True
            result.append(stripped)
            continue
        if not found_section:
            continue
        # Skip "Title: ..." or "**Title**:" lines
        if re.match(r"^title\s*:", stripped, re.IGNORECASE):
            continue
        # Skip English-only parenthetical translation lines like (*Those stars...) or (Those...)
        if re.match(r"^\*?\s*\(", stripped) and stripped.rstrip("*").rstrip().endswith(")"):
            if not any(m in stripped.lower() for m in _TAGALOG_MARKERS):
                continue
        result.append(stripped)
    cleaned = "\n".join(result).strip()
    # If we found nothing (LLM skipped section labels), just strip the preamble lines
    if not cleaned:
        for line in lines:
            stripped = re.sub(r"\*+", "", line).strip()
            if stripped and not re.match(
                r"^(okay|here|sure|certainly|below|title|inspired|i've|i have)",
                stripped.lower(),
            ):
                result.append(stripped)
        cleaned = "\n".join(result).strip()
    return cleaned


def generate_tagalog_lyrics(
    trend_context: str,
    genre_key: str = "hugot_ballad",
    extra_instructions: str = "",
) -> tuple[str, str]:
    """
    Generate hugot Tagalog lyrics inspired by a trending PH story.

    Args:
        trend_context: Context string from trending_ph.format_story_context()
        genre_key: One of GENRE_PROMPTS keys
        extra_instructions: Optional extra direction for the LLM

    Returns:
        (lyrics: str, suno_style: str)
    """
    genre = GENRE_PROMPTS.get(genre_key, GENRE_PROMPTS["hugot_ballad"])

    system_prompt = (
        "You are a professional OPM (Original Pilipino Music) songwriter and political lyricist. "
        "You write viral, emotionally resonant songs in Tagalog and Taglish "
        "that Filipinos share on social media because they deeply relate to them. "
        "Your lyrics are poetic, specific, and deeply human — not generic. "
        "IMPORTANT OUTPUT FORMAT: Start DIRECTLY with [Verse 1] or [Intro] — "
        "no preamble, no title line, no explanation, no English translations. "
        "Output ONLY the raw song lyrics with section labels. "
        "These lyrics will be fed EXACTLY as written to a music AI — "
        "write them as clean, singable, final lyrics with no notes, no commentary. "
        "Do NOT include any English-only lines — keep it Tagalog or Taglish."
    )

    user_prompt = (
        f"Inspiration (trending news in the Philippines):\n{trend_context}\n\n"
        f"Genre instructions:\n{genre['instruction']}\n\n"
        f"Write a SHORT song (strictly 3-4 minutes when performed at normal ballad tempo). "
        f"Structure: [Verse 1] → [Pre-Chorus] → [Chorus] → [Verse 2] → [Chorus] → [Bridge] → [Outro]. "
        f"MAXIMUM 2 verses + 2 chorus repeats + 1 bridge + 1 outro. "
        f"Each section: maximum 4 lines. Keep it tight and punchy — less is more. "
        f"The song should be inspired by the trending news above — channel it "
        f"into a universal Filipino emotional experience: frustration, hope, resilience, "
        f"or the feeling of being an ordinary Filipino facing real everyday struggles. "
        f"Do NOT directly name news events, politicians, or headlines in the lyrics — "
        f"make it poetic and universally relatable.\n\n"
        f"CRITICAL — OPENING LINE RULE:\n"
        f"The VERY FIRST line of [Verse 1] must be a SINGLE sentence that:\n"
        f"  • Describes a SPECIFIC, vivid emotional moment (not a generic statement)\n"
        f"  • Uses 'ako', 'ikaw', 'natin', or 'mo' to make it personal\n"
        f"  • Is 8-12 syllables — singable in one breath\n"
        f"  • Makes a Filipino immediately think: 'ako 'to'\n"
        f"  • Example: 'Naalala ko pa 'yung gabing umalis ka nang walang paalam'\n"
        f"  • Example: 'Tinanong kita kung mahal mo pa ko — tumango ka lang'\n"
        f"This opening line will be the FIRST thing viewers hear and read — it determines if they stay.\n"
    )
    if extra_instructions:
        user_prompt += f"\nAdditional direction: {extra_instructions}\n"

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]

    last_error = None
    for model in _MODELS:
        try:
            print(f"[lyrics_gen] Trying model: {model}")
            raw = _call_openrouter(messages, model)
            lyrics = _clean_lyrics(raw)
            print(f"[lyrics_gen] Lyrics generated ({len(lyrics)} chars) via {model}")
            return lyrics, genre["suno_style"]
        except Exception as e:
            print(f"[lyrics_gen] Model {model} failed: {e}")
            last_error = e

    raise RuntimeError(f"All OpenRouter models failed. Last error: {last_error}")


def _extract_title(text: str, fallback: str) -> str:
    """Pull just the title out of a possibly verbose LLM response."""
    # Bold markdown: **Title**
    m = re.search(r'\*\*([^*]{3,60})\*\*', text)
    if m:
        return m.group(1).strip()
    # Quoted: "Title" or 'Title'
    m = re.search(r'["\u201c\u201d]([^"]{3,60})["\u201c\u201d]', text)
    if m:
        return m.group(1).strip()
    # Last short line that doesn't start with filler
    _FILLER = {"okay", "here", "sure", "certainly", "the", "a", "of", "title"}
    for line in reversed(text.strip().splitlines()):
        line = line.strip().strip('"\'*:-')
        words = line.split()
        if 2 <= len(words) <= 8 and words[0].lower() not in _FILLER:
            return line
    return text.strip()[:60]


_RANT_GENRES = {"pinoy_rant", "pinoy_protest_anthem"}


def generate_song_title(lyrics: str, trend_title: str, genre_key: str = "") -> str:
    """Ask the LLM to suggest a catchy OPM song title based on the lyrics and topic."""
    api_key = os.getenv("OPENROUTER_API_KEY", "")
    if not api_key:
        for line in lyrics.splitlines():
            line = line.strip()
            if line and not line.startswith("[") and len(line) > 10:
                return line[:60]
        return trend_title

    is_rant = genre_key in _RANT_GENRES
    if is_rant:
        title_instruction = (
            f"Trending news topic: \"{trend_title}\"\n"
            f"Song lyrics inspired by this topic:\n\n{lyrics[:600]}\n\n"
            "Suggest ONE short, powerful Filipino song title in Tagalog or Taglish "
            "that hints at the news topic (political frustration, protest, social issue). "
            "Should be 3-6 words max. Bold and defiant. No quotes, just the title."
        )
    else:
        title_instruction = (
            f"Given these OPM song lyrics:\n\n{lyrics[:600]}\n\n"
            "Suggest ONE short, catchy, viral OPM song title in Tagalog or Taglish. "
            "Should be 3-7 words max. Emotionally punchy. No quotes, just the title."
        )

    messages = [{"role": "user", "content": title_instruction}]
    try:
        raw = _call_openrouter(messages, _MODELS[0])
        return _extract_title(raw, trend_title)
    except Exception:
        for line in lyrics.splitlines():
            line = line.strip()
            if line and not line.startswith("[") and len(line) > 10:
                return line[:60]
        return trend_title


def generate_viral_yt_title(story_title: str, lyrics: str, genre_key: str = "", famous_song: dict | None = None) -> str:
    """
    Generate a punchy YouTube title in Tagalog/Taglish.

    Strategy per genre type:
      - opm_funky_love: title references the famous Tagalog song name for searchability
      - Rant/protest: title MUST reference the specific news event (political rage bait)
      - Hugot (love): title is a PURE EMOTIONAL HOOK derived from the LYRICS
    """
    api_key = os.getenv("OPENROUTER_API_KEY", "")
    is_rant = genre_key in _RANT_GENRES

    _SUFFIXES = {
        "hugot_ballad":         " | OPM Hugot 2026 🎵",
        "hugot_opm_pop":        " | OPM Pop 2026 🇵🇭",
        "pinoy_rap_hugot":      " | Pinoy Rap 2026 🎤",
        "opm_rnb_hugot":        " | OPM R&B 2026 🌙",
        "pamana_folk_opm":      " | OPM Folk 2026 🎸",
        "opm_funky_love":       " | OPM Love Song 2026 🇵🇭",
        "pinoy_rant":           " | Pinoy Rant Song 😤",
        "pinoy_protest_anthem": " | OPM Protest Song 🇵🇭",
    }
    suffix = _SUFFIXES.get(genre_key, " | OPM 2026 🇵🇭")
    max_base = 100 - len(suffix)

    if not api_key:
        if genre_key == "opm_funky_love" and famous_song:
            base = f'"{famous_song["song"]}" — Bagong OPM Love Song (AI Version) 🎵'
            return base[:max_base].rstrip() + suffix
        for line in lyrics.splitlines():
            line = line.strip()
            if line and not line.startswith("[") and len(line) > 15:
                return line[:max_base].rstrip() + suffix
        return story_title[:max_base].rstrip() + suffix

    if genre_key == "opm_funky_love" and famous_song:
        # Title references the famous song name to catch search traffic,
        # but makes clear it is a fresh new version — NOT a cover.
        best_lines = "\n".join(
            line.strip() for line in lyrics.splitlines()
            if line.strip() and not line.strip().startswith("[") and len(line.strip()) > 15
        )[:300]
        content = (
            f"Famous OPM song for reference: \"{famous_song['song']}\" by {famous_song['artist']}\n"
            f"New original song theme: {famous_song['theme']}\n"
            f"Sample lyrics from the new original song:\n{best_lines}\n\n"
            "Write ONE viral YouTube title in Tagalog or Taglish for this NEW original music video.\n"
            "RULES:\n"
            f"1. MUST include the famous song title \"{famous_song['song']}\" in the title (in quotes).\n"
            "2. MUST include the words 'AI Version' somewhere in the title.\n"
            "3. Use curiosity gap (... or —) to make people click.\n"
            "4. Feel-good, romantic, upbeat energy — NOT hugot or heartbreak.\n"
            "5. Sound like something you would share on Facebook or TikTok Philippines.\n"
            f"Good examples (for song 'Ikaw'):\n"
            "- '\"Ikaw\" — Bagong OPM Love Song (AI Version) 💛'\n"
            "- 'Parang \"Ikaw\" Pero Mas Feel-Good — AI Version 😍'\n"
            "- '\"Ikaw\" AI Version — Kinikilig Ako Sa Kantang Ito!'\n"
            f"Max {max_base} characters. No hashtags. No markdown. Just the title."
        )
    elif is_rant:
        # Rant genres: title must directly name the news event so Filipinos recognize it
        content = (
            f"Trending news topic: \"{story_title}\"\n"
            f"Sample lyrics:\n{lyrics[:300]}\n\n"
            "Write ONE punchy YouTube title in Tagalog or Taglish that DIRECTLY references "
            "this specific news topic — a Filipino viewer must instantly recognize what news event this is about. "
            "Style: outraged, emotional, or eye-opening commentary — the kind shared on Facebook.\n"
            "Examples:\n"
            "- 'Bakit Nilaban Nila si Sara? Ang Boto Na Nagpagalit sa Pilipinas'\n"
            "- 'Nagkamali Ba ang Kongreso? Ito ang Katotohanang Ayaw Nilang Marinig'\n"
            "- 'Taas Presyo Na Naman — Gaano Pa Natin Kaya ang Sistemang Ito?'\n"
            f"Max {max_base} characters. No hashtags. No markdown. No quotes. Just the title."
        )
    else:
        # Hugot genres: title is a LYRIC-BASED emotional hook.
        best_lines = "\n".join(
            line.strip() for line in lyrics.splitlines()
            if line.strip() and not line.strip().startswith("[") and len(line.strip()) > 15
        )[:400]
        content = (
            f"These are the most emotional lines from an OPM hugot song:\n{best_lines}\n\n"
            "Write ONE viral YouTube title in Tagalog or Taglish for this music video.\n"
            "RULES:\n"
            "1. The title must come from the EMOTION and STORY in the lyrics — NOT from any news topic or event name.\n"
            "2. Use second-person 'ikaw/mo/ka' perspective so it feels personal to the viewer.\n"
            "3. Use ellipsis (...) or em-dash (—) to create a curiosity gap.\n"
            "4. Style: sounds like a real Filipino telling their love story to a friend.\n"
            "Good examples:\n"
            "- 'Sabi Niya Mahal Niya Ako... Tapos Pinili Niya Pa Rin Ang Iba'\n"
            "- 'Isang Taon Na Akong Naghintay... Hindi Ka Naman Pala Babalik'\n"
            "- 'Iniwanan Mo Ako — Tapos Ngayon Nagso-Sorry Ka Na Lang?'\n"
            "- 'Mahal Pa Rin Kita Kahit Matagal Ka Nang Nawala Sa Buhay Ko'\n"
            "- 'Bakit Ngayon Ka Nagbabalik... Kailan Pa Naging Madali Para Sa Iyo Ito?'\n"
            f"Max {max_base} characters. No hashtags. No news topic names. No markdown. Just the title."
        )

    messages = [{"role": "user", "content": content}]
    try:
        raw = _call_openrouter(messages, _MODELS[0])
        title = re.sub(r'\*+', '', raw).strip().strip('"\'').split("\n")[0].strip()
        base = title if title else story_title
        # For opm_funky_love: if LLM forgot the song name, build a guaranteed template
        if genre_key == "opm_funky_love" and famous_song:
            song_name = famous_song["song"]
            if song_name.lower() not in base.lower():
                base = f'"{song_name}" — Bagong OPM Love Song (AI Version) 🎵'
        return base[:max_base].rstrip() + suffix
    except Exception:
        if genre_key == "opm_funky_love" and famous_song:
            base = f'"{famous_song["song"]}" — Bagong OPM Love Song (AI Version) 🎵'
            return base[:max_base].rstrip() + suffix
        for line in lyrics.splitlines():
            line = line.strip()
            if line and not line.startswith("[") and len(line) > 15:
                return line[:max_base].rstrip() + suffix
        return story_title[:max_base].rstrip() + suffix


def generate_pinned_comment(story_title: str, lyrics: str) -> str:
    """
    Generate a viral pinned comment tied to the trending news topic.
    """
    api_key = os.getenv("OPENROUTER_API_KEY", "")
    if not api_key:
        return "🇵🇭 Para sa bawat Pilipinong may nararamdaman tungkol dito...\n\nI-share mo 'to sa kaibigan mong kailangan marinig ito 👇"

    messages = [
        {
            "role": "user",
            "content": (
                f"Trending news topic: \"{story_title}\"\n"
                f"Sample lyrics:\n{lyrics[:400]}\n\n"
                "Write a short pinned YouTube comment (4 lines max) that:\n"
                "1. Reacts to the trending news topic in Tagalog/Taglish — what most Filipinos are feeling right now\n"
                "2. Quotes the most powerful lyric line from above (in quotes)\n"
                "3. Asks viewers a question about the topic to drive replies (e.g., 'Ano ang nararamdaman mo tungkol dito?')\n"
                "4. Ends with: 'I-share mo 'to sa lahat ng Pilipinong kailangan marinig ito 🇵🇭'\n"
                "Use emojis naturally. Keep it passionate and real."
            ),
        }
    ]
    try:
        raw = _call_openrouter(messages, _MODELS[0])
        return raw.strip()[:600]
    except Exception:
        return "🇵🇭 Para sa bawat Pilipinong may nararamdaman tungkol dito...\n\nI-share mo 'to sa kaibigan mong kailangan marinig ito 👇"


def generate_viral_story_segments(story_title: str, story_description: str, duration: float) -> list:
    """
    Rewrite a PH trending news story into viral Tagalog text cards for the full video duration.
    Returns a list of short strings (one per on-screen card).

    Target: ~1 card per 5 seconds (e.g. 270s → ~54 cards).
    """
    target_cards = max(20, min(60, int(duration / 5)))

    fallback = [
        f"TRENDING: {story_title[:60]}" if story_title else "Trending ngayon sa Pilipinas...",
        "Ito ang usap-usapan ng buong bansa ngayon.",
        "Alamin natin kung bakit. 👇",
    ]

    api_key = os.getenv("OPENROUTER_API_KEY", "")
    if not api_key or not story_description:
        # Spread fallback evenly
        repeats = max(1, target_cards // len(fallback))
        return (fallback * repeats)[:target_cards]

    context = story_description.strip()[:1200]
    messages = [
        {
            "role": "user",
            "content": (
                f"Trending news in the Philippines: \"{story_title}\"\n"
                f"News details:\n{context}\n\n"
                "You are writing text cards for a VIRAL Filipino YouTube channel that covers trending PH news "
                "set to OPM music — like a news explainer but emotional and conversational.\n\n"
                "YOUR TASK:\n"
                f"1. Explain this news story in EXACTLY {target_cards} short text cards.\n"
                "2. LANGUAGE: TAGALOG ONLY. Conversational Filipino — like telling the news to a friend on chat. "
                "Use Filipino internet slang naturally ('grabe', 'shet', 'totoo ba to', 'luh', 'talaga', 'naman').\n"
                "3. Each card = 1-2 punchy sentences, MAX 15 words. Easy to read in 4 seconds.\n"
                "4. Card 1 = HOOK: Start with the most shocking or surprising part of the news.\n"
                "5. Cards 2-5 = Background: Sino, ano, kailan, saan.\n"
                f"6. Cards 6-{target_cards - 4} = Full story with rising tension and key details.\n"
                f"7. Cards {target_cards - 3}-{target_cards} = Reaction + emotional punchline + Filipino resilience/call to action.\n"
                "8. Emojis (😤 😱 🇵🇭 💪 🔥 👀) — max 1 per card, gamitin nang maingat.\n"
                "9. WALANG hashtag. WALANG 'Part 1/2'. WALANG card numbers. WALANG bullet points.\n\n"
                f"OUTPUT FORMAT: Exactly {target_cards} linya, isa lang bawat card:\n"
                "line1\nline2\nline3\n..."
            ),
        }
    ]

    try:
        raw = _call_openrouter(messages, _MODELS[0])
        segments = []
        for line in raw.splitlines():
            line = line.strip()
            if not line:
                continue
            # Strip LLM artifacts: "1.", "Card 1:", "- ", "line1", etc.
            line = re.sub(r'^[\d]+[\.\)]\s*', '', line)
            line = re.sub(r'^(?:card|slide|text|line)\s*\d+[:\-]?\s*', '', line, flags=re.IGNORECASE)
            line = line.lstrip('-• ').strip()
            if line:
                segments.append(line)

        # Trim or pad to target_cards
        if len(segments) >= target_cards * 0.7:
            return segments[:target_cards]
        # Too few — fallback
        print(f"[story_segs] Only {len(segments)} segments from LLM (wanted {target_cards}), using raw split")
    except Exception as e:
        print(f"[story_segs] Generation failed: {e}")

    # Fallback: split raw story text into ~15-word chunks
    words = story_description.split()
    chunk_size = max(8, len(words) // target_cards)
    segments = []
    for i in range(0, len(words), chunk_size):
        segments.append(" ".join(words[i:i + chunk_size]))
    return segments[:target_cards] or fallback


def generate_story_cards(story_title: str, story_description: str) -> dict:
    """
    Generate 5 short story intro text cards + 2 mid-video pull quotes.
    Returns {"intro": [str x5], "mid": [str x2]}

    These cards play over the instrumental intro (0-22s) to hook the viewer
    with the trending news story before the vocals kick in.
    """
    fallback_intro = [
        "Trending ngayon sa Pilipinas...",
        story_title[:60] if story_title else "Ito ang usap-usapan ng bansa.",
        "Ito ang nararamdaman ng bawat Pilipino.",
        "Handa ka na bang marinig ang buong kwento?",
        "Ang kantang ito ay para sa lahat ng Pilipino.",
    ]
    fallback_mid = [
        "Hindi tayo titigil sa pakikipaglaban.",
        "Sama-sama tayong babangon.",
    ]

    api_key = os.getenv("OPENROUTER_API_KEY", "")
    if not api_key:
        return {"intro": fallback_intro, "mid": fallback_mid}

    context = (story_description or "").strip()[:350] or story_title
    messages = [
        {
            "role": "user",
            "content": (
                f"Trending news topic in the Philippines: \"{story_title}\"\n"
                f"Details: {context}\n\n"
                "Gumawa ng text cards para sa Filipino viral news + OPM music video.\n"
                "3 intro cards (max 8 words bawat isa) at 2 mid-video quotes (max 8 words).\n"
                "Tagalog/Taglish. Walang hashtag. Emotional at relatable.\n\n"
                "Card 1: Ang pinaka-shocking na detalye ng balita (short, punchy hook)\n"
                "Card 2: Kung bakit mahalaga ito sa bawat Pilipino\n"
                "Card 3: Dedication ('Ang kantang ito ay para sa lahat ng Pilipino...')\n"
                "Mid 1: Pinaka-makapangyarihang insight tungkol sa balita (max 8 words)\n"
                "Mid 2: Pag-asa o tawag sa aksyon (max 8 words)\n\n"
                "EXACTLY this format, nothing else:\n"
                "INTRO:\ncard1\ncard2\ncard3\nMID:\nquote1\nquote2"
            ),
        }
    ]
    try:
        raw = _call_openrouter(messages, _MODELS[0])
        result: dict = {"intro": [], "mid": []}
        section = None
        for line in raw.splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            up = stripped.upper()
            if up.startswith("INTRO"):
                section = "intro"
                continue
            if up.startswith("MID"):
                section = "mid"
                continue
            cleaned = stripped.lstrip("0123456789.-) ")
            # Strip LLM label prefixes like "Card 1:", "Cards:", "Quote 1:"
            cleaned = re.sub(r'^(?:cards?|quote|intro|mid)\s*\d*[:\-]\s*', '', cleaned, flags=re.IGNORECASE).strip()
            if not cleaned:
                continue
            if section == "intro" and len(result["intro"]) < 3:
                result["intro"].append(cleaned)
            elif section == "mid" and len(result["mid"]) < 2:
                result["mid"].append(cleaned)
        if len(result["intro"]) < 2:
            result["intro"] = fallback_intro[:3]
        if len(result["mid"]) < 1:
            result["mid"] = fallback_mid
        return result
    except Exception as e:
        print(f"[story_cards] Generation failed: {e}")
        return {"intro": fallback_intro, "mid": fallback_mid}


if __name__ == "__main__":
    from trending_ph import get_trending_ph, pick_hugot_story, format_story_context

    print("Fetching PH trends...")
    stories = get_trending_ph(max_results=15)
    story = pick_hugot_story(stories)
    context = format_story_context(story)

    print(f"\nTrending story: {story['title']}")
    print(f"Context: {context}\n")

    lyrics, style = generate_tagalog_lyrics(context, genre_key="hugot_ballad")
    title = generate_song_title(lyrics, story["title"])

    print(f"\n{'='*60}")
    print(f"SONG TITLE: {title}")
    print(f"SUNO STYLE: {style}")
    print(f"{'='*60}\n")
    print(lyrics)
