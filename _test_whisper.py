"""Test Whisper base model on the existing audio with real lyric count."""
import sys, os, re
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

audio = r"output\hugot_ballad_20260503_141911\music.mp3"
ass   = r"output\hugot_ballad_20260503_141911\lyrics.ass"

# Count real lyric lines from existing ASS
lyric_lines = []
with open(ass, encoding="utf-8-sig") as f:
    for line in f:
        if line.startswith("Dialogue:") and ",Lyric," in line:
            lyric_lines.append(line.strip())
print(f"Lyric lines in ASS: {len(lyric_lines)}")

# Run whisper alignment
from music_video import _whisper_align
dummy = ["line"] * len(lyric_lines)
result = _whisper_align(audio, dummy)
if result:
    print(f"\nFirst 8 cues:")
    for i, (s, e) in enumerate(result[:8]):
        print(f"  [{i:02d}] {s:.2f}s - {e:.2f}s")
    print(f"  ...")
    print(f"\nLast 4 cues:")
    for i, (s, e) in enumerate(result[-4:]):
        print(f"  [{len(result)-4+i:02d}] {s:.2f}s - {e:.2f}s")
    print(f"\nTotal cues: {len(result)}, span: {result[0][0]:.1f}s - {result[-1][1]:.1f}s")
else:
    print("Whisper returned None → will use proportional fallback")
