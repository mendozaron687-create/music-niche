"""
Drop your raw cookie string into cookies_raw.txt, then run:
    python update_cookies.py

It will convert it to cookies.json automatically.

How to get raw cookies:
  1. Open Chrome → gemini.google.com (signed into your Pro account)
  2. Press F12 → Application tab → Cookies → https://gemini.google.com
  3. Or: DevTools → Console → type: document.cookie
  4. Copy the full string and paste into cookies_raw.txt
"""
import json, os, sys

raw_file = "cookies_raw.txt"
out_file = "cookies.json"

if not os.path.exists(raw_file):
    print(f"Create '{raw_file}' and paste your raw cookie string into it, then re-run.")
    sys.exit(1)

with open(raw_file, "r", encoding="utf-8") as f:
    raw = f.read().strip()

cookies = []
for part in raw.split("; "):
    part = part.strip()
    if "=" not in part:
        continue
    name, _, value = part.partition("=")
    name = name.strip()
    value = value.strip()
    secure = name.startswith("__Secure-") or name.startswith("__Host-")
    cookies.append({
        "name": name,
        "value": value,
        "domain": ".google.com",
        "path": "/",
        "secure": secure,
        "httpOnly": False,
    })

with open(out_file, "w", encoding="utf-8") as f:
    json.dump(cookies, f, indent=2)

print(f"Written {len(cookies)} cookies to {out_file}")
