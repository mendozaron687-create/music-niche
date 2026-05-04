import sys
sys.path.insert(0, '.')
from dotenv import load_dotenv
load_dotenv()
from music_video import _whisper_word_captions

caps = _whisper_word_captions('output/hugot_ballad_20260503_153509/music.mp3')
if caps:
    print(f'{len(caps)} captions')
    for c in caps[:12]:
        print(f'  {c["start"]:.1f}s - {c["end"]:.1f}s: {c["text"]}')
else:
    print('FAILED - no captions returned')
