"""
TikTok upload via tiktok-uploader (browser automation, no official API needed).

Usage:
    from tiktok_upload import upload_to_tiktok
    url = upload_to_tiktok(
        video_path="output/test/final_short.mp4",
        caption="Caption text #hashtag",
        cookies_path="tiktok_cookies.json",
    )

Cookies:
    Export your TikTok session cookies as JSON using a browser extension
    (e.g. "Cookie-Editor" → Export as JSON) and save to tiktok_cookies.json.
    Cookies last ~30 days. Re-export when they expire.

In GitHub Actions:
    Store the JSON content as secret TIKTOK_COOKIES, then the workflow
    writes it to tiktok_cookies.json before running.
"""

import os


def upload_to_tiktok(
    video_path: str,
    caption: str,
    cookies_path: str = "tiktok_cookies.json",
) -> str | None:
    """Upload a video to TikTok. Returns the video URL or None on failure."""
    if not os.path.exists(cookies_path):
        print(f"[tiktok] Cookies file not found: {cookies_path} — skipping TikTok upload")
        return None
    if not os.path.exists(video_path):
        print(f"[tiktok] Video not found: {video_path}")
        return None

    try:
        from tiktok_uploader.upload import upload_video
    except ImportError:
        print("[tiktok] tiktok-uploader not installed. Run: pip install tiktok-uploader")
        return None

    # Truncate caption to TikTok's 2200 char limit
    caption = caption[:2200]

    try:
        print(f"[tiktok] Uploading: {os.path.basename(video_path)}")
        result = upload_video(
            video_path,
            description=caption,
            cookies=cookies_path,
            headless=True,
        )
        if result:
            url = f"https://www.tiktok.com/@me/video/{result}" if isinstance(result, (int, str)) else "https://www.tiktok.com"
            print(f"[tiktok] Uploaded → {url}")
            return url
        print("[tiktok] Upload returned no ID")
        return None
    except Exception as e:
        print(f"[tiktok] Upload failed: {e}")
        return None
