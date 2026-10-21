"""Undo for the quick changes Gem makes: "undo that", "put it back".

Volume, brightness, dark mode and cancelling a timer or reminder each leave a note here saying how to put things
back. Notes go stale after ten minutes, so "undo" never reaches for something you've forgotten about.
"""
import logging
import threading
import time

from ..actions import ActionError, action

log = logging.getLogger("gem.undo")

KEEP_SECONDS = 600
_notes = []                 # [(when, what, restore)], newest last
_lock = threading.Lock()
_restoring = threading.local()


def remember(what, restore):
    """what: 'the volume'. restore: a function that puts it back and returns what to say (or None)."""
    if getattr(_restoring, "on", False):
        return                              # the undo itself changing the volume isn't a new change
    with _lock:
        _notes.append((time.time(), what, restore))
        del _notes[:-8]


def clear():
    with _lock:
        _notes.clear()


def latest():
    """What 'undo' would put back, or None."""
    with _lock:
        fresh = [n for n in _notes if time.time() - n[0] < KEEP_SECONDS]
    return fresh[-1][1] if fresh else None


@action("undo", "Undo Gem's last change to the volume, brightness or dark mode, or bring back a timer or reminder "
        "that was just cancelled.")
def undo():
    with _lock:
        while _notes and time.time() - _notes[-1][0] >= KEEP_SECONDS:
            _notes.pop()
        if not _notes:
            raise ActionError("There's nothing to undo.")
        _, what, restore = _notes.pop()
    _restoring.on = True
    try:
        said = restore()
    except Exception:
        log.exception("Undo of %s failed", what)
        raise ActionError("I couldn't put %s back." % what)
    finally:
        _restoring.on = False
    return "Put %s back. %s" % (what, said) if said else "Put %s back." % what
