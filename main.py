import os
import asyncio
import requests
import random
import json
from dotenv import load_dotenv

load_dotenv()

# Niche → best Pexels search keywords (multiple fallbacks per niche)
NICHE_KEYWORDS = {
    "finance":        ["money", "business", "office", "city", "banking"],
    "health_wellness":["workout", "nature", "meditation", "food", "running"],
    "technology":     ["technology", "computer", "city", "abstract", "network"],
    "business":       ["business", "office", "meeting", "city", "entrepreneur"],
    "motivation":     ["sunrise", "mountain", "road", "ocean", "sky"],
    "productivity":   ["desk", "notebook", "office", "coffee", "workspace"],
    "ai_tools":       ["technology", "computer", "abstract", "digital", "city"],
    "relationships":  ["people", "nature", "city", "sunset", "hands"],
    "math_quiz":      ["mathematics", "chalkboard", "classroom", "numbers", "education"],
}


def get_topic(niche: str = "finance") -> str:
    # 1. Try real-time trending topics (high CTR signal)
    try:
        from trending import get_trending_topic
        trending = get_trending_topic(niche)
        if trending:
            return trending
    except Exception as e:
        print(f"[trending] Skipped: {e}")

    # 2. Fallback: topics.json
    topics_file = os.path.join(os.path.dirname(__file__), "topics.json")
    if os.path.exists(topics_file):
        with open(topics_file, "r") as f:
            topics = json.load(f)
        niche_topics = topics.get(niche, [])
        if niche_topics:
            return random.choice(niche_topics)
    builtin = {
        "finance": [
            "5 money mistakes that keep you broke",
            "How to save $1,000 in 30 days",
            "How to invest with $100",
            "Side hustles that actually make money",
            "How to stop living paycheck to paycheck",
        ],
        "productivity": [
            "How to wake up at 5 AM",
            "How to stop procrastinating forever",
            "Morning routine of millionaires",
            "Time blocking method explained",
        ],
        "ai_tools": [
            "Top 5 free AI tools for 2025",
            "How to use ChatGPT to make money",
            "AI tools that save you 10 hours a week",
        ],
        "motivation": [
            "Why most people never succeed",
            "One habit that changed my life",
            "Stop wasting your 20s",
        ],
        "math_quiz": [
            "Can you solve this in 5 seconds",
            "99 percent of people get this wrong",
            "Simple math that tricks everyone",
            "What is 9 times 9 minus 72",
            "Only geniuses solve this fast",
            "The math problem that went viral",
            "Can you beat the calculator",
            "Most adults fail this grade school math",
            "Solve this before the timer runs out",
            "The trick question everyone gets wrong",
        ],
    }
    return random.choice(builtin.get(niche, builtin["finance"]))


def generate_script(topic: str, niche: str = "finance") -> str:
    import time
    import requests as _req
    api_key = os.getenv("OPENROUTER_API_KEY", "")
    if not api_key:
        return _fallback_script(topic)
    if niche == "math_quiz":
        prompt = f"""Write a YouTube Shorts voiceover script for a math quiz video about: "{topic}"

STRICT OUTPUT RULES — follow exactly:
- Output ONLY the spoken words. No title, no intro, no labels.
- Do NOT use markdown, asterisks, headers, or bullet points.
- Do NOT include stage directions or [brackets].
- Start immediately with the first spoken word.
- End with the last spoken word. Nothing after.

Script structure (60-80 words total):
1. Hook: Pose the math question directly — state the problem clearly.
2. Pause phrase: Say exactly "Pause and think... can you solve it?"
3. Think time: Say "Three... two... one..."
4. Reveal the answer clearly with a one-sentence explanation.
5. CTA: End with "Follow for a new math challenge every day."
"""
    else:
        prompt = f"""Write a YouTube Shorts voiceover script about: "{topic}"

STRICT OUTPUT RULES — follow exactly:
- Output ONLY the spoken words. No title, no intro, no "Here's your script:", no labels.
- Do NOT write anything before or after the script itself.
- Do NOT use markdown, asterisks, headers, or bullet points.
- Do NOT include stage directions or [brackets].
- Start immediately with the first spoken word of the hook.
- End with the last spoken word. Nothing after.

Script requirements:
- Duration: 45-55 seconds when read aloud (~120-130 words)
- First sentence must be a strong hook that grabs attention instantly
- 3 clear points, short punchy sentences
- Last sentence: "Follow for more tips like this"
"""
    for attempt in range(2):
        try:
            resp = _req.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json={"model": "google/gemini-2.0-flash-001",
                      "messages": [{"role": "user", "content": prompt}]},
                timeout=60,
            )
            if resp.status_code == 429:
                if attempt == 0:
                    print("OpenRouter rate limited — retrying in 15s...")
                    time.sleep(15)
                    continue
                print("OpenRouter rate limited — using fallback script.")
                return _fallback_script(topic)
            if resp.status_code != 200:
                print(f"OpenRouter error {resp.status_code}: {resp.text[:200]} — using fallback.")
                return _fallback_script(topic)
            script = resp.json()["choices"][0]["message"]["content"].strip()
            word_count = len(script.split())
            print(f"Script generated via OpenRouter ({word_count} words)")
            if word_count < 40:
                print("Script too short — using fallback for minimum 15s")
                return _fallback_script(topic)
            return script
        except Exception as e:
            print(f"OpenRouter error: {e} — using fallback script.")
            return _fallback_script(topic)
    return _fallback_script(topic)


def _fallback_script(topic: str) -> str:
    """Template-based fallback when Gemini is unavailable."""
    script = (
        f"Stop what you're doing — this will change how you think about {topic}. "
        f"Here's what most people get completely wrong. "
        f"First, you need to understand the basics before anything else. "
        f"This single step separates beginners from experts. "
        f"Second, consistency beats perfection every single time. "
        f"Most people quit right before they see results. "
        f"Third, take action today, not next week. "
        f"The best time to start was yesterday. The second best time is right now. "
        f"Follow for more tips like this."
    )
    print(f"Fallback script used ({len(script.split())} words)")
    return script


def _pexels_best_file(video: dict) -> dict | None:
    files = video.get("video_files", [])
    portrait = [f for f in files if f.get("height", 0) > f.get("width", 0)]
    hd = sorted(portrait or files, key=lambda x: x.get("height", 0), reverse=True)
    return hd[0] if hd else None


def get_background_video(keyword: str, output_path: str, niche: str = "",
                         num_clips: int = 3) -> str:
    """
    Download num_clips distinct Pexels portrait clips, trim each to 15s,
    scale/crop to 1080x1920, concatenate into a single background video.
    """
    import subprocess, imageio_ffmpeg, shutil as _shutil
    headers = {"Authorization": os.getenv("PEXELS_API_KEY")}
    niche_kws = NICHE_KEYWORDS.get(niche, [])
    first_word = keyword.split()[0] if keyword else "city"
    fallbacks = list(dict.fromkeys(niche_kws + [first_word, "city", "nature", "sky"]))

    videos = []
    for kw in fallbacks:
        try:
            res = requests.get(
                "https://api.pexels.com/videos/search",
                headers=headers,
                params={"query": kw, "per_page": 15, "orientation": "portrait"},
                timeout=15,
            )
            if res.status_code == 200:
                videos = res.json().get("videos", [])
            if videos:
                print(f"Background video keyword: '{kw}'")
                break
        except Exception as e:
            print(f"Pexels search error for '{kw}': {e}")
    if not videos:
        raise RuntimeError("No videos found on Pexels — check your PEXELS_API_KEY")

    os.makedirs(os.path.dirname(output_path) if os.path.dirname(output_path) else ".", exist_ok=True)

    # Pick up to num_clips distinct videos from the first 10 results
    pool = videos[:min(10, len(videos))]
    random.shuffle(pool)
    chosen = pool[:min(num_clips, len(pool))]

    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    clip_paths = []
    for i, vid in enumerate(chosen):
        vf = _pexels_best_file(vid)
        if not vf:
            continue
        raw = output_path.replace(".mp4", f"_raw{i}.mp4")
        proc = output_path.replace(".mp4", f"_clip{i}.mp4")
        print(f"Downloading clip {i + 1}/{len(chosen)}...")
        r = requests.get(vf["link"], stream=True, timeout=60)
        with open(raw, "wb") as f:
            for chunk in r.iter_content(chunk_size=8192):
                f.write(chunk)
        # Trim to 15s + scale/crop to 1080x1920 + normalize fps to 30
        cmd = [
            ffmpeg, "-y",
            "-i", raw,
            "-t", "15",
            "-vf", "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,fps=30",
            "-c:v", "libx264", "-preset", "fast", "-crf", "23",
            "-an", "-pix_fmt", "yuv420p",
            proc,
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        os.remove(raw)
        if result.returncode == 0:
            clip_paths.append(proc)
        else:
            print(f"Clip {i} processing failed, skipping")

    if not clip_paths:
        raise RuntimeError("Failed to process any background clips")

    if len(clip_paths) == 1:
        _shutil.move(clip_paths[0], output_path)
        print(f"Background video (1 clip): {output_path}")
        return output_path

    # Concatenate with ffmpeg concat demuxer (all clips same codec/res/fps)
    concat_file = output_path + ".txt"
    with open(concat_file, "w") as f:
        for cp in clip_paths:
            # Forward slashes required by ffmpeg on Windows
            abs_path = os.path.abspath(cp).replace("\\", "/")
            f.write(f"file '{abs_path}'\n")
    cmd = [
        ffmpeg, "-y",
        "-f", "concat", "-safe", "0",
        "-i", concat_file,
        "-c", "copy",
        output_path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    os.remove(concat_file)
    for cp in clip_paths:
        if os.path.exists(cp):
            os.remove(cp)
    if result.returncode != 0:
        raise RuntimeError(f"Concat failed:\n{result.stderr[-600:]}")
    print(f"Background video ({len(clip_paths)} clips): {output_path}")
    return output_path


def create_base_video(video_path: str, audio_path: str, output_path: str) -> str:
    import subprocess
    from moviepy import AudioFileClip
    import imageio_ffmpeg
    print("Assembling base video...")
    # Get audio duration
    audio = AudioFileClip(audio_path)
    duration = audio.duration
    audio.close()
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    # Background is pre-processed 1080x1920; loop it if shorter than audio, trim to audio duration
    # -map 0:v:0  → video from background (input 0)
    # -map 1:a:0  → audio from voiceover (input 1)
    cmd = [
        ffmpeg, "-y",
        "-stream_loop", "-1",   # loop background in case clips total < audio duration
        "-i", video_path,
        "-i", audio_path,
        "-t", str(duration),
        "-map", "0:v:0",
        "-map", "1:a:0",
        "-vf", "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,fps=30",
        "-c:v", "libx264", "-preset", "fast", "-crf", "23",
        "-c:a", "aac", "-b:a", "192k",
        "-pix_fmt", "yuv420p",
        output_path
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg failed:\n{result.stderr[-800:]}")
    print(f"Base video: {output_path}")
    return output_path


def upload_to_youtube(video_path: str, thumbnail_path: str,
                      title: str, description: str, tags: list) -> str:
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    SCOPES = [
        "https://www.googleapis.com/auth/youtube.upload",
        "https://www.googleapis.com/auth/youtube"
    ]
    token_path = os.path.join(os.path.dirname(__file__), "token.json")
    creds_path = os.path.join(os.path.dirname(__file__), "credentials.json")
    if os.path.exists(token_path):
        creds = Credentials.from_authorized_user_file(token_path, SCOPES)
    else:
        flow = InstalledAppFlow.from_client_secrets_file(creds_path, SCOPES)
        creds = flow.run_local_server(port=0)
        with open(token_path, "w") as f:
            f.write(creds.to_json())
    youtube = build("youtube", "v3", credentials=creds)
    print("Uploading video to YouTube...")
    insert_request = youtube.videos().insert(
        part="snippet,status",
        body={
            "snippet": {
                "title": f"{title} #shorts"[:100],
                "description": f"{description}\n\n#shorts #viral",
                "tags": tags + ["shorts", "viral", "youtubeshorts"],
                "categoryId": "22",
            },
            "status": {
                "privacyStatus": "public",
                "selfDeclaredMadeForKids": False,
            }
        },
        media_body=MediaFileUpload(video_path, chunksize=-1, resumable=True)
    )
    response = insert_request.execute()
    video_id = response["id"]
    if thumbnail_path and os.path.exists(thumbnail_path):
        print("Uploading thumbnail...")
        youtube.thumbnails().set(
            videoId=video_id,
            media_body=MediaFileUpload(thumbnail_path)
        ).execute()
    url = f"https://youtube.com/shorts/{video_id}"
    print(f"Live at: {url}")
    return url


def generate_platform_metadata(topic: str, niche: str) -> dict:
    """Generate ready-to-use titles, descriptions and hashtags for each platform."""
    niche_tags = {
        "finance":        ["finance", "money", "investing", "wealth", "financetips"],
        "health_wellness":["health", "wellness", "fitness", "healthtips", "selfcare"],
        "technology":     ["tech", "ai", "technology", "futuretech", "techtips"],
        "business":       ["business", "entrepreneurship", "startup", "ceo", "success"],
        "motivation":     ["motivation", "mindset", "success", "inspiration", "grind"],
        "productivity":   ["productivity", "habits", "focus", "timemanagement", "hustle"],
        "ai_tools":       ["ai", "chatgpt", "artificialintelligence", "aitools", "tech"],
        "relationships":  ["relationships", "selfimprovement", "psychology", "mindset", "life"],
        "math_quiz":       ["mathquiz", "math", "brainteaser", "quiz", "mathchallenge"],
    }.get(niche, [niche, "tips", "howto"])

    base_tags = niche_tags + ["shorts", "viral", "youtubeshorts", "fyp", "trending"]
    short_title = f"{topic} #shorts"[:100]
    description = (
        f"{topic}\n\n"
        f"Follow for daily {niche.replace('_', ' ')} tips!\n\n"
        + " ".join(f"#{t}" for t in base_tags[:10])
    )

    return {
        "youtube": {
            "title":       short_title,
            "description": description,
            "tags":        base_tags,
        },
        "tiktok": {
            "caption": f"{topic} " + " ".join(f"#{t}" for t in base_tags[:5]),
        },
        "instagram": {
            "caption": (
                f"{topic}\n\n"
                + " ".join(f"#{t}" for t in base_tags[:20])
            ),
        },
        "facebook": {
            "text": f"{topic}\n\nFollow for more tips like this!",
        },
    }


def add_background_music(video_path: str, output_path: str, volume: float = 0.07) -> str:
    """Mix quiet lofi bg music into final video. Drop mp3/wav files into a music/ folder."""
    import glob, subprocess, imageio_ffmpeg
    music_dir = os.path.join(os.path.dirname(__file__), "music")
    os.makedirs(music_dir, exist_ok=True)
    tracks = glob.glob(os.path.join(music_dir, "*.mp3")) + \
             glob.glob(os.path.join(music_dir, "*.wav"))
    if not tracks:
        print("[music] No tracks in music/ folder — drop mp3/wav files there to enable bg music")
        return video_path
    import random
    track = random.choice(tracks)
    print(f"[music] Mixing bg track: {os.path.basename(track)} at volume {volume}")
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    cmd = [
        ffmpeg, "-y",
        "-i", video_path,
        "-stream_loop", "-1", "-i", track,
        "-filter_complex",
        f"[1:a]volume={volume}[music];[0:a][music]amix=inputs=2:duration=first:dropout_transition=3[aout]",
        "-map", "0:v:0",
        "-map", "[aout]",
        "-c:v", "copy",
        "-c:a", "aac", "-b:a", "192k",
        output_path
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    if result.returncode == 0:
        print(f"[music] Done: {output_path}")
        return output_path
    print(f"[music] Mix failed — skipping bg music: {result.stderr[-200:]}")
    return video_path


_QUIZ_HISTORY_FILE = os.path.join(os.path.dirname(__file__), "quiz_history.json")


def _load_quiz_history() -> dict:
    if os.path.exists(_QUIZ_HISTORY_FILE):
        try:
            with open(_QUIZ_HISTORY_FILE, "r") as f:
                return json.load(f)
        except Exception:
            pass
    return {"questions": [], "video_ids": []}


def _save_quiz_history(history: dict):
    with open(_QUIZ_HISTORY_FILE, "w") as f:
        json.dump(history, f, indent=2)


def generate_quiz_content(topic: str, used_questions: list | None = None) -> dict:
    """Call OpenRouter to get a quiz question + 4 options + answer as JSON."""
    import requests as _req
    api_key = os.getenv("OPENROUTER_API_KEY", "")
    fallback = {
        "question":      "What is 15 × 8?",
        "options":       {"A": "110", "B": "120", "C": "130", "D": "140"},
        "correct_answer":"B",
        "explanation":   "15 times 8 equals 120.",
        "category":      "MATH QUIZ",
        "image_query":   "mathematics numbers chalkboard",
    }
    if not api_key:
        return fallback
    prompt = f"""Generate a TRICKY math quiz question about: "{topic}"

The question must make viewers PAUSE, doubt themselves, and want to replay the video to verify.
Use one of these high-engagement formats:
- Order of operations trap: "What is 8 ÷ 2(2+2)?" or "2 + 3 × 4?"
- Percentage/fraction trick: surprising result most people get wrong
- Classic math riddle with a counterintuitive answer
- Pattern or sequence where the obvious answer is wrong
- A question where the most common instinct gives the WRONG answer

Return ONLY a valid JSON object with exactly these keys:
{{
  "question": "the tricky question ending with ?",
  "options": {{"A": "...", "B": "...", "C": "...", "D": "..."}},
  "correct_answer": "A",
  "explanation": "surprising one-liner explaining why, max 12 words",
  "category": "MATH QUIZ",
  "image_query": "3-word Pexels PHOTO showing the math concept visually (e.g. 'pie chart fraction', 'dollar bills percentage', 'ruler triangle geometry', 'clock time numbers')",
  "bg_query": "3-word cinematic background VIDEO (e.g. 'dark bokeh studio', 'chalkboard classroom empty', 'abstract dark blue', 'night city lights')"
}}
Critical rules:
- The most common WRONG answer MUST appear as one of the options (creates the trap feeling)
- The correct answer should feel surprising or counterintuitive
- correct_answer must be exactly one of: A, B, C, or D
- Return ONLY the raw JSON — no markdown, no backticks, no extra text."""
    if used_questions:
        prompt += (
            "\n\nIMPORTANT: Do NOT reuse any of these already-posted questions:\n"
            + "\n".join(f"- {q}" for q in used_questions[-30:])
            + "\nGenerate a completely different question."
        )
    try:
        resp = _req.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={"model": "google/gemini-2.0-flash-001",
                  "messages": [{"role": "user", "content": prompt}]},
            timeout=30,
        )
        if resp.status_code != 200:
            print(f"[quiz] OpenRouter error {resp.status_code}: {resp.text[:200]}")
            return fallback
        content = resp.json()["choices"][0]["message"]["content"].strip()
        if content.startswith("```"):
            parts   = content.split("```")
            content = parts[1] if len(parts) > 1 else parts[0]
            if content.startswith("json"):
                content = content[4:]
        return json.loads(content.strip())
    except Exception as e:
        print(f"[quiz] Content generation failed: {e}")
        return fallback


def generate_quiz_post_txt(quiz_data: dict, output_dir: str) -> str:
    """Call OpenRouter to generate a viral title, SEO description, and hashtags.
    Writes post.txt to output_dir and returns the path."""
    import requests as _req
    api_key = os.getenv("OPENROUTER_API_KEY", "")
    question = quiz_data.get("question", "Can you solve this math problem?")
    correct  = quiz_data.get("correct_answer", "A")
    options  = quiz_data.get("options", {})
    answer   = options.get(correct, "")

    prompt = f"""You are a viral YouTube Shorts SEO expert. Write post copy for a math quiz Short.

Quiz question: "{question}"
Correct answer: {correct}) {answer}

Output ONLY a JSON object with exactly these keys:
{{
  "title": "A high-CTR YouTube title under 70 chars. Use curiosity, numbers, challenge hooks. Example: '90% Get This Wrong 🤯 Can You?' or '2-Second Math Trick That Fools Everyone'",
  "description": "3-4 sentences. First line is a hook. Mention the math challenge, tease the answer. Include a CTA to follow. Natural keyword-rich language, NO hashtags here.",
  "hashtags": "20 hashtags as a single line, most viral first. Include: #mathquiz #shorts #math #brainteaser #viral, plus related niche tags. No spaces within each tag."
}}

Rules:
- title: power words, emotional triggers, numbers if natural. Max 70 chars.
- description: conversational, not robotic. Don't reveal the answer.
- hashtags: space-separated, all lowercase, no quotes
- Return ONLY the raw JSON — no markdown, no backticks."""

    try:
        resp = _req.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={"model": "google/gemini-2.0-flash-001",
                  "messages": [{"role": "user", "content": prompt}]},
            timeout=30,
        )
        if resp.status_code != 200:
            raise ValueError(f"OpenRouter {resp.status_code}")
        content = resp.json()["choices"][0]["message"]["content"].strip()
        if content.startswith("```"):
            parts   = content.split("```")
            content = parts[1] if len(parts) > 1 else parts[0]
            if content.startswith("json"):
                content = content[4:]
        data = json.loads(content.strip())
    except Exception as e:
        print(f"[post] Metadata LLM failed ({e}), using fallback")
        data = {
            "title":       f"90% Get This Wrong 🤯 {question[:50]}",
            "description": (
                f"This math problem is trickier than it looks! {question} "
                f"Most people pick the wrong answer — can you get it right? "
                f"Drop your answer in the comments and follow for a new challenge every day!"
            ),
            "hashtags": "#mathquiz #shorts #math #brainteaser #viral #mathchallenge #quiz #fyp #youtubeshorts #trending #mindblown #mathtrick #smartkids #education #stem #maths #puzzle #riddle #challenge #learnmath",
        }

    txt = (
        f"TITLE\n{data['title']}\n\n"
        f"DESCRIPTION\n{data['description']}\n\n"
        f"HASHTAGS\n{data['hashtags']}\n"
    )
    out_path = os.path.join(output_dir, "post.txt")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(txt)
    print(f"[post] post.txt written → {out_path}")
    return out_path


async def create_single_short(topic: str, niche: str,
                               output_dir: str, upload: bool = True,
                               voice: str = "am_adam",
                               thumbnail_style: str = "dark",
                               use_veo: bool = False) -> dict:
    # ── math_quiz: quiz card pipeline (no subtitles, 12-second format) ──────
    if niche == "math_quiz":
        from quiz_renderer import create_quiz_video
        os.makedirs(output_dir, exist_ok=True)
        print(f"\n{'='*50}\nTopic: {topic}\n{'='*50}")
        history    = _load_quiz_history()
        used_q     = history.get("questions", [])
        used_vids  = set(history.get("video_ids", []))
        quiz_data  = generate_quiz_content(topic, used_questions=used_q)
        final_path, vid_id = await create_quiz_video(
            quiz_data, output_dir,
            voice=voice,
            pexels_key=os.getenv("PEXELS_API_KEY", ""),
            used_video_ids=used_vids,
        )
        # Persist dedup history
        q_text = quiz_data.get("question", "")
        if q_text and q_text not in used_q:
            history["questions"].append(q_text)
        if vid_id and vid_id not in history["video_ids"]:
            history["video_ids"].append(vid_id)
        _save_quiz_history(history)
        generate_quiz_post_txt(quiz_data, output_dir)
        meta   = generate_platform_metadata(topic, niche)
        result = {
            "topic": topic,
            "paths": {
                "audio":      f"{output_dir}/narration.mp3",
                "srt":        "",
                "background": "",
                "base":       "",
                "captioned":  final_path,
                "thumbnail":  f"{output_dir}/thumbnail.png",
                "final":      final_path,
            },
            "url":  None,
            "meta": meta,
        }
        if upload:
            post_meta = {}
            post_txt = os.path.join(output_dir, "post.txt")
            if os.path.exists(post_txt):
                with open(post_txt, encoding="utf-8") as f:
                    raw = f.read()
                _sections = {}
                for block in ["TITLE", "DESCRIPTION", "HASHTAGS"]:
                    if f"\n{block}\n" in f"\n{raw}":
                        parts = raw.split(f"{block}\n", 1)
                        val   = parts[1].split("\n\n")[0].strip() if len(parts) > 1 else ""
                        _sections[block] = val
                post_meta = _sections
            yt_title = post_meta.get("TITLE", topic)[:100]
            yt_desc  = (
                post_meta.get("DESCRIPTION", f"Math quiz: {topic}")
                + "\n\n"
                + post_meta.get("HASHTAGS", "#mathquiz #shorts #math")
            )
            yt_tags  = [t.lstrip("#") for t in post_meta.get("HASHTAGS", "#mathquiz #math #shorts").split() if t.startswith("#")][:20] or ["mathquiz", "math", "quiz"]
            result["url"] = upload_to_youtube(
                video_path=final_path,
                thumbnail_path=f"{output_dir}/thumbnail.png",
                title=yt_title,
                description=yt_desc,
                tags=yt_tags,
            )
            # TikTok
            tiktok_caption = post_meta.get("TITLE", topic) + "\n" + post_meta.get("HASHTAGS", "#mathquiz #shorts #math")
            from tiktok_upload import upload_to_tiktok
            result["tiktok_url"] = upload_to_tiktok(
                video_path=final_path,
                caption=tiktok_caption,
                cookies_path=os.path.join(os.path.dirname(__file__), "tiktok_cookies.json"),
            )
        return result
    # ── standard pipeline ─────────────────────────────────────────────────
    from captions import generate_captions_with_timing, burn_captions_to_video
    from thumbnail import generate_thumbnail
    import shutil
    os.makedirs(output_dir, exist_ok=True)
    paths = {
        "audio":      f"{output_dir}/voiceover.mp3",
        "srt":        f"{output_dir}/captions.srt",
        "background": f"{output_dir}/background.mp4",
        "base":       f"{output_dir}/base_video.mp4",
        "captioned":  f"{output_dir}/captioned_video.mp4",
        "thumbnail":  f"{output_dir}/thumbnail.png",
        "final":      f"{output_dir}/final_short.mp4",
    }
    print(f"\n{'='*50}")
    print(f"Topic: {topic}")
    print(f"{'='*50}")
    script = generate_script(topic, niche=niche)
    print(f"Generating voiceover + captions (voice={voice})...")
    captions, _ = await generate_captions_with_timing(script, paths["audio"], paths["srt"], voice=voice)
    keyword = f"{niche} {topic.split()[0]}"
    # Background video: Veo 3 (AI-generated) or Pexels (stock footage)
    if use_veo:
        print("[veo] Generating AI background video via Veo 3 (Selenium)...")
        try:
            from veo_selenium import get_veo_background
            get_veo_background(script, niche, paths["background"])
        except Exception as e:
            print(f"[veo] Failed: {e}\n[veo] Falling back to Pexels stock footage")
            get_background_video(keyword, paths["background"], niche=niche)
    else:
        get_background_video(keyword, paths["background"], niche=niche)
    create_base_video(paths["background"], paths["audio"], paths["base"])
    burn_captions_to_video(paths["base"], captions, paths["captioned"],
                            srt_path=paths["srt"])
    generate_thumbnail(title=topic, output_path=paths["thumbnail"],
                       background_video_path=paths["background"], style=thumbnail_style)
    # Mix in background music (optional — drop mp3s into music/ folder)
    with_music = add_background_music(paths["captioned"], paths["final"])
    if with_music == paths["captioned"]:
        # No music or mix failed — just copy captioned video as final
        import shutil as _shutil
        _shutil.copy(paths["captioned"], paths["final"])
    # Generate multi-platform metadata
    meta = generate_platform_metadata(topic, niche)
    result = {"topic": topic, "paths": paths, "url": None, "meta": meta}
    if upload:
        url = upload_to_youtube(
            video_path=paths["final"], thumbnail_path=paths["thumbnail"],
            title=topic, description=f"Learn about {topic}. Follow for daily tips!",
            tags=[niche, topic.split()[0].lower(), "tips", "howto"]
        )
        result["url"] = url
    return result


async def main():
    print("YouTube Shorts Automation\n")
    NICHE = "finance"
    topic = get_topic(NICHE)
    output_dir = f"output/single_{topic[:20].replace(' ', '_')}"
    result = await create_single_short(topic=topic, niche=NICHE,
                                       output_dir=output_dir, upload=True)
    print(f"\nComplete! Video URL: {result['url']}")


if __name__ == "__main__":
    asyncio.run(main())
