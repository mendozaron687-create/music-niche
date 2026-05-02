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
import json

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
OPT_WRONG = (210,  45,  45,  235)   # red tint for wrong options on reveal
OPT_CIRC  = (100, 175, 240,  255)
BRAND_BG  = (30,   60, 130,  220)
BRAND_FG  = (180, 220, 255,  255)
TIMER_COL = (255, 220,   0,  255)
DARK      = (15,   15,  15,  255)
QTEXT_BG  = (8,   15,   55,  175)

# ── 20 rotating card themes ───────────────────────────────────────────────────
# Each theme: banner bg, category label bg, question box bg,
#             option circle, timer digit, think overlay, trap CTA strip.
_CARD_THEMES = [
    # 0  Deep Navy (original)
    dict(banner=(15,  30,  80, 240), label=(30,  50, 120, 230), qbg=(8,  15,  55, 175),
         circle=(100, 175, 240, 255), timer=(255, 220,   0, 255), think=(180, 10, 10, 185), cta=(180, 20, 20, 235)),
    # 1  Royal Purple
    dict(banner=(60,  10, 120, 240), label=(80,  20, 140, 230), qbg=(35,  5,  75, 175),
         circle=(180, 100, 255, 255), timer=(255, 200,  50, 255), think=(100,  0, 180, 185), cta=(100,  0, 180, 235)),
    # 2  Forest Green
    dict(banner=(10,  70,  30, 240), label=(15, 100,  40, 230), qbg=(5,  40,  15, 175),
         circle=( 80, 220, 120, 255), timer=(200, 255, 100, 255), think=( 10, 100,  30, 185), cta=( 10, 100,  30, 235)),
    # 3  Crimson Red
    dict(banner=(120, 10,  20, 240), label=(160, 15,  25, 230), qbg=(70,  5,  10, 175),
         circle=(255,  80,  80, 255), timer=(255, 255, 100, 255), think=(160, 10,  10, 185), cta=(160, 10,  10, 235)),
    # 4  Midnight Teal
    dict(banner=(10,  80,  90, 240), label=(15, 110, 120, 230), qbg=(5,  45,  50, 175),
         circle=( 60, 210, 220, 255), timer=(180, 255, 255, 255), think=( 10,  90, 100, 185), cta=( 10,  90, 100, 235)),
    # 5  Burnt Orange
    dict(banner=(120, 55,  10, 240), label=(160, 70,  15, 230), qbg=(70, 30,   5, 175),
         circle=(255, 160,  60, 255), timer=(255, 240,  80, 255), think=(150,  60,  10, 185), cta=(150,  60,  10, 235)),
    # 6  Deep Magenta
    dict(banner=(100, 10,  80, 240), label=(130, 15, 100, 230), qbg=(60,  5,  45, 175),
         circle=(240,  80, 200, 255), timer=(255, 220, 255, 255), think=(120,  10,  90, 185), cta=(120,  10,  90, 235)),
    # 7  Slate Blue
    dict(banner=( 40, 55, 130, 240), label=( 55, 70, 160, 230), qbg=(20, 30,  80, 175),
         circle=(140, 160, 255, 255), timer=(220, 230, 255, 255), think=( 50,  60, 140, 185), cta=( 50,  60, 140, 235)),
    # 8  Dark Olive
    dict(banner=( 55, 65,  10, 240), label=( 75, 85,  15, 230), qbg=(30, 38,   5, 175),
         circle=(180, 210,  60, 255), timer=(230, 255, 100, 255), think=( 60,  70,  10, 185), cta=( 60,  70,  10, 235)),
    # 9  Indigo Night
    dict(banner=( 30,  0, 100, 240), label=( 45,  5, 130, 230), qbg=(15,  0,  60, 175),
         circle=(120,  80, 255, 255), timer=(200, 180, 255, 255), think=( 40,   0, 120, 185), cta=( 40,   0, 120, 235)),
    # 10 Rust & Sand
    dict(banner=(130, 45,  20, 240), label=(160, 60,  25, 230), qbg=(75, 25,  10, 175),
         circle=(255, 140,  60, 255), timer=(255, 230, 160, 255), think=(140,  50,  20, 185), cta=(140,  50,  20, 235)),
    # 11 Arctic Blue
    dict(banner=( 10, 100, 160, 240), label=( 15, 130, 200, 230), qbg=(5,  55,  90, 175),
         circle=(100, 220, 255, 255), timer=(220, 245, 255, 255), think=( 10, 110, 170, 185), cta=( 10, 110, 170, 235)),
    # 12 Jungle Dark
    dict(banner=( 20, 60,  20, 240), label=( 25, 80,  25, 230), qbg=(10, 35,  10, 175),
         circle=(100, 240, 100, 255), timer=(200, 255, 150, 255), think=( 20,  70,  20, 185), cta=( 20,  70,  20, 235)),
    # 13 Dark Wine
    dict(banner=( 90, 10,  40, 240), label=(120, 15,  55, 230), qbg=(50,  5,  20, 175),
         circle=(230,  80, 140, 255), timer=(255, 200, 220, 255), think=(100,  10,  45, 185), cta=(100,  10,  45, 235)),
    # 14 Steel Gray
    dict(banner=( 50, 55,  65, 240), label=( 65, 70,  82, 230), qbg=(25, 30,  38, 175),
         circle=(160, 180, 210, 255), timer=(220, 230, 240, 255), think=( 55,  60,  70, 185), cta=( 55,  60,  70, 235)),
    # 15 Deep Amber
    dict(banner=(110, 75,   0, 240), label=(145, 95,   0, 230), qbg=(65, 42,   0, 175),
         circle=(255, 195,   0, 255), timer=(255, 245, 150, 255), think=(120,  80,   0, 185), cta=(120,  80,   0, 235)),
    # 16 Neon Purple Night
    dict(banner=( 50,  0,  90, 240), label=( 70,  0, 120, 230), qbg=(28,  0,  55, 175),
         circle=(200,  0, 255, 255), timer=(255, 180, 255, 255), think=( 60,   0, 100, 185), cta=( 60,   0, 100, 235)),
    # 17 Ocean Depth
    dict(banner=(  0, 50, 100, 240), label=(  0, 70, 130, 230), qbg=(0,  28,  60, 175),
         circle=(  0, 190, 255, 255), timer=(150, 240, 255, 255), think=(  0,  55, 110, 185), cta=(  0,  55, 110, 235)),
    # 18 Dark Brown Earth
    dict(banner=( 70, 40,  10, 240), label=( 95, 52,  14, 230), qbg=(40, 22,   5, 175),
         circle=(200, 140,  60, 255), timer=(255, 220, 140, 255), think=( 80,  45,  10, 185), cta=( 80,  45,  10, 235)),
    # 19 Charcoal Black
    dict(banner=( 20, 20,  22, 240), label=( 35, 35,  38, 230), qbg=(10, 10,  12, 175),
         circle=(180, 180, 180, 255), timer=(255, 255, 255, 255), think=( 25,  25,  28, 185), cta=( 25,  25,  28, 235)),
]

_CHALLENGE_COUNTER_FILE = os.path.join(os.path.dirname(__file__), "challenge_counter.json")


def _get_next_challenge_num() -> int:
    """Read, increment, and persist the per-channel challenge counter."""
    try:
        if os.path.exists(_CHALLENGE_COUNTER_FILE):
            with open(_CHALLENGE_COUNTER_FILE) as f:
                data = json.load(f)
            n = data.get("count", 0) + 1
        else:
            n = 1
        with open(_CHALLENGE_COUNTER_FILE, "w") as f:
            json.dump({"count": n}, f)
        return n
    except Exception:
        return 1


# ── Helpers ───────────────────────────────────────────────────────────────────

def _font(name: str, size: int) -> ImageFont.FreeTypeFont:
    # Windows → Linux fallback map
    _fallbacks = {
        "impact.ttf":  ["impact.ttf", "Impact.ttf",
                         "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
                         "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"],
        "arialbd.ttf": ["arialbd.ttf", "Arial_Bold.ttf",
                         "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
                         "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"],
    }
    candidates = _fallbacks.get(name, [name])
    for candidate in candidates:
        for prefix in ["C:/Windows/Fonts/", "/usr/share/fonts/truetype/msttcorefonts/",
                        "/System/Library/Fonts/", ""]:
            path = candidate if candidate.startswith("/") else f"{prefix}{candidate}"
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
    question:           str,
    options:            dict,
    correct:            "str | None"         = None,
    category:           str                  = "MATH QUIZ",
    center_img:         "Image.Image | None" = None,
    timer_num:          "int | None"         = None,
    solid_bg:           bool                 = False,
    show_think_overlay: bool                 = False,
    thumbnail_banner:   "str | None"         = None,
    trap_answer:        "str | None"         = None,
    series_num:         "int | None"         = None,
    theme_idx:          "int | None"         = None,
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

    # ── Pick color theme (rotates every video based on challenge number)
    _ti = (theme_idx if theme_idx is not None else (series_num or 0)) % len(_CARD_THEMES)
    _t  = _CARD_THEMES[_ti]

    f_ban = _font("impact.ttf",   92)
    f_cat = _font("arialbd.ttf",  38)
    f_ltr = _font("arialbd.ttf",  52)
    f_opt = _font("arialbd.ttf",  46)
    f_tmr = _font("impact.ttf",  220)

    # ── QUIZ TIME / CHALLENGE banner
    banner_text = f"CHALLENGE #{series_num}" if series_num else "QUIZ TIME"
    d.rounded_rectangle([M, BANNER_Y1, W - M, BANNER_Y2], radius=20, fill=_t['banner'])
    _cc(d, banner_text, W // 2, (BANNER_Y1 + BANNER_Y2) // 2, f_ban, WHITE)

    # ── Category label
    cw  = int(d.textlength(category, font=f_cat)) + 44
    cx1 = (W - cw) // 2
    d.rounded_rectangle([cx1, LABEL_Y1, cx1 + cw, LABEL_Y2], radius=10, fill=_t['label'])
    _cc(d, category, W // 2, (LABEL_Y1 + LABEL_Y2) // 2, f_cat, WHITE, shadow=False)

    # ── Question text (adaptive font — shrink until it fits in ≤6 lines)
    for q_size, q_wrap in [(62, 28), (52, 32), (44, 38), (36, 46), (30, 54)]:
        f_q   = _font("arialbd.ttf", q_size)
        lines = textwrap.wrap(question, width=q_wrap)
        if len(lines) <= 6:
            break
    lines   = lines[:7]
    line_h  = q_size + 10
    q_block = len(lines) * line_h + 28
    d.rounded_rectangle(
        [M - 10, QUESTION_Y - 18, W - M + 10, QUESTION_Y + q_block],
        radius=16, fill=_t['qbg'],
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
        txt      = options.get(letter, "")
        y1       = OPT_START_Y + i * (OPT_H + OPT_GAP)
        y2       = y1 + OPT_H
        is_ok    = bool(correct and letter == correct)
        # Only highlight the trap answer in red — others stay neutral (less visual clutter)
        is_wrong = bool(correct and not is_ok and trap_answer and letter == trap_answer)
        d.rounded_rectangle([M, y1, W - M, y2],
                             radius=OPT_H // 2,
                             fill=OPT_OK if is_ok else (OPT_WRONG if is_wrong else OPT_WHITE))
        ccx, ccy = M + Rc + 14, (y1 + y2) // 2
        d.ellipse([ccx - Rc, ccy - Rc, ccx + Rc, ccy + Rc],
                  fill=(50, 160, 80, 255) if is_ok else ((160, 30, 30, 255) if is_wrong else _t['circle']))
        _cc(d, letter, ccx, ccy, f_ltr, WHITE, shadow=False)
        d.text((M + 2 * Rc + 34, (y1 + y2) // 2), txt,
               font=f_opt, fill=WHITE if is_wrong else DARK, anchor="lm")
        if is_ok:
            # Draw a clean checkmark using lines (avoids glyph rendering issues)
            cx0  = W - M - 58
            cy0  = ccy
            s    = 18   # half-size
            pts  = [(cx0 - s, cy0), (cx0 - s // 4, cy0 + s), (cx0 + s, cy0 - s)]
            d.line(pts, fill=(255, 255, 255, 255), width=7)

    # ── Progress bar (countdown cards only) — drains from full to empty
    if timer_num is not None:
        pb_y1, pb_y2 = 1460, 1490
        bar_colors   = {3: (72, 199, 100, 255), 2: (255, 180, 0, 255), 1: (220, 50, 50, 255)}
        bar_col      = bar_colors.get(timer_num, (72, 199, 100, 255))
        track_x1     = M
        track_x2     = W - M
        bar_w        = int((track_x2 - track_x1) * (timer_num / 3))
        d.rounded_rectangle([track_x1, pb_y1, track_x2, pb_y2], radius=15, fill=(50, 50, 50, 180))
        if bar_w > 30:
            d.rounded_rectangle([track_x1, pb_y1, track_x1 + bar_w, pb_y2], radius=15, fill=bar_col)

    # ── CTA strip on answer card (for muted viewers)
    if correct:
        f_cta   = _font("arialbd.ttf", 38)
        cta_layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        cd      = ImageDraw.Draw(cta_layer)
        if trap_answer and trap_answer != correct:
            # Trap reveal: "MOST PICK A — WRONG! 😱"
            cd.rounded_rectangle([M, 1615, W - M, 1745], radius=20, fill=_t['cta'])
            canvas  = Image.alpha_composite(canvas, cta_layer)
            d       = ImageDraw.Draw(canvas)
            f_trap1 = _font("impact.ttf", 46)
            f_trap2 = _font("arialbd.ttf", 34)
            _cc(d, f"MOST PEOPLE PICK {trap_answer} -- WRONG!",
                W // 2, 1660, f_trap1, (255, 230, 0, 255), shadow=True)
            _cc(d, "Subscribe so you never miss a trick!",
                W // 2, 1720, f_trap2, WHITE, shadow=False)
        else:
            cd.rounded_rectangle([M, 1630, W - M, 1730], radius=20, fill=(230, 160, 30, 235))
            canvas  = Image.alpha_composite(canvas, cta_layer)
            d       = ImageDraw.Draw(canvas)
            _cc(d, "SUBSCRIBE FOR DAILY CHALLENGES", W // 2, 1680, f_cta, (15, 15, 15, 255), shadow=False)

    # ── Comment bait strip on question card (drives comment engagement → algorithm boost)
    if not correct and not show_think_overlay and timer_num is None and not thumbnail_banner:
        f_cmt     = _font("arialbd.ttf", 40)
        cmt_layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        cd        = ImageDraw.Draw(cmt_layer)
        cd.rounded_rectangle([M, 1625, W - M, 1725], radius=20, fill=(10, 20, 90, 215))
        canvas = Image.alpha_composite(canvas, cmt_layer)
        d      = ImageDraw.Draw(canvas)
        _cc(d, ">> DROP YOUR ANSWER BELOW! <<", W // 2, 1675, f_cmt, (255, 220, 50, 255), shadow=True)

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
        d.text((W // 2,     TIMER_CY    ), t, font=f_tmr, fill=_t['timer'],     anchor="mm")

    # ── "THINK CAREFULLY!" overlay (pause card between question and countdown)
    if show_think_overlay:
        f_think = _font("impact.ttf", 115)
        f_sub   = _font("arialbd.ttf", 48)
        think_layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        tl      = ImageDraw.Draw(think_layer)
        tl.rounded_rectangle([M - 20, 1455, W - M + 20, 1895], radius=25, fill=_t['think'])
        canvas  = Image.alpha_composite(canvas, think_layer)
        d       = ImageDraw.Draw(canvas)
        _cc(d, "THINK",          W // 2, 1570, f_think, (255, 240,  0, 255), shadow=True)
        _cc(d, "CAREFULLY!",     W // 2, 1710, f_think, WHITE,               shadow=True)
        _cc(d, "Lock in your answer...", W // 2, 1840, f_sub, (255, 220, 100, 255), shadow=True)

    # ── Thumbnail banner (drawn on top of everything)
    if thumbnail_banner:
        f_tbn  = _font("impact.ttf", 74)
        tbn_layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        tb     = ImageDraw.Draw(tbn_layer)
        tb.rectangle([0, 1790, W, H], fill=(210, 30, 30, 245))
        canvas = Image.alpha_composite(canvas, tbn_layer)
        d      = ImageDraw.Draw(canvas)
        _cc(d, thumbnail_banner, W // 2, 1855, f_tbn, WHITE, shadow=True)

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


def _normalize_tts(text: str) -> str:
    """Expand symbols/numbers so TTS reads them as natural spoken words."""
    import re

    def _expand_currency(m):
        symbol = m.group(1)   # $, £, €
        num_str = m.group(2).replace(",", "")
        try:
            n = float(num_str)
        except ValueError:
            return m.group(0)
        if n >= 1_000_000_000:
            val = n / 1_000_000_000
            suffix = "billion"
        elif n >= 1_000_000:
            val = n / 1_000_000
            suffix = "million"
        elif n >= 1_000:
            val = n / 1_000
            suffix = "thousand"
        else:
            val = n
            suffix = ""
        val_str = f"{val:g}"  # strips trailing zeros
        currency_word = {"$": "dollars", "£": "pounds", "€": "euros"}.get(symbol, "dollars")
        parts = [val_str, suffix, currency_word] if suffix else [val_str, currency_word]
        return " ".join(p for p in parts if p)

    def _expand_plain_number(m):
        num_str = m.group(0).replace(",", "")
        try:
            n = float(num_str)
        except ValueError:
            return m.group(0)
        if n >= 1_000_000_000:
            return f"{n/1_000_000_000:g} billion"
        if n >= 1_000_000:
            return f"{n/1_000_000:g} million"
        if n >= 1_000:
            return f"{n/1_000:g} thousand"
        return num_str

    # Currency amounts: $10,000 / £1.5M / €500
    text = re.sub(r'([$£€])([0-9][0-9,]*(?:\.[0-9]+)?)', _expand_currency, text)
    # Percentages: 10% → 10 percent
    text = re.sub(r'([0-9]+(?:\.[0-9]+)?)%', r'\1 percent', text)
    # Plain numbers with commas: 1,000 → 1 thousand
    text = re.sub(r'\b[0-9]{1,3}(?:,[0-9]{3})+(?:\.[0-9]+)?\b', _expand_plain_number, text)
    return text


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
    a_text = (
        f"The answer is {correct}. {_normalize_tts(answer_text)}! "
        f"If you got it right, subscribe — you are smarter than 95 percent of people!"
    )

    q_path = os.path.join(output_dir, "_p_q.wav")
    a_path = os.path.join(output_dir, "_p_a.wav")
    await _tts(_normalize_tts(question), q_path, voice=voice)
    # Female voice on the reveal creates contrast and lifts engagement
    _reveal_voice = "af_bella" if voice.startswith("am_") else voice
    await _tts(a_text, a_path, voice=_reveal_voice)

    # Countdown: each word padded to exactly 1.0 s — matches the 1.0s video segments for t3/t2/t1
    sr      = sf.info(q_path).samplerate
    one_sec = int(1.0 * sr)
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
    # Add 0.5 s tail buffer so the female reveal voice is never hard-cut by ffmpeg
    a_dur = max(sf.info(a_path).duration, 2.0) + 0.5

    # Silence for the "THINK CAREFULLY" pause card — must match THINK_DUR (1.5 s)
    think_silence = np.zeros(int(1.5 * sr), dtype=np.float32)
    think_path    = os.path.join(output_dir, "_p_think.wav")
    sf.write(think_path, think_silence, sr)

    # Concat q + think_silence + cd + a into narration.wav
    narr_path  = os.path.join(output_dir, "narration.wav")
    concat_txt = os.path.join(output_dir, "_narr_concat.txt")
    with open(concat_txt, "w") as f:
        for p in [q_path, think_path, cd_path, a_path]:
            f.write(f"file '{os.path.abspath(p).replace(chr(92), chr(47))}'\n")
    _run_ffmpeg([
        get_ffmpeg_exe(), "-y",
        "-f", "concat", "-safe", "0", "-i", concat_txt,
        "-ar", str(sr), "-ac", "1",
        narr_path,
    ], "narr concat")
    return q_dur, a_dur


def _make_tick_track(output_path: str, q_dur: float, a_dur: float, think_dur: float = 2.0) -> str:
    """Generate a WAV with suspense sweep during think card + 3 tick beeps on countdown."""
    import wave
    sample_rate = 44100
    total_samp  = int((q_dur + think_dur + 3.0 + a_dur + 1.0) * sample_rate)
    data        = np.zeros(total_samp, dtype=np.float32)

    # Soft heartbeat during question card (two quiet low thuds encourage focus)
    q_end_samp = int(q_dur * sample_rate)
    for hb_off in [0.35, 0.70]:    # two beats spaced within the question window
        hb_s = int(hb_off * q_end_samp)
        hb_len = int(0.18 * sample_rate)
        t_hb = np.arange(hb_len, dtype=np.float32) / sample_rate
        hb   = np.sin(2 * np.pi * 65 * t_hb) * np.exp(-t_hb * 22) * 0.30
        end_hb = min(hb_s + hb_len, total_samp)
        data[hb_s:end_hb] += hb[:end_hb - hb_s]

    # Deep suspense pulses during the think card (two low "thud" beats)
    think_start_samp = int(q_dur * sample_rate)
    for beat_offset in [0.25, 0.85]:   # two thuds spread across the 2 s window
        bs = think_start_samp + int(beat_offset * sample_rate)
        # Low-freq thud: 80 Hz sine decaying quickly
        thud_len = int(0.35 * sample_rate)
        t_th = np.arange(thud_len, dtype=np.float32) / sample_rate
        thud = np.sin(2 * np.pi * 80 * t_th) * np.exp(-t_th * 18) * 0.75
        # Sub-harmonic body at 40 Hz adds weight
        thud += np.sin(2 * np.pi * 40 * t_th) * np.exp(-t_th * 10) * 0.40
        end_th = min(bs + thud_len, total_samp)
        data[bs:end_th] += thud[:end_th - bs]
    # Short rising tension tone at the end of think card (last 0.5 s)
    ris_start = think_start_samp + int((think_dur - 0.55) * sample_rate)
    ris_len   = int(0.55 * sample_rate)
    t_rs = np.arange(ris_len, dtype=np.float32) / sample_rate
    freq_rs   = 220.0 + 440.0 * (t_rs / 0.55)           # 220→660 Hz
    phase_rs  = np.cumsum(2 * np.pi * freq_rs / sample_rate)
    env_rs    = (t_rs / 0.55) * 0.45                     # ramps up
    fade_rs   = np.minimum(t_rs / 0.05, 1.0)             # 50 ms fade-in
    rise_sig  = np.sin(phase_rs) * env_rs * fade_rs
    end_rs = min(ris_start + ris_len, total_samp)
    data[ris_start:end_rs] += rise_sig[:end_rs - ris_start]

    # Countdown tick beeps (3-2-1)
    for i, freq in enumerate([700, 700, 1100]):
        tick_start = int((q_dur + think_dur + i) * sample_rate)
        tick_len   = int(0.12 * sample_rate)
        t          = np.arange(tick_len, dtype=np.float32) / sample_rate
        tick       = np.sin(2 * np.pi * freq * t) * np.exp(-t * 40) * 0.9
        end        = min(tick_start + tick_len, total_samp)
        data[tick_start:end] += tick[:end - tick_start]
    # Bright reveal ding at the exact moment the answer appears
    ding_start = int((q_dur + think_dur + 3.0) * sample_rate)
    ding_len   = int(0.35 * sample_rate)
    t_ding     = np.arange(ding_len, dtype=np.float32) / sample_rate
    ding = (
        np.sin(2 * np.pi * 880.0  * t_ding) * 0.65 +
        np.sin(2 * np.pi * 1320.0 * t_ding) * 0.35 +
        np.sin(2 * np.pi * 1760.0 * t_ding) * 0.18
    ) * np.exp(-t_ding * 12)
    end_d = min(ding_start + ding_len, total_samp)
    data[ding_start:end_d] += ding[:end_d - ding_start]
    data = np.clip(data, -1, 1)
    with wave.open(output_path, "w") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes((data * 32767).astype(np.int16).tobytes())
    return output_path


def _generate_suspense_music(output_path: str, duration: float = 35.0) -> str:
    """Auto-generate a looping minor-key suspense background track (used when music/ is empty)."""
    import wave
    sr    = 44100
    total = int(duration * sr)
    data  = np.zeros(total, dtype=np.float32)
    t     = np.arange(total, dtype=np.float32) / sr
    # Sub-bass drone (A1 + E2)
    data += np.sin(2 * np.pi * 55.0  * t) * 0.14
    data += np.sin(2 * np.pi * 82.5  * t) * 0.09
    # Pulsing A-minor chord stabs at 120 BPM (every 0.5 s)
    beat_s = 0.5
    for beat in range(int(duration / beat_s)):
        bs  = int(beat * beat_s * sr)
        bl  = min(int(0.42 * sr), total - bs)
        if bl <= 0:
            break
        t_b = np.arange(bl, dtype=np.float32) / sr
        env = np.exp(-t_b * 7.0)
        vel = 0.10 if beat % 2 == 0 else 0.065
        chord = (
            np.sin(2 * np.pi * 220.00 * t_b) * vel +
            np.sin(2 * np.pi * 261.63 * t_b) * vel * 0.75 +
            np.sin(2 * np.pi * 329.63 * t_b) * vel * 0.60
        ) * env
        data[bs:bs + bl] += chord
    # Rising tension sweep every 8 s
    for sweep_s in range(0, int(duration) - 2, 8):
        ss   = sweep_s * sr
        sl   = min(int(2.0 * sr), total - ss)
        if sl <= 0:
            break
        t_sw = np.arange(sl, dtype=np.float32) / sr
        freq = 110.0 + 330.0 * (t_sw / 2.0)
        ph   = np.cumsum(2 * np.pi * freq / sr)
        env  = (t_sw / 2.0) * 0.18
        data[ss:ss + sl] += np.sin(ph) * env
    data = np.clip(data, -1, 1)
    with wave.open(output_path, "w") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes((data * 32767).astype(np.int16).tobytes())
    print(f"[music] Auto-generated suspense track: {os.path.basename(output_path)}")
    return output_path


# ── ffmpeg assembly ────────────────────────────────────────────────────────────

def _run_ffmpeg(cmd: list, label: str):
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        raise RuntimeError(f"[quiz] {label} failed:\n{res.stderr[-1200:]}")


def _assemble_pexels_bg(ffmpeg, bg_video, fpaths, audio, music,
                        q_dur, a_dur, total, final, output_dir, tick=None, think_dur=2.0):
    """Overlay RGBA card PNGs frame-by-frame on the Pexels background video."""
    segments = [
        (fpaths["q"],  q_dur),
        (fpaths["th"], think_dur),
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


def _assemble_static(ffmpeg, fpaths, audio, tick, music, q_dur, a_dur, total, final, think_dur=2.0):
    """Fallback: static swirly card images, no video background."""
    img_inputs = [
        "-loop", "1", "-t", str(q_dur),    "-i", fpaths["q"],
        "-loop", "1", "-t", str(think_dur),"-i", fpaths["th"],
        "-loop", "1", "-t", "1.00",         "-i", fpaths["t3"],
        "-loop", "1", "-t", "1.00",         "-i", fpaths["t2"],
        "-loop", "1", "-t", "1.00",         "-i", fpaths["t1"],
        "-loop", "1", "-t", str(a_dur),     "-i", fpaths["a"],
    ]
    vf  = "[0:v][1:v][2:v][3:v][4:v][5:v]concat=n=6:v=1:a=0[cv]"
    enc = ["-c:v", "libx264", "-preset", "fast", "-crf", "23",
           "-c:a", "aac", "-b:a", "128k",
           "-r", "30", "-pix_fmt", "yuv420p", "-s", f"{W}x{H}"]
    if tick and music:
        # images 0-5, audio=6, music=7, tick=8
        af  = (f"{vf};"
               f"[7:a]volume=0.22,atrim=duration={total:.2f}[m];"
               f"[6:a][8:a]amix=inputs=2:duration=first[narr_tick];"
               f"[narr_tick][m]amix=inputs=2:duration=first:dropout_transition=2[a]")
        cmd = ([ffmpeg, "-y"] + img_inputs
               + ["-i", audio, "-i", music, "-i", tick]
               + ["-filter_complex", af, "-map", "[cv]", "-map", "[a]",
                  "-t", str(total)] + enc + [final])
    elif tick:
        # images 0-5, audio=6, tick=7
        af  = f"{vf};[6:a][7:a]amix=inputs=2:duration=first[a]"
        cmd = ([ffmpeg, "-y"] + img_inputs
               + ["-i", audio, "-i", tick]
               + ["-filter_complex", af, "-map", "[cv]", "-map", "[a]",
                  "-t", str(total)] + enc + [final])
    elif music:
        # images 0-5, audio=6, music=7
        af  = (f"{vf};"
               f"[7:a]volume=0.22,atrim=duration={total:.2f}[m];"
               f"[6:a][m]amix=inputs=2:duration=first:dropout_transition=2[a]")
        cmd = ([ffmpeg, "-y"] + img_inputs
               + ["-i", audio, "-i", music]
               + ["-filter_complex", af, "-map", "[cv]", "-map", "[a]",
                  "-t", str(total)] + enc + [final])
    else:
        # images 0-5, audio=6
        cmd = ([ffmpeg, "-y"] + img_inputs
               + ["-i", audio]
               + ["-filter_complex", vf, "-map", "[cv]", "-map", "6:a",
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

    ffmpeg     = get_ffmpeg_exe()
    os.makedirs(output_dir, exist_ok=True)
    series_num = _get_next_challenge_num()

    question    = quiz_data["question"]
    options     = quiz_data["options"]
    correct     = quiz_data["correct_answer"]
    exp         = quiz_data.get("explanation", "")
    category    = quiz_data.get("category", "MATH QUIZ")
    iq          = quiz_data.get("image_query", "mathematics classroom chalkboard")
    trap_answer = quiz_data.get("trap_answer", "")

    print(f"[quiz] Question: {question}")

    # 1. Center photo (Pexels)
    center_img = get_center_image(iq, pexels_key) if pexels_key else None

    # 2. Background video (Pexels) — math-themed fallback queries
    _MATH_BG_QUERIES = [
        "chalkboard classroom dark",
        "abstract dark blue numbers",
        "mathematics chalk equations",
        "dark bokeh abstract studio",
        "glowing neon digits",
        "blackboard chalk writing",
        "dark gradient geometric",
    ]
    bg_video  = os.path.join(output_dir, "bg_video.mp4")
    bg_q      = quiz_data.get("bg_query") or random.choice(_MATH_BG_QUERIES)
    _bg_ok, _bg_id = (False, None)
    if pexels_key:
        _bg_ok, _bg_id = _download_pexels_bg_video(bg_q, pexels_key, bg_video, used_video_ids)
    has_bg = _bg_ok

    # 3. Render card frames
    THINK_DUR = 1.5
    solid = not has_bg
    print(f"[quiz] Rendering cards (bg={'pexels_video' if has_bg else 'swirly_fallback'})...")
    keys = [
        ("q",  dict(question=question, options=options, category=category, center_img=center_img, solid_bg=solid, series_num=series_num)),
        ("th", dict(question=question, options=options, category=category, center_img=center_img, show_think_overlay=True, solid_bg=solid, series_num=series_num)),
        ("t3", dict(question=question, options=options, category=category, center_img=center_img, timer_num=3, solid_bg=solid, series_num=series_num)),
        ("t2", dict(question=question, options=options, category=category, center_img=center_img, timer_num=2, solid_bg=solid, series_num=series_num)),
        ("t1", dict(question=question, options=options, category=category, center_img=center_img, timer_num=1, solid_bg=solid, series_num=series_num)),
        ("a",  dict(question=question, options=options, correct=correct,   category=category, center_img=center_img, solid_bg=solid, trap_answer=trap_answer or None, series_num=series_num)),
    ]
    fpaths = {}
    for key, kwargs in keys:
        img = draw_quiz_card(**kwargs)
        p   = os.path.join(output_dir, f"card_{key}.png")
        img.save(p)
        fpaths[key] = p
    _THUMB_BANNERS = [
        "90% GET THIS WRONG",
        "MOST ADULTS FAIL THIS",
        "IQ TEST: 5 SECONDS",
        "ONLY 1% GET THIS RIGHT",
        "THIS BREAKS MOST BRAINS",
        "CAN YOU BEAT THE ODDS?",
        "HARVARD STUDENTS FAILED THIS",
        "EVEN TEACHERS GET THIS WRONG",
        "COMMENT IF YOU GOT IT RIGHT",
        "SOLVE THIS OR UNSUBSCRIBE",
        "GENIUS LEVEL CHALLENGE",
        "ARE YOU SMARTER THAN A 5TH GRADER?",
    ]
    draw_quiz_card(question=question, options=options, category=category,
                   center_img=center_img, solid_bg=solid,
                   thumbnail_banner=random.choice(_THUMB_BANNERS),
                   series_num=series_num).save(
        os.path.join(output_dir, "thumbnail.png"))

    # 4. TTS narration — frame-synced (question + think pause + countdown + answer)
    audio = os.path.join(output_dir, "narration.wav")
    print(f"[quiz] TTS: {question[:60]}...")
    q_dur, a_dur = await _build_synced_narration(
        question, options, correct, output_dir, voice
    )

    # 5. Timing (exact — derived from TTS part durations + think card)
    total = round(q_dur + THINK_DUR + 3.0 + a_dur, 2)
    print(f"[quiz] Audio={total:.1f}s  question={q_dur:.2f}s  think={THINK_DUR}s  3-2-1  answer={a_dur:.2f}s")

    # 6. Background music — use existing tracks or auto-generate a suspense track
    music     = None
    music_dir = os.path.join(os.path.dirname(__file__), "music")
    if os.path.isdir(music_dir):
        tracks = [os.path.join(music_dir, f) for f in os.listdir(music_dir)
                  if f.lower().endswith((".mp3", ".wav"))]
        if tracks:
            music = random.choice(tracks)
    if not music:
        gen_music = os.path.join(output_dir, "_suspense_bg.wav")
        music = _generate_suspense_music(gen_music, duration=total + 5.0)

    # 7. Tick track (ticks offset by think_dur)
    tick = _make_tick_track(os.path.join(output_dir, "tick.wav"), q_dur, a_dur, think_dur=THINK_DUR)

    # 8. Assemble
    final = os.path.join(output_dir, "final_short.mp4")
    print("[quiz] Assembling video...")
    if has_bg:
        _assemble_pexels_bg(ffmpeg, bg_video, fpaths, audio, music,
                            q_dur, a_dur, total, final, output_dir, tick, think_dur=THINK_DUR)
    else:
        _assemble_static(ffmpeg, fpaths, audio, tick, music, q_dur, a_dur, total, final, think_dur=THINK_DUR)

    # Loudness normalize to -14 LUFS (YouTube / TikTok standard)
    norm_tmp = final.replace(".mp4", "_loudnorm.mp4")
    try:
        _run_ffmpeg([
            ffmpeg, "-y", "-i", final,
            "-af", "loudnorm=I=-14:TP=-1.5:LRA=11",
            "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
            norm_tmp,
        ], "loudnorm")
        os.replace(norm_tmp, final)
        print("[quiz] Loudness normalized to -14 LUFS ✓")
    except Exception as e:
        print(f"[quiz] Loudnorm skipped: {e}")
        if os.path.exists(norm_tmp):
            os.remove(norm_tmp)
    print(f"[quiz] Done → {final}")
    return final, _bg_id