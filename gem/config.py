"""Settings, data paths and small JSON stores.

User-editable settings live in %USERPROFILE%\\.gem\\settings.json. Anything Gem
changes on its own (current mode, overlay position, ...) goes to runtime.json
so the settings file is never rewritten behind the user's back.

Not AppData: Microsoft Store Python silently redirects AppData writes into its
sandbox, where Explorer, Notepad and the built exe would never see them.
"""
import copy
import json
import logging
import os
import sys
import threading

log = logging.getLogger("gem.config")

APP_NAME = "Gem"


def _data_dir():
    path = os.path.join(os.path.expanduser("~"), ".gem")
    os.makedirs(path, exist_ok=True)
    return path


DATA_DIR = _data_dir()
SETTINGS_FILE = os.path.join(DATA_DIR, "settings.json")
RUNTIME_FILE = os.path.join(DATA_DIR, "runtime.json")
LOG_FILE = os.path.join(DATA_DIR, "gem.log")
NOTES_FILE = os.path.join(DATA_DIR, "notes.md")
VOICE_CACHE_DIR = os.path.join(DATA_DIR, "voice_cache")

if getattr(sys, "frozen", False):
    PROJECT_DIR = os.path.dirname(sys.executable)
else:
    PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

_HOME = os.path.expanduser("~")

# ── Defaults ──────────────────────────────────────────────────────────────────

DEFAULTS = {
    "user_name": "Parshv",
    "home_city": "",

    "listening": {
        # "push_to_talk" or "always_listening". Triple-tap Caps Lock switches.
        "default_mode": "push_to_talk",
        # Seconds after Gem replies during which follow-ups count as addressed to her.
        "conversation_window": 25,
        # Part of the microphone name to use; blank = Windows default.
        "input_device": "",
        # 0-3, higher = stricter about what counts as speech.
        "vad_aggressiveness": 2,
    },

    "keys": {
        # Presses shorter than this are taps; longer are holds.
        "hold_ms": 250,
        "triple_tap_ms": 900,
        "command_bar": "ctrl+alt+space",
        "panic": "ctrl+alt+shift+tab+p",
    },

    "lights": {"enabled": True, "animate": True, "flash_on_alerts": True},

    "voice": {
        # "piper" (on this PC: instant, same voice every time), "edge" (online Microsoft voices, can lag)
        # or "sapi" (the old Windows voices).
        "engine": "piper",
        "piper_voice": "en_US-amy-medium",
        "edge_voice": "en-US-AvaMultilingualNeural",
        "sapi_voice": "Zira",
        "rate": "+5%",
        "volume": 0.9,
        "speak_in_calls": False,
        "duck_others": True,                  # lower other apps while you talk to Gem or she speaks
        "duck_level": 0.3,
        "speak_in_gaming": False,
        # Softer at night so Gem doesn't wake anyone: [start hour, end hour] and how loud then.
        "quiet_hours": [23, 7],
        "quiet_volume": 0.55,
    },

    "stt": {
        "backends": ["groq", "google"],
        "groq_models": ["whisper-large-v3-turbo", "whisper-large-v3"],
        "language": "en",
    },

    "ai": {
        "models": ["openai/gpt-oss-120b", "qwen/qwen3.8-27b", "openai/gpt-oss-20b"],
        # Used by "explain my screen"; must accept images.
        "vision_models": ["qwen/qwen3.8-27b"],
        "reasoning_effort": "low",
        "history_turns": 4,
        # Used only when Groq is rate limited or down, and only if its key is set (an environment variable,
        # or the Backup AI field in the dashboard). Any OpenAI-compatible service can be added here.
        "backups": [
            # Cerebras' free tier runs the same gpt-oss-120b as Groq with a much bigger daily allowance (1M tokens,
            # 5 requests a minute per model); its Qwen takes up to two images.
            {"name": "Cerebras", "key_env": "CEREBRAS_API_KEY",
             "url": "https://api.cerebras.ai/v1/chat/completions",
             "models": ["gpt-oss-120b", "qwen-3.8-27b"], "vision_models": ["qwen-3.8-27b"],
             "extra": {"reasoning_effort": "low"}},
            {"name": "Gemini", "key_env": "GEMINI_API_KEY",
             "url": "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions",
             "models": ["gemini-flash-latest", "gemini-flash-lite-latest"], "vision_models": ["gemini-flash-latest"],
             "extra": {"reasoning_effort": "none"}},
            {"name": "OpenRouter", "key_env": "OPENROUTER_API_KEY",
             "url": "https://openrouter.ai/api/v1/chat/completions",
             "models": ["openai/gpt-oss-120b:free", "meta-llama/llama-3.3-70b-instruct:free"], "vision_models": []},
        ],
    },

    "calls": {
        "auto_detect": True,
        # Mic users that never count as a call (substring match on the app id).
        "ignore_apps": ["python", "gem.exe", "gem2.exe"],
    },

    # Only respond to your voice when always listening ("learn my voice", "only listen to me").
    # threshold: how closely speech must match your voiceprint (0.38 relaxed, 0.45 normal, 0.52 strict).
    "voice_lock": {
        "threshold": 0.45,
        "learn_from_push_to_talk": True,
        # Holding Caps Lock is checked too (a bit more forgiving; too-short clips like "pause" still pass).
        "in_push_to_talk": True,
    },

    # In a game, shout one of these (or say "clip that") and Gem clips the last 30 seconds with Game Bar.
    # Checked on this PC only. loudness_ratio: how much louder than your normal game voice counts as hype.
    "auto_clip": {
        "enabled": True,
        "phrases": ["let's go", "lets go", "no way", "oh my god", "clip that", "clip it", "what a shot", "insane",
                    "get in", "yes yes yes", "that was crazy", "no shot", "what was that"],
        "cooldown_seconds": 25,
        "loudness_ratio": 1.35,
        "only_my_voice": True,
    },

    # Gem speaks up first: rain soon (needs your city), finished downloads, a PC that's struggling, low battery.
    "heads_up": {"rain": True, "downloads": True, "pc": True, "dates": True, "air": True},

    # Remember lasting things you mention in conversation ("I main Jett") without "remember that".
    "auto_memory": True,

    # "Mute me" / "deafen me": must match Toggle Mute / Toggle Deafen in Discord's Keybinds settings.
    "discord": {
        "mute_keys": "ctrl+shift+m",
        "deafen_keys": "ctrl+shift+d",
    },

    # Big steps wait for a set phrase: the first one approves sending (messages, emails, Enter in a chat), the last one
    # everything else (Enter in a terminal, deleting files, risky clicks, power, plans Gem worked out). "Yes" isn't
    # enough, and if Gem knows your voice it has to be you. Scheduled runs skip big steps and tell you afterwards.
    "safety": {
        "confirm_phrases": ["send it", "confirm"],
        "confirm_seconds": 45,
        # Always listening, before Gem knows your voice: say "Gem, send it" so a video saying "send it" can't send.
        "name_needed_without_voice_lock": True,
        # Show the steps of anything Gem works out itself ("figure out how to ...") and wait for "confirm" first.
        "confirm_ai_plans": True,
    },

    "macros": {
        "step_delay": 0.15,                   # seconds between steps, so apps keep up
        "max_steps": 200,
        "record_minutes": 10,                 # a recording stops by itself after this long
    },

    "snooze_minutes": 10,

    # Typed by "tell them I'm away". {name} = your name, {when} = "in about 20 minutes" / "soon".
    "away_message": "{name} isn't here right now, this is his voice assistant speaking. He'll be back {when}.",

    "reminders": {
        "break_minutes": 20,
        "break_message": "Time for a quick break. Drink some water.",
        "alarm_sound": True,
        "class_heads_up_minutes": 5,          # warn this long before a class (0 = off)
    },

    "focus": {"work_minutes": 25, "break_minutes": 5},

    # Spoken name -> what to launch. Values can be a full path, a Start Menu
    # entry name, or a URL. Anything not listed is found in the Start Menu.
    "apps": {
        "brave": r"C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe",
        "chrome": r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        "spotify": _HOME + r"\AppData\Roaming\Spotify\Spotify.exe",
        "steam": r"C:\Program Files (x86)\Steam\steam.exe",
        "epic games": r"C:\Program Files (x86)\Epic Games\Launcher\Portal\Binaries\Win32\EpicGamesLauncher.exe",
        "epic": r"C:\Program Files (x86)\Epic Games\Launcher\Portal\Binaries\Win32\EpicGamesLauncher.exe",
        "fortnite": r"C:\Program Files\Epic Games\Fortnite\FortniteGame\Binaries\Win64\FortniteClient-Win64-Shipping.exe",
        "lunar client": _HOME + r"\AppData\Roaming\lunarclient\app-stable\Lunar Client.exe",
        "lunar": _HOME + r"\AppData\Roaming\lunarclient\app-stable\Lunar Client.exe",
        "vs code": "Visual Studio Code",
        "vscode": "Visual Studio Code",
        "visual studio code": "Visual Studio Code",
        "word": r"C:\Program Files\Microsoft Office\root\Office16\WINWORD.EXE",
        "excel": r"C:\Program Files\Microsoft Office\root\Office16\EXCEL.EXE",
        "powerpoint": r"C:\Program Files\Microsoft Office\root\Office16\POWERPNT.EXE",
    },

    # Spoken name -> process name(s), for closing apps and per-app volume.
    "processes": {
        "brave": ["brave.exe"],
        "chrome": ["chrome.exe"],
        "edge": ["msedge.exe"],
        "discord": ["discord.exe"],
        "spotify": ["spotify.exe"],
        "steam": ["steam.exe", "steamwebhelper.exe"],
        "epic": ["epicgameslauncher.exe"],
        "epic games": ["epicgameslauncher.exe"],
        "fortnite": ["fortniteclient-win64-shipping.exe"],
        "lunar": ["lunar client.exe"],
        "lunar client": ["lunar client.exe"],
        "minecraft": ["javaw.exe", "minecraft.windows.exe"],
        "roblox": ["robloxplayerbeta.exe"],
        "rocket league": ["rocketleague.exe"],
        "vs code": ["code.exe"],
        "vscode": ["code.exe"],
        "notepad": ["notepad.exe"],
        "word": ["winword.exe"],
        "excel": ["excel.exe"],
        "powerpoint": ["powerpnt.exe"],
        "task manager": ["taskmgr.exe"],
        "obs": ["obs64.exe"],
        "zoom": ["zoom.exe"],
        "teams": ["ms-teams.exe", "teams.exe"],
        "whatsapp": ["whatsapp.exe"],
    },

    "websites": {
        "gmail": "https://mail.google.com",
        "email": "https://mail.google.com",
        "school gmail": "https://accounts.google.com/AccountChooser?continue=https://mail.google.com",
        "school email": "https://accounts.google.com/AccountChooser?continue=https://mail.google.com",
        "youtube": "https://youtube.com",
        "google": "https://google.com",
        "google drive": "https://drive.google.com",
        "drive": "https://drive.google.com",
        "google docs": "https://docs.google.com",
        "google calendar": "https://calendar.google.com",
        "google classroom": "https://classroom.google.com",
        "google chat": "https://chat.google.com",
        "gchat": "https://chat.google.com",
        "classroom": "https://classroom.google.com",
        "google maps": "https://maps.google.com",
        "maps": "https://maps.google.com",
        "github": "https://github.com",
        "chat gpt": "https://chatgpt.com",
        "chatgpt": "https://chatgpt.com",
        "claude": "https://claude.ai",
        "reddit": "https://reddit.com",
        "netflix": "https://netflix.com",
        "twitch": "https://twitch.tv",
        "instagram": "https://instagram.com",
        "twitter": "https://x.com",
        "whatsapp web": "https://web.whatsapp.com",
        "amazon": "https://amazon.com",
    },

    "panic": {
        # Spoken phrases that trigger panic (exact match). Empty = hotkey only.
        "voice_phrases": [],
        "minimize_all": True,
        "mute": True,
        "close_apps": ["fortnite", "lunar client", "roblox", "rocket league"],
        "open_url": "https://mail.google.com",
    },

    "screenshot_dir": "",      # blank = Desktop

    "appearance": {
        "island_when_idle": True,             # keep the tiny pill at the top when nothing is happening
        "island_opacity": 0.85,               # how solid the island is while idle or showing a timer/song
        "island_hover": "see_through",        # mouse over it: "see_through" (fade, clicks pass) or "controls"
        "hide_in_fullscreen": True,           # tuck it away during fullscreen video and games
        "card_seconds": 1.0,                  # multiplier for how long answers stay on screen
        "screen_highlights": True,            # outline what Gem is talking about when it looks at your screen
    },

    "sounds": {"cues": True},                 # soft tones when listening starts and stops
}


# ── Loading ───────────────────────────────────────────────────────────────────

def _deep_merge(base, override):
    out = copy.deepcopy(base)
    for k, v in (override or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict) and k not in ("apps", "processes", "websites"):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def _read_json(path, default):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return default
    except Exception as e:
        log.error("Could not read %s: %s", path, e)
        return default


def _write_json(path, data):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    os.replace(tmp, path)


def load_settings():
    """Load settings.json merged over the defaults; create it on first run."""
    if not os.path.exists(SETTINGS_FILE):
        try:
            _write_json(SETTINGS_FILE, DEFAULTS)
            log.info("Created %s", SETTINGS_FILE)
        except Exception as e:
            log.error("Could not create settings file: %s", e)
        return copy.deepcopy(DEFAULTS)
    user = _read_json(SETTINGS_FILE, {})
    changed = False
    voice = user.get("voice") or {}
    if voice and "piper_voice" not in voice:
        # Written before the local voice existed: move to it (the online voice lagged and switched voices).
        voice["engine"] = "piper"
        changed = True
    for old in ("control_words", "overlay"):
        if old in user:
            user.pop(old)
            changed = True
    if changed:
        try:
            _write_json(SETTINGS_FILE, user)
        except Exception as e:
            log.error("Could not update settings file: %s", e)
    merged = _deep_merge(DEFAULTS, user)
    # App/site/process maps merge key-by-key so new defaults still appear.
    for key in ("apps", "processes", "websites"):
        merged[key] = {**DEFAULTS[key], **(user.get(key) or {})}
    # Backup AI services merge by name, so a service added to Gem later still shows up.
    saved = (user.get("ai") or {}).get("backups")
    if isinstance(saved, list):
        names = {b.get("name") for b in saved if isinstance(b, dict)}
        merged["ai"]["backups"] = saved + [copy.deepcopy(b) for b in DEFAULTS["ai"]["backups"]
                                           if b["name"] not in names]
    return merged


class JsonStore:
    """A small thread-safe JSON document in the data folder.

    `with store as data:` locks it and writes it back afterwards, but only if
    something actually changed, so frequent reads don't touch the disk.
    """

    def __init__(self, name, default):
        self.path = os.path.join(DATA_DIR, name)
        self._lock = threading.RLock()
        self.data = _read_json(self.path, copy.deepcopy(default))
        self._depth = 0
        self._before = None

    def save(self):
        with self._lock:
            try:
                _write_json(self.path, self.data)
            except Exception as e:
                log.error("Could not save %s: %s", self.path, e)

    def __enter__(self):
        self._lock.acquire()
        if self._depth == 0:
            self._before = json.dumps(self.data, sort_keys=True)
        self._depth += 1
        return self.data

    def __exit__(self, *exc):
        try:
            self._depth -= 1
            if self._depth == 0 and exc[0] is None and json.dumps(self.data, sort_keys=True) != self._before:
                self.save()
        finally:
            self._lock.release()


runtime = JsonStore("runtime.json", {})
