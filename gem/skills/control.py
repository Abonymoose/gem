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


@action("quiet_until_resumed", "Stay quiet until the user says \"I'm back\".")
def quiet_until_resumed():
    svc.voice.stop()
    svc.state.update(snoozed_until=math.inf)
    _feedback()
    caption("Quiet until you say I'm back.", seconds=4)
    return None


@action("resume", "End quiet time.")
def resume():
    was_quiet, was_away = svc.state.snoozed, bool(svc.state.away_until)
    svc.state.update(snoozed_until=0.0, hidden=False, away_until=0.0)
    if was_away:
        return "Welcome back."
    return "I'm back." if was_quiet else "I'm here."


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
            "summarize, rewrite or read out selected text, take dictation and screenshots, do quick maths and "
            "conversions, tell the time anywhere in the world, count down to dates, run commands later, track your "
            "screen time and habits, run a stopwatch, paste things you copied earlier, draft replies, make "
            "passwords, recap your day, explain what's on your screen, tidy your downloads, clip your games, "
            "mute you on Discord, test your internet speed, suggest something to watch or play, learn your voice "
            "so I only respond to you, recognise or ignore family members, remember screens you save, clip your "
            "best game moments, give you heads-ups, work offline for the basics, find your files, turn off the PC "
            "when your movie ends, skip around in videos, play trivia, play rain or ocean sounds, record voice notes, "
            "make images and wallpapers, switch your speakers, record your screen, check the air quality, point things "
            "out on your screen, spotlight the window you're in, suggest formulas and answers right next to what "
            "needs filling, and answer questions. "
            "Say shut up for a bit when you need quiet.")


@action("voice_volume", "Gem's own speaking volume (not the PC's): set 0-100, or change it (e.g. -15 quieter).",
        "level?: number, change?: number")
def voice_volume(level=None, change=None):
    from ..cards import card
    from ..config import SETTINGS_FILE, _read_json, _write_json
    cur = float(svc.config["voice"].get("volume", 0.9)) * 100
    new = float(level) if level is not None else cur + float(change or 0)
    new = max(10, min(100, int(round(new))))
    svc.config["voice"]["volume"] = round(new / 100.0, 2)       # the voice reads this every time it speaks
    data = _read_json(SETTINGS_FILE, {})
    data.setdefault("voice", {})["volume"] = svc.config["voice"]["volume"]
    _write_json(SETTINGS_FILE, data)
    return card("volume", "My voice is at %d now." % new, level=new, header="Gem's voice")


@action("quit_gem", "Close Gem.")
def quit_gem():
    svc.assistant.quit()
    return None
