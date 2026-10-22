"""Power when done: "turn off the PC when the movie ends", "sleep when my download finishes", "shut down in 2 hours".

A watcher waits for the moment, then gives a 60-second warning you can cancel by voice.
"""
import logging
import os
import threading
import time

from ..actions import ActionError, action
from ..cards import card
from ..runtime import say

log = logging.getLogger("gem.power_auto")

WORDS = {"shutdown": "shut down", "sleep": "go to sleep", "hibernate": "hibernate", "restart": "restart"}
PARTIAL = (".crdownload", ".part", ".partial", ".download", ".opdownload", ".!ut", ".aria2")
QUIET_FOR_S = 180               # this long with no sound means the movie is over
WARNING_S = 60

job = {"id": 0, "action": None, "trigger": None, "since": 0.0, "cancelled": True}


def _active_media():
    """True if any app other than Gem is playing sound right now."""
    from pycaw.pycaw import AudioUtilities
    me = os.getpid()
    return any(s.Process and s.Process.pid != me and s.State == 1 for s in AudioUtilities.GetAllSessions())


def _downloads_busy():
    from ..winapi import known_folder
    try:
        return any(f.lower().endswith(PARTIAL) for f in os.listdir(known_folder("downloads")))
    except OSError:
        return False


def _still(my_id):
    return job["id"] == my_id and not job["cancelled"]


def _watch(my_id, power, trigger, minutes):
    try:
        import pythoncom
        pythoncom.CoInitialize()
    except Exception:
        pass
    started = time.time()
    if trigger == "time":
        while _still(my_id) and time.time() < started + minutes * 60:
            time.sleep(2)
    elif trigger == "media_end":
        heard, quiet_since = False, None
        while _still(my_id) and time.time() - started < 6 * 3600:
            playing = _active_media()
            heard = heard or playing
            if playing:
                quiet_since = None
            elif heard:
                quiet_since = quiet_since or time.time()
                if time.time() - quiet_since >= QUIET_FOR_S:
                    break
            time.sleep(5)
    elif trigger == "download_done":
        idle_since = None
        while _still(my_id) and time.time() - started < 12 * 3600:
            if _downloads_busy():
                idle_since = None
            else:
                idle_since = idle_since or time.time()
                if time.time() - idle_since >= 45:
                    break
            time.sleep(5)
    if not _still(my_id):
        return
    job["warning_until"] = time.time() + WARNING_S + 5
    say("Heads up: I'll %s in a minute. Say cancel to stop me." % WORDS[power],
        card={"kind": "alert", "title": "%s in 60 seconds" % WORDS[power].capitalize(),
              "message": "Say cancel to stop."})
    end = time.time() + WARNING_S
    while time.time() < end:
        if not _still(my_id):
            return
        time.sleep(1)
    if not _still(my_id):
        return
    job["cancelled"] = True
    log.info("Power when done: %s", power)
    from .system import _do_power
    _do_power(power if power != "shutdown" else "shutdown")


@action("power_when", "Shut down, sleep, hibernate or restart the PC later: when the movie/video ends (media_end), when "
        "downloads finish (download_done), or after some minutes (time). Warns a minute before, and can be cancelled.",
        "power: shutdown|sleep|hibernate|restart, trigger: media_end|download_done|time, minutes?: number")
def power_when(power="shutdown", trigger="media_end", minutes=None):
    from .. import safety
    power = power if power in WORDS else "shutdown"
    if trigger == "time":
        if not minutes:
            raise ActionError("In how long?")
        minutes = float(minutes)
    elif trigger == "download_done" and not _downloads_busy():
        raise ActionError("I don't see a download in progress right now.")
    if safety.unattended():
        return safety.skip("%s later" % WORDS[power].capitalize())
    return safety.ask("%s %s" % (WORDS[power].capitalize(), _when(trigger, minutes)),
                      lambda: _plan(power, trigger, minutes), phrase="confirm")


def _when(trigger, minutes):
    return {"media_end": "when what you're watching ends", "download_done": "when your downloads finish",
            "time": "in %s" % _mins(minutes or 0)}[trigger]


def _plan(power, trigger, minutes):
    job.update(id=job["id"] + 1, action=power, trigger=trigger, since=time.time(), cancelled=False)
    threading.Thread(target=_watch, args=(job["id"], power, trigger, minutes), name="power-when", daemon=True).start()
    text = "Okay, I'll %s %s. I'll warn you a minute before." % (WORDS[power], _when(trigger, minutes))
    if trigger == "time":
        return card("alarm", text, title="Then %s" % WORDS[power], at=time.time() + minutes * 60,
                    subtitle="In " + _mins(minutes))
    return text


def _mins(m):
    m = int(round(m))
    return "%d minute%s" % (m, "" if m == 1 else "s") if m < 90 else "%.1f hours" % (m / 60.0)


def pending():
    return not job["cancelled"] and job["action"] is not None


def warning():
    """The one-minute warning is up: "cancel" now means the shutdown."""
    return pending() and time.time() < job.get("warning_until", 0)


@action("power_when_cancel", "Cancel a pending 'shut down / sleep when done' plan.")
def power_when_cancel():
    if not pending():
        return "There's nothing planned."
    job["cancelled"] = True
    return "Cancelled. I won't %s." % WORDS[job["action"]]
