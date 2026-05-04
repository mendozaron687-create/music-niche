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
    Ask OpenRouter to split 'text' into two grammatically correct Filipino lines:
      - Line 1 (yellow): the emotional hook phrase — short, punchy, fits on thumbnail
      - Line 2 (white): the follow-up / context phrase — can be empty

    Falls back to a punctuation-aware word split if OpenRouter is unavailable.
    """
    api_key = os.getenv("OPENROUTER_API_KEY", "")
    if api_key and _requests:
        try:
            prompt = (
                "Ikaw ay isang Filipino hugot copywriter para sa YouTube music thumbnails.\n"
                "Binibigyan ka ng isang raw na hugot na ideya (maaaring halo ng Tagalog at English).\n"
                "Ang trabaho mo: i-rewrite ito bilang DALAWANG maikling linya ng natural na Tagalog hugot "
                "na parang totoong pag-uusap — kung paano talaga nagsasalita ang mga Pilipino kapag masakit ang puso.\n\n"
                "Mga panuntunan:\n"
                "1. Dapat grammatically correct ang bawat linya sa natural na Filipino/Tagalog.\n"
                "2. Huwag literal na isalin — gamitin ang natural na Filipino sentence structure (Verb-Subject-Object).\n"
                "   Halimbawa: 'Walang Iwanan Sabi Mo Bakit Ako Iniwan Mo' → "
                "LINE1: Sabi mo walang iwanan? / LINE2: Bakit ako iniwan mo?\n"
                "3. Line 1 = ang emotional punch / accusation — 4-6 salita, may tanong o exclamation.\n"
                "4. Line 2 = ang follow-up na tanong o sakit — 4-6 salita. Pwedeng wala kung isang linya na lang.\n"
                "5. Gumamit ng natural na Tagalog particles: mo, ka, ako, na, ba, kaya, lang, talaga, nga, eh.\n"
                "6. Huwag mag-translate sa English. Tagalog lang.\n"
                "7. Isagot lang ang dalawang linya, wala ng iba. Format:\n"
                "LINE1: <unang linya>\n"
                "LINE2: <pangalawang linya o blangko>\n\n"
                f"Raw hugot idea: {text}"
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
                    "temperature": 0.4,
                    "max_tokens": 80,
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
                print(f"[thumb] AI text split → yellow='{line1}' white='{line2}'")
                return line1, line2
        except Exception as e:
            print(f"[thumb] AI split failed ({e}), using fallback")

    # Fallback: split at natural punctuation breaks (... / " / ? / !)
    clean = re.sub(r'[^\w\s]', '', text).strip()
    # Try splitting at ellipsis or quote boundary in original text
    for sep in ['...', '"', '?', '!']:
        parts = text.split(sep, 1)
        if len(parts) == 2:
            p1 = re.sub(r'[^\w\s]', '', parts[0]).strip()
            p2 = re.sub(r'[^\w\s]', '', parts[1]).strip()
            if p1 and p2:
                return p1[:40], p2[:40]
    # Last resort: half-split by word count
    words = clean.split()
    mid = max(2, len(words) // 2)
    return " ".join(words[:mid]), " ".join(words[mid:mid+4])


def generate_music_thumbnail(
    title: str,
    genre_key: str,
    output_path: str,
    video_path: str = None,
    story_hook: str = None,
) -> str:
    """
    High-CTR 1280x720 YouTube thumbnail.
    Layout: AI photo full-bleed → hard opaque-left dark panel → bold left text → subject visible right.
    Research: split-panel, face/emotion right, 5-6 words max, yellow first line, sadness = 2.3M avg views.
    """
    os.makedirs(os.path.dirname(output_path) if os.path.dirname(output_path) else ".", exist_ok=True)
    W, H      = 1280, 720
    BADGE_H   = 62
    LP        = int(W * 0.52)   # left panel hard edge: 665px (text stays left of this)
    FADE_END  = int(W * 0.72)   # panel fades to 0 here: 921px (subject visible right of this)
    TX        = 52              # text left margin
    MAX_TW    = LP - TX - 30    # max text pixel width: ~583px
    is_hugot  = "hugot" in genre_key or "ballad" in genre_key or "opm" in genre_key
    RED       = (210, 15, 45)
    YELLOW    = (255, 220, 0)
    WHITE     = (255, 255, 255)

    def _fn(size):
        # Search order: Windows Arial Bold → Liberation Sans Bold (Linux) → DejaVu Bold → fallback
        candidates = [
            "arialbd.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
            "/usr/share/fonts/liberation/LiberationSans-Bold.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
            "/System/Library/Fonts/Helvetica.ttc",   # macOS
        ]
        for path in candidates:
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                continue
        # Last resort: Pillow default (tiny but won't crash)
        return ImageFont.load_default()

    # ── 1. Background: AI → video frame → gradient ───────────────────────────
    frame = _generate_ai_background(genre_key)
    if frame is None and video_path and os.path.exists(video_path):
        frame = _extract_video_frame(video_path, time_sec=45.0)

    if frame:
        img = frame.resize((W, H), Image.LANCZOS)
        # Very light global darken — preserve the AI photo's vibrancy
        dark = Image.new("RGB", (W, H), (0, 0, 0))
        img  = Image.blend(img, dark, 0.08)
        img  = ImageEnhance.Brightness(img).enhance(1.25)
        img  = ImageEnhance.Color(img).enhance(1.55)
        img  = ImageEnhance.Contrast(img).enhance(1.12)
    else:
        # Fallback: dramatic diagonal gradient — still looks intentional/branded
        colors = _MUSIC_GRADIENTS.get(genre_key, [(15, 15, 35), (45, 25, 80)])
        img = Image.new("RGB", (W, H))
        try:
            import numpy as np
            yy, xx = np.mgrid[0:H, 0:W]
            # diagonal blend so right side is slightly lighter (where subject would be)
            t  = (xx / W * 0.35 + yy / H * 0.65).clip(0, 1)
            r0, g0, b0 = colors[0]
            r1, g1, b1 = colors[1]
            arr = np.stack([
                (r0 * (1-t) + r1 * t).astype(np.uint8),
                (g0 * (1-t) + g1 * t).astype(np.uint8),
                (b0 * (1-t) + b1 * t).astype(np.uint8),
            ], axis=-1)
            img = Image.fromarray(arr, 'RGB')
        except ImportError:
            for y in range(H):
                r = y / H
                img.paste((
                    int(colors[0][0] * (1-r) + colors[1][0] * r),
                    int(colors[0][1] * (1-r) + colors[1][1] * r),
                    int(colors[0][2] * (1-r) + colors[1][2] * r),
                ), (0, y, W, y + 1))

    # ── 2. Hard left dark panel (OPAQUE left half → transparent by 72%) ──────
    img = img.convert("RGBA")
    try:
        import numpy as np
        arr   = np.zeros((H, W, 4), dtype=np.uint8)
        x     = np.arange(W, dtype=float)
        alpha = np.where(
            x < LP,
            205,
            np.where(x < FADE_END,
                205 * (1.0 - (x - LP) / (FADE_END - LP)),
                0)
        ).clip(0, 255).astype(np.uint8)
        arr[:, :, 3] = alpha[np.newaxis, :]
        panel = Image.fromarray(arr, 'RGBA')
    except ImportError:
        panel = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        pd = ImageDraw.Draw(panel)
        pd.rectangle([0,  0, LP,       H], fill=(0, 0, 0, 205))
        pd.rectangle([LP, 0, FADE_END, H], fill=(0, 0, 0,  95))
    img = Image.alpha_composite(img, panel)

    # Thin top/bottom bar to frame the image nicely
    vig = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    vd  = ImageDraw.Draw(vig)
    vd.rectangle([0, 0, W, H // 11],    fill=(0, 0, 0, 60))
    vd.rectangle([0, H * 10 // 11, W, H], fill=(0, 0, 0, 80))
    img = Image.alpha_composite(img, vig).convert("RGB")
    draw = ImageDraw.Draw(img)

    # Vertical red accent stripe at the panel edge
    draw.rectangle([LP - 7, 0, LP, H - BADGE_H], fill=RED)

    # ── 3. Fonts & text ──────────────────────────────────────────────────────
    raw   = story_hook or title
    clean = re.sub(r'[^\x20-\x7E\u0080-\u024F]', '', raw).strip()

    # Use OpenRouter to split the text into 2 grammatically correct Filipino lines
    y_txt, w_txt = _ai_split_thumbnail_text(clean, MAX_TW)

    # Auto-size yellow text so it always fits in the left panel
    f_yellow   = _fn(72)
    y_size     = 72
    for sz in range(155, 64, -5):
        fnt = _fn(sz)
        bb  = fnt.getbbox(y_txt)
        if (bb[2] - bb[0]) <= MAX_TW:
            f_yellow = fnt
            y_size   = sz
            break

    w_size  = max(64, int(y_size * 0.76))
    f_white = _fn(w_size)
    f_tag   = _fn(30)
    f_sub   = _fn(34)
    f_heart = _fn(52)
    f_badge = _fn(32)

    lh_y = int(y_size  * 1.18)
    lh_w = int(w_size  * 1.18)

    # Layout: ♥ + HUGOT tag → yellow line → white line → subtitle
    H_HEART = 66
    H_TAG   = 50
    GAP     = 14
    H_SUB   = 44
    total   = (H_HEART + GAP + H_TAG + GAP
               + lh_y
               + (lh_w + GAP if w_txt else 0)
               + GAP + H_SUB)
    base_y  = max(44, (H - total) // 2)

    heart_cy  = base_y + H_HEART // 2
    tag_y     = base_y + H_HEART + GAP
    yellow_cy = tag_y + H_TAG + GAP + lh_y // 2
    white_cy  = yellow_cy + lh_y // 2 + GAP + lh_w // 2 if w_txt else 0
    sub_cy    = (white_cy + lh_w // 2 + GAP) if w_txt else (yellow_cy + lh_y // 2 + GAP)

    # ── 4. Glow pass (blurred shadow behind text) ────────────────────────────
    glow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    gd   = ImageDraw.Draw(glow)
    for ox, oy in [(-11,-11),(11,-11),(-11,11),(11,11),(0,-14),(0,14),(-14,0),(14,0)]:
        gd.text((TX + ox, yellow_cy + oy), y_txt, font=f_yellow, fill=(0, 0, 0, 255), anchor="lm")
        if w_txt:
            gd.text((TX + ox, white_cy + oy), w_txt, font=f_white, fill=(0, 0, 0, 255), anchor="lm")
    glow = glow.filter(ImageFilter.GaussianBlur(radius=12))
    img  = img.convert("RGBA")
    img  = Image.alpha_composite(img, glow)
    img  = img.convert("RGB")
    draw = ImageDraw.Draw(img)

    # ── 5. ♥ Heart symbol ────────────────────────────────────────────────────
    draw.text((TX + 3, heart_cy + 3), "\u2665", font=f_heart, fill=(90, 0, 15), anchor="lm")
    draw.text((TX,     heart_cy),     "\u2665", font=f_heart, fill=RED,          anchor="lm")

    # ── 6. HUGOT tag pill (right of heart) ───────────────────────────────────
    hb       = f_heart.getbbox("\u2665")
    heart_w  = hb[2] - hb[0] + 14
    pill_x   = TX + heart_w
    tag_lbl  = "HUGOT" if is_hugot else "OPM"
    tb       = f_tag.getbbox(tag_lbl)
    pill_w   = tb[2] - tb[0] + 26
    draw.rounded_rectangle([pill_x, tag_y, pill_x + pill_w, tag_y + H_TAG], radius=8, fill=RED)
    draw.text((pill_x + 13, tag_y + H_TAG // 2), tag_lbl, font=f_tag, fill=WHITE, anchor="lm")

    # ── 7. Yellow text (first line — the SHOCK) ───────────────────────────────
    draw.text((TX + 4, yellow_cy + 4), y_txt, font=f_yellow, fill=(0, 0, 0), anchor="lm")
    draw.text((TX,     yellow_cy),     y_txt, font=f_yellow, fill=YELLOW,    anchor="lm")
    # Yellow underline
    yb   = f_yellow.getbbox(y_txt)
    ul_y = yellow_cy + lh_y // 2 + 6
    draw.rectangle([TX, ul_y, TX + yb[2] - yb[0], ul_y + 6], fill=YELLOW)

    # ── 8. White text (second line — the CONTEXT) ────────────────────────────
    if w_txt:
        draw.text((TX + 3, white_cy + 3), w_txt, font=f_white, fill=(0, 0, 0), anchor="lm")
        draw.text((TX,     white_cy),     w_txt, font=f_white, fill=WHITE,     anchor="lm")

    # ── 9. Subtitle (song title) ──────────────────────────────────────────────
    sub_clean = re.sub(r'[^\x20-\x7E\u0080-\u024F]', '', title).strip()[:42]
    draw.text((TX + 2, sub_cy + 2), sub_clean, font=f_sub, fill=(0, 0, 0),       anchor="lm")
    draw.text((TX,     sub_cy),     sub_clean, font=f_sub, fill=(185, 185, 185), anchor="lm")

    # ── 10. Bottom badge ──────────────────────────────────────────────────────
    draw.rectangle([0, H - BADGE_H, W, H], fill=RED)
    badge_txt = "OPM HUGOT PLAYLIST  \u2022  NEW SONG" if is_hugot else "SUBSCRIBE FOR MORE MUSIC"
    draw.text((W // 2, H - BADGE_H // 2), badge_txt, font=f_badge, fill=WHITE, anchor="mm")

    # ── 11. Top accent bar ────────────────────────────────────────────────────
    draw.rectangle([0, 0, W, 6], fill=RED)

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
