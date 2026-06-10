import os
import io
import re
import subprocess
import tempfile
import textwrap
import random
import urllib.parse
import urllib.request
try:
    import requests as _requests
except ImportError:
    _requests = None
try:
    from dotenv import load_dotenv as _load_dotenv
    _load_dotenv()
except ImportError:
    pass
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageEnhance


# ── AI background prompts per genre (Pollinations.ai / FLUX) ────────────────

# ── Structured JSON prompts — fields are serialized in order for precision ──
# FLUX responds best to: subject first → position → lighting → bg → emotion → style → quality

_AI_BG_PROMPTS = {
    "hugot_ballad": [
        {
            "subject":    "young Filipino woman, 20s, crying",
            "position":   "right half of frame, close-up portrait",
            "face":       "fully visible, front-facing, looking at camera",
            "lighting":   "single warm candle light from below, highlights wet cheeks",
            "background": "left half completely dark black, right bokeh blur",
            "emotion":    "heartbreak, deep sadness, tears on cheeks",
            "style":      "cinematic portrait, film grain",
            "quality":    "photorealistic, 4k, sharp focus on face"
        },
        {
            "subject":    "Filipina woman in her 20s",
            "position":   "right side of frame, medium close-up",
            "face":       "clearly lit, facing viewer",
            "lighting":   "golden warm key light from right, deep shadow left",
            "background": "left side dark for text overlay, blurred warm bokeh right",
            "emotion":    "devastated, tearful, broken heart",
            "style":      "cinematic drama, shallow depth of field",
            "quality":    "photorealistic, ultra-detailed, 4k"
        },
    ],
    "hugot_opm_pop": [
        {
            "subject":    "young sad Filipina woman, 20s",
            "position":   "right half of frame, medium shot",
            "face":       "fully visible, large, looking slightly off-camera",
            "lighting":   "golden hour sunlight on face, warm orange glow, well-lit",
            "background": "left half dark shadow for text, right bokeh sunset city",
            "emotion":    "longing, heartbreak, tear on cheek",
            "style":      "cinematic, magazine quality",
            "quality":    "photorealistic, 4k, high contrast, vibrant colors"
        },
        {
            "subject":    "beautiful Filipina woman looking sad",
            "position":   "right two-thirds of frame, portrait",
            "face":       "prominent, well-lit with warm light, direct gaze",
            "lighting":   "dramatic warm rim lighting, strong contrast",
            "background": "deep black left side, blurred city bokeh right",
            "emotion":    "sad, betrayed, tears forming",
            "style":      "Sony A7 portrait, cinematic",
            "quality":    "photorealistic, sharp face, 4k"
        },
    ],
    "opm_rnb_hugot": [
        {
            "subject":    "young Filipino woman",
            "position":   "right side of frame",
            "face":       "clearly lit by neon city lights, visible, emotional",
            "lighting":   "cool blue and purple neon from right, dark left",
            "background": "rainy city night, neon reflections, left side dark",
            "emotion":    "melancholy, lost, heartbroken",
            "style":      "R&B music video aesthetic, cinematic",
            "quality":    "photorealistic, 4k, moody color grade"
        },
    ],
    "pinoy_rap_hugot": [
        {
            "subject":    "young Filipino man, emotional expression",
            "position":   "right side of frame, medium close-up",
            "face":       "clearly visible, intense gaze, well-lit",
            "lighting":   "harsh neon side light, deep shadows",
            "background": "dark urban street left, graffiti blur right",
            "emotion":    "pain, anger, heartbreak",
            "style":      "hip hop music video, cinematic",
            "quality":    "photorealistic, 4k"
        },
    ],
    "default": [
        {
            "subject":    "heartbroken Filipino woman",
            "position":   "right half of frame, portrait",
            "face":       "clearly visible, illuminated, facing camera",
            "lighting":   "dramatic warm key light, dark left side",
            "background": "pure dark left half, soft bokeh right",
            "emotion":    "deep sadness, tears, vulnerability",
            "style":      "cinematic portrait",
            "quality":    "photorealistic, 4k, ultra-sharp"
        },
    ],
}


# ── Pexels high-emotion search queries per genre ─────────────────────────────
_PEXELS_THUMB_QUERIES: dict = {
    "hugot_ballad":         ["woman crying face closeup", "sad woman portrait tears", "crying woman face"],
    "hugot_opm_pop":        ["shocked woman face closeup", "woman open mouth surprise", "emotional woman face"],
    "opm_rnb_hugot":        ["sad woman night portrait", "emotional woman crying", "heartbroken woman face"],
    "opm_funky_love":       ["romantic couple sunset golden hour", "couple laughing happy love", "woman smiling joyful portrait", "couple embrace romantic", "happy woman in love closeup"],
    "pinoy_rap_hugot":      ["emotional man crying face", "sad man portrait", "man heartbroken face"],
    "pamana_folk_opm":      ["sad woman portrait", "tearful woman face closeup", "woman crying face"],
    "pinoy_rant":           ["angry man face closeup", "frustrated man expression", "shocked man face"],
    "pinoy_protest_anthem": ["angry person face", "frustrated person shouting face", "shocked person face"],
    "motivational_hip_hop": ["confident man face closeup", "motivated man portrait", "determined man face"],
    "lofi_hiphop":          ["sad girl face aesthetic", "lonely woman face", "melancholy woman portrait"],
    "chill_pop":            ["happy woman laughing face", "joyful woman face closeup", "happy girl face"],
    "default":              ["romantic couple sunset", "happy woman portrait smiling", "couple in love golden hour"],
}


def _fetch_pexels_background(genre_key: str, pexels_key: str) -> "Image.Image | None":
    """
    Fetch a high-emotion face photo from Pexels for the thumbnail background.
    Prefers portrait orientation (vertical) so the face fills the frame well.
    Crops/pads portrait photos to 1280x720 with face on the right side.
    Returns a 1280x720 PIL Image, or None on failure / missing API key.
    """
    if not pexels_key or not _requests:
        return None

    queries = _PEXELS_THUMB_QUERIES.get(genre_key) or _PEXELS_THUMB_QUERIES["default"]
    query   = random.choice(queries)
    page    = random.randint(1, 3)

    def _try_fetch(orientation: str, pg: int):
        try:
            resp = _requests.get(
                "https://api.pexels.com/v1/search",
                headers={"Authorization": pexels_key},
                params={"query": query, "per_page": 15, "page": pg, "orientation": orientation},
                timeout=20,
            )
            resp.raise_for_status()
            return resp.json().get("photos", [])
        except Exception:
            return []

    # Try portrait first (tall photos = face fills frame), fallback landscape
    photos = _try_fetch("portrait", page)
    if not photos:
        photos = _try_fetch("portrait", 1)
    if not photos:
        photos = _try_fetch("landscape", page)
    if not photos:
        photos = _try_fetch("landscape", 1)
    if not photos:
        return None

    photo   = random.choice(photos)
    src     = photo.get("src") or {}
    img_url = src.get("large2x") or src.get("original") or src.get("large")
    if not img_url:
        return None

    try:
        img_resp = _requests.get(img_url, timeout=30)
        img_resp.raise_for_status()
        img = Image.open(io.BytesIO(img_resp.content)).convert("RGB")
        W_out, H_out = 1280, 720
        iw, ih = img.size

        if iw < ih:
            # Portrait photo: scale to ~760px wide (face stays on right, gradient blends over left edge)
            target_w = 760
            scale    = target_w / iw
            new_h    = int(ih * scale)
            img      = img.resize((target_w, new_h), Image.LANCZOS)
            # Crop from top — face is typically in upper 720px of a portrait
            crop_h   = min(new_h, H_out)
            img      = img.crop((0, 0, target_w, crop_h))
            if crop_h < H_out:
                pad = Image.new("RGB", (target_w, H_out), (0, 0, 0))
                pad.paste(img, (0, 0))
                img = pad
            canvas  = Image.new("RGB", (W_out, H_out), (0, 0, 0))
            paste_x = W_out - target_w  # ≈520
            # Build a left-to-right gradient mask to feather the portrait's left edge
            blend_w = min(240, target_w // 3)
            mask    = Image.new("L", (target_w, H_out), 255)
            try:
                import numpy as _np
                m_arr = _np.full((H_out, target_w), 255, dtype=_np.uint8)
                fade  = (_np.arange(blend_w, dtype=float) / blend_w * 255).astype(_np.uint8)
                m_arr[:, :blend_w] = fade[_np.newaxis, :]
                mask = Image.fromarray(m_arr, "L")
            except ImportError:
                md = ImageDraw.Draw(mask)
                for x in range(blend_w):
                    md.line([(x, 0), (x, H_out)], fill=int(255 * x / blend_w))
            canvas.paste(img, (paste_x, 0), mask=mask)
            img = canvas
        else:
            # Landscape: fit to 1280x720
            img = img.resize((W_out, H_out), Image.LANCZOS)

        print(f"[thumb] Pexels background: '{query}' ({photo.get('width')}x{photo.get('height')}, {len(img_resp.content)//1024}KB)")
        return img
    except Exception as e:
        print(f"[thumb] Pexels background download failed: {e}")
        return None


def _prompt_to_text(p: dict) -> str:
    """Serialize structured JSON prompt dict to a precise ordered FLUX prompt string."""
    order = ["subject", "position", "face", "lighting", "background", "emotion", "style", "quality"]
    return ", ".join(p[k] for k in order if k in p)


def _generate_ai_background(genre_key: str, seed: int = None) -> "Image.Image | None":
    """
    Generate an AI background via Pollinations.ai (FLUX). Free, no API key.
    Returns a 1280x720 PIL Image or None on failure.
    Tries full structured prompt first, then a short fallback prompt on timeout.
    """
    prompts = _AI_BG_PROMPTS.get(genre_key) or _AI_BG_PROMPTS["default"]
    p       = random.choice(prompts)
    if seed is None:
        seed = random.randint(1, 99999)

    # First attempt: full structured prompt
    full_prompt = _prompt_to_text(p)
    # Short fallback prompt if server is slow
    short_prompt = f"{p.get('subject', 'sad Filipino woman')}, right side of frame, face clearly visible, dramatic lighting, left side dark, photorealistic, 4k"

    for attempt, prompt in enumerate([full_prompt, short_prompt], 1):
        print(f"[thumb] Attempt {attempt} — Prompt: {prompt[:70]}...")
        encoded = urllib.parse.quote(prompt)
        url = (
            f"https://image.pollinations.ai/prompt/{encoded}"
            f"?width=1280&height=720&nologo=true&model=flux&seed={seed + attempt}"
        )
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=55) as resp:
                data = resp.read()
            img = Image.open(io.BytesIO(data)).convert("RGB")
            img = img.resize((1280, 720), Image.LANCZOS)
            print(f"[thumb] AI background generated ({len(data)//1024}KB)")
            return img
        except Exception as e:
            print(f"[thumb] Attempt {attempt} failed: {e}")
            if attempt == 1:
                import time; time.sleep(3)  # brief pause before retry

    print("[thumb] All AI attempts failed — falling back to gradient")
    return None

# ── Music niche thumbnail (1280x720 landscape) ──────────────────────────────

_MUSIC_GRADIENTS = {
    "lofi_hiphop":         [(20, 20, 40),    (60, 40, 100)],
    "cinematic_orchestral":[(10, 10, 10),    (80, 30, 0)],
    "dark_ambient":        [(5, 5, 15),      (30, 0, 60)],
    "phonk":               [(10, 0, 0),      (80, 10, 10)],
    "chill_pop":           [(255, 180, 200), (150, 100, 220)],
    "nature_meditation":   [(10, 40, 20),    (30, 80, 50)],
    "motivational_hip_hop":[(20, 10, 0),     (120, 60, 0)],
    "sleep_music":         [(5, 5, 30),      (20, 20, 60)],
    "hugot_ballad":        [(5, 0, 8),       (90, 0, 22)],
}

_MUSIC_ICONS = {
    "lofi_hiphop":         "🎧",
    "cinematic_orchestral":"🎬",
    "dark_ambient":        "🖤",
    "phonk":               "💀",
    "chill_pop":           "🌸",
    "nature_meditation":   "🍃",
    "motivational_hip_hop":"🔥",
    "sleep_music":         "😴",
    "hugot_ballad":        "💔",
}


def _extract_video_frame(video_path: str, time_sec: float = 45.0) -> "Image.Image | None":
    """Extract a single frame from video at time_sec using ffmpeg."""
    try:
        import imageio_ffmpeg
        ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return None
    tmp = tempfile.NamedTemporaryFile(suffix=".jpg", delete=False)
    tmp.close()
    try:
        r = subprocess.run(
            [ffmpeg, "-y", "-ss", str(time_sec), "-i", video_path,
             "-vframes", "1", "-q:v", "2", tmp.name],
            capture_output=True, timeout=15,
        )
        if r.returncode == 0 and os.path.exists(tmp.name) and os.path.getsize(tmp.name) > 1000:
            return Image.open(tmp.name).copy()
    except Exception:
        pass
    finally:
        if os.path.exists(tmp.name):
            os.remove(tmp.name)
    return None


def _ai_split_thumbnail_text(text: str, max_tw_px: int) -> tuple[str, str]:
    """
    Split 'text' (the actual song/video title) into two thumbnail display lines.
    Line 1 (yellow): first emotional chunk — punchy, 3-6 words.
    Line 2 (white): second chunk — context/follow-up, can be empty.
    IMPORTANT: preserve the original words — do NOT rewrite or translate.
    """
    api_key = os.getenv("OPENROUTER_API_KEY", "")
    if api_key and _requests:
        try:
            prompt = (
                "You are a YouTube thumbnail text layout assistant.\n"
                "Given a song/video title, split it into EXACTLY two display lines for a thumbnail.\n"
                "Rules:\n"
                "1. Do NOT change, translate, or rewrite the words — only split them.\n"
                "2. LINE1 = the first emotional punch — 3 to 5 words from the title.\n"
                "3. LINE2 = the remaining words. Can be empty if title is very short.\n"
                "4. Split at a natural phrase boundary (after a comma, conjunction, or question mark).\n"
                "5. Reply ONLY in this format:\n"
                "LINE1: <first part>\n"
                "LINE2: <second part or empty>\n\n"
                f"Title: {text}"
            )
            resp = _requests.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                    "HTTP-Referer": "https://github.com/music-niche-automation",
                },
                json={
                    "model": "google/gemini-2.0-flash-001",
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.1,
                    "max_tokens": 60,
                },
                timeout=15,
            )
            resp.raise_for_status()
            raw = resp.json()["choices"][0]["message"]["content"].strip()
            line1, line2 = "", ""
            for line in raw.splitlines():
                if line.upper().startswith("LINE1:"):
                    line1 = line.split(":", 1)[1].strip()
                elif line.upper().startswith("LINE2:"):
                    line2 = line.split(":", 1)[1].strip()
            if line1:
                print(f"[thumb] Title split → yellow='{line1}' white='{line2}'")
                return line1, line2
        except Exception as e:
            print(f"[thumb] AI split failed ({e}), using fallback")

    # Fallback: split at natural punctuation breaks
    clean = re.sub(r'[^\w\s]', '', text).strip()
    for sep in ['...', ',', '?', '!', ' na ', ' at ']:
        parts = text.split(sep, 1)
        if len(parts) == 2:
            p1 = re.sub(r'[^\w\s]', '', parts[0]).strip()
            p2 = re.sub(r'[^\w\s]', '', parts[1]).strip()
            if p1 and p2:
                return p1[:44], p2[:44]
    # Last resort: half-split by word count
    words = clean.split()
    mid = max(2, len(words) // 2)
    return " ".join(words[:mid]), " ".join(words[mid:])


def generate_music_thumbnail(
    title: str,
    genre_key: str,
    output_path: str,
    video_path: str = None,
    story_hook: str = None,
    pexels_key: str = "",
) -> str:
    """
    High-CTR 1280x720 YouTube thumbnail.
    Style: MCA Music PH / Star Music PH — full-bleed emotional Pexels face,
    soft left gradient (no hard line/border), thick-stroke bold text left,
    large face right, red arrows + circle, red bottom badge.
    """
    os.makedirs(os.path.dirname(output_path) if os.path.dirname(output_path) else ".", exist_ok=True)
    W, H       = 1280, 720
    BADGE_H    = 70
    TX         = 50               # text left margin
    TEXT_ZONE  = int(W * 0.53)    # text stays left of this (~678px)
    MAX_TW     = TEXT_ZONE - TX - 18
    YELLOW     = (255, 220, 0)
    GOLD       = (255, 185, 0)
    WHITE      = (255, 255, 255)

    def _fn(size):
        candidates = [
            "arialbd.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
            "/usr/share/fonts/liberation/LiberationSans-Bold.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
            "/System/Library/Fonts/Helvetica.ttc",
        ]
        for path in candidates:
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                continue
        return ImageFont.load_default()

    def _stroke_text(d, xy, text, font, fill, sw=9, sf=(0, 0, 0), anchor="lm"):
        """Thick black-stroke text — multiple offset pass to simulate bold outline."""
        x, y = xy
        for ox in range(-sw, sw + 1, 3):
            for oy in range(-sw, sw + 1, 3):
                if ox == 0 and oy == 0:
                    continue
                d.text((x + ox, y + oy), text, font=font, fill=sf, anchor=anchor)
        d.text((x, y), text, font=font, fill=fill, anchor=anchor)

    # ── 1. Background: Pexels → AI → video frame → gradient ──────────────────
    frame = _fetch_pexels_background(genre_key, pexels_key)
    if frame is None:
        frame = _generate_ai_background(genre_key)
    if frame is None and video_path and os.path.exists(video_path):
        frame = _extract_video_frame(video_path, time_sec=45.0)

    if frame:
        img = frame.resize((W, H), Image.LANCZOS)
        img = ImageEnhance.Brightness(img).enhance(1.12)
        img = ImageEnhance.Color(img).enhance(1.65)
        img = ImageEnhance.Contrast(img).enhance(1.18)
        img = ImageEnhance.Sharpness(img).enhance(1.4)
    else:
        colors = _MUSIC_GRADIENTS.get(genre_key, [(15, 15, 35), (45, 25, 80)])
        img = Image.new("RGB", (W, H))
        for y in range(H):
            r = y / H
            img.paste((
                int(colors[0][0] * (1-r) + colors[1][0] * r),
                int(colors[0][1] * (1-r) + colors[1][1] * r),
                int(colors[0][2] * (1-r) + colors[1][2] * r),
            ), (0, y, W, y + 1))

    # ── 2. Soft LEFT-ONLY gradient (no hard edge, no vertical line) ───────────
    # Darkens the text zone smoothly; face on the right stays fully bright.
    img = img.convert("RGBA")
    try:
        import numpy as np
        FADE_START = int(W * 0.08)   # solid dark starts here
        FADE_END   = int(W * 0.60)   # fully transparent by 60%
        arr   = np.zeros((H, W, 4), dtype=np.uint8)
        x_idx = np.arange(W, dtype=float)
        alpha = np.where(
            x_idx < FADE_START,
            215,
            np.where(
                x_idx < FADE_END,
                215 * (1.0 - (x_idx - FADE_START) / (FADE_END - FADE_START)),
                0,
            )
        ).clip(0, 255).astype(np.uint8)
        arr[:, :, 3] = alpha[np.newaxis, :]
        panel = Image.fromarray(arr, "RGBA")
    except ImportError:
        panel = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        pd = ImageDraw.Draw(panel)
        pd.rectangle([0, 0, int(W * 0.38), H], fill=(0, 0, 0, 210))
        pd.rectangle([int(W * 0.38), 0, int(W * 0.60), H], fill=(0, 0, 0, 95))
    img = Image.alpha_composite(img, panel).convert("RGB")

    # ── 3. Split the ACTUAL title into 2 display lines ────────────────────────
    # Strip suffix and AI Version label — thumbnail shows just the core title
    clean_title = re.sub(r'\s*\|\s*OPM Love Song.*$', '', title, flags=re.IGNORECASE).strip()
    clean_title = re.sub(r'\s*\|\s*Music\s*$', '', clean_title, flags=re.IGNORECASE).strip()
    clean_title = re.sub(r'\s*\(AI Version\)\s*', ' ', clean_title, flags=re.IGNORECASE).strip()
    clean_title = re.sub(r'\s*AI Version\s*', ' ', clean_title, flags=re.IGNORECASE).strip()
    clean_title = re.sub(r'[^\x20-\x7E\u0080-\u024F]', '', clean_title).strip()
    y_txt, w_txt = _ai_split_thumbnail_text(clean_title, MAX_TW)

    # ── 4. Fonts & auto-sizing ────────────────────────────────────────────────
    f_yellow = _fn(72)
    y_size   = 72
    for sz in range(148, 54, -4):
        fnt = _fn(sz)
        bb  = fnt.getbbox(y_txt)
        if (bb[2] - bb[0]) <= MAX_TW:
            f_yellow = fnt
            y_size   = sz
            break

    w_size  = max(56, int(y_size * 0.74))
    f_white = _fn(w_size)
    f_tag   = _fn(28)
    f_heart = _fn(50)
    f_badge = _fn(31)

    lh_y = int(y_size  * 1.20)
    lh_w = int(w_size  * 1.20)

    # ── 5. Vertical layout (centered in left text zone, clear of badge) ───────
    H_TAG = 44
    GAP   = 18
    total = H_TAG + GAP + lh_y + (lh_w + GAP if w_txt else 0)
    avail = H - BADGE_H - 60
    base_y     = max(40, (avail - total) // 2 + 20)
    tag_cy     = base_y + H_TAG // 2
    yellow_cy  = base_y + H_TAG + GAP + lh_y // 2
    white_cy   = yellow_cy + lh_y // 2 + GAP + lh_w // 2 if w_txt else 0

    # ── 6. Glow blob behind text (large soft dark halo for readability) ───────
    glow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    gd   = ImageDraw.Draw(glow)
    for ox, oy in [(-16, -16), (16, -16), (-16, 16), (16, 16),
                   (0, -20), (0, 20), (-20, 0), (20, 0)]:
        gd.text((TX + ox, yellow_cy + oy), y_txt, font=f_yellow,
                fill=(0, 0, 0, 210), anchor="lm")
        if w_txt:
            gd.text((TX + ox, white_cy + oy), w_txt, font=f_white,
                    fill=(0, 0, 0, 210), anchor="lm")
    glow = glow.filter(ImageFilter.GaussianBlur(radius=22))
    img  = img.convert("RGBA")
    img  = Image.alpha_composite(img, glow).convert("RGB")
    draw = ImageDraw.Draw(img)

    # ── 7. Genre pill tag (no red, no hugot) ───────────────────────────────────
    tag_lbl = "OPM LOVE SONG"
    tb      = f_tag.getbbox(tag_lbl)
    pill_w  = tb[2] - tb[0] + 22
    draw.rounded_rectangle(
        [TX, tag_cy - H_TAG // 2, TX + pill_w, tag_cy + H_TAG // 2],
        radius=7, fill=(20, 20, 20),
    )
    draw.text((TX + 11, tag_cy), tag_lbl, font=f_tag, fill=YELLOW, anchor="lm")

    # ── 8. Yellow first line — thick stroke + fill ────────────────────────────
    _stroke_text(draw, (TX, yellow_cy), y_txt, f_yellow, YELLOW, sw=10, anchor="lm")
    # Bold yellow underline
    yb   = f_yellow.getbbox(y_txt)
    ul_y = yellow_cy + lh_y // 2 + 5
    draw.rectangle([TX, ul_y, TX + yb[2] - yb[0], ul_y + 7], fill=YELLOW)

    # ── 9. Second line — same yellow as first ────────────────────────────────
    if w_txt:
        _stroke_text(draw, (TX, white_cy), w_txt, f_white, YELLOW, sw=9, anchor="lm")

    # ── 10. Bottom dark badge ────────────────────────────────────────────────
    draw.rectangle([0, H - BADGE_H, W, H], fill=(15, 15, 15))
    badge_txt = "BAGONG OPM LOVE SONG  \u2022  SUBSCRIBE FOR MORE"
    draw.text((W // 2, H - BADGE_H // 2), badge_txt, font=f_badge, fill=YELLOW, anchor="mm")

    # ── 12. Thin top accent bar (4px yellow) ──────────────────────────────────
    draw.rectangle([0, 0, W, 4], fill=GOLD)

    img.save(output_path, "PNG", quality=95)
    print(f"[thumb] Music thumbnail saved: {output_path}")
    return output_path




def generate_thumbnail(title: str, output_path: str,
                        background_video_path: str = None,
                        style: str = "dark") -> str:
    os.makedirs(os.path.dirname(output_path) if os.path.dirname(output_path) else ".", exist_ok=True)
    width, height = 1080, 1920
    if background_video_path and os.path.exists(background_video_path):
        try:
            bg = _extract_frame(background_video_path, width, height)
        except Exception:
            bg = _gradient(width, height, style)
    else:
        bg = _gradient(width, height, style)
    overlay = Image.new("RGBA", (width, height), (0, 0, 0, 140))
    bg = Image.alpha_composite(bg.convert("RGBA"), overlay).convert("RGB")
    draw = ImageDraw.Draw(bg)
    _draw_top_badge(draw, width)
    _draw_main_title(draw, title, width, height)
    _draw_bottom_bar(draw, width, height)
    _draw_border(draw, width, height)
    bg.save(output_path, "PNG", quality=95)
    print(f"Thumbnail saved: {output_path}")
    return output_path


def _extract_frame(video_path, width, height):
    from moviepy import VideoFileClip
    clip = VideoFileClip(video_path)
    frame = clip.get_frame(clip.duration * 0.3)
    clip.close()
    img = Image.fromarray(frame).resize((width, height), Image.LANCZOS)
    img = img.filter(ImageFilter.GaussianBlur(2))
    return ImageEnhance.Brightness(img).enhance(0.6)


def _gradient(width, height, style):
    gradients = {
        "dark":     [(15, 15, 35),   (45, 25, 80)],
        "gradient": [(255, 65, 108), (255, 75, 43)],
        "bright":   [(67, 198, 172), (25, 22, 84)],
        "gold":     [(255, 165, 0),  (139, 69, 19)],
    }
    c = gradients.get(style, gradients["dark"])
    img = Image.new("RGB", (width, height))
    for y in range(height):
        r = y / height
        img.paste(
            (int(c[0][0]*(1-r)+c[1][0]*r),
             int(c[0][1]*(1-r)+c[1][1]*r),
             int(c[0][2]*(1-r)+c[1][2]*r)),
            (0, y, width, y+1)
        )
    return img


def _font(name, size):
    try:
        return ImageFont.truetype(name, size)
    except:
        return ImageFont.load_default()


def _draw_top_badge(draw, width):
    draw.rectangle([width//2-200, 80, width//2+200, 160], fill=(255, 0, 0))
    font = _font("arial.ttf", 48)
    text = "▶ #SHORTS"
    bbox = draw.textbbox((0, 0), text, font=font)
    draw.text(((width-(bbox[2]-bbox[0]))//2, 95), text, fill="white", font=font)


def _draw_main_title(draw, title, width, height):
    font_l = _font("arialbd.ttf", 95)
    font_m = _font("arialbd.ttf", 75)
    wrapped = textwrap.wrap(title.upper(), width=15)
    font = font_l if len(wrapped) <= 3 else font_m
    line_h = 110
    start_y = (height - len(wrapped)*line_h) // 2 - 100
    for i, line in enumerate(wrapped):
        y = start_y + i*line_h
        draw.text((width//2+4, y+4), line, fill=(0,0,0,180), font=font, anchor="mm")
        draw.text((width//2, y), line, fill=(255,220,50) if i==0 else "white",
                  font=font, anchor="mm")


def _draw_bottom_bar(draw, width, height):
    y = height - 200
    draw.rectangle([0, y, width, y+130], fill=(255, 0, 0))
    font = _font("arialbd.ttf", 55)
    text = "FOLLOW FOR MORE"
    bbox = draw.textbbox((0, 0), text, font=font)
    draw.text(((width-(bbox[2]-bbox[0]))//2, y+35), text, fill="white", font=font)


def _draw_border(draw, width, height):
    b = 12
    draw.rectangle([0, 0, width, b], fill=(255,0,0))
    draw.rectangle([0, height-b, width, height], fill=(255,0,0))
    draw.rectangle([0, 0, b, height], fill=(255,0,0))
    draw.rectangle([width-b, 0, width, height], fill=(255,0,0))
