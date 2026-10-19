"""Shared services. app.py fills these in at startup; skills import them."""
import logging
import time
import winsound

log = logging.getLogger("gem.runtime")


class Services:
    config = None
    state = None
    voice = None
    lights = None
    brain = None
    stt = None
    listener = None
    assistant = None
    scheduler = None
    overlay = None
    tray = None
    keys = None


svc = Services()


def say(text, caption_only=False):
    if text and svc.voice:
        svc.voice.say(text, caption_only=caption_only)


def caption(text, you=None, seconds=None):
    if svc.overlay:
        svc.overlay.caption(gem=text, you=you, seconds=seconds)


def chime(kind="soft"):
    """Short sounds. Never played during calls, snooze or gaming."""
    if svc.state and svc.state.quiet_alerts():
        return
    try:
        if kind == "alarm":
            for _ in range(3):
                winsound.Beep(988, 180)
                winsound.Beep(1319, 220)
                time.sleep(0.15)
        elif kind == "soft":
            winsound.Beep(880, 90)
        elif kind == "up":
            winsound.Beep(660, 70)
            winsound.Beep(990, 90)
        elif kind == "down":
            winsound.Beep(990, 70)
            winsound.Beep(660, 90)
    except Exception:
        pass


def notify(title, message, speak=True, sound=None, flash=True):
    """Alert the user in the least intrusive way the current state allows."""
    log.info("Notify: %s — %s", title, message)
    if svc.tray:
        svc.tray.notify(title, message)
    if flash and svc.lights and svc.config["lights"].get("flash_on_alerts", True):
        svc.lights.flash("alert")
    if sound:
        chime(sound)
    if speak:
        say(message)
    else:
        caption(message)
