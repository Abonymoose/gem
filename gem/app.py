"""Startup: build every service, wire them together, run the overlay."""
import ctypes
import logging
import logging.handlers
import os
import sys
import threading
import time

from . import __version__
from .config import DATA_DIR, LOG_FILE, load_settings, runtime
from .runtime import caption, svc
from .state import ALWAYS_LISTENING, MODE_NAMES, PUSH_TO_TALK, State

log = logging.getLogger("gem")


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
    kernel32 = ctypes.windll.kernel32
    handle = kernel32.CreateMutexW(None, False, "Local\\GemVoiceAssistant")
    if kernel32.GetLastError() == 183:      # ERROR_ALREADY_EXISTS
        return None
    return handle


def _quit():
    log.info("Shutting down")
    try:
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
    svc.listener.begin_hold(talk=talk)
    svc.lights.show("talk" if talk else "mute")


def _on_release(was_tap):
    svc.state.update(key_held=False)
    svc.listener.end_hold(discard=was_tap)
    svc.lights.show("normal")


def _on_tap():
    pass        # pressing already stopped any speech


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
    from .stt import Transcriber
    from .tts import Voice
    from .ui.overlay import GemOverlay
    from .ui.tray import Tray

    overlay = GemOverlay(show_crystal=cfg["overlay"].get("enabled", True))
    svc.overlay = overlay
    svc.voice = Voice(st, cfg["voice"], on_caption=lambda text, secs: overlay.caption(gem=text, seconds=secs))
    svc.lights = KeyboardLights(enabled=cfg["lights"].get("enabled", True), animate=cfg["lights"].get("animate", True))
    svc.brain = Brain(cfg["ai"], st, cfg.get("user_name"), memory)
    svc.stt = Transcriber(cfg["stt"])
    svc.assistant = Assistant(on_quit=_quit)
    svc.listener = Listener(st, svc.assistant.submit, cfg["listening"].get("input_device", ""),
                            cfg["listening"].get("vad_aggressiveness", 2))
    svc.scheduler = Scheduler(cfg)
    svc.tray = Tray()

    index.refresh_async()
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
    overlay.root.after(3200, lambda: overlay.caption(gem="Gem is ready. " + hint, seconds=4))
    log.info("Ready: %s", st.describe())

    try:
        overlay.run()
    finally:
        if svc.lights:
            svc.lights.close()
    time.sleep(0.2)
    os._exit(0)
