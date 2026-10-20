"""Shared services. app.py fills these in at startup; skills import them."""
import logging

log = logging.getLogger("gem.runtime")


class Services:
    config = None
    state = None
    voice = None
    lights = None
    ducker = None
    sounds = None
    brain = None
    stt = None
    listener = None
    assistant = None
    scheduler = None
    overlay = None
    tray = None
    keys = None


svc = Services()


def say(text, caption_only=False, card=None):
    if text and svc.voice:
        svc.voice.say(text, caption_only=caption_only, card=card)


def caption(text, you=None, seconds=None, card=None):
    if svc.overlay:
        svc.overlay.caption(gem=text, you=you, seconds=seconds, card=card)


def chime(kind="soft"):
    """Alert sounds. Never played during calls, quiet time or gaming."""
    if svc.sounds:
        svc.sounds.play({"soft": "alert", "alarm": "alarm", "ack": "ack"}.get(kind, kind))


def notify(title, message, speak=True, sound=None, flash=True, icon="bell"):
    """Alert the user in the least intrusive way the current state allows."""
    log.info("Notify: %s — %s", title, message)
    try:
        from . import headsup
        headsup.note_missed(title, message)          # kept for "while you were away" if you're not at the PC
    except Exception:
        pass
    if svc.tray:
        svc.tray.notify(title, message)
    if flash and svc.lights and svc.config["lights"].get("flash_on_alerts", True):
        svc.lights.flash("alert")
    if sound:
        chime(sound)
    card = {"kind": "alert", "title": title, "message": message, "icon": icon}
    if speak:
        say(message, card=card)
    else:
        caption(message, card=card)
