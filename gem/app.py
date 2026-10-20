"""Startup: build every service, wire them together, run the UI."""
import ctypes
import logging
import logging.handlers
import os
import subprocess
import sys
import threading
import time

from . import __version__
from .config import DATA_DIR, LOG_FILE, load_settings, runtime
from .runtime import caption, svc
from .state import ALWAYS_LISTENING, MODE_NAMES, PUSH_TO_TALK, State

log = logging.getLogger("gem")

MUTEX_NAME = "Local\\GemVoiceAssistant"
RESTART_FLAG = "--restart"


def _setup_logging():
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    fmt = logging.Formatter("%(asctime)s %(levelname)-7s %(name)s: %(message)s", "%H:%M:%S")
    fh = logging.handlers.RotatingFileHandler(LOG_FILE, maxBytes=1_000_000, backupCount=2, encoding="utf-8")
    fh.setFormatter(fmt)
    root.addHandler(fh)
    if sys.stdout and sys.stdout.isatty():
        sh = logging.StreamHandler(sys.stdout)
        sh.setFormatter(fmt)
        root.addHandler(sh)
    for noisy in ("urllib3", "comtypes", "PIL", "asyncio", "websockets", "aiohttp"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def _single_instance():
    """Own a named mutex for our lifetime. After a restart, wait for the old copy to exit."""
    kernel32 = ctypes.windll.kernel32
    kernel32.CreateMutexW.restype = ctypes.c_void_p
    handle = kernel32.CreateMutexW(None, True, MUTEX_NAME)
    if kernel32.GetLastError() != 183:          # ERROR_ALREADY_EXISTS
        return handle
    if RESTART_FLAG in sys.argv:
        r = kernel32.WaitForSingleObject(ctypes.c_void_p(handle), 15000)
        if r in (0, 0x80):                      # signalled or abandoned: the old Gem is gone
            return handle
    return None


def _ensure_shortcut():
    """Keep a Start Menu shortcut to the installed exe, so Gem shows up in Start search."""
    installed = os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs", "Gem", "Gem.exe")
    if not getattr(sys, "frozen", False) or os.path.normcase(sys.executable) != os.path.normcase(installed):
        return                                  # only the installed copy, never a test build in dist\
    try:
        import pythoncom
        import win32com.client
        pythoncom.CoInitialize()
        path = os.path.join(os.environ.get("APPDATA", ""), r"Microsoft\Windows\Start Menu\Programs\Gem.lnk")
        sh = win32com.client.Dispatch("WScript.Shell")
        if os.path.exists(path) and os.path.normcase(sh.CreateShortcut(path).TargetPath) == os.path.normcase(sys.executable):
            return
        lnk = sh.CreateShortcut(path)
        lnk.TargetPath = sys.executable
        lnk.WorkingDirectory = os.path.dirname(sys.executable)
        lnk.IconLocation = sys.executable + ",0"
        lnk.Description = "Gem voice assistant"
        lnk.Save()
        log.info("Start Menu shortcut created")
    except Exception:
        log.debug("Couldn't create the Start Menu shortcut", exc_info=True)


def restart():
    """Start a fresh copy of Gem, then quit this one."""
    if getattr(sys, "frozen", False):
        cmd = [sys.executable, RESTART_FLAG]
    else:
        script = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "gem2.py"))
        exe = sys.executable
        pyw = os.path.join(os.path.dirname(exe), "pythonw.exe")
        cmd = [pyw if os.path.exists(pyw) else exe, script, RESTART_FLAG]
    log.info("Restarting: %s", cmd)
    subprocess.Popen(cmd, cwd=os.path.dirname(cmd[1]) if len(cmd) > 2 else None,
                     creationflags=subprocess.DETACHED_PROCESS)
    _quit()


def _quit():
    log.info("Shutting down")
    try:
        if svc.ducker:
            svc.ducker.release_all()
        if svc.lights:
            svc.lights.close()
        if svc.tray:
            svc.tray.stop()
    finally:
        if svc.overlay:
            svc.overlay.quit()
        threading.Timer(1.5, lambda: os._exit(0)).start()


# ── Caps Lock behaviour ──────────────────────────────────────────────────────

def _on_press():
    st = svc.state
    svc.voice.stop()
    st.update(key_held=True)
    talk = st.effective_mode == PUSH_TO_TALK
    if talk:
        svc.sounds.play("listen_start")     # right away, before you start speaking
        svc.ducker.duck("listen")
    svc.listener.begin_hold(talk=talk)
    svc.lights.show("talk" if talk else "mute")
    if talk:
        svc.overlay.dismiss()


def _on_release(was_tap):
    st = svc.state
    talk = st.effective_mode == PUSH_TO_TALK
    st.update(key_held=False)
    svc.listener.end_hold(discard=was_tap)
    svc.lights.show("normal")
    svc.ducker.unduck("listen", delay=0.6)
    if talk and not was_tap:
        # After the recording tail, so the tone isn't captured.
        threading.Timer(0.32, svc.sounds.play, args=("listen_end",)).start()


def _on_tap():
    svc.overlay.dismiss()      # pressing already stopped any speech


def _on_triple_tap():
    from . import actions
    actions.run("set_mode", {"mode": "toggle"})
    mode = svc.state.mode
    caption(MODE_NAMES[mode] + (". Hold Caps Lock to talk." if mode == PUSH_TO_TALK else
                                ". Hold Caps Lock to mute me for a moment."), seconds=3.5)


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    _setup_logging()
    log.info("Gem %s starting (data in %s)", __version__, DATA_DIR)
    if _single_instance() is None:
        ctypes.windll.user32.MessageBoxW(None, "Gem is already running. Look for the crystal in the tray.", "Gem", 0x40)
        return

    cfg = load_settings()
    svc.config = cfg

    mode = runtime.data.get("mode") or cfg["listening"].get("default_mode", PUSH_TO_TALK)
    if mode not in (PUSH_TO_TALK, ALWAYS_LISTENING):
        mode = PUSH_TO_TALK
    st = State(mode=mode, conversation_window=cfg["listening"].get("conversation_window", 25))
    st.voice_enabled = runtime.data.get("voice_enabled", True)
    st.speak_in_calls = cfg["voice"].get("speak_in_calls", False)
    st.speak_in_gaming = cfg["voice"].get("speak_in_gaming", False)
    svc.state = st

    from .ui.overlay import Overlay
    overlay = Overlay(cfg)              # creates the Qt application; must come first
    svc.overlay = overlay

    from . import skills  # noqa: F401  (registers actions)
    from .assistant import Assistant
    from .audio import Listener
    from .brain import Brain
    from .calls import CallWatcher
    from .keys import TalkKey, register_hotkeys
    from .lights import KeyboardLights
    from .skills.apps import index
    from .skills.productivity import memory
    from .skills.timers import Scheduler
    from .sounds import Sounds
    from .stt import Transcriber
    from .tts import Voice
    from .ui.tray import Tray

    svc.sounds = Sounds(cfg.setdefault("sounds", {"cues": True}), st)
    from .ducking import Ducker
    svc.ducker = Ducker(cfg["voice"])
    def duck_on_state(s, ch):
        for key in ("speaking", "thinking"):
            if key in ch:
                svc.ducker.duck(key) if ch[key] else svc.ducker.unduck(key, delay=0.3)
    st.subscribe(duck_on_state)
    svc.voice = Voice(st, cfg["voice"],
                      on_caption=lambda text, secs, card=None: overlay.caption(gem=text, seconds=secs, card=card))
    svc.lights = KeyboardLights(enabled=cfg["lights"].get("enabled", True), animate=cfg["lights"].get("animate", True))
    svc.brain = Brain(cfg["ai"], st, cfg.get("user_name"), memory)
    svc.stt = Transcriber(cfg["stt"])
    svc.assistant = Assistant(on_quit=_quit)
    svc.listener = Listener(st, svc.assistant.submit, cfg["listening"].get("input_device", ""),
                            cfg["listening"].get("vad_aggressiveness", 2))
    svc.scheduler = Scheduler(cfg)
    svc.tray = Tray()

    index.refresh_async()
    from .skills.clipboard import start_watcher
    from .skills.insights import start_tracker
    start_watcher()
    start_tracker()
    threading.Thread(target=_ensure_shortcut, name="shortcut", daemon=True).start()
    svc.assistant.start()
    svc.listener.start()
    svc.scheduler.start()
    CallWatcher(cfg["calls"]).start()
    svc.tray.start()

    keys = cfg["keys"]
    svc.keys = TalkKey(_on_press, _on_release, _on_tap, _on_triple_tap,
                       hold_ms=keys.get("hold_ms", 250), triple_tap_ms=keys.get("triple_tap_ms", 900))
    svc.keys.start()
    register_hotkeys(keys.get("command_bar"), overlay.open_command_bar,
                     keys.get("panic"), lambda: threading.Thread(target=svc.assistant.panic, daemon=True).start())

    if not svc.brain.available():
        log.warning("GROQ_API_KEY not set: AI answers and Whisper are off")
    hint = "Hold Caps Lock to talk." if st.mode == PUSH_TO_TALK else "I'm listening. Hold Caps Lock to mute me."
    threading.Timer(2.8, lambda: caption("Gem is ready. " + hint, seconds=4)).start()
    log.info("Ready: %s", st.describe())

    try:
        overlay.run()
    finally:
        if svc.lights:
            svc.lights.close()
    time.sleep(0.2)
    os._exit(0)
