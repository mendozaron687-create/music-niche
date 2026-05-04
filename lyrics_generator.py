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
}


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
        "You are a professional OPM (Original Pilipino Music) songwriter. "
        "You write viral, emotionally resonant hugot songs in Tagalog and Taglish "
        "that Filipinos share on social media because they deeply relate to them. "
        "Your lyrics are poetic, specific, and deeply human — not generic. "
        "IMPORTANT OUTPUT FORMAT: Start DIRECTLY with [Verse 1] — no preamble, no title line, "
        "no explanation, no English translations. Just the raw song lyrics with section labels. "
        "Do NOT include any English-only lines — keep it Tagalog or Taglish."
    )

    user_prompt = (
        f"Inspiration (trending story in the Philippines):\n{trend_context}\n\n"
        f"Genre instructions:\n{genre['instruction']}\n\n"
        f"Write a SHORT song (strictly 3-4 minutes when performed at normal ballad tempo). "
        f"Structure: [Verse 1] → [Pre-Chorus] → [Chorus] → [Verse 2] → [Chorus] → [Bridge] → [Outro]. "
        f"MAXIMUM 2 verses + 2 chorus repeats + 1 bridge + 1 outro. "
        f"Each section: maximum 4 lines. Keep it tight and punchy — less is more. "
        f"The song theme should be inspired by the trending story above — adapt it "
        f"into a universal hugot/heartbreak/relatable emotional experience that Filipinos "
        f"can deeply connect with. Don't directly name celebrities or news events.\n"
        f"Make the opening line instantly hook the listener.\n"
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


def generate_song_title(lyrics: str, trend_title: str) -> str:
    """Ask the LLM to suggest a catchy OPM song title based on the lyrics."""
    api_key = os.getenv("OPENROUTER_API_KEY", "")
    if not api_key:
        # Fallback: extract first memorable line
        for line in lyrics.splitlines():
            line = line.strip()
            if line and not line.startswith("[") and len(line) > 10:
                return line[:60]
        return trend_title

    messages = [
        {
            "role": "user",
            "content": (
                f"Given these OPM song lyrics:\n\n{lyrics[:800]}\n\n"
                f"Suggest ONE short, catchy, viral OPM song title in Tagalog or Taglish. "
                f"Should be 3-7 words max. Emotionally punchy. No quotes, just the title."
            ),
        }
    ]
    try:
        raw = _call_openrouter(messages, _MODELS[0])
        return _extract_title(raw, trend_title)
    except Exception:
        for line in lyrics.splitlines():
            line = line.strip()
            if line and not line.startswith("[") and len(line) > 10:
                return line[:60]
        return trend_title


def generate_viral_yt_title(story_title: str, lyrics: str) -> str:
    """
    Generate a punchy story-driven YouTube title in Tagalog/Taglish.
    These hook-style titles get clicked — not generic "— Filipino Heartbreak Song" suffixes.
    """
    api_key = os.getenv("OPENROUTER_API_KEY", "")
    if not api_key:
        return story_title[:100]

    messages = [
        {
            "role": "user",
            "content": (
                f"Reddit story inspiration: \"{story_title}\"\n"
                f"First lyric lines:\n{lyrics[:300]}\n\n"
                "Write ONE viral YouTube title in Tagalog or Taglish for this OPM hugot music video. "
                "Style: emotional story hook, the kind Filipinos share on social media. "
                "Examples of the right vibe:\n"
                "- 'Sabi Niya Mahal Niya Ako... Tapos Pinili Niya Pa Rin Ang Iba'\n"
                "- 'Isang Taon Na Hinintay Kita... Hindi Ka Naman Bumalik'\n"
                "- 'Iniwanan Mo Ako Para Sa Iyong Ex... Tapos Nagsorry Ka Nang Matagal Na'\n"
                "Max 90 characters. No hashtags. No quotes around the title. Just the title."
            ),
        }
    ]
    try:
        raw = _call_openrouter(messages, _MODELS[0])
        title = raw.strip().strip('"\'').split("\n")[0].strip()
        return title[:100] if title else story_title[:100]
    except Exception:
        return story_title[:100]


def generate_pinned_comment(story_title: str, lyrics: str) -> str:
    """
    Generate a viral pinned comment: emotional reflection + hitting lyric + engagement question + share CTA.
    """
    api_key = os.getenv("OPENROUTER_API_KEY", "")
    if not api_key:
        return "💔 Para sa lahat ng nasaktan... Alam ko kung paano 'yan.\n\nI-share mo 'to sa taong kailangan marinig ito 👇"

    messages = [
        {
            "role": "user",
            "content": (
                f"Song inspired by: \"{story_title}\"\n"
                f"Sample lyrics:\n{lyrics[:400]}\n\n"
                "Write a short pinned YouTube comment (4 lines max) that:\n"
                "1. Reflects emotionally on the song in Tagalog/Taglish\n"
                "2. Quotes the most emotionally hitting lyric line from above (in quotes)\n"
                "3. Asks viewers a direct question to drive replies (e.g., 'Sino ang nasa isip mo habang naririnig ito?')\n"
                "4. Ends with: 'I-share mo 'to sa taong kailangan marinig ito 💔'\n"
                "Use emojis naturally. Keep it real and personal, not corporate."
            ),
        }
    ]
    try:
        raw = _call_openrouter(messages, _MODELS[0])
        return raw.strip()[:600]
    except Exception:
        return "💔 Para sa lahat ng nasaktan... Alam ko kung paano 'yan.\n\nI-share mo 'to sa taong kailangan marinig ito 👇"


def generate_viral_story_segments(story_title: str, story_description: str, duration: float) -> list:
    """
    Rewrite a Reddit story into viral Tagalog/Taglish text cards that fill the
    entire video duration. Returns a list of short strings (one per on-screen card).

    Target: ~1 card per 5 seconds (e.g. 270s → ~54 cards).
    """
    target_cards = max(20, min(60, int(duration / 5)))

    fallback = [
        f"📖 {story_title[:60]}" if story_title else "📖 Isang tunay na kwento...",
        "Maniwala ka man o hindi, nangyari talaga ito...",
        "Handa ka na ba? 👇",
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
                f"Reddit post title: \"{story_title}\"\n"
                f"Full story:\n{context}\n\n"
                "You are writing text cards for a VIRAL Filipino YouTube channel in the style of "
                "'Reddit Story + OPM music' videos that get 1-5 million views each.\n\n"
                "YOUR TASK:\n"
                f"1. Rewrite this story into EXACTLY {target_cards} short text cards.\n"
                "2. LANGUAGE: TAGALOG ONLY. Pure Filipino — NOT English, NOT Taglish. "
                "Use natural Filipino internet slang (e.g. 'grabe', 'shet', 'naman', 'talaga', 'char', 'luh', 'hindi ko alam'). "
                "Keep it conversational, like a friend retelling the story sa grupong chat.\n"
                "3. Each card = 1-2 punchy sentences, MAX 15 words total. Easy to read in 4 seconds.\n"
                "4. Card 1 = SHOCKING HOOK na pampatigil ng scroll. Simulan sa pinaka-emotional/dramatic na detalye.\n"
                "5. Cards 2-5 = Ipaliwanag nang mabilis. Sino, ano, kailan.\n"
                f"6. Cards 6-{target_cards - 4} = Ikwento nang may LUMALAKING TENSION. Mag-cliffhanger tuwing ika-5 card.\n"
                f"7. Cards {target_cards - 3}-{target_cards} = Emotional climax + punchline + hugot reflection.\n"
                "8. Emojis (💔 😭 😤 👀 🙃) — max 1 per card, gamitin nang maingat.\n"
                "9. WALANG hashtag. WALANG 'Part 1/2'. WALANG card numbers. WALANG bullet points.\n\n"
                f"OUTPUT FORMAT: Exactly {target_cards} linya, isa lang bawat card, wala nang iba:\n"
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
    with the real Reddit story before the vocals kick in.
    """
    fallback_intro = [
        "Isang tunay na kwento...",
        story_title[:60] if story_title else "Sabi niya mahal niya ako.",
        "Pero pinili niya pa rin ang iba.",
        "Ganito ang mahalin ang taong hindi mo mapipigilan.",
        "Ang kantang ito ay para sa lahat ng nasaktan.",
    ]
    fallback_mid = [
        "Hindi mo kasalanan ang umasa.",
        "Mahal ka ng taong hindi mo pa nakilala.",
    ]

    api_key = os.getenv("OPENROUTER_API_KEY", "")
    if not api_key:
        return {"intro": fallback_intro, "mid": fallback_mid}

    context = (story_description or "").strip()[:350] or story_title
    messages = [
        {
            "role": "user",
            "content": (
                f"Reddit story: \"{story_title}\"\n"
                f"Context: {context}\n\n"
                "Gumawa ng text cards para sa Filipino viral hugot music video.\n"
                "3 intro cards (max 8 words bawat isa) at 2 mid-video quotes (max 8 words).\n"
                "Tagalog/Taglish. Walang hashtag. Emotional at relatable.\n\n"
                "Card 1: Ang painful na nangyari (short, punchy — the hook)\n"
                "Card 2: Kung paano nasaktan (the emotional gut-punch)\n"
                "Card 3: Dedication ('Ang kantang ito ay para sa...')\n"
                "Mid 1: Pinaka-masakit na linya (most painful insight, max 8 words)\n"
                "Mid 2: Pang-aaliw o closure (comforting close, max 8 words)\n\n"
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
