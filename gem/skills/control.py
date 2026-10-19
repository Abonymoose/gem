"""Controlling Gem herself: quiet time, modes, voice, gaming and help."""
import math
import time

from ..actions import action
from ..config import runtime
from ..runtime import caption, svc
from ..state import ALWAYS_LISTENING, MODE_NAMES, PUSH_TO_TALK


def _feedback(flash="ack"):
    """Lights, a soft tone and a glimpse of the crystal for silent state changes."""
    if svc.lights:
        svc.lights.flash(flash)
    if svc.overlay:
        svc.overlay.flash(2.6)


@action("snooze", "Go quiet for a while (default 10 min).", "minutes?: number")
def snooze(minutes=None):
    minutes = float(minutes or svc.config.get("snooze_minutes", 10))
    svc.voice.stop()
    svc.state.update(snoozed_until=time.time() + minutes * 60)
    _feedback()
    until = time.strftime("%I:%M %p", time.localtime(svc.state.snoozed_until)).lstrip("0")
    caption("Quiet until %s." % until, seconds=3)
    return None


def ruhig():
    svc.voice.stop()
    svc.state.update(snoozed_until=math.inf)
    _feedback()
    caption("Ruhig. Hold Caps Lock and say Weiter to bring me back.", seconds=4)


@action("resume", "End quiet time.")
def resume():
    was = svc.state.snoozed
    svc.state.update(snoozed_until=0.0)
    return "I'm back." if was else "I'm here."


@action("set_mode", "Listening mode.", "mode: push_to_talk|always_listening|toggle")
def set_mode(mode="toggle"):
    st = svc.state
    if mode == "toggle":
        mode = ALWAYS_LISTENING if st.mode == PUSH_TO_TALK else PUSH_TO_TALK
    if mode not in MODE_NAMES:
        return None
    st.update(mode=mode)
    with runtime as data:
        data["mode"] = mode
    _feedback(mode)
    if svc.sounds:
        svc.sounds.play("ack")
    return MODE_NAMES[mode] + "."


@action("voice_replies", "Spoken replies on/off (captions stay).", "on: bool")
def voice_replies(on=True):
    svc.state.update(voice_enabled=bool(on))
    with runtime as data:
        data["voice_enabled"] = bool(on)
    if on:
        return "Voice replies on."
    caption("Voice replies off. I'll show answers as text.")
    return None


@action("gaming_mode", "Gaming mode on/off (quiet, captions only).", "on: bool")
def gaming_mode(on=True):
    svc.state.update(gaming=bool(on))
    _feedback()
    if on:
        caption("Gaming mode on.", seconds=3)
        return None
    return "Gaming mode off."


@action("stop", "Stop talking or cancel what Gem is doing.", ai=False)
def stop():
    svc.voice.stop()
    return None


@action("repeat", "Repeat what Gem last said.", ai=False)
def repeat():
    return svc.voice.last_text or "I haven't said anything yet."


@action("what_did_you_hear", "Say what Gem last heard, to check recognition.", ai=False)
def what_did_you_hear():
    heard = svc.assistant.last_heard
    return "I heard: %s." % heard[-1] if heard else "I haven't heard anything yet."


@action("clear_conversation", "Forget the current conversation context.", ai=False)
def clear_conversation():
    svc.brain.clear_history()
    return "Conversation cleared."


@action("open_dashboard", "Open Gem's window.", "page?: home|reminders|classes|todo|notes|memory|history|settings")
def open_dashboard(page="home"):
    if svc.overlay:
        svc.overlay.open_dashboard(page or "home")
    return None


@action("open_gem_settings", "Open Gem's settings.", ai=False)
def open_gem_settings():
    return open_dashboard("settings")


@action("help", "Explain what Gem can do and how to talk to her.", ai=False)
def help_text():
    mode = svc.state.mode
    how = ("Hold Caps Lock while you talk to me." if mode == PUSH_TO_TALK else
           "I'm listening all the time. Hold Caps Lock to mute me for a moment.")
    return (how + " Triple tap Caps Lock to switch modes, and tap it to stop me talking. "
            "I can open and close apps and websites, control volume and music, set timers, alarms and reminders, "
            "keep your to-do list and notes, run focus sessions, tell you the weather and your schedule, "
            "summarize or rewrite selected text, take dictation and screenshots, and answer questions. "
            "Say shut up for a bit when you need quiet.")


@action("quit_gem", "Close Gem.")
def quit_gem():
    svc.assistant.quit()
    return None
