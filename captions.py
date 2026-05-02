import os
import asyncio
import subprocess
import shutil
import imageio_ffmpeg
import edge_tts


# ── ASS subtitle style ────────────────────────────────────────────────────────
# TikTok / YouTube Shorts style:
#   Large bold white text + thick black outline + shadow, bottom-center
ASS_HEADER = """\
[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Arial Black,95,&H00FFFFFF,&H000000FF,&H00000000,&H00000000,-1,0,0,0,100,100,2,0,1,5,2,2,40,40,220,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""


def _ass_time(seconds: float) -> str:
    """Format seconds as ASS time H:MM:SS.cc (centiseconds)."""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    cs = int((seconds % 1) * 100)
    return f"{h}:{m:02}:{s:02}.{cs:02}"


def _write_ass(captions: list, ass_path: str):
    """Write an ASS subtitle file from captions list."""
    with open(ass_path, "w", encoding="utf-8") as f:
        f.write(ASS_HEADER)
        for cap in captions:
            text = cap["text"].replace("{", "").replace("}", "")
            start = _ass_time(cap["start"])
            end = _ass_time(cap["end"])
            f.write(f"Dialogue: 0,{start},{end},Default,,0,0,0,,{text}\n")


def format_time(seconds: float) -> str:
    """Format seconds as SRT time HH:MM:SS,mmm."""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = int((seconds % 1) * 1000)
    return f"{hours:02}:{minutes:02}:{secs:02},{millis:03}"


def _parse_submaker_srt(srt_content: str, group_size: int = 3) -> list:
    """
    Parse SubMaker's word-per-entry SRT into grouped captions.
    SubMaker emits one word per SRT block; we re-group into group_size chunks.
    Handles both ',' and '.' as decimal separator in timecodes.
    """
    def _t(s: str) -> float:
        s = s.strip().replace(",", ".")
        parts = s.split(":")
        return int(parts[0]) * 3600 + int(parts[1]) * 60 + float(parts[2])

    words = []
    for block in srt_content.strip().split("\n\n"):
        lines = [l.strip() for l in block.strip().splitlines() if l.strip()]
        if len(lines) < 3:
            continue
        try:
            start_s, end_s = lines[1].split(" --> ")
            words.append({
                "start": _t(start_s),
                "end": _t(end_s),
                "word": " ".join(lines[2:]),
            })
        except Exception:
            continue

    captions = []
    for i in range(0, len(words), group_size):
        group = words[i:i + group_size]
        captions.append({
            "start": group[0]["start"],
            "end": group[-1]["end"],
            "text": " ".join(w["word"] for w in group).upper(),
        })
    return captions


def _estimate_captions(script: str, audio_path: str, group_size: int = 3) -> list:
    """Fallback: estimate caption timing from total audio duration + word count."""
    total_dur = None
    try:
        ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
        r = subprocess.run(
            [ffmpeg_exe, "-i", audio_path],
            capture_output=True, text=True, timeout=10
        )
        for line in (r.stdout + r.stderr).splitlines():
            if "Duration:" in line:
                t = line.split("Duration:")[1].split(",")[0].strip()
                h, m, s = t.split(":")
                total_dur = int(h) * 3600 + int(m) * 60 + float(s)
                break
    except Exception:
        pass
    if not total_dur:
        total_dur = len(script.split()) / 2.5
    script_words = script.split()
    per_word = total_dur / max(len(script_words), 1)
    captions = []
    for i in range(0, len(script_words), group_size):
        group = script_words[i:i + group_size]
        start = i * per_word
        end = min((i + len(group)) * per_word, total_dur)
        captions.append({"start": start, "end": end, "text": " ".join(group).upper()})
    print(f"[captions] Estimated {len(captions)} groups from {len(script_words)} words")
    return captions


async def generate_captions_with_timing(script: str, audio_path: str, srt_path: str,
                                        voice: str = "en-US-ChristopherNeural"):
    """Generate TTS audio + word-timed captions. Returns (captions, audio_path)."""
    communicate = edge_tts.Communicate(script, voice=voice)
    submaker = edge_tts.SubMaker()
    raw_words = []   # backup: raw WordBoundary list
    audio_data = bytearray()

    async for chunk in communicate.stream():
        if chunk["type"] == "audio":
            audio_data.extend(chunk["data"])
        elif chunk["type"] == "WordBoundary":
            raw_words.append({
                "word": chunk["text"],
                "start": chunk["offset"] / 10_000_000,
                "end": (chunk["offset"] + chunk["duration"]) / 10_000_000,
            })
            try:
                submaker.feed(chunk)
            except Exception:
                pass

    # Save audio
    os.makedirs(os.path.dirname(audio_path) if os.path.dirname(audio_path) else ".", exist_ok=True)
    with open(audio_path, "wb") as f:
        f.write(bytes(audio_data))

    captions = []
    group_size = 3  # 3 words per caption line = tight TikTok sync

    # ── Strategy 1: SubMaker SRT (official edge-tts subtitle API) ────────────
    try:
        try:
            srt_raw = submaker.get_srt(words_in_cue=group_size)
        except TypeError:
            srt_raw = submaker.get_srt()
        if srt_raw and srt_raw.strip():
            captions = _parse_submaker_srt(srt_raw, group_size)
            if captions:
                print(f"[captions] SubMaker sync: {len(captions)} groups ✓")
    except Exception as e:
        print(f"[captions] SubMaker error: {e}")

    # ── Strategy 2: raw WordBoundary data collected above ────────────────────
    if not captions and raw_words:
        for i in range(0, len(raw_words), group_size):
            group = raw_words[i:i + group_size]
            captions.append({
                "start": group[0]["start"],
                "end": group[-1]["end"],
                "text": " ".join(w["word"] for w in group).upper(),
            })
        print(f"[captions] WordBoundary sync: {len(captions)} groups ✓")

    # ── Strategy 3: estimate from audio duration ──────────────────────────────
    if not captions:
        print("[captions] No word timing from edge-tts — estimating from audio length")
        captions = _estimate_captions(script, audio_path, group_size)

    # Write SRT (for archiving / reference)
    with open(srt_path, "w", encoding="utf-8") as f:
        for idx, cap in enumerate(captions, 1):
            f.write(f"{idx}\n")
            f.write(f"{format_time(cap['start'])} --> {format_time(cap['end'])}\n")
            f.write(f"{cap['text']}\n\n")

    # Write ASS (used for burning — full style control)
    ass_path = srt_path.replace(".srt", ".ass")
    _write_ass(captions, ass_path)

    print(f"Captions: {len(captions)} groups | SRT: {srt_path} | ASS: {ass_path}")
    return captions, audio_path


def burn_captions_to_video(video_path: str, captions: list,
                            output_path: str, srt_path: str = "",
                            font_size: int = 70,
                            color: str = "white", stroke_color: str = "black",
                            stroke_width: int = 3) -> str:
    """Burn captions into video. Tries ASS filter → drawtext → copy fallback."""
    print("Burning captions into video...")
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()

    # ── Method 1: ASS file (best quality, full style control) ────────────────
    ass_path = srt_path.replace(".srt", ".ass") if srt_path else ""

    # Regenerate ASS if missing
    if captions and ass_path and not os.path.exists(ass_path):
        _write_ass(captions, ass_path)

    if ass_path and os.path.exists(ass_path) and os.path.getsize(ass_path) > 0:
        # Windows ffmpeg path escaping: C:\path\file.ass → C\:/path/file.ass
        abs_ass = os.path.abspath(ass_path)
        escaped = abs_ass.replace("\\", "/").replace(":", "\\:", 1)
        cmd = [
            ffmpeg, "-y",
            "-i", video_path,
            "-vf", f"ass='{escaped}'",
            "-c:v", "libx264", "-preset", "fast", "-crf", "23",
            "-c:a", "copy",
            output_path,
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        if result.returncode == 0:
            print(f"Captioned video (ASS style): {output_path}")
            return output_path
        print(f"ASS filter failed: {result.stderr[-400:]}")

    # ── Method 2: drawtext via filter script file ─────────────────────────────
    if captions:
        # Arial Bold is at this path on Windows — ffmpeg escaping needs double backslash
        font_path = "C\\\\:/Windows/Fonts/arialbd.ttf"
        filters = []
        for cap in captions:
            text = (
                cap["text"]
                .replace("\\", "")
                .replace("'", "\u2019")
                .replace(":", " ")
                .replace(",", " ")
                .replace("%", "%%")
                .replace("\n", " ")
            )
            filters.append(
                f"drawtext=text='{text}'"
                f":fontfile='{font_path}'"
                f":fontsize=85"
                f":fontcolor=white"
                f":x=(w-text_w)/2"
                f":y=h*0.74"
                f":borderw=5"
                f":bordercolor=black"
                f":enable='between(t,{cap['start']:.3f},{cap['end']:.3f})'"
            )

        filter_file = output_path + ".vf"
        with open(filter_file, "w", encoding="utf-8") as f:
            f.write(",".join(filters))
        try:
            cmd = [
                ffmpeg, "-y",
                "-i", video_path,
                "-filter_script:v", filter_file,
                "-c:v", "libx264", "-preset", "fast", "-crf", "23",
                "-c:a", "copy",
                output_path,
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
            if result.returncode == 0:
                print(f"Captioned video (drawtext): {output_path}")
                return output_path
            print(f"Drawtext failed: {result.stderr[-200:]}")
        finally:
            if os.path.exists(filter_file):
                os.remove(filter_file)

    # ── Final fallback: copy without captions ─────────────────────────────────
    shutil.copy(video_path, output_path)
    print("Warning: captions could not be burned — video copied without subtitles")
    return output_path
