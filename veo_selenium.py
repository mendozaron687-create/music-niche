"""
Veo 3 video generation via Selenium on gemini.google.com.

WORKFLOW:
  1. Script → Gemini generates JSON scene breakdown (one scene per ~8s clip needed)
  2. Each scene → crafted Veo 3 prompt (subject, camera, lighting, mood, color grade)
  3. Selenium submits each prompt to gemini.google.com and downloads the clip
  4. ffmpeg auto-edit: crossfade transitions between clips → single background video

REQUIREMENTS:
  Either:
    A) Launch Chrome first with: chrome.exe --remote-debugging-port=9222
       (sign into gemini.google.com, keep Chrome open, Selenium attaches)
    B) Close ALL Chrome windows — Selenium uses your saved profile (already signed in)

INSTALL:
  pip install undetected-chromedriver
"""

import os
import re
import json
import glob
import time
import math
import shutil
import subprocess

# Default Chrome profile path on Windows
_CHROME_PROFILE = os.path.join(
    os.environ.get("LOCALAPPDATA", os.path.expanduser("~")),
    "Google", "Chrome", "User Data"
)

# ── Trending niche visual identities ─────────────────────────────────────────
_NICHE_STYLE = {
    "ai_tools": {
        "setting":  "sleek dark server room with glowing holographic interfaces",
        "camera":   "slow push-in with subtle drone tilt-up",
        "lighting": "cool blue and purple neon backlighting, volumetric glow",
        "mood":     "futuristic, high-tech, awe-inspiring",
        "color":    "teal and neon purple color grade, high contrast",
    },
    "finance": {
        "setting":  "modern glass skyscrapers at golden hour, Wall Street aesthetic",
        "camera":   "smooth lateral tracking shot, shallow depth of field",
        "lighting": "warm golden hour sunlight through glass, lens flares",
        "mood":     "ambitious, professional, aspirational",
        "color":    "warm teal-and-orange Hollywood color grade",
    },
    "health_wellness": {
        "setting":  "misty sunrise mountain ridge, serene nature landscape",
        "camera":   "slow aerial drone glide, macro details of nature",
        "lighting": "soft golden sunrise rays, natural diffused glow",
        "mood":     "peaceful, energizing, transformative",
        "color":    "warm earthy tones, desaturated greens with golden highlights",
    },
    "technology": {
        "setting":  "cutting-edge data center, glowing circuit boards, abstract digital",
        "camera":   "rotating orbit shot, extreme close-up macro on tech details",
        "lighting": "cool blue LED strips, dramatic shadows, electric blue glow",
        "mood":     "innovative, powerful, mind-blowing",
        "color":    "cool cyan-tinted, high contrast, cyberpunk color grade",
    },
    "business": {
        "setting":  "modern open-plan office, glass boardroom, city skyline view",
        "camera":   "wide establishing shot to slow close-up push",
        "lighting": "clean professional natural light, dramatic window shadows",
        "mood":     "confident, elite, success-driven",
        "color":    "clean desaturated with warm highlights, corporate chic",
    },
    "motivation": {
        "setting":  "dramatic mountain summit, open highway at dawn, vast sky",
        "camera":   "cinematic drone ascent revealing epic landscape",
        "lighting": "golden hour magic light, dramatic god rays through clouds",
        "mood":     "epic, triumphant, life-changing",
        "color":    "warm golden-orange grade, crushed blacks, high saturation",
    },
    "productivity": {
        "setting":  "minimal clean workspace, morning coffee steam, crisp notebook",
        "camera":   "close-up table-level shot, smooth rack focus pull",
        "lighting": "soft diffused morning window light, clean shadows",
        "mood":     "focused, calm, efficient",
        "color":    "warm neutral tones, slightly desaturated, clean aesthetic",
    },
    "relationships": {
        "setting":  "golden hour park, ocean cliff sunset, cozy cafe window",
        "camera":   "slow orbit around subject, dreamy rack focus",
        "lighting": "warm bokeh golden hour, lens flare, soft glow",
        "mood":     "emotional, heartfelt, relatable",
        "color":    "warm orange and amber tones, soft film grain, cinematic",
    },
}

_DEFAULT_STYLE = {
    "setting":  "cinematic professional B-roll, dynamic urban environment",
    "camera":   "smooth gimbal shot with subtle push-in",
    "lighting": "dramatic cinematic lighting, golden hour tones",
    "mood":     "inspiring, engaging, high-energy",
    "color":    "teal and orange Hollywood color grade",
}

# Every prompt ends with these technical Veo 3 parameters
_TRENDING_SUFFIX = (
    "Trending TikTok/Reels cinematic aesthetic. "
    "Hyper-realistic photographic quality, 4K HDR. "
    "Smooth professional camera movement, no shake. "
    "No text overlays, no captions, no watermarks, no logos. "
    "No people talking or mouths moving. "
    "9:16 vertical portrait orientation. "
    "8 seconds duration."
)


# ── Scene generation via Gemini (JSON) ───────────────────────────────────────

def _seconds_from_script(script: str) -> float:
    """Estimate TTS audio duration (~155 wpm average)."""
    return (len(script.split()) / 155) * 60


def _num_clips_needed(audio_seconds: float, clip_duration: int = 8) -> int:
    """How many Veo clips to request to cover the full audio length."""
    return max(2, math.ceil(audio_seconds / clip_duration))


def _craft_veo_prompt(scene: dict) -> str:
    """Convert a structured scene JSON dict into the best Veo 3 text prompt."""
    subject  = scene.get("subject", "cinematic B-roll footage")
    action   = scene.get("action", "")
    setting  = scene.get("setting", "")
    camera   = scene.get("camera", "smooth gimbal movement")
    lighting = scene.get("lighting", "cinematic lighting")
    mood     = scene.get("mood", "engaging")
    color    = scene.get("color", "teal and orange color grade")

    parts = [subject]
    if action:
        parts.append(action)
    if setting:
        parts.append(f"Location: {setting}")
    parts.append(f"Camera: {camera}")
    parts.append(f"Lighting: {lighting}")
    parts.append(f"Mood: {mood}")
    parts.append(f"Color grade: {color}")
    parts.append(_TRENDING_SUFFIX)

    return ". ".join(parts)


def _generate_scenes_via_selenium(script: str, niche: str, num_clips: int, style: dict) -> list:
    """Generate scene JSON via Gemini web (Selenium) when API quota is exhausted."""
    from dotenv import load_dotenv
    load_dotenv()
    cookies_path = os.getenv("GEMINI_COOKIES", "cookies.json")
    if not os.path.exists(cookies_path):
        return []

    gemini_prompt = f"""You are a viral video director for YouTube Shorts and TikTok.

Voiceover script to visualize:
"{script}"

Niche: {niche}

Break this script into EXACTLY {num_clips} sequential visual scenes for AI video generation.

STRICT OUTPUT RULES:
- Output ONLY a valid JSON array. No explanation, no markdown, no code fences.
- Start with [ and end with ]

Each object must have these fields:
"subject", "action", "setting", "camera", "lighting", "mood", "color"

Rules for scenes:
- NO people talking, no mouths moving, no faces in close-up
- NO text, logos, or overlays visible
- Each scene visually DISTINCT from others
- Hyper-specific cinematic descriptions"""

    try:
        text = generate_text_via_selenium(gemini_prompt, cookies_path)
        if not text:
            return []
        raw = re.sub(r"^```(?:json)?\s*", "", text.strip(), flags=re.MULTILINE)
        raw = re.sub(r"\s*```\s*$", "", raw, flags=re.MULTILINE)
        # Find the JSON array in the response
        match = re.search(r"\[.*\]", raw, re.DOTALL)
        if not match:
            return []
        scenes = json.loads(match.group())
        if isinstance(scenes, list) and scenes:
            while len(scenes) < num_clips:
                scenes.append(scenes[-1].copy())
            scenes = scenes[:num_clips]
            print(f"[veo] Selenium scene generation: {len(scenes)} scenes")
            return scenes
    except Exception as e:
        print(f"[veo] Selenium scene gen failed: {e}")
    return []


def _generate_scenes_via_gemini(script: str, niche: str, num_clips: int) -> list:
    """
    Ask Gemini to break the script into per-scene Veo prompt data (JSON).
    Returns list of scene dicts. Falls back to niche templates on any failure.
    """
    from dotenv import load_dotenv
    load_dotenv()

    style = _NICHE_STYLE.get(niche, _DEFAULT_STYLE)

    try:
        from google import genai
        api_key = os.getenv("GEMINI_API_KEY", "")
        if not api_key:
            raise ValueError("No GEMINI_API_KEY")

        client = genai.Client(api_key=api_key)
        gemini_prompt = f"""You are a viral video director for YouTube Shorts and TikTok.

Voiceover script to visualize:
"{script}"

Niche: {niche}
Default visual style reference: {json.dumps(style, indent=2)}

Your task: Break this script into EXACTLY {num_clips} sequential visual scenes.
Each scene visually illustrates the corresponding moment of the voiceover.
Make the scenes MATCH the script content — if the script mentions money, show money visuals, etc.

Return ONLY a valid JSON array with EXACTLY {num_clips} objects. Each object must have ALL these fields:
- "subject": The main visual element (1-2 sentences, hyper-specific and cinematic)
- "action": What is happening / moving in the shot
- "setting": The environment or location
- "camera": Exact camera movement and framing technique
- "lighting": Specific lighting description
- "mood": The emotional tone
- "color": Color grading style

RULES:
- NO people talking, no mouths moving, no faces in close-up
- NO text, logos, UI, or overlays visible in the frame
- Each scene must be VISUALLY DISTINCT from the others
- Use TRENDING cinematic aesthetics (hyper-realistic, smooth, professional)
- Be HYPER SPECIFIC — Veo performs better with detailed prompts
- Scenes must build narrative tension matching the script

Return ONLY the JSON array. No explanation, no markdown fences, just the JSON."""

        response = client.models.generate_content(
            model="gemini-2.0-flash",
            contents=gemini_prompt
        )
        raw = response.text.strip()
        # Strip markdown code fences if present
        raw = re.sub(r"^```(?:json)?\s*", "", raw, flags=re.MULTILINE)
        raw = re.sub(r"\s*```\s*$", "", raw, flags=re.MULTILINE)
        scenes = json.loads(raw.strip())

        if isinstance(scenes, list) and scenes:
            while len(scenes) < num_clips:
                scenes.append(scenes[-1].copy())
            scenes = scenes[:num_clips]
            print(f"[veo] Gemini generated {num_clips} scene prompts:")
            for i, s in enumerate(scenes):
                print(f"  [{i+1}] {s.get('subject', '')[:80]}")
            return scenes

    except Exception as e:
        err = str(e)
        if "RESOURCE_EXHAUSTED" in err or "limit: 0" in err or "429" in err:
            print(f"[veo] Gemini API quota hit — trying scene gen via Selenium web...")
            scenes = _generate_scenes_via_selenium(script, niche, num_clips, style)
            if scenes:
                return scenes
        else:
            print(f"[veo] Gemini scene generation failed ({e}) — using niche templates")

    # Fallback templates
    base = _NICHE_STYLE.get(niche, _DEFAULT_STYLE)
    subjects = [
        f"Dramatic cinematic opening establishing the world of {niche.replace('_', ' ')}",
        f"Close-up detail shot revealing the key insight about {niche.replace('_', ' ')}",
        f"Wide inspiring shot showing transformation and success in {niche.replace('_', ' ')}",
        f"Dynamic action shot of the key concept in {niche.replace('_', ' ')}",
        f"Epic closing shot with emotional resonance related to {niche.replace('_', ' ')}",
        f"Abstract cinematic metaphor for growth and progress in {niche.replace('_', ' ')}",
    ]
    scenes = []
    for i in range(num_clips):
        s = base.copy()
        s["subject"] = subjects[i % len(subjects)]
        s["action"] = "smooth slow motion camera movement revealing the scene"
        scenes.append(s)
    return scenes


# ── Cookie helpers ────────────────────────────────────────────────────────────

def _load_cookies(driver, cookies_path: str):
    """Load exported browser cookies into the Selenium driver."""
    if not cookies_path or not os.path.exists(cookies_path):
        return
    try:
        with open(cookies_path, "r", encoding="utf-8") as f:
            cookies = json.load(f)
        loaded = 0
        for c in cookies:
            # Normalize expirationDate → expiry (Selenium expects int)
            clean = {k: v for k, v in c.items()
                     if k in ("name", "value", "domain", "path", "secure", "httpOnly")}
            if "expirationDate" in c:
                clean["expiry"] = int(c["expirationDate"])
            elif "expiry" in c:
                clean["expiry"] = int(c["expiry"])
            # Must be on the right domain before adding cookies
            try:
                driver.add_cookie(clean)
                loaded += 1
            except Exception:
                pass
        print(f"[veo] Loaded {loaded}/{len(cookies)} cookies from {cookies_path}")
    except Exception as e:
        print(f"[veo] Cookie load warning: {e}")


def _inject_cookies_and_navigate(driver, cookies_path: str, url: str):
    """
    Proper cookie injection: go to google.com first (correct domain),
    load cookies, then navigate to the target URL.
    """
    driver.get("https://google.com")
    time.sleep(2)
    _load_cookies(driver, cookies_path)
    time.sleep(0.5)
    driver.get(url)
    time.sleep(4)


def _extract_gemini_response(driver, timeout: int = 90) -> str:
    """Wait for Gemini to finish generating and return the response text."""
    from selenium.webdriver.common.by import By

    deadline = time.time() + timeout

    # Wait for a response to appear (any of several selectors Gemini uses)
    response_selectors = [
        "message-content",
        ".response-content",
        "model-response",
        "[data-message-author-role='model']",
        ".markdown",
    ]

    # First wait for the stop/loading indicator to appear then disappear
    stop_selectors = [
        'button[aria-label*="Stop"]',
        'button[aria-label*="stop"]',
        '[data-test-id*="stop"]',
    ]
    # Give it a moment to start generating
    time.sleep(3)

    # Poll until response is fully streamed (stop button gone + text present)
    while time.time() < deadline:
        time.sleep(2)
        stop_visible = False
        for sel in stop_selectors:
            if driver.find_elements(By.CSS_SELECTOR, sel):
                stop_visible = True
                break
        if not stop_visible:
            # Generation done — try to grab text
            for sel in response_selectors:
                elems = driver.find_elements(By.CSS_SELECTOR, sel)
                if elems:
                    # Take the last element (most recent response)
                    text = elems[-1].text.strip()
                    if len(text) > 20:
                        return text
            # One more second then return whatever we have
            time.sleep(1)
            for sel in response_selectors:
                elems = driver.find_elements(By.CSS_SELECTOR, sel)
                if elems:
                    text = elems[-1].text.strip()
                    if text:
                        return text
            break

    # Final fallback: grab all visible text from the page body
    try:
        body = driver.find_element(By.TAG_NAME, "body").text
        # Trim to a reasonable chunk
        return body[-3000:].strip()
    except Exception:
        return ""


def _strip_gemini_preamble(text: str) -> str:
    """
    Remove Gemini's conversational wrapper and return only the script body.
    Looks for the first line that reads like actual spoken content (not meta-commentary).
    """
    import re
    if not text:
        return text

    lines = text.splitlines()
    skip_patterns = re.compile(
        r"^(here'?s?|okay|sure|of course|absolutely|great|certainly|"
        r"this is|below is|i'?ve|i have|as requested|based on|"
        r"script:|voiceover:|draft:|here you go|let me|note:|"
        r"\*\*script\*\*|\*\*voiceover\*\*|#)",
        re.IGNORECASE
    )
    # Find first non-empty line that doesn't look like preamble
    start_idx = 0
    for i, line in enumerate(lines):
        stripped = line.strip()
        if not stripped:
            continue
        if skip_patterns.match(stripped):
            start_idx = i + 1
        else:
            start_idx = i
            break

    result = "\n".join(lines[start_idx:]).strip()

    # Also strip any trailing "follow for more" duplication or Gemini sign-off lines
    end_patterns = re.compile(
        r"\n(---+|\*\*\*+|note:|want me to|let me know|hope this|"
        r"feel free|i hope|this script).*$",
        re.IGNORECASE | re.DOTALL
    )
    result = end_patterns.sub("", result).strip()

    return result if result else text


def generate_text_via_selenium(prompt: str,
                                cookies_path: str = None,
                                chrome_profile: str = None) -> str:
    """
    Submit a text prompt to Gemini web UI via Selenium and return the response.
    Uses your Pro account (via cookies/profile) — bypasses free-tier API limits.
    Always uses a fresh temp profile to avoid locking conflicts with running Chrome.
    """
    from dotenv import load_dotenv
    import tempfile
    load_dotenv()

    cookies_path = cookies_path or os.getenv("GEMINI_COOKIES", "cookies.json")

    dl_tmp = tempfile.mkdtemp()
    # Always use a fresh temp dir as profile to avoid lock conflicts
    tmp_profile = tempfile.mkdtemp(prefix="uc_profile_")
    driver = None
    we_own = False

    try:
        # Always use a fresh temp profile — we have cookies for auth.
        # Attaching to port 9222 causes session loss when user's Chrome closes.
        import undetected_chromedriver as uc
        ver = _chrome_major_version()
        uc_kwargs = {"version_main": ver} if ver else {}
        opts = uc.ChromeOptions()
        opts.add_argument(f"--user-data-dir={tmp_profile}")
        opts.add_argument("--no-first-run")
        opts.add_argument("--no-default-browser-check")
        driver = uc.Chrome(options=opts, **uc_kwargs)
        we_own = True
        print(f"[veo-text] Launched fresh Chrome for script generation (ver={ver})")

        cookies_path = cookies_path or os.getenv("GEMINI_COOKIES", "cookies.json")
        has_cookies = bool(cookies_path and os.path.exists(cookies_path))

        # Always inject cookies via google.com to ensure Pro account is used
        if has_cookies:
            print(f"[veo-text] Injecting cookies from {cookies_path}...")
            _inject_cookies_and_navigate(driver, cookies_path, "https://gemini.google.com")
        else:
            driver.get("https://gemini.google.com")
            time.sleep(4)

        if "accounts.google.com" in driver.current_url:
            raise RuntimeError(
                "Not signed in after cookie injection — cookies may be expired. "
                "Re-export from Cookie-Editor on gemini.google.com and save as cookies.json"
            )

        _type_prompt(driver, prompt)
        response = _extract_gemini_response(driver)
        return _strip_gemini_preamble(response)
    finally:
        if driver:
            driver.__class__.__del__ = lambda self: None  # suppress WinError 6 on detached session
        if driver and we_own:
            try:
                driver.quit()
            except Exception:
                pass
        shutil.rmtree(dl_tmp, ignore_errors=True)
        shutil.rmtree(tmp_profile, ignore_errors=True)


# ── Selenium Chrome helpers ───────────────────────────────────────────────────

def _chrome_major_version() -> int:
    """Read installed Chrome major version from Windows registry."""
    try:
        import winreg
        for hive in [winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE]:
            for key_path in [
                r"SOFTWARE\Google\Chrome\BLBeacon",
                r"SOFTWARE\Wow6432Node\Google\Chrome\BLBeacon",
            ]:
                try:
                    key = winreg.OpenKey(hive, key_path)
                    version, _ = winreg.QueryValueEx(key, "version")
                    return int(version.split(".")[0])
                except Exception:
                    pass
    except Exception:
        pass
    return None


def _select_veo_model(driver) -> bool:
    """
    Activate Veo video generation by clicking the 'Create video' button
    on the Gemini main page. Returns True if found and clicked.
    """
    from selenium.webdriver.common.by import By

    time.sleep(2)

    # Primary: aria-label contains "Create video"
    for xpath in [
        '//button[contains(@aria-label, "Create video")]',
        '//button[contains(@aria-label, "create video")]',
        '//*[contains(@jslog, "intent_chip_video")]',
        '//button[contains(@class, "card") and contains(., "Create video")]',
        '//button[contains(@class, "card") and contains(., "create video")]',
    ]:
        elems = driver.find_elements(By.XPATH, xpath)
        if elems:
            try:
                driver.execute_script("arguments[0].click();", elems[0])
                # Wait for page transition — Veo chat page takes longer than a regular chat
                time.sleep(5)
                url_after = driver.current_url
                print(f"[veo] Clicked 'Create video' button ✓  (url={url_after})")
                return True
            except Exception:
                continue

    # Fallback: any card button whose text is exactly "Create video"
    for btn in driver.find_elements(By.CSS_SELECTOR, "button.card, button.card-zero-state"):
        if "create video" in (btn.text or "").lower():
            try:
                driver.execute_script("arguments[0].click();", btn)
                time.sleep(5)
                url_after = driver.current_url
                print(f"[veo] Clicked 'Create video' card ✓  (url={url_after})")
                return True
            except Exception:
                continue

    print("[veo] 'Create video' button not found — proceeding without model switch")
    print(f"[veo] Current URL: {driver.current_url}")
    return False


def _make_driver_fresh(download_dir: str, profile_dir: str):
    """Launch a fresh Chrome process we own — never attaches to port 9222."""
    import undetected_chromedriver as uc
    ver = _chrome_major_version()
    uc_kwargs = {"version_main": ver} if ver else {}
    opts = uc.ChromeOptions()
    opts.add_argument(f"--user-data-dir={profile_dir}")
    opts.add_argument("--no-first-run")
    opts.add_argument("--no-default-browser-check")
    # Stability flags — prevent Chrome renderer crashes in automation
    opts.add_argument("--disable-gpu-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--disable-background-timer-throttling")
    opts.add_argument("--disable-backgrounding-occluded-windows")
    opts.add_argument("--disable-renderer-backgrounding")
    opts.add_argument("--no-sandbox")
    opts.add_experimental_option("prefs", {
        "download.default_directory": download_dir,
        "download.prompt_for_download": False,
        "download.directory_upgrade": True,
        "safebrowsing.enabled": True,
    })
    driver = uc.Chrome(options=opts, **uc_kwargs)
    print(f"[veo] Launched fresh Chrome for Veo generation (ver={ver})")
    return driver


def _make_driver(download_dir: str, chrome_profile: str):
    import undetected_chromedriver as uc

    ver = _chrome_major_version()
    uc_kwargs = {"version_main": ver} if ver else {}

    # Try attaching to existing Chrome debug session (recommended approach)
    try:
        opts = uc.ChromeOptions()
        opts.debugger_address = "127.0.0.1:9222"
        driver = uc.Chrome(options=opts, **uc_kwargs)
        driver.execute_cdp_cmd("Browser.setDownloadBehavior", {
            "behavior": "allow",
            "downloadPath": download_dir,
        })
        print(f"[veo] Attached to running Chrome (port 9222, ver={ver})")
        return driver, False
    except Exception:
        pass

    # Launch using user's existing saved profile
    opts = uc.ChromeOptions()
    opts.add_argument(f"--user-data-dir={chrome_profile}")
    opts.add_argument("--profile-directory=Default")
    opts.add_argument("--no-first-run")
    opts.add_argument("--no-default-browser-check")
    opts.add_experimental_option("prefs", {
        "download.default_directory": download_dir,
        "download.prompt_for_download": False,
        "download.directory_upgrade": True,
        "safebrowsing.enabled": True,
    })
    driver = uc.Chrome(options=opts, **uc_kwargs)
    print(f"[veo] Launched Chrome with saved profile (ver={ver})")
    return driver, True


def _type_prompt(driver, text: str):
    import subprocess
    from selenium.webdriver.common.by import By
    from selenium.webdriver.common.keys import Keys
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC

    # Copy text to clipboard via PowerShell (avoids send_keys truncation)
    subprocess.run(
        ["powershell", "-command", "Set-Clipboard -Value $input"],
        input=text, text=True, check=True, capture_output=True
    )

    wait = WebDriverWait(driver, 25)
    selectors = [
        'div.ql-editor[contenteditable="true"]',
        'div[contenteditable="true"][data-placeholder]',
        'rich-textarea div[contenteditable="true"]',
        'div[contenteditable="true"]',
        'textarea',
    ]

    # "Create video" may open a new tab — switch to the latest tab
    try:
        handles = driver.window_handles
        if len(handles) > 1:
            driver.switch_to.window(handles[-1])
            time.sleep(2)
    except Exception:
        pass

    # Check for rate-limited state: ql-editor present but contenteditable=false
    # Gemini Veo disables input after ~3 clips per session.
    try:
        disabled = driver.find_elements(By.CSS_SELECTOR, 'div.ql-editor[contenteditable="false"]')
        if disabled:
            raise RuntimeError("VEO_RATE_LIMITED")
    except RuntimeError:
        raise
    except Exception:
        pass

    inp = None
    for sel in selectors:
        try:
            inp = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, sel)))
            print(f"[veo] Input found via selector: {sel}")
            break
        except Exception:
            continue
    if inp is None:
        # Dump page info to diagnose
        try:
            url = driver.current_url
            all_inputs = driver.find_elements(By.CSS_SELECTOR, "input, textarea, [contenteditable]")
            print(f"[veo] Input not found. URL={url}")
            print(f"[veo] Editable elements on page ({len(all_inputs)}):")
            for el in all_inputs[:6]:
                tag = el.tag_name
                ce = el.get_attribute("contenteditable")
                ph = el.get_attribute("placeholder") or el.get_attribute("data-placeholder") or ""
                cls = (el.get_attribute("class") or "")[:60]
                print(f"  <{tag} contenteditable={ce} placeholder={ph!r} class={cls!r}>")
        except Exception as de:
            print(f"[veo] Diagnostic dump failed: {de}")
        raise RuntimeError("Cannot find Gemini chat input box")

    driver.execute_script("arguments[0].click();", inp)
    time.sleep(0.4)
    # Select all existing text and replace with clipboard paste
    inp.send_keys(Keys.CONTROL, "a")
    time.sleep(0.1)
    inp.send_keys(Keys.CONTROL, "v")
    time.sleep(0.5)
    # Submit via Enter
    inp.send_keys(Keys.RETURN)


def _wait_for_video_ready(driver, timeout: int = 240) -> bool:
    from selenium.webdriver.common.by import By
    deadline = time.time() + timeout
    while time.time() < deadline:
        time.sleep(4)
        elapsed = int(time.time() - (deadline - timeout))
        if elapsed % 20 == 0:
            print(f"[veo]   ... generating ({elapsed}s)")
        try:
            # Video element present
            if driver.find_elements(By.TAG_NAME, "video"):
                return True
            # Download button visible (various Gemini UI patterns)
            for sel in [
                'button[aria-label*="Download"]',
                'button[aria-label*="download"]',
                'button[mattooltip*="Download"]',
                'button[mattooltip*="download"]',
                '[data-test-id*="download"]',
                # Veo result container patterns
                'video-result',
                '[class*="video-result"]',
                '[class*="generated-video"]',
                'generated-video',
            ]:
                if driver.find_elements(By.CSS_SELECTOR, sel):
                    return True
            # XPath: any element containing "Download video" text
            if driver.find_elements(By.XPATH, '//*[contains(@aria-label, "Download video")]'):
                return True
        except Exception:
            pass
    return False


def _download_clip(driver, download_dir: str, before: set, timeout: int = 45) -> str | None:
    from selenium.webdriver.common.by import By

    # Try all download button patterns
    clicked = False
    for sel in [
        'button[aria-label*="Download"]', 'button[aria-label*="download"]',
        'button[mattooltip*="Download"]', 'button[mattooltip*="download"]',
        '[data-test-id*="download"]',
    ]:
        btns = driver.find_elements(By.CSS_SELECTOR, sel)
        if btns:
            try:
                driver.execute_script("arguments[0].click();", btns[-1])
                clicked = True
                break
            except Exception:
                pass

    if not clicked:
        for btn in reversed(driver.find_elements(By.TAG_NAME, "button")):
            label = ((btn.get_attribute("aria-label") or "") + (btn.get_attribute("title") or "")).lower()
            if "download" in label:
                try:
                    driver.execute_script("arguments[0].click();", btn)
                    clicked = True
                    break
                except Exception:
                    pass

    if clicked:
        deadline = time.time() + timeout
        while time.time() < deadline:
            time.sleep(2)
            current = {f for f in glob.glob(os.path.join(download_dir, "*.mp4"))
                       if not f.endswith(".crdownload")}
            new = current - before
            if new:
                time.sleep(1)
                return max(new, key=os.path.getmtime)

    # Fallback: grab video src directly
    try:
        vids = driver.find_elements(By.TAG_NAME, "video")
        for vid in reversed(vids):
            src = vid.get_attribute("src") or ""
            if src.startswith("http") and "blob:" not in src:
                import requests as req
                cookies = {c["name"]: c["value"] for c in driver.get_cookies()}
                r = req.get(src, cookies=cookies, timeout=60, stream=True)
                if r.status_code == 200:
                    path = os.path.join(download_dir, f"veo_{int(time.time())}.mp4")
                    with open(path, "wb") as f:
                        for chunk in r.iter_content(8192):
                            f.write(chunk)
                    return path
    except Exception as e:
        print(f"[veo] Direct src fallback failed: {e}")
    return None


def _new_chat(driver):
    from selenium.webdriver.common.by import By
    # Always go back to the main page so the 'Create video' button reappears
    driver.get("https://gemini.google.com")
    time.sleep(3)


# ── Auto-edit: xfade transitions ─────────────────────────────────────────────

def _get_duration(ffmpeg: str, path: str) -> float:
    r = subprocess.run([ffmpeg, "-i", path], capture_output=True, text=True, timeout=15)
    for line in (r.stdout + r.stderr).splitlines():
        if "Duration:" in line:
            t = line.split("Duration:")[1].split(",")[0].strip()
            h, m, s = t.split(":")
            return int(h)*3600 + int(m)*60 + float(s)
    return 8.0


def _apply_transitions(clip_paths: list, output_path: str,
                        trans_dur: float = 0.5) -> str:
    """Join processed clips with xfade transitions. Each transition type rotates."""
    import imageio_ffmpeg
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()

    if len(clip_paths) == 1:
        shutil.copy(clip_paths[0], output_path)
        return output_path

    # Alternate between transition styles for visual variety
    transitions = ["fade", "dissolve", "wipeleft", "slideright", "radial"]
    durations = [_get_duration(ffmpeg, p) for p in clip_paths]

    filter_parts = []
    offset = 0.0
    prev_label = "[0:v]"

    for i in range(1, len(clip_paths)):
        offset += durations[i-1] - trans_dur
        t = transitions[(i-1) % len(transitions)]
        next_label = f"[xf{i}]"
        filter_parts.append(
            f"{prev_label}[{i}:v]xfade=transition={t}"
            f":duration={trans_dur}:offset={offset:.3f}{next_label}"
        )
        prev_label = next_label

    cmd = [ffmpeg, "-y"]
    for p in clip_paths:
        cmd += ["-i", p]
    cmd += [
        "-filter_complex", ";".join(filter_parts),
        "-map", prev_label,
        "-c:v", "libx264", "-preset", "fast", "-crf", "22",
        "-pix_fmt", "yuv420p", "-an",
        output_path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
    if result.returncode == 0:
        print(f"[veo] Auto-edit with xfade transitions applied")
        return output_path

    print(f"[veo] xfade failed, using plain concat: {result.stderr[-150:]}")
    concat_file = output_path + ".txt"
    with open(concat_file, "w") as f:
        for p in clip_paths:
            f.write(f"file '{os.path.abspath(p).replace(chr(92), '/')}'\n")
    subprocess.run([ffmpeg, "-y", "-f", "concat", "-safe", "0",
                    "-i", concat_file, "-c", "copy", output_path],
                   capture_output=True, timeout=120)
    os.remove(concat_file)
    return output_path


# ── Main Selenium generation loop ─────────────────────────────────────────────

def generate_veo_clips(script: str, niche: str, output_dir: str,
                       chrome_profile: str = None,
                       generation_timeout: int = 240) -> list:
    """
    Run the full Selenium loop: prompt → generate → download → process each clip.
    Returns list of processed 1080x1920 .mp4 paths.
    """
    import imageio_ffmpeg

    audio_secs = _seconds_from_script(script)
    num_clips = _num_clips_needed(audio_secs)
    print(f"[veo] Audio ~{audio_secs:.0f}s → {num_clips} clips needed")

    scenes = _generate_scenes_via_gemini(script, niche, num_clips)

    dl_dir = os.path.abspath(os.path.join(output_dir, "_veo_dl"))
    os.makedirs(dl_dir, exist_ok=True)

    # Always use a fresh temp profile so we own the session (no port-9222 attachment).
    # Port-9222 sessions die when the user's Chrome closes, killing all clips mid-run.
    import tempfile
    tmp_profile = tempfile.mkdtemp(prefix="veo_profile_")
    driver = _make_driver_fresh(dl_dir, tmp_profile)
    we_own = True
    clips = []

    try:
        from dotenv import load_dotenv
        load_dotenv()
        cookies_path = os.getenv("GEMINI_COOKIES", "cookies.json")
        has_cookies = bool(cookies_path and os.path.exists(cookies_path))

        # Always inject cookies via google.com to ensure Pro account is used
        if has_cookies:
            print(f"[veo] Injecting cookies from {cookies_path}...")
            _inject_cookies_and_navigate(driver, cookies_path, "https://gemini.google.com")
        else:
            driver.get("https://gemini.google.com")
            time.sleep(4)

        if "accounts.google.com" in driver.current_url:
            driver.quit()
            raise RuntimeError(
                "Chrome is not signed into Google. "
                "Either: (A) add cookies.json file, or "
                "(B) open Chrome → gemini.google.com → sign in → close Chrome → retry."
            )

        # Switch to Veo 3 video generation model
        _select_veo_model(driver)

        # Verify session survived the model switch
        try:
            _ = driver.current_url
        except Exception:
            raise RuntimeError("[veo] Chrome session lost during model selection — cannot proceed")

        for i, scene in enumerate(scenes):
            prompt = _craft_veo_prompt(scene)
            print(f"\n[veo] Clip {i+1}/{num_clips}")
            print(f"      Subject: {scene.get('subject', '')[:80]}")

            before = {f for f in glob.glob(os.path.join(dl_dir, "*.mp4"))
                      if not f.endswith(".crdownload")}

            # Prefix that routes Gemini to Veo (no prefix needed once model selected,
            # but a short trigger helps if model wasn't switched)
            full_request = prompt
            try:
                _type_prompt(driver, full_request)
            except RuntimeError as e:
                if "VEO_RATE_LIMITED" in str(e):
                    print(f"[veo] Rate limit hit after clip {i} — restarting Chrome session...")
                    try:
                        driver.quit()
                    except Exception:
                        pass
                    restart_profile = tempfile.mkdtemp(prefix="veo_restart_")
                    driver = _make_driver_fresh(dl_dir, restart_profile)
                    cookies_path2 = os.getenv("GEMINI_COOKIES", "cookies.json")
                    if os.path.exists(cookies_path2):
                        _inject_cookies_and_navigate(driver, cookies_path2, "https://gemini.google.com")
                    else:
                        driver.get("https://gemini.google.com")
                        time.sleep(4)
                    _select_veo_model(driver)
                    try:
                        _type_prompt(driver, full_request)
                        print(f"[veo] Session restarted — retrying clip {i+1}")
                    except Exception as re2:
                        print(f"[veo] Restart failed: {re2} — stopping at clip {i+1}, keeping {len(clips)} clip(s)")
                        break
                else:
                    print(f"[veo] Could not submit prompt: {e}")
                    # Check if session is dead
                    session_dead = False
                    try:
                        driver.current_url
                    except Exception:
                        session_dead = True

                    if session_dead:
                        print(f"[veo] Session lost — attempting restart...")
                        try:
                            driver.quit()
                        except Exception:
                            pass
                        try:
                            restart_profile = tempfile.mkdtemp(prefix="veo_restart_")
                            driver = _make_driver_fresh(dl_dir, restart_profile)
                            cookies_path2 = os.getenv("GEMINI_COOKIES", "cookies.json")
                            if os.path.exists(cookies_path2):
                                _inject_cookies_and_navigate(driver, cookies_path2, "https://gemini.google.com")
                            else:
                                driver.get("https://gemini.google.com")
                                time.sleep(4)
                            _select_veo_model(driver)
                            _type_prompt(driver, full_request)
                            print(f"[veo] Session restarted successfully")
                        except Exception as re2:
                            print(f"[veo] Restart failed: {re2} — stopping at clip {i+1}, keeping {len(clips)} clip(s)")
                            break
                    else:
                        _new_chat(driver)
                        _select_veo_model(driver)
                        continue
            except Exception as e:
                print(f"[veo] Could not submit prompt: {e}")
                # Check if session is dead — if so stop and use what we have
                try:
                    driver.current_url
                except Exception:
                    print(f"[veo] Session lost — stopping at clip {i+1}, keeping {len(clips)} clip(s)")
                    break
                _new_chat(driver)
                _select_veo_model(driver)
                continue

            print(f"[veo] Generating... (up to {generation_timeout}s)")
            ready = _wait_for_video_ready(driver, generation_timeout)

            if not ready:
                print(f"[veo] Clip {i+1} timed out — skipping")
                _new_chat(driver)
                continue

            print(f"[veo] Video ready — downloading...")
            path = _download_clip(driver, dl_dir, before)

            if path and os.path.exists(path):
                ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
                proc = os.path.join(output_dir, f"veo_clip_{i}.mp4")
                cmd = [
                    ffmpeg, "-y", "-i", path,
                    "-vf", ("scale=1080:1920:force_original_aspect_ratio=increase,"
                            "crop=1080:1920,fps=30"),
                    "-c:v", "libx264", "-preset", "fast", "-crf", "22",
                    "-an", "-pix_fmt", "yuv420p",
                    proc,
                ]
                res = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
                os.remove(path)
                if res.returncode == 0:
                    clips.append(proc)
                    print(f"[veo] Clip {i+1} processed ✓")
                else:
                    print(f"[veo] Processing clip {i+1} failed")
            else:
                print(f"[veo] Download failed for clip {i+1}")

            # Start a new chat for next clip, then re-select Veo model
            # (new chat resets the model back to default)
            if i < num_clips - 1:
                _new_chat(driver)
                _select_veo_model(driver)

    finally:
        if we_own:
            try:
                driver.quit()
            except Exception:
                pass
        shutil.rmtree(tmp_profile, ignore_errors=True)

    return clips


# ── Public entry point ────────────────────────────────────────────────────────

def get_veo_background(script: str, niche: str, output_path: str,
                       chrome_profile: str = None) -> str:
    """
    Full pipeline: script → JSON scenes → Selenium → clips → auto-edit → output_path.
    Raises RuntimeError so caller can fall back to Pexels.
    """
    output_dir = os.path.dirname(output_path) or "."
    clips = generate_veo_clips(script, niche, output_dir, chrome_profile)

    if not clips:
        raise RuntimeError("[veo] No clips were generated")

    print(f"[veo] Auto-editing {len(clips)} clip(s) with xfade transitions...")
    _apply_transitions(clips, output_path)

    for c in clips:
        if os.path.exists(c) and c != output_path:
            os.remove(c)
    dl_dir = os.path.join(output_dir, "_veo_dl")
    if os.path.exists(dl_dir):
        shutil.rmtree(dl_dir, ignore_errors=True)

    print(f"[veo] Done: {output_path}")
    return output_path
