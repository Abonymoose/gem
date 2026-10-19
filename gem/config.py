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
        "engine": "edge",                     # "edge" (natural, online) or "sapi" (offline)
        "edge_voice": "en-US-AvaMultilingualNeural",
        "rate": "+5%",
        "volume": 0.9,
        "speak_in_calls": False,
        "speak_in_gaming": False,
    },

    "stt": {
        "backends": ["groq", "google"],
        "groq_models": ["whisper-large-v3-turbo", "whisper-large-v3"],
        "language": "en",
    },

    "ai": {
        "models": ["openai/gpt-oss-120b", "qwen/qwen3.8-27b", "openai/gpt-oss-20b"],
        "reasoning_effort": "low",
        "history_turns": 4,
    },

    "calls": {
        "auto_detect": True,
        # Mic users that never count as a call (substring match on the app id).
        "ignore_apps": ["python", "gem.exe", "gem2.exe"],
    },

    "snooze_minutes": 10,

    "reminders": {
        "break_minutes": 20,
        "break_message": "Time for a quick break. Drink some water.",
        "alarm_sound": True,
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

    # Whole-utterance control words. They work in every mode. The odd entries
    # are common mis-hearings of the German words.
    "control_words": {
        "quit": ["schluss", "shluss", "schlus", "shloos", "shoes", "sleeves", "sleeve"],
        "lock": ["sperren", "shperren", "sparren", "sparen", "sparring", "sperm",
                 "sparrow", "sperrung", "sparing", "sprain", "spurn"],
        "ruhig": ["ruhig", "rooky", "rookie", "rocky", "roomy", "ruby", "rohit", "ronak",
                  "rowdy", "juhi", "judy", "julie", "rui", "ruhi", "roohi", "rudy", "ruki", "rubik"],
        "weiter": ["weiter", "viter", "fighter", "writer", "lighter", "wider", "waiter",
                   "wither", "whiter"],
    },

    "screenshot_dir": "",      # blank = Desktop
    "overlay": {"enabled": True},
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
    merged = _deep_merge(DEFAULTS, user)
    # App/site/process maps merge key-by-key so new defaults still appear.
    for key in ("apps", "processes", "websites"):
        merged[key] = {**DEFAULTS[key], **(user.get(key) or {})}
    return merged


class JsonStore:
    """A small thread-safe JSON document in the data folder."""

    def __init__(self, name, default):
        self.path = os.path.join(DATA_DIR, name)
        self._lock = threading.RLock()
        self.data = _read_json(self.path, copy.deepcopy(default))

    def save(self):
        with self._lock:
            try:
                _write_json(self.path, self.data)
            except Exception as e:
                log.error("Could not save %s: %s", self.path, e)

    def __enter__(self):
        self._lock.acquire()
        return self.data

    def __exit__(self, *exc):
        try:
            if exc[0] is None:
                self.save()
        finally:
            self._lock.release()


runtime = JsonStore("runtime.json", {})
