"""
music_video.py — Build a viral-ready YouTube music video.

Visual pipeline (all in one ffmpeg filter_complex call):
  1. Pexels background clips downloaded & scaled to 1920x1080
  2. xFade crossfade transitions between clips (genre-specific type)
  3. Color grade + vignette + film grain (per visual style)
  4. Bottom gradient overlay (dark box) for lyric readability
  5. Cinematic letterbox bars 2.39:1 (hugot/cinematic styles)
  6. Music waveform visualizer overlay (showwaves, bottom strip)
  7. Animated title card — slide-up + fade, first 5 seconds
  8. ASS karaoke-style subtitles (glow, per-cue fade)
  Output: 1920x1080 @ 30fps, H.264, AAC 192k, YouTube-ready

Public API:
    build_music_video(audio_path, lyrics, title, genre_dict, output_path, pexels_key)
"""

import os
import re
import math
import random
import subprocess
import requests
import imageio_ffmpeg
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


TARGET_W, TARGET_H = 1920, 1080
CLIP_DURATION = 30       # seconds per background clip
XFADE_DUR = 1.0          # crossfade duration between clips


# ── Visual style presets ─────────────────────────────────────────────────────

VISUAL_STYLES = {
    "lofi": {
        "color_filter": "curves=vintage,hue=s=0.7,eq=brightness=-0.03:contrast=1.05:saturation=0.85",
        "vignette": True,
        "grain": True,
        "letterbox": False,
        "visualizer": True,
        "viz_color": "0xFFD700@0.55",
        "transition": "dissolve",
        "subtitle_color": "&H00FFFFFF",
        "subtitle_outline": "&H00FFD700",
        "subtitle_size": 62,
        "sub_margin_v": 220,
    },
    "cinematic": {
        "color_filter": "curves=lighter,eq=contrast=1.12:saturation=0.88,colorbalance=bs=-0.05:gs=-0.02",
        "vignette": True,
        "grain": False,
        "letterbox": True,
        "visualizer": False,
        "viz_color": "0xFFFFFF@0.4",
        "transition": "fade",
        "subtitle_color": "&H00FFFFFF",
        "subtitle_outline": "&H00000000",
        "subtitle_size": 66,
        "sub_margin_v": 240,
    },
    "dark": {
        "color_filter": "eq=brightness=-0.1:contrast=1.15:saturation=0.6",
        "vignette": True,
        "grain": True,
        "letterbox": False,
        "visualizer": True,
        "viz_color": "0xFF2200@0.6",
        "transition": "wipeleft",
        "subtitle_color": "&H00E0E0E0",
        "subtitle_outline": "&H00880000",
        "subtitle_size": 60,
        "sub_margin_v": 220,
    },
    "nature": {
        "color_filter": "eq=brightness=0.02:contrast=1.05:saturation=1.15",
        "vignette": False,
        "grain": False,
        "letterbox": False,
        "visualizer": True,
        "viz_color": "0x44FF88@0.5",
        "transition": "smoothleft",
        "subtitle_color": "&H00FFFFFF",
        "subtitle_outline": "&H0022AA22",
        "subtitle_size": 62,
        "sub_margin_v": 220,
    },
    "city": {
        "color_filter": "eq=contrast=1.12:saturation=1.2,colorbalance=rs=0.05",
        "vignette": True,
        "grain": False,
        "letterbox": False,
        "visualizer": True,
        "viz_color": "0xFF6600@0.65",
        "transition": "slideleft",
        "subtitle_color": "&H00FFFFFF",
        "subtitle_outline": "&H00FF4400",
        "subtitle_size": 64,
        "sub_margin_v": 220,
    },
}


# ── Audio duration ───────────────────────────────────────────────────────────

def get_audio_duration(audio_path: str) -> float:
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    r = subprocess.run([ffmpeg, "-i", audio_path], capture_output=True, text=True)
    m = re.search(r"Duration: (\d+):(\d+):([\d.]+)", r.stderr)
    if m:
        return int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3))
    return 240.0


# ── Pexels background clips ──────────────────────────────────────────────────

def _pexels_best_file(video: dict) -> dict | None:
    files = video.get("video_files", [])
    landscape = [f for f in files if f.get("width", 0) >= f.get("height", 0)]
    hd = sorted(landscape or files, key=lambda x: x.get("width", 0), reverse=True)
    return hd[0] if hd else None


def fetch_background_clips(
    keywords: list[str],
    pexels_key: str,
    output_dir: str,
    needed_duration: float,
) -> list[str]:
    """
    Download Pexels clips as-is (no pre-encode). The main ffmpeg filter_complex
    handles scale/trim/fps inline, avoiding double-encoding.
    Returns list of raw clip file paths.
    """
    os.makedirs(output_dir, exist_ok=True)
    headers = {"Authorization": pexels_key}

    videos = []
    used_ids: set = set()
    for kw in keywords:
        try:
            res = requests.get(
                "https://api.pexels.com/videos/search",
                headers=headers,
                params={"query": kw, "per_page": 15, "orientation": "landscape", "page": random.randint(1, 4)},
                timeout=15,
            )
            if res.status_code == 200:
                new = [v for v in res.json().get("videos", []) if v["id"] not in used_ids]
                videos.extend(new)
                for v in new:
                    used_ids.add(v["id"])
                print(f"[bg] Pexels '{kw}' -> {len(new)} results")
        except Exception as e:
            print(f"[bg] Pexels error for '{kw}': {e}")

    if not videos:
        raise RuntimeError("No Pexels videos found — check PEXELS_API_KEY")

    # With xfade: total = N*CLIP_DUR - (N-1)*XFADE_DUR, solve for N
    clips_needed = max(3, math.ceil((needed_duration - XFADE_DUR) / (CLIP_DURATION - XFADE_DUR)) + 1)

    random.shuffle(videos)
    pool = videos[:min(12, len(videos))]

    chosen = []
    while len(chosen) < clips_needed:
        chosen += pool
    chosen = chosen[:clips_needed]

    clip_paths = []
    for i, vid in enumerate(chosen):
        vf = _pexels_best_file(vid)
        if not vf:
            continue
        dest = os.path.join(output_dir, f"_clip{i}.mp4")
        print(f"[bg] Downloading clip {i+1}/{len(chosen)}...")
        try:
            r = requests.get(vf["link"], stream=True, timeout=120)
            with open(dest, "wb") as f:
                for chunk in r.iter_content(8192):
                    f.write(chunk)
            if os.path.getsize(dest) > 10_000:
                clip_paths.append(dest)
            else:
                print(f"[bg] Clip {i} too small, skipping")
                os.remove(dest)
        except Exception as e:
            print(f"[bg] Download clip {i} failed: {e}")

    if not clip_paths:
        raise RuntimeError("All background clip downloads failed")

    print(f"[bg] {len(clip_paths)} clips ready")
    return clip_paths


# ── Visual keyword extraction from lyrics ────────────────────────────────────

def _extract_visual_keywords(lyrics: str, title: str, fallback: list[str]) -> list[str]:
    """
    Ask OpenRouter for 5 Pexels-friendly English scene keywords that visually
    match the song. Falls back to genre mood_tags if the API call fails.
    """
    api_key = os.getenv("OPENROUTER_API_KEY", "")
    if not api_key:
        return fallback
    prompt = (
        f"Song title: {title}\n"
        f"Lyrics (may be in Tagalog/Filipino):\n{lyrics[:600]}\n\n"
        "List exactly 5 short English Pexels stock-video search terms (2-4 words each) "
        "that would visually match this song's scenes and emotions. "
        "Focus on concrete visual scenes like 'rain on window', 'couple at night', "
        "'empty road', 'candle flame'. "
        "Return ONLY the 5 terms, one per line, no numbers, no explanation."
    )
    try:
        resp = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={
                "model": "google/gemini-2.0-flash-001",
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 80,
            },
            timeout=20,
        )
        if resp.status_code == 200:
            text = resp.json()["choices"][0]["message"]["content"].strip()
            terms = [ln.strip().strip("-•*").strip() for ln in text.splitlines() if ln.strip()][:5]
            if terms:
                print(f"[bg] Visual keywords from lyrics: {terms}")
                return terms
    except Exception as e:
        print(f"[bg] Keyword extraction failed ({e}), using defaults")
    return fallback


# ── ASS subtitles ────────────────────────────────────────────────────────────

def _ass_time(s: float) -> str:
    h = int(s // 3600)
    m = int((s % 3600) // 60)
    sec = int(s % 60)
    cs = int((s % 1) * 100)
    return f"{h}:{m:02}:{sec:02}.{cs:02}"


def _group_words_into_lines(all_words: list, words_per_line: int = 6) -> list:
    """Group word dicts {word, start, end} into caption display lines."""
    captions = []
    chunk = []
    for i, w in enumerate(all_words):
        chunk.append(w)
        gap_to_next = (all_words[i + 1]["start"] - w["end"]) if i + 1 < len(all_words) else 999
        at_limit = len(chunk) >= words_per_line
        at_pause = gap_to_next > 0.5   # natural breath/phrase break
        if at_limit or at_pause:
            text = " ".join(c["word"] for c in chunk).strip()
            if text:
                captions.append({
                    "text": text,
                    "start": chunk[0]["start"],
                    "end": chunk[-1]["end"] + 0.08,
                })
            chunk = []
    if chunk:
        text = " ".join(c["word"] for c in chunk).strip()
        if text:
            captions.append({
                "text": text,
                "start": chunk[0]["start"],
                "end": chunk[-1]["end"] + 0.08,
            })
    return captions


def _whisper_word_captions(audio_path: str, words_per_line: int = 6, lyrics_hint: str = "") -> list | None:
    """
    Transcribe audio for word-level captions.

    Priority:
      1. Groq whisper-large-v3-turbo (free API, best accuracy for music + Tagalog)
      2. Local faster-whisper small model (fallback, uses lyrics_hint as initial_prompt)

    Returns list of {"text": str, "start": float, "end": float} display chunks.
    Returns None if both fail.
    """
    # ── 1. Groq Whisper API (free, most accurate) ──────────────────────────
    groq_key = os.environ.get("GROQ_API_KEY", "")
    if groq_key:
        try:
            import groq as _groq
            print("[whisper] Using Groq whisper-large-v3-turbo...")
            client = _groq.Groq(api_key=groq_key)
            with open(audio_path, "rb") as f:
                result = client.audio.transcriptions.create(
                    file=(os.path.basename(audio_path), f),
                    model="whisper-large-v3-turbo",
                    response_format="verbose_json",
                    timestamp_granularities=["word"],
                    language="tl",
                    prompt=lyrics_hint[:224] if lyrics_hint else None,
                )
            raw_words = getattr(result, "words", None) or []
            if raw_words:
                all_words = []
                for w in raw_words:
                    # Groq may return dicts or objects depending on SDK version
                    if isinstance(w, dict):
                        word_text = w.get("word", "").strip()
                        start = w.get("start", 0.0)
                        end = w.get("end", 0.0)
                    else:
                        word_text = getattr(w, "word", "").strip()
                        start = getattr(w, "start", 0.0)
                        end = getattr(w, "end", 0.0)
                    if word_text:
                        all_words.append({"word": word_text, "start": start, "end": end})
                print(f"[groq] {len(all_words)} words transcribed")
                caps = _group_words_into_lines(all_words, words_per_line)
                print(f"[groq] {len(caps)} caption lines")
                return caps if caps else None
            else:
                print("[groq] No word timestamps returned, falling back to local")
        except Exception as e:
            print(f"[groq] Whisper failed: {e} — falling back to local faster-whisper")

    # ── 2. Local faster-whisper (small model) ─────────────────────────────
    # Key settings to prevent hallucination on singing:
    #   initial_prompt   — first lines of lyrics give Whisper vocabulary/context
    #   condition_on_previous_text=False — prevents repetition loops
    #   no_speech_threshold=0.1  — don't skip quiet/melodic segments
    #   temperature=0.0  — deterministic; combined with above avoids loops
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        print("[whisper] faster-whisper not installed")
        return None

    model_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "models", "whisper-small")
    try:
        print("[whisper] Local faster-whisper (small, tl, anti-hallucination)...")
        os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")
        model = WhisperModel("small", device="cpu", compute_type="int8", download_root=model_dir)

        # Use first ~200 chars of lyrics as context so Whisper knows the vocabulary
        prompt = lyrics_hint[:200] if lyrics_hint else ""

        seg_gen, info = model.transcribe(
            audio_path,
            language="tl",
            vad_filter=False,
            word_timestamps=True,
            beam_size=5,
            temperature=0.0,
            initial_prompt=prompt or None,
            condition_on_previous_text=False,   # prevents repetition spiral
            no_speech_threshold=0.1,            # don't skip singing segments
            log_prob_threshold=-1.0,            # accept lower-confidence words
        )
        print(f"[whisper] Language: {info.language} ({info.language_probability:.0%})")

        all_words = []
        for seg in seg_gen:
            if seg.words:
                for w in seg.words:
                    word = w.word.strip()
                    if word:
                        all_words.append({"word": word, "start": w.start, "end": w.end})

        if not all_words:
            print("[whisper] No words found")
            return None

        # Deduplicate: remove any word whose start is identical to previous (hallucination artifact)
        deduped = [all_words[0]]
        for w in all_words[1:]:
            if abs(w["start"] - deduped[-1]["start"]) > 0.05:
                deduped.append(w)
        if len(deduped) < len(all_words):
            print(f"[whisper] Deduped {len(all_words)} → {len(deduped)} words")
        all_words = deduped

        print(f"[whisper] {len(all_words)} words transcribed")
        caps = _group_words_into_lines(all_words, words_per_line)
        print(f"[whisper] {len(caps)} caption lines")
        return caps if caps else None
    except Exception as e:
        print(f"[whisper] Local transcription failed: {e}")
        return None


def _detect_vocal_onset(audio_path: str) -> float | None:
    """
    Use faster-whisper to detect when vocals actually start in the song.
    Returns the start time of the first detected word, or None on failure.
    Downloads 'base' model (~150MB) to models/whisper-base/ on first run.
    """
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        return None

    model_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "models", "whisper-base")
    try:
        print("[whisper] Detecting vocal onset...")
        os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")
        model = WhisperModel("base", device="cpu", compute_type="int8", download_root=model_dir)
        segments, info = model.transcribe(
            audio_path,
            vad_filter=True,
            word_timestamps=True,
            beam_size=2,
        )
        print(f"[whisper] Language: {info.language} ({info.language_probability:.0%})")
        # Find the first word timestamp
        for seg in segments:
            if seg.words:
                onset = seg.words[0].start
            else:
                onset = seg.start
            print(f"[whisper] Vocal onset: {onset:.2f}s")
            return onset
        print("[whisper] No vocals detected")
        return None
    except Exception as e:
        print(f"[whisper] Vocal onset detection failed: {e}")
        return None


def _build_ass(lyrics: str, duration: float, vstyle: dict, output_path: str, is_opm: bool = False, story_cards: list = None, pull_quotes: list = None, audio_path: str = None, story_segments: list = None, song_title: str = ""):
    """Create an ASS subtitle file. In story mode (story_segments provided), fills the
    entire video with timed story cards + a mid-video 'song inspired by this story' bridge.
    Otherwise falls back to Whisper captions."""
    sub_color = vstyle.get("subtitle_color", "&H00FFFFFF")
    out_color = vstyle.get("subtitle_outline", "&H00000000")
    size = vstyle.get("subtitle_size", 64)
    margin_v = vstyle.get("sub_margin_v", 220)

    raw_lines = []
    for line in lyrics.splitlines():
        line = re.sub(r"\*+", "", line).strip()
        if not line or re.match(r"^\[.*\]$", line):
            continue
        # Skip English-only translation lines (parenthetical)
        if re.match(r"^\*?\s*\(", line) and line.rstrip("*").rstrip().endswith(")"):
            continue
        raw_lines.append(line)

    if not raw_lines:
        raw_lines = ["♪ ♪ ♪"]

    chunks = []
    for i in range(len(raw_lines)):
        chunks.append(raw_lines[i])

    # Fallback intro gap (only used when Whisper is unavailable).
    # Whisper detects the real vocal onset automatically.
    if story_cards:
        default_intro_gap = len(story_cards) * 3.25 + 0.5
    elif is_opm:
        default_intro_gap = 0.0
    else:
        default_intro_gap = 18.0 if duration > 200 else 10.0

    usable_end = duration - 5.0

    # Build a lyrics hint (first ~200 chars of raw lyrics) to guide Whisper
    lyrics_hint = " ".join(chunks[:6]) if chunks else ""

    # ── ASS header ─────────────────────────────────────────────────────────
    header = (
        "[Script Info]\n"
        "ScriptType: v4.00+\n"
        f"PlayResX: {TARGET_W}\n"
        f"PlayResY: {TARGET_H}\n"
        "ScaledBorderAndShadow: yes\n"
        "WrapStyle: 0\n"
        "Collisions: Normal\n\n"
        "[V4+ Styles]\n"
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, "
        "OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, "
        "ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
        "Alignment, MarginL, MarginR, MarginV, Encoding\n"
        # Story cards — white bold, thick black outline + shadow, readable on any bg
        "Style: Story,Arial Black,58,&H00FFFFFF,&H000000FF,&H00000000,&H00000000,-1,0,0,0,100,100,1.5,0,1,6,3,5,120,120,80,1\n"
        # Inspired bridge — cyan italic, thick black outline
        "Style: Bridge,Arial,46,&H0033DDFF,&H000000FF,&H00000000,&H00000000,0,-1,0,0,100,100,2,0,1,5,3,5,120,120,130,1\n"
        # Badge — white bold on 75%-opaque dark box with padding
        "Style: Badge,Arial Black,36,&H00FFFFFF,&H000000FF,&H00000000,&H40000000,-1,0,0,0,100,100,1,0,3,14,0,2,80,80,40,1\n"
        # Legacy lyric style (unused in story mode but kept for fallback)
        f"Style: Lyric,Arial Black,{size},{sub_color},&H000000FF,{out_color},"
        f"&H96000000,-1,0,0,0,100,100,2.5,0,1,5,4,2,80,80,{margin_v},1\n"
        "Style: Quote,Arial,44,&H0000D7FF,&H000000FF,&H00000000,&H00000000,0,-1,0,0,100,100,1.5,0,1,4,5,8,120,120,80,1\n\n"
        "[Events]\n"
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
    )

    events = []

    # ══════════════════════════════════════════════════════════════════════
    # STORY MODE: full-duration story cards — no captions
    # ══════════════════════════════════════════════════════════════════════
    if story_segments:
        n = len(story_segments)
        usable = duration - 2.0          # leave 2s gap at end
        card_dur = max(3.5, usable / n)  # at least 3.5s per card
        fade = min(600, int(card_dur * 180))  # smooth fade proportional to card length

        # 1. Opening badge: "♪ Isang Tunay na Kwento" (bottom, 0–4s)
        events.append(
            f"Dialogue: 0,{_ass_time(0.3)},{_ass_time(4.0)},Badge,,0,0,0,,"
            f"{{\\an2\\fad(800,600)}}♪  I S A N G  T U N A Y  N A  K W E N T O"
        )

        t = 5.5  # start after title card fades out at 5s
        bridge_done = False
        bridge_at = duration * 0.50  # inject song-link bridge at 50% mark

        for i, seg in enumerate(story_segments):
            # Insert "song inspired by" bridge once, ~halfway through
            if not bridge_done and t >= bridge_at:
                bridge_done = True
                b_title = song_title or "Ang Kantang Ito"
                bridge_cards = [
                    "♪  Ang kantang ito ay inspirado ng totoong kwentong ito",
                    f"♪  \"{ b_title }\"  —  para sa lahat ng nasaktan",
                    "♪  Pakinggan mo... ramdam mo ang bawat salita",
                ]
                for bc in bridge_cards:
                    safe_bc = bc.replace("{", "").replace("}", "")
                    events.append(
                        f"Dialogue: 0,{_ass_time(t)},{_ass_time(t + 3.8)},Bridge,,0,0,0,,"
                        f"{{\\an5\\fad(800,800)\\blur1}}{safe_bc}"
                    )
                    t += 4.0

            safe = seg.replace("{", "").replace("}", "")
            events.append(
                f"Dialogue: 0,{_ass_time(t)},{_ass_time(t + card_dur - 0.2)},Story,,0,0,0,,"
                f"{{\\an5\\fad({fade},{fade})\\blur1}}{safe}"
            )
            t += card_dur
            if t >= usable:
                break

        # Closing badge: "Basahin ang buong kwento sa pinned comment" (last 5s)
        events.append(
            f"Dialogue: 0,{_ass_time(duration - 5.0)},{_ass_time(duration - 0.5)},Badge,,0,0,0,,"
            f"{{\\an2\\fad(600,800)}}💬  Basahin ang buong kwento sa pinned comment  👇"
        )

        print(f"[subs] Story mode: {len(events)} cues across {duration:.0f}s")

    # ══════════════════════════════════════════════════════════════════════
    # CAPTION / LYRIC MODE (fallback when no story_segments)
    # ══════════════════════════════════════════════════════════════════════
    else:
        # Story intro cards (old 3-card style, kept for non-OPM genres)
        if story_cards:
            card_dur2, gap2, t2 = 3.0, 0.25, 0.5
            for card in story_cards:
                safe = card.replace("{", "").replace("}", "")
                events.append(
                    f"Dialogue: 0,{_ass_time(t2)},{_ass_time(t2 + card_dur2)},Story,,0,0,0,,"
                    f"{{\\an5\\fad(700,700)}}{safe}"
                )
                t2 += card_dur2 + gap2

        word_captions = _whisper_word_captions(audio_path, lyrics_hint=lyrics_hint) if audio_path else None

        if word_captions:
            usable_start = word_captions[0]["start"]
            print(f"[subs] Word-level captions: {len(word_captions)} lines, "
                  f"first at {usable_start:.2f}s, last at {word_captions[-1]['start']:.2f}s")
            for cap in word_captions:
                text = cap["text"].replace("{", "").replace("}", "")
                events.append(
                    f"Dialogue: 0,{_ass_time(cap['start'])},{_ass_time(cap['end'])},Lyric,,0,0,0,,"
                    f"{{\\fad(300,200)\\blur2}}{text}"
                )
        else:
            if audio_path:
                onset = _detect_vocal_onset(audio_path)
                usable_start = onset if onset is not None else default_intro_gap
            else:
                usable_start = default_intro_gap
            if story_cards:
                usable_start = max(usable_start, len(story_cards) * 3.25 + 0.5)
            print(f"[subs] Proportional fallback from {usable_start:.2f}s")
            total_words = sum(max(1, len(c.split())) for c in chunks)
            total_time = usable_end - usable_start
            t = usable_start
            for chunk in chunks:
                w = max(1, len(chunk.split()))
                dur = total_time * w / total_words
                text = chunk.replace("{", "").replace("}", "")
                events.append(
                    f"Dialogue: 0,{_ass_time(t)},{_ass_time(t + dur - 0.15)},Lyric,,0,0,0,,"
                    f"{{\\fad(400,400)\\blur2}}{text}"
                )
                t += dur

        if pull_quotes:
            q_dur = 5.0
            q_times = [duration * 0.33, duration * 0.66]
            usable_start_q = word_captions[0]["start"] if word_captions else default_intro_gap
            for q_text, q_start in zip(pull_quotes, q_times):
                q_start = max(q_start, usable_start_q + 20)
                safe_q = q_text.replace("{", "").replace("}", "")
                events.append(
                    f"Dialogue: 0,{_ass_time(q_start)},{_ass_time(q_start + q_dur)},Quote,,0,0,0,,"
                    f"{{\\an8\\fad(500,500)}}\u201c {safe_q} \u201d"
                )

    with open(output_path, "w", encoding="utf-8-sig") as f:
        f.write(header)
        f.write("\n".join(events) + "\n")

    print(f"[subs] ASS: {len(events)} cues -> {output_path}")


def extract_chapters_from_ass(ass_path: str, song_title: str = "") -> str:
    """
    Parse ASS subtitle cues and generate YouTube chapter timestamps from lyric section markers.
    Returns a string block suitable for pasting into a video description.
    e.g.:
      00:00 Intro
      00:18 Verse 1
      01:05 Chorus
      ...
    """
    if not os.path.exists(ass_path):
        return ""

    # Collect all dialogue lines with timestamps
    cues = []
    try:
        with open(ass_path, encoding="utf-8-sig") as f:
            for line in f:
                if not line.startswith("Dialogue:"):
                    continue
                parts = line.split(",", 9)
                if len(parts) < 10:
                    continue
                start_str = parts[1].strip()  # H:MM:SS.cs
                text = re.sub(r"\{[^}]+\}", "", parts[9]).strip()
                if not text:
                    continue
                h, m, rest = start_str.split(":")
                s, cs = rest.split(".")
                t = int(h) * 3600 + int(m) * 60 + int(s) + int(cs) / 100
                cues.append((t, text))
    except Exception:
        return ""

    if not cues:
        return ""

    chapters = []
    # Always start with 00:00 Intro
    chapters.append((0.0, "Intro"))

    # Sample every ~30s to get section markers (don't output every subtitle line)
    last_t = 0.0
    section_idx = 1
    section_names = ["Verse 1", "Chorus", "Verse 2", "Chorus", "Bridge", "Final Chorus", "Outro"]
    for t, text in cues:
        if t - last_t >= 28.0 and section_idx < len(section_names):
            chapters.append((t, section_names[section_idx]))
            last_t = t
            section_idx += 1

    # Format as MM:SS strings
    lines = []
    for t, label in chapters:
        mm = int(t // 60)
        ss = int(t % 60)
        lines.append(f"{mm:02d}:{ss:02d} {label}")

    return "\n".join(lines)


# ── filter_complex builder ────────────────────────────────────────────────────

def _escape_ass_path(path: str) -> str:
    """Escape a file path for ffmpeg's ass filter inside filter_complex."""
    p = path.replace("\\", "/")
    if len(p) >= 2 and p[1] == ":":
        p = p[0] + "\\:" + p[2:]
    return p


def _preprocess_clips(clip_paths: list, work_dir: str, ffmpeg: str,
                      vstyle: dict, log_path: str) -> list:
    """
    Pre-process each clip independently — one at a time — into a normalized
    1920×1080 @ 30fps segment with Ken Burns applied and trimmed to CLIP_DURATION.

    This avoids the ~48GB memory spike that occurs when all 18 clips are
    looped and scaled simultaneously inside a single filter_complex.

    Returns a list of preprocessed clip paths (_proc{i}.mp4).
    """
    _KB_W = int(TARGET_W * 1.13)
    _KB_H = int(TARGET_H * 1.13)
    proc_paths = []

    for i, src in enumerate(clip_paths):
        dst = os.path.join(work_dir, f"_proc{i}.mp4")
        # Skip if already done (crash recovery)
        if os.path.exists(dst) and os.path.getsize(dst) > 100_000:
            print(f"[video] Clip {i+1}/{len(clip_paths)} already preprocessed, skipping")
            proc_paths.append(dst)
            continue

        pan = i % 4
        if pan == 0:
            px, py = f"(iw-ow)*t/{CLIP_DURATION}", "(ih-oh)/2"
        elif pan == 1:
            px, py = f"(iw-ow)*(1-t/{CLIP_DURATION})", "(ih-oh)/2"
        elif pan == 2:
            px, py = "(iw-ow)/2", f"(ih-oh)*t/{CLIP_DURATION}"
        else:
            px, py = "(iw-ow)/2", f"(ih-oh)*(1-t/{CLIP_DURATION})"

        vf = (
            f"fps=30,"
            f"loop=loop=-1:size=900:start=0,"
            f"trim=duration={CLIP_DURATION},setpts=PTS-STARTPTS,"
            f"scale={_KB_W}:{_KB_H}:force_original_aspect_ratio=increase,"
            f"crop={TARGET_W}:{TARGET_H}:{px}:{py},"
            f"fps=30"
        )
        # Try NVENC first, fall back to CPU
        for vcodec, label in (
            (["-c:v", "h264_nvenc", "-preset", "p4", "-cq", "23", "-b:v", "0"], "nvenc"),
            (["-c:v", "libx264", "-preset", "ultrafast", "-crf", "23"], "cpu"),
        ):
            cmd = [ffmpeg, "-y", "-i", src, "-vf", vf, "-t", str(CLIP_DURATION)]
            cmd += vcodec
            cmd += ["-an", "-pix_fmt", "yuv420p", dst]
            print(f"[video] Pre-processing clip {i+1}/{len(clip_paths)} ({label})...")
            with open(log_path, "a") as lf:
                r = subprocess.run(cmd, stdout=lf, stderr=lf, timeout=180)
            if r.returncode == 0:
                break

        if r.returncode == 0 and os.path.getsize(dst) > 100_000:
            proc_paths.append(dst)
        else:
            print(f"[video] Pre-process clip {i} failed, using original")
            proc_paths.append(src)

    return proc_paths


def _build_filter_complex(
    n_clips: int,
    vstyle: dict,
    duration: float,
    ass_path: str,
    title: str,
    hook_text: str = "",
    with_title_card: bool = True,
    preprocessed: bool = False,
) -> str:
    """
    Build the complete ffmpeg filter_complex string.

    Input stream layout:
      [0:v] ... [n_clips-1:v]  — background video clips
      [n_clips:a]               — audio

    Output label: [vout]

    When preprocessed=True the clips are already 1920×1080 @ 30fps
    (produced by _preprocess_clips) so the per-clip loop/scale/crop
    steps are skipped — this eliminates the ~48GB RAM spike.
    """
    parts = []
    transition = vstyle.get("transition", "fade")
    audio_idx = n_clips

    if preprocessed:
        # Clips already normalized — just alias each input stream
        for i in range(n_clips):
            parts.append(f"[{i}:v]null[sc{i}]")
    else:
        # 0. Per-clip: normalize fps, loop to cover CLIP_DURATION (fixes freeze on short clips),
        #    trim to exactly CLIP_DURATION, then Ken Burns pan for cinematic motion.
        #    Scale 13% oversized, then use time-varying crop to pan across the frame.
        #    WARNING: with many clips this buffers ~48GB of frame data. Use preprocessed=True.
        _KB_W = int(TARGET_W * 1.13)  # 2170 — oversized width for pan room
        _KB_H = int(TARGET_H * 1.13)  # 1222 — oversized height for pan room
        for i in range(n_clips):
            # Alternate pan direction per clip: right→left→down→up
            pan = i % 4
            if pan == 0:    # pan right
                px = f"(iw-ow)*t/{CLIP_DURATION}"
                py = "(ih-oh)/2"
            elif pan == 1:  # pan left
                px = f"(iw-ow)*(1-t/{CLIP_DURATION})"
                py = "(ih-oh)/2"
            elif pan == 2:  # pan down
                px = "(iw-ow)/2"
                py = f"(ih-oh)*t/{CLIP_DURATION}"
            else:           # pan up
                px = "(iw-ow)/2"
                py = f"(ih-oh)*(1-t/{CLIP_DURATION})"
            parts.append(
                f"[{i}:v]fps=30,"
                f"loop=loop=-1:size=900:start=0,"
                f"trim=duration={CLIP_DURATION},setpts=PTS-STARTPTS,"
                f"scale={_KB_W}:{_KB_H}:force_original_aspect_ratio=increase,"
                f"crop={TARGET_W}:{TARGET_H}:{px}:{py},"
                f"fps=30[sc{i}]"
            )

    # 1. xFade chain
    if n_clips == 1:
        bg_label = "[sc0]"
    else:
        prev = "[sc0]"
        for i in range(1, n_clips):
            out = f"[xf{i}]"
            offset = i * (CLIP_DURATION - XFADE_DUR)
            parts.append(
                f"{prev}[sc{i}]xfade=transition={transition}"
                f":duration={XFADE_DUR}:offset={offset:.1f}{out}"
            )
            prev = out
        bg_label = prev

    # Trim to exact audio duration
    parts.append(
        f"{bg_label}trim=duration={duration:.3f},setpts=PTS-STARTPTS[vbg]"
    )
    cur = "[vbg]"

    # 2. Color grade
    color_f = vstyle.get("color_filter", "")
    if color_f:
        parts.append(f"{cur}{color_f}[vc]")
        cur = "[vc]"

    # 3. Vignette
    if vstyle.get("vignette"):
        parts.append(f"{cur}vignette=PI/4[vv]")
        cur = "[vv]"

    # 4. Film grain
    if vstyle.get("grain"):
        parts.append(f"{cur}noise=alls=8:allf=t+u[vgr]")
        cur = "[vgr]"

    # 5. Bottom gradient (dark box) for text readability
    parts.append(
        f"{cur}drawbox=x=0:y=640:w=1920:h=440:color=black@0.55:t=fill[vdb]"
    )
    cur = "[vdb]"

    # 6. Cinematic letterbox bars
    if vstyle.get("letterbox"):
        BAR = 113  # 2.39:1 from 1080p
        parts.append(
            f"{cur}"
            f"drawbox=x=0:y=0:w=1920:h={BAR}:color=black:t=fill,"
            f"drawbox=x=0:y={TARGET_H - BAR}:w=1920:h={BAR}:color=black:t=fill"
            f"[vlb]"
        )
        cur = "[vlb]"

    # 7. Music waveform visualizer
    if vstyle.get("visualizer", True):
        viz_color = vstyle.get("viz_color", "white@0.5")
        parts.append(
            f"[{audio_idx}:a]showwaves=s=1920x120:mode=cline"
            f":colors={viz_color}:draw=full:scale=sqrt[wave]"
        )
        parts.append(f"{cur}[wave]overlay=0:820:format=auto[vw]")
        cur = "[vw]"

    # 8. Animated title card — use story hook if provided (retention in first 5s)
    if with_title_card:
        import re as _re
        # Strip emojis and non-ASCII — ffmpeg drawtext cannot render them
        card_text = _re.sub(r'[^\x20-\x7E]', '', (hook_text or title)).strip()[:60]
        if not card_text:
            card_text = "OPM Hugot"
        safe_title = (
            card_text
            .replace("\\", "\\\\")
            .replace("'", "\\'")
            .replace(":", "\\:")
            .replace("[", "\\[")
            .replace("]", "\\]")
        )
        title_f = (
            f"drawtext=text='{safe_title}':fontsize=76:fontcolor=white"
            f":x=(w-text_w)/2"
            f":y=(h-text_h)/2+80*max(0\\,1-t/0.8)"
            f":alpha='if(lt(t\\,0.8)\\,t/0.8\\,if(lt(t\\,4.0)\\,1\\,max(0\\,(5.0-t))))'"
            f":box=1:boxcolor=black@0.72:boxborderw=28"
            f":shadowx=3:shadowy=3:shadowcolor=black@0.9"
            f":enable='lt(t\\,5)'"
        )
        parts.append(f"{cur}{title_f}[vtc]")
        cur = "[vtc]"

    # 9. ASS subtitles (last)
    safe_ass = _escape_ass_path(ass_path)
    parts.append(f"{cur}ass='{safe_ass}'[vout]")

    return ";\n".join(parts)


# ── Master build function ────────────────────────────────────────────────────

def build_music_video(
    audio_path: str,
    lyrics: str,
    title: str,
    genre_dict: dict,
    output_path: str,
    pexels_key: str,
    hook_text: str = "",
    story_cards: list = None,
    pull_quotes: list = None,
    story_segments: list = None,
    song_title: str = "",
) -> str:
    """
    Full pipeline: background clips -> effects filter_complex -> final mp4.
    Returns output_path.
    """
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    work_dir = os.path.dirname(output_path)
    os.makedirs(work_dir, exist_ok=True)

    duration = get_audio_duration(audio_path)
    print(f"[video] Audio: {duration:.1f}s ({duration/60:.1f} min)")

    visual_key = genre_dict.get("video_style", "cinematic")
    vstyle = VISUAL_STYLES.get(visual_key, VISUAL_STYLES["cinematic"])

    base_keywords = genre_dict.get("mood_tags", ["nature", "city"])
    keywords = _extract_visual_keywords(lyrics, title, base_keywords)
    clip_paths = fetch_background_clips(keywords, pexels_key, work_dir, duration)

    ass_path = os.path.join(work_dir, "lyrics.ass")
    is_opm = genre_dict.get("lang", "") == "tl"
    _build_ass(lyrics, duration, vstyle, ass_path, is_opm=is_opm,
               story_cards=story_cards, pull_quotes=pull_quotes, audio_path=audio_path,
               story_segments=story_segments, song_title=song_title)

    # In story mode use short song title for drawtext (avoids emoji/long text crashes)
    if story_segments and song_title:
        hook_text = song_title

    log_path = os.path.join(work_dir, "_ffmpeg.log")

    # Pre-process each clip individually (one at a time) to avoid the ~48GB
    # frame-buffer spike that occurs when all clips loop simultaneously inside
    # a single filter_complex.
    print("[video] Pre-processing clips (two-pass encode to keep RAM low)...")
    proc_paths = _preprocess_clips(clip_paths, work_dir, ffmpeg, vstyle, log_path)

    def _try_encoder(with_title: bool, use_nvenc: bool) -> subprocess.CompletedProcess:
        fc = _build_filter_complex(
            n_clips=len(proc_paths),
            vstyle=vstyle,
            duration=duration,
            ass_path=ass_path,
            title=title,
            hook_text=hook_text,
            with_title_card=with_title,
            preprocessed=True,
        )
        if use_nvenc:
            vcodec = ["-c:v", "h264_nvenc", "-preset", "p4", "-cq", "19", "-b:v", "0"]
            enc = "nvenc/GPU"
        else:
            vcodec = ["-c:v", "libx264", "-preset", "ultrafast", "-crf", "19"]
            enc = "libx264/CPU"
        cmd = [ffmpeg, "-y"]
        for cp in proc_paths:
            cmd += ["-i", cp]
        cmd += ["-i", audio_path]
        cmd += ["-filter_complex", fc,
                "-map", "[vout]",
                "-map", f"{len(proc_paths)}:a:0",
                "-t", str(duration)]
        cmd += vcodec
        cmd += ["-c:a", "aac", "-b:a", "192k",
                "-pix_fmt", "yuv420p",
                "-movflags", "+faststart",
                output_path]
        print(
            f"[video] Rendering | {enc} | xfade={vstyle['transition']} | "
            f"title_card={with_title} | log={log_path}"
        )
        # Write to log file — avoids buffering gigabytes of ffmpeg output in VS Code
        with open(log_path, "w") as lf:
            return subprocess.run(cmd, stdout=lf, stderr=lf, timeout=1800)

    # Try GPU first, fall back to CPU
    result = _try_encoder(with_title=True, use_nvenc=True)
    if result.returncode != 0:
        print("[video] NVENC failed, retrying with CPU...")
        result = _try_encoder(with_title=True, use_nvenc=False)
    if result.returncode != 0:
        print("[video] Title card failed, retrying without...")
        result = _try_encoder(with_title=False, use_nvenc=False)
    if result.returncode != 0:
        try:
            lines = open(log_path).readlines()
            err_tail = "".join(lines[-50:])
        except Exception:
            err_tail = "(see " + log_path + ")"
        raise RuntimeError(f"[video] ffmpeg failed:\n{err_tail}")

    for cp in clip_paths:
        if os.path.exists(cp):
            os.remove(cp)
    for cp in proc_paths:
        if os.path.exists(cp):
            os.remove(cp)

    print(f"[video] Done -> {output_path}")
    return output_path
