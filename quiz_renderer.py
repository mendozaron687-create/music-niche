"""
Quiz-style video renderer for math_quiz niche.

12-second portrait short:
  0 → q_dur    : question card (narrator reads question)
  q_dur → +3s  : countdown cards  3 / 2 / 1  (1 s each)
  +3s → end    : answer card (correct option highlighted green)

Pexels video plays as the background. No subtitles — narrator voice only.
"""

import os
import asyncio
import subprocess
import random
import textwrap

import numpy as np
from PIL import Image, ImageDraw, ImageFont
import requests

# ── Canvas size ──────────────────────────────────────────────────────────────
W, H = 1080, 1920

# ── Layout (px) ──────────────────────────────────────────────────────────────
BANNER_Y1, BANNER_Y2 = 50,  178
LABEL_Y1,  LABEL_Y2  = 196, 244
QUESTION_Y           = 290
IMAGE_Y1,  IMAGE_Y2  = 510,  885
OPT_START_Y          = 935
OPT_H                = 112
OPT_GAP              = 18
TIMER_CY             = 1700

# ── Colors (RGBA) ─────────────────────────────────────────────────────────────
NAVY      = (15,  30,  80,  240)
WHITE     = (255, 255, 255, 255)
LABEL_BG  = (30,  50, 120,  230)
GOLD      = (230, 160,  30,  255)
OPT_WHITE = (255, 255, 255, 245)
OPT_OK    = (72,  199, 100,  255)
OPT_CIRC  = (100, 175, 240,  255)
BRAND_BG  = (30,   60, 130,  220)
BRAND_FG  = (180, 220, 255,  255)
TIMER_COL = (255, 220,   0,  255)
DARK      = (15,   15,  15,  255)
QTEXT_BG  = (8,   15,   55,  175)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _font(name: str, size: int) -> ImageFont.FreeTypeFont:
    for path in [
        f"C:/Windows/Fonts/{name}",
        f"/usr/share/fonts/truetype/msttcorefonts/{name}",
        f"/System/Library/Fonts/{name}",
    ]:
        try:
            return ImageFont.truetype(path, size)
        except Exception:
            pass
    return ImageFont.load_default()


def _cc(draw, text, cx, cy, font, fill, shadow=True):
    """Draw text centered at (cx, cy) with optional drop shadow."""
    if shadow:
        draw.text((cx + 4, cy + 4), text, font=font, fill=(0, 0, 0, 200), anchor="mm")
    draw.text((cx, cy), text, font=font, fill=fill, anchor="mm")


def _swirly_fallback() -> Image.Image:
    """Swirly blue background used when Pexels video download fails."""
    x = np.linspace(-3.0, 3.0, W, dtype=np.float32)
    y = np.linspace(-5.0, 5.0, H, dtype=np.float32)
    X, Y  = np.meshgrid(x, y)
    R     = np.sqrt(X**2 + Y**2)
    theta = np.arctan2(Y, X)
    wave  = (np.sin(R * 2.8 + theta * 1.8) + 1.0) * 0.5
    r_ch  = (wave * 35  + 100).clip(80,  180).astype(np.uint8)
    g_ch  = (wave * 50  + 175).clip(140, 225).astype(np.uint8)
    b_ch  = (wave * 25  + 205).clip(185, 255).astype(np.uint8)
    a_ch  = np.full((H, W), 255, dtype=np.uint8)
    return Image.fromarray(np.stack([r_ch, g_ch, b_ch, a_ch], axis=2), "RGBA")


def get_center_image(query: str, pexels_key: str) -> "Image.Image | None":
    """Download a Pexels photo for the center frame."""
    try:
        from io import BytesIO
        r = requests.get(
            "https://api.pexels.com/v1/search",
            headers={"Authorization": pexels_key},
            params={"query": query, "per_page": 5, "orientation": "landscape"},
            timeout=15,
        )
        photos = r.json().get("photos", [])
        if not photos:
            return None
        url  = random.choice(photos[:3])["src"]["large"]
        data = requests.get(url, timeout=20).content
        img  = Image.open(BytesIO(data)).convert("RGBA")
        target_w = IMAGE_Y2 - IMAGE_Y1 - 20
        target_h = IMAGE_Y2 - IMAGE_Y1 - 20
        return img.resize((W - 120, target_h), Image.LANCZOS)
    except Exception:
        return None


def _download_pexels_bg_video(query: str, pexels_key: str, out_path: str,
                               used_video_ids: set | None = None) -> "tuple[bool, int | None]":
    """Download a Pexels video clip (portrait preferred) for the background.
    Skips video IDs already in used_video_ids. Returns (success, video_id)."""
    used = used_video_ids or set()
    try:
        for orientation in ("portrait", None):
            params = {"query": query, "per_page": 15, "size": "medium"}
            if orientation:
                params["orientation"] = orientation
            r = requests.get(
                "https://api.pexels.com/videos/search",
                headers={"Authorization": pexels_key},
                params=params,
                timeout=15,
            )
            vids = r.json().get("videos", [])
            if vids:
                break
        if not vids:
            return False, None
        # Prefer unused; fall back to any if all have been seen
        fresh = [v for v in vids if v["id"] not in used]
        pool  = fresh if fresh else vids
        vid   = random.choice(pool[:8])
        files = sorted(vid.get("video_files", []),
                       key=lambda f: f.get("width", 0) * f.get("height", 0), reverse=True)
        portrait = [f for f in files if f.get("height", 0) >= f.get("width", 0)]
        chosen   = (portrait or files)[0]
        resp = requests.get(chosen["link"], timeout=90, stream=True)
        with open(out_path, "wb") as f:
            for chunk in resp.iter_content(65536):
                f.write(chunk)
        print(f"[quiz] BG video downloaded: {os.path.basename(out_path)} (id={vid['id']})")
        return True, vid["id"]
    except Exception as e:
        print(f"[quiz] Pexels video download failed: {e}")
        return False, None


# ── Card renderer ─────────────────────────────────────────────────────────────

def draw_quiz_card(
    question:    str,
    options:     dict,
    correct:     "str | None" = None,
    category:    str          = "MATH QUIZ",
    center_img:  "Image.Image | None" = None,
    timer_num:   "int | None" = None,
    solid_bg:    bool         = False,   # True = swirly (fallback), False = semi-transparent for video
) -> Image.Image:
    """Returns an RGBA card image."""
    if solid_bg:
        canvas = _swirly_fallback()
    else:
        # Semi-transparent dark overlay — Pexels video shows through
        canvas = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        dark   = Image.new("RGBA", (W, H), (5, 5, 20, 155))
        canvas = Image.alpha_composite(canvas, dark)

    M  = 45
    d  = ImageDraw.Draw(canvas)

    f_ban = _font("impact.ttf",   92)
    f_cat = _font("arialbd.ttf",  38)
    f_ltr = _font("arialbd.ttf",  52)
    f_opt = _font("arialbd.ttf",  46)
    f_tmr = _font("impact.ttf",  220)

    # ── QUIZ TIME banner
    d.rounded_rectangle([M, BANNER_Y1, W - M, BANNER_Y2], radius=20, fill=NAVY)
    _cc(d, "QUIZ TIME", W // 2, (BANNER_Y1 + BANNER_Y2) // 2, f_ban, WHITE)

    # ── Category label
    cw  = int(d.textlength(category, font=f_cat)) + 44
    cx1 = (W - cw) // 2
    d.rounded_rectangle([cx1, LABEL_Y1, cx1 + cw, LABEL_Y2], radius=10, fill=LABEL_BG)
    _cc(d, category, W // 2, (LABEL_Y1 + LABEL_Y2) // 2, f_cat, WHITE, shadow=False)

    # ── Question text (adaptive font — shrink until it fits in ≤4 lines)
    for q_size, q_wrap in [(62, 28), (52, 32), (44, 38)]:
        f_q   = _font("arialbd.ttf", q_size)
        lines = textwrap.wrap(question, width=q_wrap)
        if len(lines) <= 4:
            break
    lines   = lines[:5]
    line_h  = q_size + 14
    q_block = len(lines) * line_h + 28
    d.rounded_rectangle(
        [M - 10, QUESTION_Y - 18, W - M + 10, QUESTION_Y + q_block],
        radius=16, fill=QTEXT_BG,
    )
    qy = QUESTION_Y + 20
    for line in lines:
        _cc(d, line, W // 2, qy, f_q, WHITE, shadow=True)
        qy += line_h

    # ── Center image — shift down if question panel is taller than default
    _img_y1 = max(IMAGE_Y1, QUESTION_Y + q_block + 20)
    _img_y2 = min(IMAGE_Y2, OPT_START_Y - 45)
    ix1, iy1 = M + 10, _img_y1
    ix2, iy2 = W - M - 10, _img_y2
    d.rounded_rectangle([ix1 - 5, iy1 - 5, ix2 + 5, iy2 + 5], radius=18, fill=GOLD)
    if center_img:
        ci = center_img.convert("RGBA").resize((ix2 - ix1, iy2 - iy1), Image.LANCZOS)
        canvas.paste(ci, (ix1, iy1), ci)
    else:
        d.rounded_rectangle([ix1, iy1, ix2, iy2], radius=14, fill=(20, 20, 40, 220))

    # ── Answer options A / B / C / D
    Rc     = 38
    for i, letter in enumerate("ABCD"):
        txt   = options.get(letter, "")
        y1    = OPT_START_Y + i * (OPT_H + OPT_GAP)
        y2    = y1 + OPT_H
        is_ok = bool(correct and letter == correct)
        d.rounded_rectangle([M, y1, W - M, y2],
                             radius=OPT_H // 2,
                             fill=OPT_OK if is_ok else OPT_WHITE)
        ccx, ccy = M + Rc + 14, (y1 + y2) // 2
        d.ellipse([ccx - Rc, ccy - Rc, ccx + Rc, ccy + Rc],
                  fill=(50, 160, 80, 255) if is_ok else OPT_CIRC)
        _cc(d, letter, ccx, ccy, f_ltr, WHITE, shadow=False)
        d.text((M + 2 * Rc + 34, (y1 + y2) // 2), txt,
               font=f_opt, fill=DARK, anchor="lm")
        if is_ok:
            # Draw a clean checkmark using lines (avoids glyph rendering issues)
            cx0  = W - M - 58
            cy0  = ccy
            s    = 18   # half-size
            pts  = [(cx0 - s, cy0), (cx0 - s // 4, cy0 + s), (cx0 + s, cy0 - s)]
            d.line(pts, fill=(255, 255, 255, 255), width=7)

    # ── Timer countdown digit with glow rings
    if timer_num is not None:
        glow_map = {3: (255, 220, 0), 2: (255, 130, 0), 1: (255, 40, 40)}
        gc = glow_map.get(timer_num, (255, 220, 0))
        for r_size, alpha in [(220, 28), (115, 55)]:
            layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
            ld    = ImageDraw.Draw(layer)
            ld.ellipse([W // 2 - r_size, TIMER_CY - r_size,
                        W // 2 + r_size, TIMER_CY + r_size],
                       fill=(*gc, alpha))
            canvas = Image.alpha_composite(canvas, layer)
        d = ImageDraw.Draw(canvas)
        t = str(timer_num)
        d.text((W // 2 + 6, TIMER_CY + 6), t, font=f_tmr, fill=(0, 0, 0, 200), anchor="mm")
        d.text((W // 2,     TIMER_CY    ), t, font=f_tmr, fill=TIMER_COL,       anchor="mm")

    return canvas


# ── Audio helpers ─────────────────────────────────────────────────────────────

_MODELS_DIR   = os.path.join(os.path.dirname(__file__), "models")
_MODEL_PATH   = os.path.join(_MODELS_DIR, "kokoro-v1.0.int8.onnx")
_VOICES_PATH  = os.path.join(_MODELS_DIR, "voices-v1.0.bin")
_MODEL_URL    = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/kokoro-v1.0.int8.onnx"
_VOICES_URL   = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/voices-v1.0.bin"
_kokoro_inst  = None   # lazy singleton


def _get_kokoro():
    global _kokoro_inst
    if _kokoro_inst is not None:
        return _kokoro_inst
    import urllib.request
    os.makedirs(_MODELS_DIR, exist_ok=True)
    if not os.path.exists(_MODEL_PATH):
        print("[tts] Downloading Kokoro model (~88MB, one-time)...")
        urllib.request.urlretrieve(_MODEL_URL, _MODEL_PATH)
    if not os.path.exists(_VOICES_PATH):
        print("[tts] Downloading Kokoro voices (~26MB, one-time)...")
        urllib.request.urlretrieve(_VOICES_URL, _VOICES_PATH)
    from kokoro_onnx import Kokoro
    _kokoro_inst = Kokoro(_MODEL_PATH, _VOICES_PATH)
    return _kokoro_inst


async def _tts(text: str, out_path: str, voice: str = "am_adam", speed: float = 1.05):
    """Generate speech with Kokoro TTS; falls back to edge-tts on any error."""
    try:
        import soundfile as sf
        k = _get_kokoro()
        samples, sr = k.create(text, voice=voice, speed=speed)
        # Write to WAV; ffmpeg will handle conversion / resampling later
        sf.write(out_path, samples, sr)
        print(f"[tts] Kokoro ({voice}): {len(samples)/sr:.1f}s")
    except Exception as e:
        print(f"[tts] Kokoro failed ({e}), falling back to edge-tts")
        import edge_tts
        # edge-tts voice mapping: prefer en-US-GuyNeural for male
        et_voice = "en-US-GuyNeural"
        await edge_tts.Communicate(text, et_voice).save(out_path)

def _audio_duration(ffmpeg: str, path: str) -> float:
    out = subprocess.run([ffmpeg, "-i", path], capture_output=True, text=True)
    for line in out.stderr.splitlines():
        if "Duration:" in line:
            t      = line.split("Duration:")[1].split(",")[0].strip()
            h, m, s = t.split(":")
            return float(h) * 3600 + float(m) * 60 + float(s)
    return 14.0


def _build_narration(question: str, options: dict, correct: str) -> str:
    answer_text = options.get(correct, "")
    return (
        f"{question}  "
        f"Three. Two. One.  "
        f"The answer is {correct}... {answer_text}!  "
        f"Follow for more math challenges!"
    )


async def _build_synced_narration(
    question: str, options: dict, correct: str,
    output_dir: str, voice: str,
) -> "tuple[float, float]":
    """Generate TTS in 3 frame-synced parts and concat into narration.wav.
    - Part 1: question          → q_dur (exact spoken duration)
    - Part 2: Three/Two/One     → 3.0 s (each word padded to 1.0 s)
    - Part 3: answer + CTA      → a_dur (exact spoken duration)
    Returns (q_dur, a_dur)."""
    import soundfile as sf
    from imageio_ffmpeg import get_ffmpeg_exe

    answer_text = options.get(correct, "")
    a_text = f"The answer is {correct}. {answer_text}! Follow for more math challenges!"

    q_path = os.path.join(output_dir, "_p_q.wav")
    a_path = os.path.join(output_dir, "_p_a.wav")
    await _tts(question, q_path, voice=voice)
    await _tts(a_text,   a_path, voice=voice)

    # Countdown: each word padded to exactly 1.0 s
    sr      = sf.info(q_path).samplerate
    one_sec = sr
    cd_chunks = []
    for word in ["Three.", "Two.", "One."]:
        tmp = os.path.join(output_dir, f"_p_{word[0].lower()}.wav")
        await _tts(word, tmp, voice=voice, speed=0.85)
        try:
            data, _ = sf.read(tmp, dtype="float32")
            if data.ndim > 1:
                data = data[:, 0]
            if len(data) < one_sec:
                data = np.pad(data.astype(np.float32), (0, one_sec - len(data)))
            else:
                data = data[:one_sec]
        except Exception:
            data = np.zeros(one_sec, dtype=np.float32)
        cd_chunks.append(data)

    cd_all  = np.concatenate(cd_chunks)
    cd_path = os.path.join(output_dir, "_p_cd.wav")
    sf.write(cd_path, cd_all, sr)

    q_dur = max(sf.info(q_path).duration, 2.5)
    a_dur = max(sf.info(a_path).duration, 2.0)

    # Concat q + cd + a into narration.wav
    narr_path  = os.path.join(output_dir, "narration.wav")
    concat_txt = os.path.join(output_dir, "_narr_concat.txt")
    with open(concat_txt, "w") as f:
        for p in [q_path, cd_path, a_path]:
            f.write(f"file '{os.path.abspath(p).replace(chr(92), chr(47))}'\n")
    _run_ffmpeg([
        get_ffmpeg_exe(), "-y",
        "-f", "concat", "-safe", "0", "-i", concat_txt,
        "-ar", str(sr), "-ac", "1",
        narr_path,
    ], "narr concat")
    return q_dur, a_dur


def _make_tick_track(output_path: str, q_dur: float, a_dur: float) -> str:
    """Generate a WAV with 3 tick beeps aligned to countdown seconds."""
    import wave
    sample_rate = 44100
    total_samp  = int((q_dur + 3.0 + a_dur + 1.0) * sample_rate)
    data        = np.zeros(total_samp, dtype=np.float32)
    for i, freq in enumerate([700, 700, 1100]):
        tick_start = int((q_dur + i) * sample_rate)
        tick_len   = int(0.12 * sample_rate)
        t          = np.arange(tick_len, dtype=np.float32) / sample_rate
        tick       = np.sin(2 * np.pi * freq * t) * np.exp(-t * 40) * 0.9
        end        = min(tick_start + tick_len, total_samp)
        data[tick_start:end] += tick[:end - tick_start]
    data = np.clip(data, -1, 1)
    with wave.open(output_path, "w") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes((data * 32767).astype(np.int16).tobytes())
    return output_path


# ── ffmpeg assembly ────────────────────────────────────────────────────────────

def _run_ffmpeg(cmd: list, label: str):
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        raise RuntimeError(f"[quiz] {label} failed:\n{res.stderr[-1200:]}")


def _assemble_pexels_bg(ffmpeg, bg_video, fpaths, audio, music,
                        q_dur, a_dur, total, final, output_dir, tick=None):
    """Overlay RGBA card PNGs frame-by-frame on the Pexels background video."""
    segments = [
        (fpaths["q"],  q_dur),
        (fpaths["t3"], 1.0),
        (fpaths["t2"], 1.0),
        (fpaths["t1"], 1.0),
        (fpaths["a"],  a_dur),
    ]
    seg_files = []
    for i, (card_png, dur) in enumerate(segments):
        seg = os.path.join(output_dir, f"_seg{i}.mp4")
        _run_ffmpeg([
            ffmpeg, "-y",
            "-stream_loop", "-1", "-i", bg_video,
            "-loop", "1", "-i", card_png,
            "-filter_complex",
            f"[0:v]scale={W}:{H}:force_original_aspect_ratio=increase,"
            f"crop={W}:{H},fps=30[bg];"
            f"[bg][1:v]overlay=0:0[out]",
            "-map", "[out]",
            "-t", str(dur),
            "-c:v", "libx264", "-preset", "ultrafast", "-crf", "24",
            "-pix_fmt", "yuv420p", "-r", "30", "-an", seg,
        ], f"segment {i}")
        seg_files.append(seg)

    # Concatenate video segments
    concat_txt = os.path.join(output_dir, "_concat.txt")
    with open(concat_txt, "w") as f:
        for s in seg_files:
            f.write(f"file '{os.path.abspath(s).replace(chr(92), chr(47))}'\n")
    no_audio = os.path.join(output_dir, "_no_audio.mp4")
    _run_ffmpeg([
        ffmpeg, "-y", "-f", "concat", "-safe", "0", "-i", concat_txt,
        "-c:v", "copy", no_audio,
    ], "concat")

    # Add narration + tick + optional music
    if tick and music:
        af = (f"[2:a]volume=0.22,atrim=duration={total:.2f}[m];"
              f"[1:a][3:a]amix=inputs=2:duration=first[narr_tick];"
              f"[narr_tick][m]amix=inputs=2:duration=first:dropout_transition=2[aout]")
        _run_ffmpeg([
            ffmpeg, "-y", "-i", no_audio, "-i", audio, "-i", music, "-i", tick,
            "-filter_complex", af,
            "-map", "0:v", "-map", "[aout]",
            "-c:v", "copy", "-c:a", "aac", "-b:a", "128k", "-t", str(total), final,
        ], "audio merge")
    elif tick:
        af = "[1:a][2:a]amix=inputs=2:duration=first[aout]"
        _run_ffmpeg([
            ffmpeg, "-y", "-i", no_audio, "-i", audio, "-i", tick,
            "-filter_complex", af,
            "-map", "0:v", "-map", "[aout]",
            "-c:v", "copy", "-c:a", "aac", "-b:a", "128k", "-t", str(total), final,
        ], "audio merge")
    elif music:
        af = (f"[2:a]volume=0.22,atrim=duration={total:.2f}[m];"
              f"[1:a][m]amix=inputs=2:duration=first:dropout_transition=2[aout]")
        _run_ffmpeg([
            ffmpeg, "-y", "-i", no_audio, "-i", audio, "-i", music,
            "-filter_complex", af,
            "-map", "0:v", "-map", "[aout]",
            "-c:v", "copy", "-c:a", "aac", "-b:a", "128k", "-t", str(total), final,
        ], "audio merge")
    else:
        _run_ffmpeg([
            ffmpeg, "-y", "-i", no_audio, "-i", audio,
            "-map", "0:v", "-map", "1:a",
            "-c:v", "copy", "-c:a", "aac", "-b:a", "128k", "-t", str(total), final,
        ], "audio merge")


def _assemble_static(ffmpeg, fpaths, audio, tick, music, q_dur, a_dur, total, final):
    """Fallback: static swirly card images, no video background."""
    img_inputs = [
        "-loop", "1", "-t", str(q_dur),  "-i", fpaths["q"],
        "-loop", "1", "-t", "1.00",      "-i", fpaths["t3"],
        "-loop", "1", "-t", "1.00",      "-i", fpaths["t2"],
        "-loop", "1", "-t", "1.00",      "-i", fpaths["t1"],
        "-loop", "1", "-t", str(a_dur),  "-i", fpaths["a"],
    ]
    vf  = "[0:v][1:v][2:v][3:v][4:v]concat=n=5:v=1:a=0[cv]"
    enc = ["-c:v", "libx264", "-preset", "fast", "-crf", "23",
           "-c:a", "aac", "-b:a", "128k",
           "-r", "30", "-pix_fmt", "yuv420p", "-s", f"{W}x{H}"]
    if tick and music:
        af  = (f"{vf};"
               f"[6:a]volume=0.22,atrim=duration={total:.2f}[m];"
               f"[5:a][7:a]amix=inputs=2:duration=first[narr_tick];"
               f"[narr_tick][m]amix=inputs=2:duration=first:dropout_transition=2[a]")
        cmd = ([ffmpeg, "-y"] + img_inputs
               + ["-i", audio, "-i", music, "-i", tick]
               + ["-filter_complex", af, "-map", "[cv]", "-map", "[a]",
                  "-t", str(total)] + enc + [final])
    elif tick:
        af  = f"{vf};[5:a][6:a]amix=inputs=2:duration=first[a]"
        cmd = ([ffmpeg, "-y"] + img_inputs
               + ["-i", audio, "-i", tick]
               + ["-filter_complex", af, "-map", "[cv]", "-map", "[a]",
                  "-t", str(total)] + enc + [final])
    elif music:
        af  = (f"{vf};"
               f"[6:a]volume=0.22,atrim=duration={total:.2f}[m];"
               f"[5:a][m]amix=inputs=2:duration=first:dropout_transition=2[a]")
        cmd = ([ffmpeg, "-y"] + img_inputs
               + ["-i", audio, "-i", music]
               + ["-filter_complex", af, "-map", "[cv]", "-map", "[a]",
                  "-t", str(total)] + enc + [final])
    else:
        cmd = ([ffmpeg, "-y"] + img_inputs
               + ["-i", audio]
               + ["-filter_complex", vf, "-map", "[cv]", "-map", "5:a",
                  "-t", str(total)] + enc + [final])
    _run_ffmpeg(cmd, "static assemble")


# ── Main entry point ──────────────────────────────────────────────────────────

async def create_quiz_video(
    quiz_data:       dict,
    output_dir:      str,
    voice:           str       = "am_adam",
    pexels_key:      str       = "",
    used_video_ids:  set | None = None,
) -> "tuple[str, int | None]":
    """Returns (final_path, pexels_video_id_used_or_None)."""
    from imageio_ffmpeg import get_ffmpeg_exe

    ffmpeg = get_ffmpeg_exe()
    os.makedirs(output_dir, exist_ok=True)

    question = quiz_data["question"]
    options  = quiz_data["options"]
    correct  = quiz_data["correct_answer"]
    exp      = quiz_data.get("explanation", "")
    category = quiz_data.get("category", "MATH QUIZ")
    iq       = quiz_data.get("image_query", "mathematics classroom chalkboard")

    print(f"[quiz] Question: {question}")

    # 1. Center photo (Pexels)
    center_img = get_center_image(iq, pexels_key) if pexels_key else None

    # 2. Background video (Pexels)
    bg_video  = os.path.join(output_dir, "bg_video.mp4")
    bg_q = quiz_data.get("bg_query", iq)
    _bg_ok, _bg_id = (False, None)
    if pexels_key:
        _bg_ok, _bg_id = _download_pexels_bg_video(bg_q, pexels_key, bg_video, used_video_ids)
    has_bg = _bg_ok

    # 3. Render card frames
    solid = not has_bg
    print(f"[quiz] Rendering cards (bg={'pexels_video' if has_bg else 'swirly_fallback'})...")
    keys = [
        ("q",  dict(question=question, options=options, category=category, center_img=center_img, solid_bg=solid)),
        ("t3", dict(question=question, options=options, category=category, center_img=center_img, timer_num=3, solid_bg=solid)),
        ("t2", dict(question=question, options=options, category=category, center_img=center_img, timer_num=2, solid_bg=solid)),
        ("t1", dict(question=question, options=options, category=category, center_img=center_img, timer_num=1, solid_bg=solid)),
        ("a",  dict(question=question, options=options, correct=correct,   category=category, center_img=center_img, solid_bg=solid)),
    ]
    fpaths = {}
    for key, kwargs in keys:
        img = draw_quiz_card(**kwargs)
        p   = os.path.join(output_dir, f"card_{key}.png")
        img.save(p)
        fpaths[key] = p
    draw_quiz_card(question=question, options=options, category=category,
                   center_img=center_img, solid_bg=solid).save(
        os.path.join(output_dir, "thumbnail.png"))

    # 4. TTS narration — frame-synced (question + countdown + answer)
    audio = os.path.join(output_dir, "narration.wav")
    print(f"[quiz] TTS: {question[:60]}...")
    q_dur, a_dur = await _build_synced_narration(
        question, options, correct, output_dir, voice
    )

    # 5. Timing (exact — derived from TTS part durations)
    total = round(q_dur + 3.0 + a_dur, 2)
    print(f"[quiz] Audio={total:.1f}s  question={q_dur:.2f}s  3-2-1  answer={a_dur:.2f}s")

    # 6. Background music
    music     = None
    music_dir = os.path.join(os.path.dirname(__file__), "music")
    if os.path.isdir(music_dir):
        tracks = [os.path.join(music_dir, f) for f in os.listdir(music_dir)
                  if f.lower().endswith((".mp3", ".wav"))]
        if tracks:
            music = random.choice(tracks)

    # 7. Tick track
    tick = _make_tick_track(os.path.join(output_dir, "tick.wav"), q_dur, a_dur)

    # 8. Assemble
    final = os.path.join(output_dir, "final_short.mp4")
    print("[quiz] Assembling video...")
    if has_bg:
        _assemble_pexels_bg(ffmpeg, bg_video, fpaths, audio, music,
                            q_dur, a_dur, total, final, output_dir, tick)
    else:
        _assemble_static(ffmpeg, fpaths, audio, tick, music, q_dur, a_dur, total, final)

    print(f"[quiz] Done → {final}")
    return final, _bg_id

