"""
Music genre/style topic picker for the YouTube Music Niche channel.

Genres are designed for high watch-time (3-6 min tracks):
  lofi, cinematic, epic orchestral, dark ambient, chill pop, phonk, etc.

Each genre entry has:
  style        — Suno style string
  mood_tags    — used in Pexels background search
  youtube_tags — for SEO
  video_style  — visual treatment: 'lofi' | 'cinematic' | 'dark' | 'nature' | 'city'
"""

import random

GENRES = {
    "lofi_hiphop": {
        "style": "lo-fi hip hop, chill beats, jazzy, mellow, vintage, relaxing study music",
        "title_templates": [
            "Lo-Fi Chill Beats 🎧 | Study & Relax | {duration} Hours",
            "Lofi Hip Hop Radio 🎵 | Chill Beats to Study/Relax To",
            "Aesthetic Lofi Beats 🌙 | Late Night Study Session",
            "Chill Lofi Mix 🍃 | Focus Music for Deep Work",
            "Lofi Bedroom Beats 🎹 | Calm Your Mind",
        ],
        "lyric_prompt": "a chill lo-fi hip hop song about late nights, studying, rainy windows, warm coffee, and peaceful solitude. Dreamy, introspective, short verses.",
        "mood_tags": ["lofi", "coffee shop", "rain window", "study desk", "night city"],
        "youtube_tags": ["lofi", "chillbeats", "studymusic", "lofihiphop", "relaxingmusic", "chillhop", "aestheticmusic", "focusmusic"],
        "video_style": "lofi",
    },
    "cinematic_orchestral": {
        "style": "epic cinematic orchestral, Hans Zimmer inspired, sweeping strings, powerful percussion, emotional, trailer music",
        "title_templates": [
            "Epic Cinematic Music 🎬 | Most Powerful Orchestral Pieces",
            "Epic Orchestra | Emotional Cinematic Soundtrack {year}",
            "Most Epic Music Ever Made 🔥 | Cinematic Orchestral Mix",
            "Powerful Cinematic Orchestral Music | Epic Battle Themes",
            "Emotional Orchestral Music 🎻 | Cinematic Masterpiece",
        ],
        "lyric_prompt": "an epic cinematic orchestral song about rising against all odds, battle, triumph, and destiny. Powerful, emotional, anthem-like chorus.",
        "mood_tags": ["mountains", "epic landscape", "storm", "dark clouds", "warrior", "ancient ruins"],
        "youtube_tags": ["epicmusic", "cinematicmusic", "orchestralmusic", "epicorchestra", "trailermusic", "powerfulmusic", "emotionalmusic"],
        "video_style": "cinematic",
    },
    "dark_ambient": {
        "style": "dark ambient, atmospheric, eerie, deep drone, horror soundscape, cinematic tension",
        "title_templates": [
            "Dark Ambient Music 🖤 | Deep Atmospheric Soundscape",
            "Horror Ambient Mix 😱 | Scary Background Music",
            "Dark Cinematic Atmosphere 🌑 | Tension & Mystery Music",
            "Creepy Ambient Soundscape | Dark Fantasy Music",
            "Eerie Atmospheric Music 🌫️ | Deep Focus Dark Ambient",
        ],
        "lyric_prompt": "a dark atmospheric ambient song about shadows, the unknown, deep space, and the void. Minimal, haunting, poetic imagery.",
        "mood_tags": ["dark forest", "fog", "abandoned building", "night sky", "shadow", "dark clouds"],
        "youtube_tags": ["darkambient", "atmosphericmusic", "ambientmusic", "darkmusic", "horrorsoundtrack", "deepambient"],
        "video_style": "dark",
    },
    "phonk": {
        "style": "phonk, dark trap, distorted 808s, memphis rap, aggressive, drift phonk, cowbell, vinyl crackle",
        "title_templates": [
            "PHONK MIX 🔥 | Aggressive Drift Phonk 2026",
            "Dark Phonk Music ⚡ | Best Phonk Songs Mix",
            "Phonk Playlist 💀 | Dark Trap Bangers",
            "Aggressive Phonk Mix 🔥 | Gym & Workout Music",
            "DARK PHONK 😤 | Motivation & Energy Boost",
        ],
        "lyric_prompt": "a dark phonk rap song about dominance, grinding, street life, fast cars drifting at night, never stopping. Hard-hitting, short punchy lines.",
        "mood_tags": ["night city", "car drift", "dark street", "neon lights", "urban"],
        "youtube_tags": ["phonk", "darkphonk", "driftphonk", "phonkmusic", "phonkmix", "trapmusic", "workoutmusic", "gymmusic"],
        "video_style": "city",
    },
    "chill_pop": {
        "style": "chill pop, indie pop, dreamy, bedroom pop, soft synths, warm vocals, nostalgic, summer vibes",
        "title_templates": [
            "Chill Pop Music 🌸 | Feel Good Indie Songs 2026",
            "Aesthetic Bedroom Pop 🌙 | Soft Indie Music Mix",
            "Dreamy Chill Pop Playlist ☁️ | Good Vibes Only",
            "Summer Indie Pop Mix 🌊 | Chill Good Feeling Music",
            "Soft Pop Vibes 🌷 | Relax & Feel Good Music",
        ],
        "lyric_prompt": "a dreamy chill pop song about summer nostalgia, young love, golden hour drives, and living in the moment. Catchy hook, soft verse.",
        "mood_tags": ["summer beach", "golden hour", "flower field", "road trip", "sunset"],
        "youtube_tags": ["chillpop", "indiepop", "bedroompop", "aestheticmusic", "feelgoodmusic", "summermusic", "chillsongs"],
        "video_style": "nature",
    },
    "nature_meditation": {
        "style": "meditation music, ambient nature, singing bowls, flute, deep relaxation, healing frequencies, binaural",
        "title_templates": [
            "Deep Meditation Music 🧘 | Relax Mind Body Soul",
            "Healing Meditation Music 432Hz 🌿 | Stress Relief",
            "Nature Meditation Sounds 🍃 | Deep Sleep & Relaxation",
            "Tibetan Singing Bowls 🪘 | 1 Hour Meditation Music",
            "Calm Your Mind 🌊 | Healing Frequencies 528Hz",
        ],
        "lyric_prompt": "a healing meditation song with gentle affirmations about peace, inner calm, breathing, releasing stress, and connecting with nature. Slow, soft, mantra-like.",
        "mood_tags": ["nature waterfall", "zen garden", "forest", "mountain lake", "sunrise nature"],
        "youtube_tags": ["meditationmusic", "relaxingmusic", "healingmusic", "sleepmusic", "ambientmusic", "432hz", "naturesounds", "stressrelief"],
        "video_style": "nature",
    },
    "motivational_hip_hop": {
        "style": "motivational hip hop, uplifting rap, inspiring beats, boom bap, empowerment anthem, positive energy",
        "title_templates": [
            "Motivational Hip Hop Mix 🔥 | Rap Songs to Get You Going",
            "Best Motivational Rap 💪 | Workout & Hustle Music 2026",
            "Hip Hop Motivation 🎯 | Songs for Grinders & Dreamers",
            "Uplifting Rap Playlist ⚡ | Rise Up & Conquer",
            "Motivational Music 🏆 | Greatest Rap Anthems",
        ],
        "lyric_prompt": "a powerful motivational hip hop song about rising from nothing, grinding, believing in yourself, never giving up, and proving doubters wrong. Strong hook, confident verses.",
        "mood_tags": ["sunrise city", "boxing gym", "mountains", "highway", "skyscraper"],
        "youtube_tags": ["motivationalmusic", "motivationalhiphop", "rapmusic", "workoutmusic", "gymmusic", "hustle", "inspiration", "motivationrap"],
        "video_style": "city",
    },
    "sleep_music": {
        "style": "deep sleep music, gentle piano, soft ambient pads, lullaby, calming, 8 hours sleep, peaceful",
        "title_templates": [
            "Deep Sleep Music 😴 | 3 Hours Relaxing Piano",
            "Sleep Music 🌙 | Calm Piano & Ambient Sounds for Deep Sleep",
            "Relaxing Sleep Sounds 💤 | Fall Asleep Fast Tonight",
            "Peaceful Piano Sleep Music 🎹 | Stress Relief & Insomnia Help",
            "3 Hour Sleep Music 🌌 | Soft Ambient for Deep Restful Sleep",
        ],
        "lyric_prompt": "a gentle sleep lullaby about drifting off to dreamland, peaceful night sky, soft moonlight, and deep rest. Very slow, soothing, simple melody.",
        "mood_tags": ["night sky stars", "ocean waves", "fireplace", "moonlight", "calm lake"],
        "youtube_tags": ["sleepmusic", "relaxingmusic", "deepsleeep", "calmmusic", "pianomusic", "ambientmusic", "insomnia", "sleepsounds"],
        "video_style": "nature",
    },

    # ── OPM / Hugot Tagalog genres ──────────────────────────────────────────
    # Lyrics are generated via OpenRouter LLM (lyrics_generator.py) using
    # real-time trending PH stories from trending_ph.py.
    # These genre entries are used for Suno style + video/thumbnail settings.

    "hugot_ballad": {
        "style": "OPM ballad, hugot, emotional Filipino pop, slow piano, heartbreak, cinematic strings, soulful vocals",
        "title_templates": [
            "{song_title} — OPM Hugot Ballad 🎵",
            "{song_title} | Pinoy Love Song 💔",
            "{song_title} — Filipino Heartbreak Song",
            "{song_title} | OPM Trending 2026 🇵🇭",
            "{song_title} — Hugot ng Puso 🎶",
        ],
        "lyric_prompt": "slow OPM hugot ballad in Tagalog about heartbreak, longing, and sawi love. Cinematic, poetic, deeply emotional.",
        "mood_tags": ["rain window", "city lights night", "couple silhouette", "lonely street", "candle light"],
        "youtube_tags": ["OPM", "hugot", "Tagalog", "OPMballad", "PinoyMusic", "heartbreak", "hugotlines",
                         "OPM2026", "Philippinesmusic", "sawi", "hugotsongs2026", "bagongOPM",
                         "pinakamahusaynahugot", "tagaloglovesongs", "brokenheartedtagalog",
                         "hugotlyrics", "OPMnewrelease", "BenAndBeninspired", "kiligOPM"],
        "video_style": "cinematic",
        "lang": "tl",
    },
    "hugot_opm_pop": {
        "style": "OPM pop, catchy Taglish, acoustic guitar, feel-good sad, Filipino millennial anthem, Ben&Ben style",
        "title_templates": [
            "{song_title} 🌧️ | OPM Hit 2026",
            "{song_title} — Taglish Pop Hugot",
            "{song_title} | Pinoy Feel-Good Sad Song 🎸",
            "{song_title} — OPM Trending Playlist 🇵🇭",
            "{song_title} | Hugot OPM Pop 2026",
        ],
        "lyric_prompt": "catchy OPM pop in Taglish about bittersweet love, moving on, and Filipino youth emotions. Shareable, quotable hook.",
        "mood_tags": ["coffee shop", "rainy street manila", "young couple", "sunset city", "acoustic performance"],
        "youtube_tags": ["OPM", "Taglish", "OPMpop", "hugot", "PinoyPop", "BenAndBen", "MoiraDelaTorre",
                         "OPM2026", "PinoyMusic", "viral", "hugotsongs2026", "bagongOPM2026",
                         "OPMhit", "tagaloglovesongs", "pinoyfeelgood", "hugotlines", "OPMnewrelease"],
        "video_style": "lofi",
        "lang": "tl",
    },
    "pinoy_rap_hugot": {
        "style": "Pinoy rap, trap OPM, hugot rap, Tagalog hip hop, Flow G style, emotional bars, 808 bass, Filipino urban",
        "title_templates": [
            "{song_title} 🔥 | Pinoy Rap Hugot",
            "{song_title} — Tagalog Trap 2026",
            "{song_title} | OPM Rap Hugot Banger",
            "{song_title} — Flow G Style Hugot Rap 🇵🇭",
            "{song_title} | Pinoy Hip Hop 2026 🎤",
        ],
        "lyric_prompt": "Pinoy trap/rap hugot in Tagalog. Emotional bars about betrayal, moving on, heartbreak. Hard-hitting but heartfelt chorus.",
        "mood_tags": ["neon city manila", "basketball court night", "urban street", "dark alley lights", "roof top city"],
        "youtube_tags": ["PinoyRap", "hugotrap", "TagalogRap", "FlowG", "SkustaClee", "OPMrap",
                         "PinoyHiphop", "hugot", "viral2026", "PhilippinesRap", "hugotsongs2026",
                         "tagalograp2026", "OPMnewrelease", "bagongOPM", "hugotlines"],
        "video_style": "city",
        "lang": "tl",
    },
    "opm_rnb_hugot": {
        "style": "OPM R&B, smooth Filipino soul, neo-soul, emotional Tagalog vocals, late night vibes, Arthur Nery inspired",
        "title_templates": [
            "{song_title} 🌙 | OPM R&B Hugot",
            "{song_title} — Smooth Pinoy Soul",
            "{song_title} | Late Night OPM 2026",
            "{song_title} — Filipino Neo-Soul Hugot 🎷",
            "{song_title} | OPM R&B Trending 🇵🇭",
        ],
        "lyric_prompt": "smooth OPM R&B hugot in Tagalog. Late night, introspective, missing someone. Silky vocal runs in the chorus.",
        "mood_tags": ["city lights rain", "jazz club manila", "late night coffee", "empty room", "neon reflections"],
        "youtube_tags": ["OPMrnb", "ArthurNery", "PinoyRnB", "hugot", "neosoul", "OPM2026",
                         "TagalogSoul", "PinoyMusic", "smoothOPM", "latenightmusic",
                         "hugotsongs2026", "bagongOPM", "tagaloglovesongs", "OPMnewrelease", "hugotlines"],
        "video_style": "city",
        "lang": "tl",
    },
    "pamana_folk_opm": {
        "style": "Filipino folk OPM, acoustic guitar, heartfelt, Tagalog storytelling, Rivermaya inspired, warm, organic",
        "title_templates": [
            "{song_title} 🎸 | OPM Folk Hugot",
            "{song_title} — Pinoy Acoustic Love Song",
            "{song_title} | Heartfelt Filipino Folk Song 2026",
            "{song_title} — Tagalog Folk Ballad 🇵🇭",
            "{song_title} | OPM Acoustic Trending",
        ],
        "lyric_prompt": "heartfelt Filipino acoustic folk OPM in Tagalog. Storytelling style about love, family, OFW longing, or bittersweet memories.",
        "mood_tags": ["provincial Philippines", "beach sunset", "rice fields", "old house", "guitar by the sea"],
        "youtube_tags": ["OPMfolk", "Rivermaya", "Eraserheads", "Bamboo", "PinoyAcoustic",
                         "TagalogFolk", "hugot", "OPM2026", "PinoyMusic", "acoustic",
                         "hugotsongs2026", "bagongOPM", "OPMnewrelease", "hugotlines", "tagaloglovesongs"],
        "video_style": "nature",
        "lang": "tl",
    },

    # ── Feel-Good Original Love Song genre ──────────────────────────────────
    # Original compositions — no trending news. Copyright-safe.
    # Primary genre: upbeat funky pop OPM love song.

    "opm_funky_love": {
        "style": (
            "A catchy, feel-good love song with a smooth funky pop style inspired by modern "
            "retro R&B. Upbeat groove, warm bassline, clean guitar riffs, soft synth layers, "
            "and a danceable rhythm. The vibe is romantic, playful, and slightly flirtatious—"
            "like falling in love unexpectedly. Male vocals with soulful delivery, light "
            "falsetto moments, and catchy melodic hooks. Chorus is addictive and easy to sing "
            "along to. Tempo is mid-to-upbeat, perfect for dancing or cruising at night. "
            "Overall mood: joyful, charming, and uplifting love energy."
        ),
        "title_templates": [
            "{song_title} 🎶 | OPM Feel-Good Love Song 2026",
            "{song_title} — Bagong OPM Funky Pop",
            "{song_title} | Pinoy Funky Love Song 🇵🇭",
            "{song_title} — OPM Pop Love 2026 🔥",
            "{song_title} | Feel-Good OPM Music 2026",
        ],
        "lyric_prompt": "a catchy feel-good OPM love song in Taglish with upbeat funky pop vibes, romantic and playful.",
        "mood_tags": ["romantic couple sunset", "city lights night", "dancing couple", "neon city", "golden hour philippines"],
        "youtube_tags": [
            "OPMlove", "OPM2026", "OPMpop", "PinoyMusic", "TagalogLoveSong",
            "OPMhits", "BagongOPM", "feelgoodmusic", "FilipinoLoveSong",
            "OPMnewrelease", "PinoyRnB", "OPMvibes", "romanticOPM",
            "funkyPOP", "OPMdance",
        ],
        "video_style": "city",
        "lang": "tl",
    },

    # ── Political / Rant / Social Commentary genres ─────────────────────────
    # Triggered by political/social trending topics on YouTube PH.
    # Inspired by Filipino frustration with government, corruption, daily struggles.

    "pinoy_rant": {
        "style": "Pinoy rant rap, angry Tagalog hip hop, social commentary, spoken word, trap beat, frustrated Filipino, political satire, raw vocals",
        "title_templates": [
            "{song_title} 🔥 | Pinoy Rant Song",
            "{song_title} — Galit na Galit na Pilipino 😤",
            "{song_title} | OPM Social Commentary 2026",
            "{song_title} — Boses ng Bayan 🇵🇭",
            "{song_title} | Pinoy Protest Song 2026",
        ],
        "lyric_prompt": (
            "angry Pinoy rant rap/spoken word in Tagalog about government corruption, "
            "rising prices, broken promises, and everyday Filipino struggles. "
            "Blunt, sarcastic, but emotionally raw — the kind of song a frustrated "
            "Filipino worker sings after a long terrible day. Strong hook, quotable lines."
        ),
        "mood_tags": ["protest crowd", "night street manila", "traffic", "construction", "poverty urban"],
        "youtube_tags": ["PinoyRant", "SocialCommentary", "PinoyRap", "TagalogRap",
                         "PolitikaPH", "BosBayan", "OPM2026", "viral", "trending",
                         "PhilippinesNews", "Hugot", "PinoyHiphop", "rantmusic",
                         "PinoyProtestSong", "galit", "FrustratedFilipino"],
        "video_style": "city",
        "lang": "tl",
    },
    "pinoy_protest_anthem": {
        "style": "Filipino protest anthem, OPM rock, powerful choir, emotional, Pinoy rally music, Noel Cabangon style, call to action, acoustic to electric build",
        "title_templates": [
            "{song_title} 🇵🇭 | Pinoy Protest Anthem",
            "{song_title} — Laban Tayo! OPM 2026",
            "{song_title} | Filipino Rally Song 🔊",
            "{song_title} — Boses ng Sambayanan",
            "{song_title} | OPM Protest Music 2026",
        ],
        "lyric_prompt": (
            "a powerful Filipino protest anthem in Tagalog about standing up for truth, "
            "fighting corruption, and the resilience of the Filipino people. "
            "Inspired by Noel Cabangon, APO Hiking Society, and Freddie Aguilar. "
            "Starts soft and builds to a rousing chorus that makes you want to raise your fist."
        ),
        "mood_tags": ["protest rally", "Philippine flag", "sunset Philippines", "crowd power", "fist raised"],
        "youtube_tags": ["PinoyProtest", "ProtestAnthem", "OPMrock", "PinoyRock",
                         "FreddieAguilar", "NoelCabangon", "Bayan", "LKB", "OPM2026",
                         "PinoyPride", "TagalogRock", "FightingSpirit", "Philippines2026",
                         "sambayanan", "laban", "PatrioticOPM"],
        "video_style": "cinematic",
        "lang": "tl",
    },
}


def get_random_genre() -> tuple[str, dict]:
    """Return (genre_key, genre_dict) — opm_funky_love is the primary genre."""
    return "opm_funky_love", GENRES["opm_funky_love"]


def get_genre(genre_key: str) -> dict:
    return GENRES.get(genre_key, GENRES["lofi_hiphop"])


def build_video_title(genre_dict: dict, duration_min: int = 4, song_title: str = "") -> str:
    import random, datetime
    template = random.choice(genre_dict["title_templates"])
    return template.format(
        duration=duration_min,
        year=datetime.date.today().year,
        song_title=song_title or "Pag-ibig",
    )


def get_pexels_keywords(genre_dict: dict) -> list[str]:
    return genre_dict.get("mood_tags", ["nature", "city"])
