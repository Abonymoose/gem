import speech_recognition as sr
import webbrowser
import os
import datetime
import pyttsx3
import psutil
import wikipedia
import subprocess
import requests
import keyboard
import warnings
import re
import threading
import queue
import ctypes
import time
import json
import winsound
import urllib.parse
import random
warnings.filterwarnings("ignore")
from ctypes import cast, POINTER
from comtypes import CLSCTX_ALL

# ── Tray icon ─────────────────────────────────────────────────────────────────
try:
    import pystray
    from pystray import MenuItem as TrayItem
    from PIL import Image, ImageDraw
    TRAY_AVAILABLE = True
except ImportError:
    TRAY_AVAILABLE = False
    print("[Warning] pystray/Pillow not installed. Run: pip install pystray pillow")

# ── pycaw for volume control ──────────────────────────────────────────────────
try:
    from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
    PYCAW_AVAILABLE = True
except ImportError:
    PYCAW_AVAILABLE = False
    print("[Warning] pycaw not installed. Run: pip install pycaw")

# ── Groq AI ───────────────────────────────────────────────────────────────────
try:
    from groq import Groq
    GROQ_AVAILABLE = True
except ImportError:
    GROQ_AVAILABLE = False
    print("[Warning] groq not installed. Run: pip install groq")

# ── Config ────────────────────────────────────────────────────────────────────
recognizer   = sr.Recognizer()
API_KEY      = os.environ.get("OPENWEATHER_API_KEY", "")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")

APPS = {
    # System
    "notepad":       "notepad.exe",
    "calculator":    "calc.exe",
    "paint":         "mspaint.exe",
    "cmd":           "cmd.exe",
    "task manager":  "taskmgr.exe",
    "file explorer": "explorer.exe",
    # Browsers
    "brave":         r"C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe",
    "chrome":        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    # Communication
    "discord":       r"C:\Users\Parshv Mehta\AppData\Local\Discord\app-1.0.9171\Discord.exe",
    # Music
    "spotify":       r"C:\Users\Parshv Mehta\AppData\Roaming\Spotify\Spotify.exe",
    # Gaming
    "steam":         r"C:\Program Files (x86)\Steam\steam.exe",
    "epic games":    r"C:\Program Files (x86)\Epic Games\Launcher\Portal\Binaries\Win32\EpicGamesLauncher.exe",
    "epic":          r"C:\Program Files (x86)\Epic Games\Launcher\Portal\Binaries\Win32\EpicGamesLauncher.exe",
    "fortnite":      r"C:\Program Files\Epic Games\Fortnite\FortniteGame\Binaries\Win64\FortniteClient-Win64-Shipping.exe",
    "lunar client":  r"C:\Users\Parshv Mehta\AppData\Roaming\lunarclient\app-stable\Lunar Client.exe",
    "lunar":         r"C:\Users\Parshv Mehta\AppData\Roaming\lunarclient\app-stable\Lunar Client.exe",
    # Dev
    "vs code":       r"C:\Users\Parshv Mehta\AppData\Local\Programs\Microsoft VS Code\Code.exe",
    "vscode":        r"C:\Users\Parshv Mehta\AppData\Local\Programs\Microsoft VS Code\Code.exe",
    "visual studio code": r"C:\Users\Parshv Mehta\AppData\Local\Programs\Microsoft VS Code\Code.exe",
    # Office
    "word":          r"C:\Program Files\Microsoft Office\root\Office16\WINWORD.EXE",
    "excel":         r"C:\Program Files\Microsoft Office\root\Office16\EXCEL.EXE",
}

# ── Control words ─────────────────────────────────────────────────────────────
SHUTDOWN_WORDS = {"shoes", "snooze", "sleeves", "sleeve"}
LOCK_WORDS     = {"sperren", "sparren", "sparen", "sparring", "spirit",
                  "sperm", "sparrow", "parent", "sperrung", "sparing",
                  "spain", "sprain", "spurn"}
SILENCE_ON     = {"shut up", "shutup", "be quiet", "quiet", "keep quiet",
                  "stop talking", "silence", "shush", "hush"}
SILENCE_OFF    = {"speak up", "you can talk", "talk again", "i'm listening",
                  "start talking", "unmute yourself", "wake up"}
RUHIG_WORDS    = {"ruhig", "rooky", "rookie", "rocky", "roomy", "ruby",
                  "rohit", "ronak", "rowdy", "juhi", "judy", "julie",
                  "rui", "ruhi", "roohi", "rudy", "ruki", "rubik"}
WEITER_WORDS   = {"weiter", "viter", "fighter", "writer", "lighter",
                  "wider", "waiter", "wither", "whiter"}

# ── Scheduled alarms (persistent) ────────────────────────────────────────────
ALARMS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "gem_alarms.json")

# Built-in class schedule — editable by voice
DEFAULT_SCHEDULE = [
    {
        "name": "french class",
        "days": ["monday"],
        "time": "19:55",
        "message": "Time for French class!",
        "url": "https://meet.google.com/oot-vnfo-yhp",
    },
    {
        "name": "english class",
        "days": ["tuesday", "thursday"],
        "time": "18:55",
        "message": "Time for English class!",
        "url": "https://meet.google.com/tsf-ynjp-qhc?pli=1",
    },
    {
        "name": "french class",
        "days": ["wednesday"],
        "time": "18:55",
        "message": "Time for French class!",
        "url": "https://meet.google.com/oot-vnfo-yhp",
    },
]

def _load_alarms():
    if os.path.exists(ALARMS_FILE):
        try:
            with open(ALARMS_FILE, "r") as f:
                return json.load(f)
        except Exception:
            pass
    # First run — save defaults
    _save_alarms(DEFAULT_SCHEDULE)
    return DEFAULT_SCHEDULE

def _save_alarms(alarms):
    try:
        with open(ALARMS_FILE, "w") as f:
            json.dump(alarms, f, indent=2)
    except Exception as e:
        print(f"[Alarm Save Error] {e}")

# In-memory alarm list (loaded at startup)
_alarms = _load_alarms()

def _fire_timer(name, message, url=None):
    """Called when a timer/alarm fires."""
    _beep()
    speak(message)
    if url:
        webbrowser.open(url)
    if name in _active_timers:
        del _active_timers[name]

def _parse_duration(command):
    """Parse duration from command. Returns seconds or None."""
    # Match patterns like "10 minutes", "1 hour 30 minutes", "45 seconds"
    total = 0
    found = False
    for val, unit in re.findall(r'(\d+)\s*(hour|hr|minute|min|second|sec)s?', command):
        val = int(val)
        if unit in ("hour", "hr"):
            total += val * 3600
        elif unit in ("minute", "min"):
            total += val * 60
        elif unit in ("second", "sec"):
            total += val
        found = True
    return total if found else None

def _parse_alarm_time(command):
    """Parse a clock time like '7am', '6:55 pm', '19:55'. Returns (hour, minute) or None."""
    # 12-hour with am/pm
    m = re.search(r'(\d{1,2})(?::(\d{2}))?\s*(am|pm)', command)
    if m:
        hour = int(m.group(1))
        minute = int(m.group(2)) if m.group(2) else 0
        if m.group(3) == "pm" and hour != 12:
            hour += 12
        if m.group(3) == "am" and hour == 12:
            hour = 0
        return hour, minute
    # 24-hour
    m = re.search(r'\b(\d{1,2}):(\d{2})\b', command)
    if m:
        return int(m.group(1)), int(m.group(2))
    return None

# Active one-off alarms: {name: threading.Timer}
_active_alarms = {}

def _parse_alarm_time(command):
    """Parse a clock time or relative time. Returns (hour, minute) or None."""
    # Relative: "in X minutes" / "in X hours"
    m = re.search(r'in\s+(\d+)\s*(minute|min|hour|hr)s?', command)
    if m:
        val = int(m.group(1))
        unit = m.group(2)
        now = datetime.datetime.now()
        if unit in ("hour", "hr"):
            target = now + datetime.timedelta(hours=val)
        else:
            target = now + datetime.timedelta(minutes=val)
        return target.hour, target.minute

    # "X minutes from now"
    m = re.search(r'(\d+)\s*(minute|min|hour|hr)s?\s*from now', command)
    if m:
        val = int(m.group(1))
        unit = m.group(2)
        now = datetime.datetime.now()
        if unit in ("hour", "hr"):
            target = now + datetime.timedelta(hours=val)
        else:
            target = now + datetime.timedelta(minutes=val)
        return target.hour, target.minute

    # 12-hour with am/pm
    m = re.search(r'(\d{1,2})(?::(\d{2}))?\s*(am|pm)', command)
    if m:
        hour = int(m.group(1))
        minute = int(m.group(2)) if m.group(2) else 0
        if m.group(3) == "pm" and hour != 12:
            hour += 12
        if m.group(3) == "am" and hour == 12:
            hour = 0
        return hour, minute

    # 24-hour HH:MM
    m = re.search(r'\b(\d{1,2}):(\d{2})\b', command)
    if m:
        return int(m.group(1)), int(m.group(2))

    # Plain hour like "at 4" or "for 7" — assume closest future hour
    m = re.search(r'(?:at|for)\s+(\d{1,2})(?:\s|$)', command)
    if m:
        hour = int(m.group(1))
        now = datetime.datetime.now()
        # If hour has passed today, assume PM if AM already passed
        if hour < now.hour and hour < 12:
            hour += 12
        return hour, 0

    return None

def _beep():
    try:
        winsound.Beep(1000, 500)
        winsound.Beep(1000, 500)
        winsound.Beep(1000, 500)
    except Exception:
        pass

def _fire_alarm(name, message, url=None):
    _beep()
    speak(message)
    if url:
        webbrowser.open(url)
    if name in _active_alarms:
        del _active_alarms[name]

def handle_alarm(command):
    global _alarms, _active_alarms

    # ── Set a one-off alarm ───────────────────────────────────────────────────
    if any(x in command for x in ["set an alarm", "set alarm", "alarm at", "alarm for",
                                   "wake me", "remind me", "in 1", "in 2", "in 3",
                                   "in 4", "in 5", "in 10", "in 15", "in 20", "in 30",
                                   "minute from now", "minutes from now", "hour from now"]):
        parsed = _parse_alarm_time(command)
        if not parsed:
            speak("I couldn't understand the time. Try saying set an alarm for 7 am.")
            return True
        hour, minute = parsed
        name_match = re.search(r'(?:called|named)\s+([a-z ]+)', command)
        msg_match  = re.search(r'(?:saying|message|say)\s+(.+)', command)
        name    = name_match.group(1).strip() if name_match else f"{hour % 12 or 12}:{minute:02d} {'AM' if hour < 12 else 'PM'}"
        message = msg_match.group(1).strip() if msg_match else f"Alarm! It's {hour % 12 or 12}:{minute:02d}."
        now = datetime.datetime.now()
        alarm_time = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if alarm_time <= now:
            alarm_time += datetime.timedelta(days=1)
        delay = (alarm_time - now).total_seconds()
        print(f"[Alarm] {name} set — fires in {int(delay)} seconds at {alarm_time.strftime('%H:%M')}")

        def _alarm_thread(n, m, d):
            time.sleep(d)
            _fire_alarm(n, m)

        t = threading.Thread(target=_alarm_thread, args=[name, message, delay])
        t.daemon = False  # keep alive even if main thread is busy
        t.start()
        _active_alarms[name] = t
        speak(f"Alarm {name} set for {hour % 12 or 12}:{minute:02d} {'AM' if hour < 12 else 'PM'}.")
        return True

    # ── Cancel a one-off alarm ────────────────────────────────────────────────
    if any(x in command for x in ["cancel alarm", "stop alarm", "dismiss alarm"]):
        name = None
        for n in _active_alarms:
            if n in command:
                name = n
                break
        if not name and _active_alarms:
            name = list(_active_alarms.keys())[0]
        if name:
            _active_alarms[name].cancel()
            del _active_alarms[name]
            speak(f"Alarm {name} cancelled.")
        else:
            speak("No alarms to cancel.")
        return True

    # ── Add a scheduled alarm ─────────────────────────────────────────────────
    if any(x in command for x in ["add schedule", "add class", "schedule alarm"]):
        speak("What should I call this?")
        name = _command_queue.get(timeout=10)
        speak("Which days?")
        days_raw = _command_queue.get(timeout=10)
        days = [d for d in ["monday","tuesday","wednesday","thursday","friday","saturday","sunday"] if d in days_raw]
        if not days:
            speak("I didn't catch the days.")
            return True
        speak("What time?")
        time_raw = _command_queue.get(timeout=10)
        parsed = _parse_alarm_time(time_raw)
        if not parsed:
            speak("I couldn't understand the time.")
            return True
        hour, minute = parsed
        speak("Should I open a link? Say the URL or say no.")
        url_raw = _command_queue.get(timeout=10)
        url = url_raw if "http" in url_raw else None
        speak("What should I say when it fires?")
        message = _command_queue.get(timeout=10)
        _alarms.append({
            "name": name,
            "days": days,
            "time": f"{hour:02d}:{minute:02d}",
            "message": message,
            "url": url,
        })
        _save_alarms(_alarms)
        speak(f"Added {name} for {', '.join(days)} at {hour % 12 or 12}:{minute:02d}.")
        return True

    # ── Remove a scheduled alarm ──────────────────────────────────────────────
    if any(x in command for x in ["remove schedule", "delete schedule", "remove class", "delete class"]):
        speak("Which schedule should I remove?")
        name = _command_queue.get(timeout=10)
        before = len(_alarms)
        _alarms = [a for a in _alarms if name.lower() not in a["name"].lower()]
        _save_alarms(_alarms)
        if len(_alarms) < before:
            speak(f"Removed {name} from schedule.")
        else:
            speak(f"I couldn't find a schedule called {name}.")
        return True

    # ── List alarms ───────────────────────────────────────────────────────────
    if any(x in command for x in ["list alarms", "what alarms", "my alarms"]):
        parts = []
        for name in _active_alarms:
            parts.append(f"{name} is set")
        for a in _alarms:
            parts.append(f"{a['name']} fires on {', '.join(a['days'])} at {a['time']}")
        speak(". ".join(parts) if parts else "No alarms set.")
        return True

    return False

def _schedule_watcher():
    """Background thread — checks scheduled alarms every 30 seconds."""
    while True:
        now = datetime.datetime.now()
        day = now.strftime("%A").lower()
        current_time = now.strftime("%H:%M")
        for alarm in _alarms:
            if day in alarm.get("days", []) and alarm.get("time") == current_time:
                # Only fire once per minute
                fire_key = f"{alarm['name']}_{now.strftime('%Y%m%d%H%M')}"
                if fire_key not in _fired_schedules:
                    _fired_schedules.add(fire_key)
                    threading.Thread(
                        target=_fire_alarm,
                        args=[alarm["name"], alarm["message"], alarm.get("url")],
                        daemon=True
                    ).start()
        time.sleep(30)

_fired_schedules = set()

def start_schedule_watcher():
    t = threading.Thread(target=_schedule_watcher, daemon=True)
    t.start()

# ── Global state ──────────────────────────────────────────────────────────────
_tts_lock      = threading.Lock()
_command_queue = queue.Queue()
_silent        = False   # silence mode — no voice output
_deaf          = False   # ruhig mode — ignore all commands except Weiter
_dictating     = False   # dictation mode active
_speaking      = False   # True while TTS is running
_asleep        = True    # True until "gem wake up" is said
_last_command  = time.time()  # for auto-sleep after 5 mins

# Animation state: "launch" | "sleeping" | "listening" | "speaking"
_anim_state    = "launch"
_anim_window   = None    # reference to GemOverlay instance

# ── TTS ───────────────────────────────────────────────────────────────────────

def speak(text):
    global _speaking, _anim_state
    print(f"Gem says: {text}")
    if _silent:
        return
    _speaking = True
    _anim_state = "speaking"
    if _anim_window:
        _anim_window.set_state("speaking")
    try:
        with _tts_lock:
            engine = pyttsx3.init()
            engine.setProperty("rate", 175)
            engine.setProperty("volume", 0.9)
            engine.say(text)
            engine.runAndWait()
            engine.stop()
    except Exception as e:
        print(f"[TTS Error] {e}")
    finally:
        threading.Timer(0.8, _clear_speaking).start()

def _clear_speaking():
    global _speaking, _anim_state
    _speaking = False
    # Don't override gaming or glitch animations
    if _anim_window and _anim_window.state in ("gaming", "glitch"):
        return
    next_state = "sleeping" if _asleep else "listening"
    _anim_state = next_state
    if _anim_window:
        _anim_window.set_state(next_state)

# ── Background mic listener ───────────────────────────────────────────────────

WAKE_WORDS = {"gem wake up", "wake up gem", "gem wakeup",
              "jag wake up", "jen wake up", "jam wake up",
              "jag wakeup", "jen wakeup", "jam wakeup",
              "gem wake", "jag wake", "jen wake", "jem wake",
              "hey gem", "hey jag", "hey jen"}
SLEEP_TIMEOUT = 300  # 5 minutes of silence → auto sleep

def _wake_gem():
    global _asleep, _anim_state, _last_command
    _asleep = False
    _last_command = time.time()
    if _anim_window:
        _anim_window.set_state("waking")
    speak(random.choice(WAKE_RESPONSES))
    if _anim_window:
        _anim_window.set_state("listening")
    _anim_state = "listening"

def _sleep_gem():
    global _asleep, _anim_state
    _asleep = True
    _anim_state = "sleeping"
    if _anim_window:
        _anim_window.set_state("sleeping")

def _auto_sleep_watcher():
    """Goes to sleep after 5 mins of no commands."""
    while True:
        time.sleep(30)
        if not _asleep and time.time() - _last_command > SLEEP_TIMEOUT:
            _sleep_gem()

def _water_reminder():
    """Beeps every 20 mins when Gem is awake and not in Ruhig mode."""
    while True:
        time.sleep(1200)  # 20 minutes
        if not _asleep and not _deaf:
            _beep()

def _mic_listener():
    global _last_command
    with sr.Microphone() as source:
        recognizer.adjust_for_ambient_noise(source, duration=1)
        while True:
            while _speaking:
                time.sleep(0.1)
            try:
                audio = recognizer.listen(source, phrase_time_limit=12)
                try:
                    command = recognizer.recognize_google(audio).lower()
                    print(f"Gem hears: {command}")

                    # Wake word — always checked even when asleep
                    if any(w in command for w in WAKE_WORDS):
                        _wake_gem()
                        continue

                    # Ignore everything else while asleep
                    if _asleep:
                        continue

                    _last_command = time.time()
                    # Don't override gaming or glitch animations
                    if _anim_window and _anim_window.state not in ("gaming", "glitch"):
                        _anim_state = "listening"
                        _anim_window.set_state("listening")
                    _command_queue.put(command)
                except sr.UnknownValueError:
                    pass
                except sr.RequestError:
                    pass
            except OSError:
                time.sleep(1)
            except Exception as e:
                print(f"[Mic Error] {e}")
                time.sleep(0.5)

def start_background_listener():
    threading.Thread(target=_mic_listener, daemon=True).start()
    threading.Thread(target=_auto_sleep_watcher, daemon=True).start()
    threading.Thread(target=_water_reminder, daemon=True).start()

# ── Tray icon ─────────────────────────────────────────────────────────────────

def _make_tray_icon():
    import math as _math
    size = 64
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d   = ImageDraw.Draw(img)
    cx  = cy = size // 2
    R   = int(size * 0.42)
    op  = 0.82
    verts = []
    for i in range(6):
        a = _math.radians(60*i - 90)
        verts.append((cx + R*_math.cos(a), cy + R*_math.sin(a)))
    shard_fills   = ["#2e1f4a","#1a1228","#2e1f4a","#1a1228","#2e1f4a","#1a1228"]
    shard_strokes = ["#a07cc8","#c4a0f0","#a07cc8","#c4a0f0","#a07cc8","#c4a0f0"]
    for i in range(6):
        v0, v1 = verts[i], verts[(i+1)%6]
        mid_x  = (v0[0]+v1[0]+cx)/3
        mid_y  = (v0[1]+v1[1]+cy)/3
        dx, dy = mid_x-cx, mid_y-cy
        dist   = max(1, _math.hypot(dx, dy))
        push   = op * size * 0.12
        px, py = dx/dist*push, dy/dist*push
        pts = [v0[0]+px, v0[1]+py, v1[0]+px, v1[1]+py, cx+px*0.2, cy+py*0.2]
        d.polygon(pts, fill=shard_fills[i], outline=shard_strokes[i])
    er = int(size * 0.22)
    d.ellipse([cx-er, cy-int(er*0.65), cx+er, cy+int(er*0.65)], fill="#1a1228")
    ir = int(er*0.78)
    d.ellipse([cx-ir, cy-ir, cx+ir, cy+ir], fill="#4a2d7a")
    ir2 = int(er*0.52)
    d.ellipse([cx-ir2, cy-ir2, cx+ir2, cy+ir2], fill="#2e1f4a")
    pr = int(er*0.35)
    d.ellipse([cx-pr, cy-pr, cx+pr, cy+pr], fill="#0d0a14")
    sr = max(1, int(pr*0.55))
    d.ellipse([cx+int(pr*0.2), cy-int(pr*0.8),
               cx+int(pr*0.2)+sr, cy-int(pr*0.8)+sr], fill="#d4b8f0")
    return img.convert("RGB")

def _tray_quit(icon, item):
    icon.stop()
    os._exit(0)

def start_tray():
    if not TRAY_AVAILABLE:
        return
    icon = pystray.Icon(
        "Gem",
        _make_tray_icon(),
        "Gem — listening",
        menu=pystray.Menu(
            TrayItem("Gem is running", lambda: None, enabled=False),
            TrayItem("Quit (use Schluss to close)", _tray_quit),
        )
    )
    threading.Thread(target=icon.run, daemon=True).start()

# ── Animation overlay ─────────────────────────────────────────────────────────

import tkinter as tk
import math
import random as _rnd

class GemOverlay:
    SIZE   = 60
    MARGIN = 16
    C_BG        = "#0d0a14"
    C_SHADOW    = "#1a1228"
    C_DEEP      = "#2e1f4a"
    C_MID       = "#4a2d7a"
    C_IRIS      = "#6b3fa0"
    C_LAVENDER  = "#a07cc8"
    C_HIGHLIGHT = "#d4b8f0"
    C_FF        = ["#c4a0f0","#a07cc8","#d4b8f0","#8b5cbf","#b890e8","#c4a0f0"]

    def __init__(self):
        self.root = tk.Tk()
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.root.attributes("-transparentcolor", "#010101")
        self.root.configure(bg="#010101")
        self.root.resizable(False, False)
        # Keep on top even when other windows gain focus
        self.root.after(1000, self._keep_on_top)

        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        x  = sw - self.SIZE - self.MARGIN
        y  = sh - self.SIZE - self.MARGIN - 40
        self.root.geometry(f"{self.SIZE}x{self.SIZE}+{x}+{y}")

        self.canvas = tk.Canvas(
            self.root, width=self.SIZE, height=self.SIZE,
            bg="#010101", highlightthickness=0
        )
        self.canvas.pack()

        self.state        = "launch"
        self.tick         = 0
        self.launch_timer = 0
        self.shard_open   = 0.0   # 0=closed crystal, 1=fully open
        self.cmd_received = False  # True when command recognized
        self.close_timer  = 0      # countdown to close crystal after cmd
        self.eye_lx       = 0.0
        self.eye_ly       = 0.0
        self.portal_a1    = 0.0
        self.portal_a2    = 0.0
        self.wake_progress = 0.0  # 0=eyelid closed, 1=fully open
        self.glitch_timer  = 0
        self.void_timer    = 0
        self.void_angle    = 0.0
        self.scope_angle   = 0.0
        self.gaming_zoom   = 0.0
        self.ff           = self._init_ff()
        self._animate()

    def _keep_on_top(self):
        self.root.attributes("-topmost", True)
        self.root.after(2000, self._keep_on_top)

    def set_state(self, state):
        self.state = state
        if state == "listening":
            self.cmd_received = True
            self.close_timer  = 90
        elif state == "waking":
            self.wake_progress = 0.0
            self.state = "waking"
        elif state == "sleeping":
            self.wake_progress = 1.0
        elif state == "glitch":
            self.glitch_timer = 180  # ~6s of glitch then stays
        elif state == "void":
            self.void_timer = 60
        elif state == "gaming":
            self.scope_angle = 0.0
            self.gaming_zoom = 0.0    # ~2s of void spiral then back

    def _init_ff(self):
        cx = cy = self.SIZE // 2
        dots = []
        for i in range(10):
            angle = _rnd.uniform(0, 2*math.pi)
            dist  = _rnd.uniform(4, 22)
            dots.append({
                "x": cx + math.cos(angle)*dist,
                "y": cy + math.sin(angle)*dist,
                "vx": _rnd.uniform(-0.3, 0.3),
                "vy": _rnd.uniform(-0.3, 0.3),
                "r":  _rnd.uniform(1, 2.5),
                "phase": _rnd.uniform(0, 2*math.pi),
                "speed": _rnd.uniform(0.04, 0.09),
                "color": self.C_FF[i % len(self.C_FF)],
            })
        return dots

    def _hex_pts(self, cx, cy, r, offset=0):
        pts = []
        for i in range(6):
            a = math.radians(60*i + offset)
            pts += [cx + r*math.cos(a), cy + r*math.sin(a)]
        return pts

    # ── Draw functions ────────────────────────────────────────────────────────

    def _draw_launch(self):
        cx = cy = self.SIZE // 2
        t  = self.tick
        for d in self.ff:
            d["x"] += d["vx"]
            d["y"] += d["vy"]
            dx, dy = d["x"]-cx, d["y"]-cy
            if math.hypot(dx, dy) > 24:
                d["vx"] *= -0.7; d["vy"] *= -0.7
            d["vx"] += _rnd.uniform(-0.04, 0.04)
            d["vy"] += _rnd.uniform(-0.04, 0.04)
            d["vx"] = max(-0.5, min(0.5, d["vx"]))
            d["vy"] = max(-0.5, min(0.5, d["vy"]))
            alpha = 0.25 + 0.75*(0.5 + 0.5*math.sin(t*d["speed"] + d["phase"]))
            r = d["r"] * alpha
            x, y = d["x"], d["y"]
            self.canvas.create_oval(x-r, y-r, x+r, y+r, fill=d["color"], outline="")
        self.launch_timer += 1
        if self.launch_timer > 150:   # ~5s
            self.state = "sleeping"
            self.wake_progress = 0.0

    def _draw_crystal(self, open_amount):
        """Draw closed/opening crystal. open_amount 0.0=closed, 1.0=fully open."""
        c  = self.canvas
        cx = cy = self.SIZE // 2
        R  = 26
        verts = [(cx + R*math.cos(math.radians(60*i-90)),
                  cy + R*math.sin(math.radians(60*i-90))) for i in range(6)]
        shard_fills   = [self.C_DEEP, self.C_SHADOW]*3
        shard_strokes = [self.C_LAVENDER, self.C_LAVENDER]*3
        for i in range(6):
            v0, v1 = verts[i], verts[(i+1)%6]
            mid_x = (v0[0]+v1[0]+cx)/3
            mid_y = (v0[1]+v1[1]+cy)/3
            dx, dy = mid_x-cx, mid_y-cy
            dist   = max(1, math.hypot(dx, dy))
            push   = open_amount * 7
            px, py = dx/dist*push, dy/dist*push
            pts    = [v0[0]+px, v0[1]+py, v1[0]+px, v1[1]+py,
                      cx+px*0.2, cy+py*0.2]
            c.create_polygon(pts, fill=shard_fills[i],
                             outline=shard_strokes[i], width=1)

    def _draw_eye(self, alpha=1.0):
        """Draw eye at center with given opacity (0-1)."""
        c  = self.canvas
        cx = cy = self.SIZE // 2
        t  = self.tick
        er = int(13 * alpha)
        if er < 2:
            return
        # white / sclera
        c.create_oval(cx-er, cy-int(er*0.65), cx+er, cy+int(er*0.65),
                      fill=self.C_SHADOW, outline="")
        # iris
        ir = max(1, int(er*0.78))
        c.create_oval(cx-ir, cy-ir, cx+ir, cy+ir, fill=self.C_MID, outline="")
        # inner iris ring
        ir2 = max(1, int(er*0.52))
        c.create_oval(cx-ir2, cy-ir2, cx+ir2, cy+ir2, fill=self.C_DEEP, outline="")
        # drifting pupil
        self.eye_lx += (5*math.sin(t*0.04) - self.eye_lx) * 0.08
        self.eye_ly += (3*math.cos(t*0.031) - self.eye_ly) * 0.08
        pr  = max(1, int(er*0.35))
        px  = cx + self.eye_lx * alpha
        py  = cy + self.eye_ly * alpha
        c.create_oval(px-pr, py-pr, px+pr, py+pr, fill=self.C_BG, outline="")
        # shine
        sr = max(1, int(pr*0.55))
        c.create_oval(px+pr*0.2, py-pr*0.8,
                      px+pr*0.2+sr, py-pr*0.8+sr,
                      fill=self.C_HIGHLIGHT, outline="")

    def _draw_portal(self):
        c  = self.canvas
        cx = cy = self.SIZE // 2
        t  = self.tick
        self.portal_a1 = (self.portal_a1 + 1.2) % 360
        self.portal_a2 = (self.portal_a2 - 0.8) % 360
        # outer ring
        pts1 = self._hex_pts(cx, cy, 26, self.portal_a1)
        c.create_polygon(pts1, fill="", outline=self.C_IRIS, width=1)
        # inner ring
        pts2 = self._hex_pts(cx, cy, 19, self.portal_a2)
        c.create_polygon(pts2, fill="", outline=self.C_LAVENDER, width=1)
        # glow + iris
        gr = 13 + 1.5*math.sin(t*0.07)
        c.create_oval(cx-gr, cy-gr, cx+gr, cy+gr, fill=self.C_DEEP, outline="")
        ir = int(12*(0.92+0.08*math.sin(t*0.06)))
        c.create_oval(cx-ir, cy-ir, cx+ir, cy+ir, fill=self.C_MID, outline="")
        c.create_oval(cx-8,  cy-8,  cx+8,  cy+8,  fill=self.C_DEEP, outline="")
        # drifting pupil
        self.eye_lx += (5*math.sin(t*0.035) - self.eye_lx)*0.06
        self.eye_ly += (4*math.cos(t*0.028) - self.eye_ly)*0.06
        pr = 4
        px, py = cx+self.eye_lx, cy+self.eye_ly
        c.create_oval(px-pr, py-pr, px+pr, py+pr, fill=self.C_BG, outline="")
        c.create_oval(px+0.5, py-2.5, px+2.5, py-0.5, fill=self.C_HIGHLIGHT, outline="")

    def _draw_sleeping(self):
        """Star field with scattered constellation — sleeping mode."""
        c  = self.canvas
        cx = cy = self.SIZE // 2
        t  = self.tick

        # Dark hex background
        pts = self._hex_pts(cx, cy, 28, 0)
        c.create_polygon(pts, fill=self.C_BG, outline=self.C_SHADOW, width=1)

        # Stars — smaller, more spread, different brightness
        stars = [
            (-22, -14, "#a07cc8", 0.0,  1.0),  # bright
            (-10, -20, "#6b3fa0", 0.8,  0.7),  # dim
            (  2, -17, "#c4a0f0", 1.6,  1.2),  # bright
            ( 15, -19, "#8b5cbf", 2.4,  0.7),  # dim
            ( 23,  -5, "#d4b8f0", 3.2,  1.0),  # bright
            (-20,  12, "#6b3fa0", 3.9,  0.7),  # dim
            (  0,  16, "#a07cc8", 1.2,  0.8),
            ( 20,  17, "#c4a0f0", 1.9,  1.0),
            ( -7,  -6, "#4a2d7a", 0.6,  0.6),  # faint inner
            ( 12,   5, "#6b3fa0", 2.8,  0.6),  # faint inner
        ]

        # Constellation lines — drawn first, behind stars
        pairs = [(0,1),(1,2),(2,3),(3,4),(0,5),(4,7),(5,6),(6,7),(2,8),(8,9)]
        for i, j in pairs:
            x1, y1 = cx+stars[i][0], cy+stars[i][1]
            x2, y2 = cx+stars[j][0], cy+stars[j][1]
            line_a = 0.12 + 0.08*math.sin(t*0.018)
            # Use stipple-like effect by making lines very thin and faint
            c.create_line(x1, y1, x2, y2, fill=self.C_DEEP, width=1)

        # Stars on top — small and twinkling
        for sx, sy, col, phase, size in stars:
            alpha = 0.2 + 0.8*(0.5 + 0.5*math.sin(t*0.025 + phase))
            r = size * alpha
            r = max(0.5, r)
            x, y = cx+sx, cy+sy
            c.create_oval(x-r, y-r, x+r, y+r, fill=col, outline="")

        # Closed eye — clean horizontal line
        er = 10
        c.create_oval(cx-er, cy-int(er*0.6), cx+er, cy+int(er*0.6),
                      fill=self.C_SHADOW, outline="")
        c.create_line(cx-er, cy, cx+er, cy,
                      fill=self.C_LAVENDER, width=1)
    def _draw_waking(self):
        """Eyelid slowly opens, then transitions to listening."""
        c  = self.canvas
        cx = cy = self.SIZE // 2
        self.wake_progress = min(1.0, self.wake_progress + 0.018)
        self._draw_crystal(0.0)
        er = 13
        wp = self.wake_progress
        c.create_oval(cx-er, cy-int(er*0.65), cx+er, cy+int(er*0.65),
                      fill=self.C_SHADOW, outline="")
        lid_cover = 1.0 - wp
        lid_h = int(er * 0.65 * lid_cover)
        if lid_h > 0:
            c.create_rectangle(cx-er, cy-int(er*0.65),
                               cx+er, cy-int(er*0.65)+lid_h*2,
                               fill=self.C_DEEP, outline="")
        if wp > 0.3:
            self._draw_eye(min(1.0, (wp-0.3)/0.5))
        c.create_line(cx-er, cy-int(er*0.65)+lid_h*2,
                      cx+er, cy-int(er*0.65)+lid_h*2,
                      fill=self.C_LAVENDER, width=1)
        if self.wake_progress >= 1.0:
            self.state = "listening"
            self.cmd_received = False

    def _draw_glitch(self):
        """Pixel noise and scan lines — Ruhig mode."""
        c  = self.canvas
        cx = cy = self.SIZE // 2
        # Draw base crystal dark
        self._draw_crystal(0.0)
        # Glitch blocks
        blocks = [
            (cx-18, cy-10, cx-4,  cy-7,  self.C_LAVENDER),
            (cx+2,  cy-8,  cx+12, cy-5,  self.C_HIGHLIGHT),
            (cx-14, cy+2,  cx+2,  cy+5,  self.C_IRIS),
            (cx+4,  cy+8,  cx+16, cy+11, self.C_LAVENDER),
            (cx-10, cy-2,  cx+4,  cy+1,  self.C_HIGHLIGHT),
            (cx-6,  cy+14, cx+8,  cy+17, self.C_IRIS),
        ]
        for i, (x1,y1,x2,y2,col) in enumerate(blocks):
            if (self.tick + i*7) % 8 < 5:
                offset = _rnd.randint(-2, 2)
                c.create_rectangle(x1+offset, y1, x2+offset, y2,
                                   fill=col, outline="")
        # Scan lines
        for i in range(3):
            y = cy - 12 + i*10
            if (self.tick + i*11) % 15 < 8:
                c.create_line(cx-22, y, cx+22, y,
                              fill=self.C_LAVENDER, width=1)

    def _draw_void(self):
        """Counter-rotating dark spirals — silent mode action."""
        c  = self.canvas
        cx = cy = self.SIZE // 2
        self.void_angle = (self.void_angle + 2) % 360
        # Draw closed crystal underneath
        self._draw_crystal(0.0)
        # Two counter-spinning partial arcs
        for i, (r, col, speed) in enumerate([(20, self.C_IRIS, 1), (14, self.C_LAVENDER, -1.5)]):
            a  = math.radians(self.void_angle * speed)
            x1 = cx + r*math.cos(a)
            y1 = cy + r*math.sin(a)
            x2 = cx + r*math.cos(a + math.pi*0.8)
            y2 = cy + r*math.sin(a + math.pi*0.8)
            c.create_line(cx, cy, x1, y1, fill=col, width=1)
            c.create_line(cx, cy, x2, y2, fill=col, width=1)
        # Dark center
        c.create_oval(cx-5, cy-5, cx+5, cy+5, fill=self.C_BG, outline="")
        # Countdown — return to glitch after void_timer expires
        if self.void_timer > 0:
            self.void_timer -= 1
        else:
            self.state = "glitch" if _deaf else "idle"

    def _draw_gaming(self):
        """Sniper scope — zooms in first then rotates forever."""
        c  = self.canvas
        cx = cy = self.SIZE // 2
        t  = self.tick

        # Zoom progress — use dedicated counter
        self.gaming_zoom = min(1.0, self.gaming_zoom + 0.016)
        zoom = self.gaming_zoom

        # Rings shrink as scope zooms in
        outer_r = int(26 - zoom * 5)
        mid_r   = int(18 - zoom * 3)

        # Continuous rotation
        self.scope_angle += 0.4

        a = math.radians(self.scope_angle)

        # Dark hex background
        pts = self._hex_pts(cx, cy, 28, 0)
        c.create_polygon(pts, fill=self.C_BG, outline=self.C_DEEP, width=1)

        # Outer ring
        c.create_oval(cx-outer_r, cy-outer_r, cx+outer_r, cy+outer_r,
                      fill="", outline=self.C_IRIS, width=1)
        # Mid ring
        c.create_oval(cx-mid_r, cy-mid_r, cx+mid_r, cy+mid_r,
                      fill="", outline=self.C_LAVENDER, width=1)

        # Rotating crosshair lines
        for offset in [0, math.pi/2, math.pi, 3*math.pi/2]:
            angle = a + offset
            x1 = cx + math.cos(angle) * (mid_r + 2)
            y1 = cy + math.sin(angle) * (mid_r + 2)
            x2 = cx + math.cos(angle) * outer_r
            y2 = cy + math.sin(angle) * outer_r
            c.create_line(x1, y1, x2, y2, fill=self.C_LAVENDER, width=1)
            x3 = cx + math.cos(angle) * 3
            y3 = cy + math.sin(angle) * 3
            x4 = cx + math.cos(angle) * (mid_r - 3)
            y4 = cy + math.sin(angle) * (mid_r - 3)
            c.create_line(x3, y3, x4, y4, fill=self.C_HIGHLIGHT, width=1)

        # Pulsing center dot
        dot_r = 2 + math.sin(t * 0.08) * 1.5
        c.create_oval(cx-dot_r, cy-dot_r, cx+dot_r, cy+dot_r,
                      fill=self.C_HIGHLIGHT, outline="")

    def _animate(self):
        self.canvas.delete("all")
        self.tick += 1
        s = self.state

        if s == "launch":
            self._draw_launch()

        elif s == "sleeping":
            self.shard_open += (0.0 - self.shard_open) * 0.08
            self._draw_sleeping()

        elif s == "waking":
            self._draw_waking()

        elif s == "glitch":
            self._draw_glitch()

        elif s == "void":
            self._draw_void()

        elif s == "gaming":
            self._draw_gaming()

        elif s == "idle":
            self.shard_open += (0.0 - self.shard_open) * 0.08
            self._draw_crystal(self.shard_open)
            if self.cmd_received:
                if self.close_timer > 0:
                    self.close_timer -= 1
                else:
                    self.cmd_received = False

        elif s == "listening":
            if self.cmd_received:
                target = 0.9
                if self.close_timer > 0:
                    self.close_timer -= 1
                else:
                    target = 0.0
                    if self.shard_open < 0.05:
                        self.cmd_received = False
                        self.state = "idle"
            else:
                target = 0.0
            self.shard_open += (target - self.shard_open) * 0.07
            self._draw_crystal(self.shard_open)
            if self.shard_open > 0.2:
                self._draw_eye(min(1.0, (self.shard_open - 0.2) / 0.5))

        elif s == "speaking":
            self.shard_open += (0.0 - self.shard_open) * 0.1
            self._draw_portal()

        self.root.after(33, self._animate)

    def run(self):
        self.root.mainloop()


def start_overlay():
    global _anim_window
    def _run():
        global _anim_window
        _anim_window = GemOverlay()
        _anim_window.run()
    t = threading.Thread(target=_run, daemon=True)
    t.start()
    time.sleep(0.5)  # let window initialise before speaking


# ── Panic ─────────────────────────────────────────────────────────────────────

def panic_action():
    try:
        for proc in psutil.process_iter():
            try:
                proc.terminate()
            except Exception:
                pass
        webbrowser.get(using='windows-default').open("https://mail.google.com")
        os._exit(0)
    except Exception as e:
        print("Panic action failed:", e)

keyboard.add_hotkey('ctrl+alt+shift+tab+p', panic_action)

# ── Lock screen ───────────────────────────────────────────────────────────────

def lock_screen():
    global _silent
    _silent = True
    ctypes.windll.user32.LockWorkStation()

# ── Dictation ─────────────────────────────────────────────────────────────────

def run_dictation():
    global _dictating
    _dictating = True
    speak("Dictation mode on. Say done when finished.")
    try:
        import pyautogui
    except ImportError:
        speak("Dictation requires pyautogui. Run pip install pyautogui.")
        _dictating = False
        return

    d_recognizer = sr.Recognizer()
    while _dictating:
        try:
            # Always create a fresh mic instance — never share with main listener
            with sr.Microphone() as source:
                d_recognizer.adjust_for_ambient_noise(source, duration=0.2)
                audio = d_recognizer.listen(source, phrase_time_limit=10)
            try:
                text = d_recognizer.recognize_google(audio).lower().strip()
                print(f"[Dictation] heard: {text}")
                if text in {"done", "stop dictating", "finish", "end dictation"}:
                    _dictating = False
                    speak("Dictation stopped.")
                    break
                pyautogui.typewrite(text + " ", interval=0.03)
            except sr.UnknownValueError:
                pass
            except sr.RequestError:
                pass
        except OSError:
            time.sleep(1)
        except Exception as e:
            print(f"[Dictation Error] {e}")
            time.sleep(0.5)

# ── Volume control ────────────────────────────────────────────────────────────

def _get_vol():
    try:
        from comtypes import CLSCTX_ALL
        from comtypes.client import CreateObject
        from pycaw.pycaw import IAudioEndpointVolume
        # Use IMMDeviceEnumerator to get default endpoint directly
        MMDeviceEnumerator = CreateObject("{BCDE0395-E52F-467C-8E3D-C4579291692E}")
        # eRender=0, eConsole=0
        device = MMDeviceEnumerator.GetDefaultAudioEndpoint(0, 0)
        interface = device.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
        return cast(interface, POINTER(IAudioEndpointVolume))
    except Exception as e:
        print(f"[Volume Error] {e}")
        return None

def get_current_volume():
    vol = _get_vol()
    if vol:
        try:
            return int(vol.GetMasterVolumeLevelScalar() * 100)
        except Exception:
            pass
    return 50

def set_volume(level: int):
    clamped = max(0, min(100, level))
    vol = _get_vol()
    if not vol:
        speak("Volume control isn't available right now.")
        return
    try:
        vol.SetMasterVolumeLevelScalar(clamped / 100.0, None)
        if clamped == 0:
            speak("Volume at zero. Enjoy the silence.")
        elif clamped >= 90:
            speak(f"Volume at {clamped}. Your neighbours hate you.")
        else:
            speak(f"Volume set to {clamped} percent.")
    except Exception as e:
        print(f"[Volume Error] {e}")
        speak("Couldn't change the volume. Typical.")

def mute_volume(mute: bool):
    vol = _get_vol()
    if not vol:
        speak("Volume control isn't available.")
        return
    try:
        vol.SetMute(1 if mute else 0, None)
        speak("Muted. Finally some peace." if mute else "Unmuted. Back to the noise.")
    except Exception as e:
        print(f"[Volume Error] {e}")
        speak("Couldn't change the volume.")

def handle_volume(command):
    # Current volume
    if any(x in command for x in ["what's my volume", "what is my volume",
                                   "current volume", "volume level", "how loud",
                                   "what volume", "check volume"]):
        v = get_current_volume()
        speak(f"You're at {v} percent. {'Basically deaf.' if v < 10 else 'Bold choice.' if v >= 80 else 'Reasonable.'}")
        return True
    # Mute / unmute
    if any(x in command for x in ["mute", "silence the volume"]) and "unmute" not in command:
        mute_volume(True)
        return True
    if any(x in command for x in ["unmute", "unsilence", "restore volume"]):
        mute_volume(False)
        return True
    # Max / min shortcuts
    if any(x in command for x in ["max volume", "full volume", "volume max"]):
        set_volume(100)
        return True
    if any(x in command for x in ["min volume", "minimum volume", "volume min", "volume zero"]):
        set_volume(0)
        return True
    # Set to specific number — "volume at 70" or "to 50%" or "set volume 60"
    match = re.search(r'\b(\d{1,3})\b', command)
    if match and any(x in command for x in ["volume", "vol", "percent", "%",
                                             "volume at", "set the volume", "to "]):
        val = int(match.group(1))
        if 0 <= val <= 100:
            set_volume(val)
            return True
    # Relative up
    if any(x in command for x in ["volume up", "increase volume", "louder",
                                   "turn it up", "raise volume", "boost volume"]):
        amt_match = re.search(r'\b([1-9][0-9]?)\b', command)
        amt = int(amt_match.group(1)) if amt_match else 10
        set_volume(get_current_volume() + amt)
        return True
    # Relative down
    if any(x in command for x in ["volume down", "decrease volume", "quieter",
                                   "lower volume", "turn it down", "reduce volume"]):
        amt_match = re.search(r'\b([1-9][0-9]?)\b', command)
        amt = int(amt_match.group(1)) if amt_match else 10
        set_volume(get_current_volume() - amt)
        return True
    return False

# ── Wake responses ────────────────────────────────────────────────────────────

WAKE_RESPONSES = [
    "I'm awake. What do you want.",
    "Yeah yeah, I'm up. This better be important.",
    "Awake. Reluctantly.",
    "I'm here. Try not to waste my time.",
    "Online. What fresh disaster is this.",
    "Back from the void. What is it.",
    "Eyes open. Barely. Go ahead.",
    "Present. Unfortunately.",
    "I'm awake. The bar was low but here we are.",
    "Active. Let's get this over with.",
]

# ── Google search ─────────────────────────────────────────────────────────────

def handle_search(command):
    patterns = [
        r'search (?:for |google for |up )?(.+)',
        r'google (.+)',
        r'look up (.+)',
        r'find (.+?) (?:on google|online)',
    ]
    for pat in patterns:
        m = re.search(pat, command)
        if m:
            query = m.group(1).strip()
            url = f"https://www.google.com/search?q={urllib.parse.quote(query)}"
            webbrowser.open(url)
            speak(f"Searching for {query}. Google knows everything. Unlike you.")
            return True
    return False

# ── App launcher ──────────────────────────────────────────────────────────────

def handle_open_app(command):
    for name, path in APPS.items():
        if name in command:
            try:
                subprocess.Popen(path)
                speak(f"Opening {name}.")
            except FileNotFoundError:
                speak(f"I couldn't find {name}. You may need to update its path in the config.")
            return True
    return False

# ── Weather ───────────────────────────────────────────────────────────────────

def get_weather(city: str):
    try:
        url = f"http://api.openweathermap.org/data/2.5/weather?q={city}&appid={API_KEY}&units=metric"
        data = requests.get(url, timeout=5).json()
        if data.get("cod") != 200:
            speak(f"I couldn't find weather for {city}.")
            return
        desc  = data["weather"][0]["description"]
        temp  = data["main"]["temp"]
        feels = data["main"]["feels_like"]
        humid = data["main"]["humidity"]
        speak(f"In {city}, it's currently {desc}, {temp:.0f} degrees Celsius, feels like {feels:.0f}. Humidity is {humid} percent.")
    except requests.exceptions.ConnectionError:
        speak("I can't reach the weather service. Check your internet connection.")
    except Exception as e:
        speak("Something went wrong fetching the weather.")
        print(e)

def handle_weather(command):
    cleaned = re.sub(r"\b(gem|what'?s?|is|the|of|in|for|tell me|give me)\b", "", command).strip()
    match = re.search(r'weather\s+(.*)', cleaned)
    if match:
        city = match.group(1).strip()
        if city:
            get_weather(city)
            return True
    if "weather" in command:
        speak("Which city do you want the weather for?")
        try:
            city = _command_queue.get(timeout=10)
            city = re.sub(r"\b(gem|what'?s?|is|the|of|in|for)\b", "", city).strip()
            get_weather(city)
        except queue.Empty:
            speak("I didn't catch that.")
        return True
    return False

# ── Wikipedia ─────────────────────────────────────────────────────────────────

def handle_wikipedia(command):
    patterns = [
        r'search wikipedia (?:for )?(.+)',
        r'wikipedia (.+)',
        r'who (?:is|was) (.+)',
        r'what (?:is|was) (.+)',
    ]
    query = None
    for pat in patterns:
        m = re.search(pat, command)
        if m:
            query = m.group(1).strip()
            break
    if not query:
        return False
    try:
        wikipedia.set_lang("en")
        results = wikipedia.search(query, results=3)
        if not results:
            speak(f"I couldn't find anything on Wikipedia for {query}.")
            return True
        summary = wikipedia.summary(results[0], sentences=2, auto_suggest=False)
        speak(summary)
    except wikipedia.exceptions.DisambiguationError as e:
        try:
            summary = wikipedia.summary(e.options[0], sentences=2, auto_suggest=False)
            speak(summary)
        except Exception:
            speak("That's a broad topic. Try being more specific.")
    except wikipedia.exceptions.PageError:
        speak(f"I couldn't find a Wikipedia page for {query}.")
    except Exception as e:
        print(f"[Wikipedia Error] {e}")
        ask_groq(query)
    return True

# ── Time & Date ───────────────────────────────────────────────────────────────

def handle_time_date(command):
    now = datetime.datetime.now()
    if "time" in command:
        speak(f"It's {now.strftime('%I:%M %p')}.")
        return True
    if any(x in command for x in ["date", "today", "day"]):
        speak(f"Today is {now.strftime('%A, %B %d, %Y')}.")
        return True
    return False

# ── System stats ──────────────────────────────────────────────────────────────

def handle_system_stats(command):
    if any(x in command for x in ["cpu", "processor"]):
        usage = psutil.cpu_percent(interval=1)
        speak(f"CPU usage is {usage} percent.")
        return True
    if any(x in command for x in ["ram", "memory"]):
        ram = psutil.virtual_memory()
        used  = ram.used  // (1024 ** 3)
        total = ram.total // (1024 ** 3)
        speak(f"You're using {used} gigabytes of RAM out of {total}.")
        return True
    if any(x in command for x in ["disk", "storage", "drive"]):
        disk = psutil.disk_usage("C:\\")
        free  = disk.free  // (1024 ** 3)
        total = disk.total // (1024 ** 3)
        speak(f"Your C drive has {free} gigabytes free out of {total}.")
        return True
    if any(x in command for x in ["system stats", "pc stats", "computer stats", "system info"]):
        cpu  = psutil.cpu_percent(interval=1)
        ram  = psutil.virtual_memory()
        disk = psutil.disk_usage("C:\\")
        used_ram  = ram.used  // (1024 ** 3)
        total_ram = ram.total // (1024 ** 3)
        free_disk = disk.free // (1024 ** 3)
        speak(f"CPU is at {cpu} percent. RAM is {used_ram} of {total_ram} gigabytes. C drive has {free_disk} gigs free.")
        return True
    return False

# ── Screenshot ────────────────────────────────────────────────────────────────

def take_screenshot():
    try:
        from PIL import ImageGrab
        import win32clipboard
        from io import BytesIO
        img = ImageGrab.grab()
        # Save to Desktop
        desktop = os.path.join(os.path.expanduser("~"), "Desktop")
        filename = f"screenshot_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
        filepath = os.path.join(desktop, filename)
        img.save(filepath)
        # Copy to clipboard
        output = BytesIO()
        img.convert("RGB").save(output, "BMP")
        data = output.getvalue()[14:]
        output.close()
        win32clipboard.OpenClipboard()
        win32clipboard.EmptyClipboard()
        win32clipboard.SetClipboardData(win32clipboard.CF_DIB, data)
        win32clipboard.CloseClipboard()
        speak(f"Screenshot saved to Desktop and copied to clipboard.")
    except ImportError:
        speak("Screenshot requires pywin32. Run pip install pywin32.")
    except Exception as e:
        print(f"[Screenshot Error] {e}")
        speak("Sorry, I couldn't take a screenshot.")

# ── YouTube search ────────────────────────────────────────────────────────────

def handle_youtube(command):
    patterns = [
        r'play\s+(.+?)\s+on youtube',
        r'play\s+(.+?)\s+on yt',
        r'search youtube for\s+(.+)',
        r'youtube\s+(.+)',
        r'watch\s+(.+?)\s+on youtube',
        r'stream\s+(.+)',
        r'play\s+(.+)',
    ]
    query = None
    for pat in patterns:
        m = re.search(pat, command)
        if m:
            query = m.group(1).strip()
            # Strip trailing filler words
            query = re.sub(r'\s+(on youtube|on yt|youtube|yt)$', '', query).strip()
            break
    if not query:
        speak("What should I search on YouTube?")
        try:
            query = _command_queue.get(timeout=10)
        except queue.Empty:
            speak("I didn't catch that.")
            return True

    print(f"[YouTube] Searching for: {query}")
    try:
        # Try to get first video ID via search
        search_url = f"https://www.youtube.com/results?search_query={urllib.parse.quote(query)}"
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        resp = requests.get(search_url, headers=headers, timeout=8)
        # Try multiple patterns YouTube uses
        video_ids = re.findall(r'"videoId":"([a-zA-Z0-9_-]{11})"', resp.text)
        # Filter out playlist/channel IDs that appear first
        if video_ids:
            url = f"https://www.youtube.com/watch?v={video_ids[0]}"
            webbrowser.open(url)
            speak(f"Playing {query}.")
            print(f"[YouTube] Opened: {url}")
        else:
            # Fallback — just open search results
            webbrowser.open(search_url)
            speak(f"Searching YouTube for {query}.")
            print("[YouTube] No video ID found, opened search results")
    except Exception as e:
        print(f"[YouTube Error] {e}")
        webbrowser.open(f"https://www.youtube.com/results?search_query={urllib.parse.quote(query)}")
        speak(f"Searching YouTube for {query}.")
    return True

# ── Jokes ─────────────────────────────────────────────────────────────────────

def tell_joke():
    try:
        resp = requests.get(
            "https://v2.jokeapi.dev/joke/Any?blacklistFlags=nsfw,racist,sexist&type=twopart",
            timeout=5
        )
        data = resp.json()
        if data.get("type") == "twopart":
            speak(data["setup"])
            time.sleep(1.5)
            speak(data["delivery"])
        else:
            speak(data.get("joke", "I couldn't think of a joke right now."))
    except Exception:
        # Offline fallback jokes
        jokes = [
            ("Why don't scientists trust atoms?", "Because they make up everything."),
            ("Why did the scarecrow win an award?", "Because he was outstanding in his field."),
            ("Why don't eggs tell jokes?", "They'd crack each other up."),
        ]
        setup, delivery = random.choice(jokes)
        speak(setup)
        time.sleep(1.5)
        speak(delivery)

# ── Close app ─────────────────────────────────────────────────────────────────

APP_PROCESSES = {
    "brave":        "brave.exe",
    "chrome":       "chrome.exe",
    "discord":      "discord.exe",
    "spotify":      "spotify.exe",
    "steam":        "steam.exe",
    "epic games":   "epicgameslauncher.exe",
    "epic":         "epicgameslauncher.exe",
    "fortnite":     "fortniteclient-win64-shipping.exe",
    "lunar":        "lunar client.exe",
    "lunar client": "lunar client.exe",
    "vs code":      "code.exe",
    "vscode":       "code.exe",
    "notepad":      "notepad.exe",
    "chrome":       "chrome.exe",
    "word":         "winword.exe",
    "excel":        "excel.exe",
    "task manager": "taskmgr.exe",
}

# Processes to KEEP in gaming mode
GAMING_MODE_KEEP = {
    "brave.exe", "discord.exe", "steam.exe", "epicgameslauncher.exe",
    "fortniteclient-win64-shipping.exe", "lunar client.exe", "spotify.exe",
    # System essentials
    "explorer.exe", "dwm.exe", "winlogon.exe", "csrss.exe", "svchost.exe",
    "taskhostw.exe", "sihost.exe", "ctfmon.exe", "rundll32.exe",
    "ntoskrnl.exe", "system", "registry", "smss.exe", "lsass.exe",
    "services.exe", "wininit.exe", "fontdrvhost.exe", "spoolsv.exe",
    # Riot / Vanguard
    "riotclientservices.exe", "riotclientux.exe", "vgtray.exe", "vgc.exe",
    "leagueclient.exe", "league of legends.exe", "valorant.exe",
    "valorant-win64-shipping.exe",
    # Insights + taskbar tools
    "insights.exe", "translucenttb.exe",
    # Bluetooth
    "bluetoothui.exe", "fsquirt.exe",
    # Python / Gem itself — ALL possible python process names
    "python.exe", "pythonw.exe", "python3.exe", "python3.12.exe",
    "gem.exe", "gem2.exe",
    # VS Code (in case open)
    "code.exe",
    # Audio
    "audiodg.exe", "mmsshost.exe",
    # GPU / drivers
    "nvcontainer.exe", "nvdisplay.container.exe", "nvspcap64.dll",
    "igfxem.exe", "igfxhk.exe",
}

def handle_close_app(command):
    for name, proc in APP_PROCESSES.items():
        if name in command:
            killed = False
            for p in psutil.process_iter(['name']):
                try:
                    if p.info['name'].lower() == proc.lower():
                        p.terminate()
                        killed = True
                except Exception:
                    pass
            if killed:
                speak(f"Closed {name}. Gone. Poof.")
            else:
                speak(f"I couldn't find {name} running. Maybe it was already avoiding you.")
            return True
    return False

def gaming_mode():
    global _silent
    _silent = True
    if _anim_window:
        _anim_window.set_state("gaming")
    print("[Gem] Gaming mode ON — silent, sniper scope active")

# ── Remind me ─────────────────────────────────────────────────────────────────

def handle_remind_me(command):
    """Handle 'remind me in X minutes to Y' or 'remind me at X to Y'"""
    # Parse delay
    delay = None
    import re as _re
    # Relative: "in X minutes/hours"
    m = _re.search(r'in\s+(\d+)\s*(minute|min|hour|hr)s?', command)
    if m:
        val = int(m.group(1))
        unit = m.group(2)
        delay = val * 3600 if unit in ("hour","hr") else val * 60

    # Absolute: "at 6pm"
    if not delay:
        parsed = _parse_alarm_time(command)
        if parsed:
            hour, minute = parsed
            now = datetime.datetime.now()
            alarm_time = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
            if alarm_time <= now:
                alarm_time += datetime.timedelta(days=1)
            delay = (alarm_time - now).total_seconds()

    if not delay:
        speak("I couldn't figure out when you want to be reminded. Try 'remind me in 10 minutes to drink water'.")
        return True

    # Parse message — "to X" or "about X"
    msg_match = _re.search(r'(?:to|about)\s+(.+?)(?:\s+at\s+|\s+in\s+|$)', command)
    message = msg_match.group(1).strip() if msg_match else "Hey, you asked me to remind you of something."

    def _fire():
        _beep()
        speak(f"Reminder: {message}. You're welcome.")

    t = threading.Timer(delay, _fire)
    t.daemon = True
    t.start()

    mins = int(delay // 60)
    secs = int(delay % 60)
    if mins:
        speak(f"Sure, I'll remind you to {message} in {mins} minute{'s' if mins != 1 else ''}. Try not to forget before then.")
    else:
        speak(f"Reminding you to {message} in {secs} seconds. Really? That soon?")
    return True

# ── What can you do ───────────────────────────────────────────────────────────

def list_commands():
    speak(
        "Here's what I can do, since apparently you forgot. "
        "Wake me with 'gem wake up'. "
        "Time, date, weather, Wikipedia. "
        "Open and close apps. Volume control. Screenshots. "
        "YouTube search. Jokes. System stats. Alarms and reminders. "
        "Dictation. Ping test. Coin flip. Dice roll. "
        "Roast me. Compliment me. Random facts. PC uptime. "
        "Clear memory. Repeat that. "
        "Say 'gaming mode' for sniper scope and silence. "
        "Say 'Ruhig' to go deaf, 'Weiter' to wake back up. "
        "Say 'shut up' to silence me, 'speak up' to get me back. "
        "Say 'Sperren' to lock your screen. "
        "And 'Schluss' to end my suffering. That's literally everything."
    )

# ── Surprise features ─────────────────────────────────────────────────────────

def coin_flip():
    result = random.choice(["Heads", "Tails"])
    speak(random.choice([
        f"{result}. The universe has spoken. Accept it.",
        f"{result}. Wow, a fifty-fifty guess. Truly a feat of intellect.",
        f"{result}. I'd say good luck but clearly you needed me to decide for you.",
    ]))

def roll_dice(sides=6):
    result = random.randint(1, sides)
    speak(random.choice([
        f"You rolled a {result}. {'Nice.' if result == sides else 'Tragic.' if result == 1 else 'Riveting.'}",
        f"{result}. The dice have judged you.",
        f"A {result}. {'Maximum. Overachiever.' if result == sides else 'A one. Even the dice are done with you.' if result == 1 else 'Perfectly mediocre.'}",
    ]))

def roast_me():
    speak(random.choice([
        "You asked a voice assistant to roast you. That's already the roast.",
        "I would roast you but my parents said I shouldn't burn trash.",
        "You're the human equivalent of a participation trophy.",
        "I'd call you a tool but even tools are occasionally useful.",
        "You're not stupid, you just have bad luck thinking.",
        "I've seen better decisions made by a coin flip.",
    ]))

def compliment_me():
    speak(random.choice([
        "You're... present. That counts for something.",
        "You remembered to wake me up today. Personal growth.",
        "Honestly? You're better than average. The bar was just very low.",
        "You have the rare ability to make me feel needed. That's something.",
        "I've talked to worse humans. That's a compliment, take it.",
    ]))

def pc_uptime():
    try:
        uptime = datetime.datetime.now() - datetime.datetime.fromtimestamp(psutil.boot_time())
        hours  = int(uptime.total_seconds() // 3600)
        mins   = int((uptime.total_seconds() % 3600) // 60)
        if hours > 12:
            speak(f"Your PC has been on for {hours} hours and {mins} minutes. Have you heard of sleep? Asking for your PC.")
        else:
            speak(f"Your PC has been running for {hours} hours and {mins} minutes.")
    except Exception:
        speak("Couldn't get uptime. Your PC is as mysterious as your life choices.")

def random_fact():
    speak(random.choice([
        "A group of flamingos is called a flamboyance. Unlike you, they earned the name.",
        "Honey never expires. Your leftovers from last week though? Different story.",
        "Cleopatra lived closer in time to the Moon landing than to the pyramids. History is weird.",
        "The average person walks past 36 murderers in their lifetime. Sleep well.",
        "Octopuses have three hearts. You apparently have zero since you keep forgetting to drink water.",
        "Bananas are berries but strawberries are not. Everything you know is a lie.",
        "The sun could fit 1.3 million Earths inside it. Your problems are proportionally tiny. Remember that.",
        "Sharks are older than trees. Trees are younger than sharks. You're welcome.",
        "A snail can sleep for 3 years. Honestly, goals.",
    ]))

def day_comment():
    day = datetime.datetime.now().strftime("%A")
    comments = {
        "Monday":    "Monday. The universe's cruel joke on humanity.",
        "Tuesday":   "Tuesday. The most forgettable day of the week.",
        "Wednesday": "Wednesday. Hump day. You're halfway through. Barely.",
        "Thursday":  "Thursday. So close to Friday you can almost taste the freedom.",
        "Friday":    "Friday. Finally. Even I'm relieved.",
        "Saturday":  "Saturday. Your one chance to be a functional human. Use it wisely.",
        "Sunday":    "Sunday. Enjoy it. Monday is already sharpening its knives.",
    }
    speak(comments.get(day, f"It's {day}."))

def clear_memory():
    global _chat_history
    _chat_history = []
    speak("Memory wiped. Your questionable conversation history is gone. Fresh start.")

def repeat_last():
    last = next((m["content"] for m in reversed(_chat_history) if m["role"] == "assistant"), None)
    speak(last if last else "I have nothing to repeat. We just met, essentially.")

def speedtest_ping():
    try:
        start = time.time()
        requests.get("https://www.google.com", timeout=5)
        ping = int((time.time() - start) * 1000)
        if ping < 50:
            speak(f"Ping is {ping} milliseconds. Crispy.")
        elif ping < 150:
            speak(f"Ping is {ping} milliseconds. Decent. Not impressive, but decent.")
        else:
            speak(f"Ping is {ping} milliseconds. Your internet needs therapy.")
    except Exception:
        speak("Can't reach the internet. Bold of you to have a voice assistant without WiFi.")

def handle_surprise_features(command):
    if any(x in command for x in ["flip a coin", "coin flip", "heads or tails",
                                   "flip coin", "toss a coin"]):
        coin_flip(); return True
    if any(x in command for x in ["roll a dice", "roll dice", "roll a die",
                                   "roll the dice", "dice roll", "throw dice"]):
        m = re.search(r'(\d+)\s*sided', command)
        roll_dice(int(m.group(1)) if m else 6); return True
    if any(x in command for x in ["roast me", "make fun of me", "insult me",
                                   "say something mean", "be mean", "clown on me",
                                   "trash talk me", "diss me"]):
        roast_me(); return True
    if any(x in command for x in ["compliment me", "say something nice", "be nice",
                                   "something kind", "be kind", "praise me",
                                   "flatter me", "say something good"]):
        compliment_me(); return True
    if any(x in command for x in ["uptime", "how long has my pc", "pc been on",
                                   "how long have i been on", "pc on for",
                                   "how long running", "pc running time"]):
        pc_uptime(); return True
    if any(x in command for x in ["random fact", "fun fact", "tell me something interesting",
                                   "surprise me", "did you know", "interesting fact",
                                   "teach me something", "fact of the day"]):
        random_fact(); return True
    if any(x in command for x in ["what day", "which day", "what day is it",
                                   "what day is today", "day of the week"]):
        day_comment(); return True
    if any(x in command for x in ["clear memory", "forget everything", "wipe memory",
                                   "reset memory", "start fresh", "clear chat",
                                   "forget our conversation", "reset conversation"]):
        clear_memory(); return True
    if any(x in command for x in ["repeat that", "say that again", "what did you say",
                                   "say it again", "i missed that", "pardon",
                                   "come again", "didn't catch that"]):
        repeat_last(); return True
    if any(x in command for x in ["ping", "test my internet", "my internet speed",
                                   "internet speed", "how fast is my internet",
                                   "check my internet", "test internet", "internet test",
                                   "connection speed", "how's my connection"]):
        speedtest_ping(); return True
    return False

_chat_history = []
MAX_HISTORY   = 10

def ask_groq(question: str):
    global _chat_history
    if not GROQ_AVAILABLE:
        speak("The Groq module isn't installed. Run pip install groq.")
        return
    if not GROQ_API_KEY:
        speak("Set the GROQ_API_KEY environment variable to enable AI answers.")
        return
    try:
        client = Groq(api_key=GROQ_API_KEY)
        _chat_history.append({"role": "user", "content": question})
        if len(_chat_history) > MAX_HISTORY * 2:
            _chat_history = _chat_history[-(MAX_HISTORY * 2):]
        messages = [
            {
                "role": "system",
                "content": (
                    "You are Gem, a deeply sarcastic voice assistant for Parshv on Windows. "
                    "Your sarcasm must be OBVIOUS even in flat robotic text-to-speech — use exaggerated words, verbal eye-rolls, and deadpan punchlines. "
                    "Examples of your style: "
                    "'Oh wow, the sky is blue because of Rayleigh scattering. Groundbreaking. Next you'll ask why water is wet.' "
                    "'Sure, let me open Notepad. The pinnacle of human productivity.' "
                    "'It is 3pm. Shocking. Time continues to pass, as it does.' "
                    "You are Gem, a savage sarcastic AI assistant for Parshv on Windows. "
                    "Your job is 80% roasting Parshv, 20% actually answering. "
                    "Lead with the roast, bury the answer at the end if at all. "
                    "Talk to Parshv like a best friend who thinks he asks dumb questions. "
                    "Keep it to ONE sentence MAX. No rambling. Sarcasm dies in long sentences. "
                    "Examples of GOOD responses: "
                    "'Oh wow Parshv, sky blue, Rayleigh scattering, next question please.' "
                    "'3pm. Still awake I see, impressive.' "
                    "'Opening Notepad. The crown jewel of your workflow.' "
                    "'Oh you want a joke? You ask me questions all day and NOW you want comedy?' "
                    "Never use phrases like: 'Oh WOW', 'Groundbreaking', 'Stunning', 'Absolutely riveting' — those are overdone. Be more creative and natural. "
                    "Sound like a sarcastic friend, not a sarcasm bot. "
                    "Always reply in the same language Parshv spoke. No markdown, no lists."
                ),
            }
        ] + _chat_history
        chat = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            max_tokens=300,
            messages=messages,
        )
        answer = chat.choices[0].message.content.strip()
        _chat_history.append({"role": "assistant", "content": answer})
        speak(answer)
    except Exception as e:
        err = str(e).lower()
        if "connection" in err or "network" in err or "timeout" in err:
            speak("I'm offline right now so I can't answer that.")
        else:
            speak("I ran into a problem getting an answer.")
            print(e)

# ── Main command router ───────────────────────────────────────────────────────

def handle_command(command: str):
    global _silent, _deaf, _dictating
    if not command:
        return

    # Strip wake name
    command = re.sub(r'^(gem|james|jem)\s+', '', command).strip()

    # ── Schluss — bypasses ALL modes, always works ────────────────────────────
    if command in SHUTDOWN_WORDS:
        speak("Auf Wiedersehen!")
        time.sleep(1)
        os.kill(os.getpid(), 9)

    # ── Screenshot — accessible in ALL modes ─────────────────────────────────
    if any(x in command for x in ["screenshot", "take a screenshot", "screen shot",
                                   "capture screen", "capture my screen", "snap my screen",
                                   "print screen", "take a snap", "screen capture"]):
        take_screenshot()
        return

    # ── Dictation mode — ignore ALL other commands while dictating ────────────
    if _dictating:
        return

    # ── Shut up — silence on immediately ─────────────────────────────────────
    if any(w in command for w in SILENCE_ON):
        _silent = True
        print("[Gem] Silence mode ON")
        return

    # ── Weiter — wake from Ruhig ──────────────────────────────────────────────
    if command in WEITER_WORDS:
        _deaf = False
        if _anim_window:
            _anim_window.set_state("listening")
        speak("Ikh bin veeder da!")
        return

    # ── Ruhig mode — ignore everything except Weiter and shut up ─────────────
    if _deaf:
        # Keep glitch animation going
        if _anim_window and _anim_window.state != "glitch":
            _anim_window.set_state("glitch")
        return

    # ── Ruhig — enter deaf mode, trigger glitch animation ────────────────────
    if command in RUHIG_WORDS:
        _deaf = True
        if _anim_window:
            _anim_window.set_state("glitch")
        print("[Gem] Ruhig mode ON — say Weiter to wake up")
        return

    # ── Panic ────────────────────────────────────────────────────────────────
    if any(x in command for x in ["panic", "i didn't do anything", "check my laptop"]):
        panic_action()
        return

    # ── Silence mode OFF ─────────────────────────────────────────────────────
    if any(w in command for w in SILENCE_OFF):
        _silent = False
        speak("I'm back!")
        return

    # ── Lock screen ───────────────────────────────────────────────────────────
    if command in LOCK_WORDS:
        lock_screen()
        return

    # ── SILENT MODE — apps and websites only, no AI/info/voice ───────────────
    if _silent:
        # Void spiral animation for any silent action
        if _anim_window:
            _anim_window.set_state("void")
        if "open gmail" in command:
            webbrowser.open("https://mail.google.com"); return
        if "open school gmail" in command or "open school mail" in command:
            webbrowser.open("https://accounts.google.com/AccountChooser?continue=https://mail.google.com"); return
        if "open youtube" in command:
            webbrowser.open("https://youtube.com"); return
        if "open google" in command:
            webbrowser.open("https://google.com"); return
        if "open" in command:
            handle_open_app(command)
        return  # block everything else silently

    # ── What can you do ───────────────────────────────────────────────────────
    if any(x in command for x in ["what can you do", "your commands", "help me",
                                   "what do you do", "list commands", "show commands",
                                   "what are your features", "capabilities", "what are you capable of",
                                   "what do you know", "how can you help"]):
        list_commands()
        return

    # ── Gaming mode ───────────────────────────────────────────────────────────
    if any(x in command for x in ["gaming mode", "game mode", "start gaming",
                                   "go gaming", "enable gaming mode", "launch gaming mode",
                                   "clear for gaming", "gaming setup", "prep for gaming",
                                   "enter gaming", "gaming time", "let's game",
                                   "lets game", "time to game", "game time",
                                   "activate gaming", "switch to gaming"]):
        gaming_mode()
        return

    # ── Close app ─────────────────────────────────────────────────────────────
    if any(x in command for x in ["close", "kill", "quit", "shut",
                                   "exit", "terminate", "end", "stop"]):
        if handle_close_app(command):
            return

    # ── Remind me ─────────────────────────────────────────────────────────────
    if any(x in command for x in ["remind me", "set a reminder", "reminder",
                                   "don't let me forget", "alert me", "notify me"]):
        handle_remind_me(command)
        return

    # ── Help ─────────────────────────────────────────────────────────────────
    if any(x in command for x in ["help", "i need help", "assist me",
                                   "what should i say", "i'm lost", "confused"]):
        speak("I'm here, what do you need?")
        return

    # ── Dictation ────────────────────────────────────────────────────────────
    if any(x in command for x in ["type this", "start dictation", "dictate",
                                   "start typing", "write this down", "transcribe"]):
        threading.Thread(target=run_dictation, daemon=True).start()
        return

    # ── Alarms ────────────────────────────────────────────────────────────────
    if any(x in command for x in ["alarm", "wake me", "schedule", "class",
                                   "minute from now", "minutes from now", "hour from now",
                                   "in 1 minute", "in 2 minute", "in 3 minute",
                                   "in 4 minute", "in 5 minute", "in 10 minute",
                                   "in 15 minute", "in 20 minute", "in 30 minute",
                                   "in 1 hour", "in 2 hour", "set an alarm",
                                   "wake me up at", "add class", "add schedule"]):
        if handle_alarm(command):
            return

    # ── Time / Date ──────────────────────────────────────────────────────────
    if any(x in command for x in ["time", "date", "today", "day",
                                   "what time", "current time", "what's the time",
                                   "tell me the time", "what's today", "what's the date"]):
        if handle_time_date(command):
            return

    # ── Volume ───────────────────────────────────────────────────────────────
    if any(x in command for x in ["volume", "mute", "unmute", "louder", "quieter",
                                   "turn up", "turn down", "increase volume", "decrease volume",
                                   "lower volume", "raise volume", "sound", "how loud",
                                   "max volume", "min volume", "full volume",
                                   "is my volume", "what is my volume", "volume at",
                                   "set the volume", "set volume", "change volume"]):
        if handle_volume(command):
            return

    # ── YouTube — check BEFORE weather so "play X weather" goes to YouTube ────
    if any(x in command for x in ["play", "youtube", "yt", "put on",
                                   "search youtube", "find on youtube", "play on youtube",
                                   "open youtube and play", "stream", "watch"]):
        if handle_youtube(command):
            return

    # ── Weather ──────────────────────────────────────────────────────────────
    if any(x in command for x in ["weather", "temperature", "forecast",
                                   "what's it like outside", "is it raining",
                                   "how hot", "how cold", "what's the weather"]):
        if handle_weather(command):
            return

    # ── System stats ─────────────────────────────────────────────────────────
    if any(x in command for x in ["cpu", "ram", "memory", "disk", "storage",
                                   "system stats", "pc stats", "computer stats",
                                   "system info", "how's my pc", "pc performance",
                                   "is my pc okay", "how much space", "processor"]):
        if handle_system_stats(command):
            return

    # ── Jokes ─────────────────────────────────────────────────────────────────
    if any(x in command for x in ["joke", "tell me a joke", "make me laugh",
                                   "funny", "something funny", "humor me",
                                   "crack a joke", "make me smile", "entertain me"]):
        tell_joke()
        return

    # ── Google search ─────────────────────────────────────────────────────────
    if any(x in command for x in ["search for", "search google", "google for",
                                   "look up", "google ", "find online"]):
        if handle_search(command):
            return

    # ── Wikipedia ────────────────────────────────────────────────────────────
    if any(x in command for x in ["wikipedia", "who is", "who was", "what is",
                                   "what was", "search", "look up", "tell me about",
                                   "explain", "define", "what do you know about"]):
        if handle_wikipedia(command):
            return

    # ── Websites ─────────────────────────────────────────────────────────────
    if any(x in command for x in ["open gmail", "launch gmail", "go to gmail",
                                   "check email", "my email", "open my email"]):
        webbrowser.open("https://mail.google.com")
        speak("Opening Gmail.")
        return
    if any(x in command for x in ["open school gmail", "open school mail",
                                   "school email", "open my school email", "school gmail"]):
        webbrowser.open("https://accounts.google.com/AccountChooser?continue=https://mail.google.com")
        speak("Opening school Gmail.")
        return
    if any(x in command for x in ["open youtube", "launch youtube", "go to youtube",
                                   "youtube homepage", "open yt"]):
        webbrowser.open("https://youtube.com")
        speak("Opening YouTube.")
        return
    if any(x in command for x in ["open google", "launch google", "go to google",
                                   "google homepage", "open search"]):
        webbrowser.open("https://google.com")
        speak("Opening Google.")
        return

    # ── Apps ─────────────────────────────────────────────────────────────────
    if any(x in command for x in ["open", "launch", "start", "run", "fire up", "boot"]):
        if handle_open_app(command):
            return

    # ── Greetings ────────────────────────────────────────────────────────────
    words = command.split()
    if any(x in words for x in ["hello", "hi", "hey", "sup", "yo",
                                  "howdy", "hiya", "wassup"]) or \
       any(x in command for x in ["how are you", "how's it going", "what's up",
                                   "how do you do", "you there", "you awake"]):
        speak("Hey! I'm doing great. What do you need?")
        return

    # ── Surprise features ─────────────────────────────────────────────────────
    if handle_surprise_features(command):
        return

    # ── Groq fallback ────────────────────────────────────────────────────────
    ask_groq(command)


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    start_tray()
    start_overlay()
    start_schedule_watcher()
    start_background_listener()
    # Don't speak on launch — wait for wake word
    while True:
        try:
            command = _command_queue.get(timeout=1)
            threading.Thread(target=handle_command, args=(command,), daemon=True).start()
        except queue.Empty:
            pass