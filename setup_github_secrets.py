"""
Run this locally AFTER logging in with the new YouTube account.
It prints the values you need to paste into GitHub Secrets.

Usage:
  python setup_github_secrets.py
"""
import json
import os

base = os.path.dirname(__file__)

def read_and_print(label: str, path: str):
    if not os.path.exists(path):
        print(f"[!] {label}: file not found at {path}")
        return
    with open(path) as f:
        content = f.read().strip()
    print(f"\n{'='*60}")
    print(f"Secret name : {label}")
    print(f"Secret value (paste this into GitHub):")
    print(f"{'='*60}")
    print(content)

read_and_print("YOUTUBE_TOKEN", os.path.join(base, "token.json"))
read_and_print("YOUTUBE_CREDS", os.path.join(base, "credentials.json"))

print("\n\nAlso add these from your .env:")
env_keys = ["KIE_API_KEY", "SUNO_API_KEY", "OPENROUTER_API_KEY", "PEXELS_API_KEY", "GROQ_API_KEY", "GEMINI_API_KEY"]
env_path = os.path.join(base, ".env")
if os.path.exists(env_path):
    env = {}
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if "=" in line and not line.startswith("#"):
                k, _, v = line.partition("=")
                env[k.strip()] = v.strip()
    print(f"\n{'='*60}")
    for k in env_keys:
        v = env.get(k, "NOT FOUND")
        print(f"  {k} = {v}")
    print(f"{'='*60}")
