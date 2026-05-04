"""Re-render final.mp4 for hugot_ballad_20260503_153509 using existing clips."""
import os, glob, subprocess, json, shutil
import imageio_ffmpeg
from music_video import (VISUAL_STYLES, _build_filter_complex,
                          _preprocess_clips, get_audio_duration, _build_ass)
from music_topics import get_genre
from thumbnail import generate_music_thumbnail

OUT          = r'C:\Users\onel_\Desktop\Music Niche\faceless-video-automation\output\hugot_ballad_20260503_153509'
audio_path   = os.path.join(OUT, 'music.mp3')
ass_path     = os.path.join(OUT, 'lyrics.ass')
lyrics_path  = os.path.join(OUT, 'lyrics.txt')
output_path  = os.path.join(OUT, 'final.mp4')
song_title   = 'Second Best Na Lang Ba?'
upload_title = '30 Na Ko, Pero Ni Isa, Hindi Ako Pinili \U0001f494'
hook_text    = '30 Na Ko, Pero Ni Isa, Hindi Ako Pinili'
duration     = get_audio_duration(audio_path)
print(f'[rerender] Audio duration before trim: {duration:.1f}s')

# ── Trim music to max 270s (4.5 min) with fade-out ───────────────────────────
MAX_SEC, FADE_SEC = 270, 5
if duration > MAX_SEC:
    tmp = audio_path + '.trimtmp.mp3'
    ffmpeg_trim = imageio_ffmpeg.get_ffmpeg_exe()
    fade_start = MAX_SEC - FADE_SEC
    r = subprocess.run(
        [ffmpeg_trim, '-y', '-i', audio_path,
         '-t', str(MAX_SEC),
         '-af', f'afade=t=out:st={fade_start:.1f}:d={FADE_SEC}',
         '-q:a', '2', tmp],
        capture_output=True,
    )
    if r.returncode == 0:
        shutil.move(tmp, audio_path)
        duration = MAX_SEC
        print(f'[rerender] Trimmed to {MAX_SEC}s with {FADE_SEC}s fade-out')
    else:
        if os.path.exists(tmp):
            os.remove(tmp)
        print('[rerender] Trim failed, keeping original length')
print(f'[rerender] Audio duration: {duration:.1f}s')

# ── Rebuild lyrics.ass with Whisper-aligned timing ───────────────────────────
with open(lyrics_path, 'r', encoding='utf-8') as f:
    lyrics_text = f.read()
story_cards = [
    'Nakakapagod ang hindi piliin.',
    'Hindi man lang ako nasubukan.',
    'Para sa mga laging option B.',
]
pull_quotes = [
    'Parang hindi ako deserving piliin.',
    'Balang araw, mapipili rin ako.',
]
_build_ass(lyrics_text, duration, VISUAL_STYLES.get('cinematic', {}),
           ass_path, is_opm=True, story_cards=story_cards,
           pull_quotes=pull_quotes, audio_path=audio_path)
print(f'[rerender] lyrics.ass rebuilt')

clip_paths = sorted(
    glob.glob(os.path.join(OUT, '_clip*.mp4')),
    key=lambda p: int(os.path.basename(p).replace('_clip', '').replace('.mp4', ''))
)
print(f'[rerender] Clips found: {len(clip_paths)}')
if not clip_paths:
    raise RuntimeError('No clips found')

genre_dict = get_genre('hugot_ballad')
visual_key = genre_dict.get('video_style', 'cinematic')
vstyle = VISUAL_STYLES.get(visual_key, VISUAL_STYLES['cinematic'])
print(f'[rerender] Visual style: {visual_key}')

ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
log_path = os.path.join(OUT, '_ffmpeg.log')

# ── Pass 1: Pre-process each clip one-at-a-time ──────────────────────────────
# Pre-processing runs one clip at a time so the loop/scale/crop step never
# needs more than ~3GB of RAM (vs ~48GB for all 18 clips simultaneously).
# Supports crash recovery: already-preprocessed clips are skipped.
print('[rerender] Pass 1 — pre-processing clips (Ken Burns + normalize)...')
proc_paths = _preprocess_clips(clip_paths, OUT, ffmpeg, vstyle, log_path)
print(f'[rerender] Pre-processed {len(proc_paths)} clips')

# ── Pass 2: Compose final video ───────────────────────────────────────────────
def _run(with_title, use_nvenc=True):
    fc = _build_filter_complex(
        n_clips=len(proc_paths), vstyle=vstyle, duration=duration,
        ass_path=ass_path, title=song_title, hook_text=hook_text,
        with_title_card=with_title,
        preprocessed=True,
    )
    if use_nvenc:
        vcodec = ['-c:v', 'h264_nvenc', '-preset', 'p4', '-cq', '19', '-b:v', '0']
        enc_label = 'nvenc/GPU'
    else:
        vcodec = ['-c:v', 'libx264', '-preset', 'ultrafast', '-crf', '19']
        enc_label = 'libx264/CPU'

    cmd = [ffmpeg, '-y']
    for cp in proc_paths:
        cmd += ['-i', cp]
    cmd += ['-i', audio_path,
            '-filter_complex', fc,
            '-map', '[vout]',
            '-map', f'{len(proc_paths)}:a:0',
            '-t', str(duration)]
    cmd += vcodec
    cmd += ['-c:a', 'aac', '-b:a', '192k',
            '-pix_fmt', 'yuv420p',
            '-movflags', '+faststart',
            output_path]
    print(f'[rerender] Pass 2 — encoding with {enc_label} (title_card={with_title}) — log: {log_path}')
    with open(log_path, 'a') as log_f:
        r = subprocess.run(cmd, stdout=log_f, stderr=log_f, timeout=1800)
    return r

def _is_valid(path):
    """Return True if ffmpeg can fully decode the file without errors."""
    chk = subprocess.run(
        [ffmpeg, '-v', 'error', '-i', path, '-f', 'null', '-'],
        capture_output=True, text=True, timeout=60,
    )
    return chk.returncode == 0

if _is_valid(output_path):
    print(f'[rerender] final.mp4 already valid ({os.path.getsize(output_path)/1024/1024:.1f} MB), skipping encode')
else:
    r = _run(True, use_nvenc=True)
    if r.returncode != 0:
        print('[rerender] NVENC failed, retrying with CPU...')
        r = _run(True, use_nvenc=False)
    if r.returncode != 0:
        print('[rerender] Title card failed, retrying without...')
        r = _run(False, use_nvenc=False)
    if r.returncode != 0:
        try:
            lines = open(log_path).readlines()
            print(''.join(lines[-50:]))
        except Exception:
            pass
        raise RuntimeError('ffmpeg failed — see ' + log_path)
    print(f'[rerender] final.mp4 done ({os.path.getsize(output_path)/1024/1024:.1f} MB)')

# Clean up preprocessed temp files
for cp in proc_paths:
    if os.path.exists(cp):
        os.remove(cp)

# Thumbnail
thumbnail_path = os.path.join(OUT, 'thumbnail.png')
generate_music_thumbnail(title=upload_title, genre_key='hugot_ballad',
                         output_path=thumbnail_path, video_path=output_path,
                         story_hook=hook_text or None)
print(f'[rerender] thumbnail done')

# Metadata
meta_path = os.path.join(OUT, 'metadata.json')
with open(meta_path, 'w', encoding='utf-8') as f:
    json.dump({'title': upload_title, 'song_title': song_title,
               'genre': 'hugot_ballad', 'style': genre_dict['style'],
               'duration': duration, 'hook_text': hook_text},
              f, indent=2, ensure_ascii=False)
print('[rerender] ALL DONE')
