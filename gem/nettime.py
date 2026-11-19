"""The real time, for a PC whose clock drifts (a BIOS that loses or shifts the time).

How far off the PC is comes from a web server's Date header every half hour. Plain http on purpose: when the PC's
date is far off, https refuses the server's certificate. If the PC's clock is changed in between (Windows syncing
it, or you fixing it), the change is spotted at once and taken off, so the real time doesn't jump.
"""
import datetime
import email.utils
import logging
import threading
import time

import requests

log = logging.getLogger("gem.nettime")

SERVERS = ("http://www.google.com", "http://www.msftconnecttest.com/connecttest.txt", "http://www.cloudflare.com")
REFRESH = 1800          # seconds between checks once it worked; a minute after one that didn't

_state = {"offset": None}       # seconds to add to the PC's clock for the real time; None until checked


def measure():
    """Seconds the PC's clock is behind the real time (negative: ahead), or None when no server answered."""
    for url in SERVERS:
        try:
            sent = time.time()
            r = requests.head(url, timeout=4, allow_redirects=False)
            got = time.time()
            date = r.headers.get("Date")
            if date:
                server = email.utils.parsedate_to_datetime(date).timestamp() + 0.5    # Date drops the fraction
                return server - (sent + got) / 2
        except Exception as e:
            log.debug("Time from %s failed: %s", url, e)
    return None


def offset():
    return _state["offset"]


def time_now():
    """The real time.time(): what timers, alarms, reminders and classes are set and checked by."""
    return time.time() + (_state["offset"] or 0.0)


def now():
    """The real local time (the PC's own until the first check worked)."""
    return datetime.datetime.fromtimestamp(time_now())


def status():
    """One line on how the PC's clock compares, for the clock window."""
    off = _state["offset"]
    if off is None:
        return "Checking the real time online…"
    if abs(off) < 2:
        return "In sync · your PC's clock is right"
    gap = abs(off)
    if gap >= 2 * 86400:
        words = "%d days" % (gap // 86400)
    else:
        from .parse import duration_phrase
        words = duration_phrase(gap if gap >= 60 else round(gap))
    return "In sync · your PC is %s %s" % (words, "behind" if off > 0 else "ahead")


def _tick(wall, mono):
    """Take a change of the PC's clock since (wall, mono) off the offset. Returns the new (wall, mono)."""
    jump = (time.time() - wall) - (time.monotonic() - mono)
    if abs(jump) > 1 and _state["offset"] is not None:
        _state["offset"] -= jump            # the PC's clock moved; the real time didn't
    return time.time(), time.monotonic()


def _loop():
    wall, mono, due = time.time(), time.monotonic(), 0.0
    while True:
        wall, mono = _tick(wall, mono)
        if mono >= due:
            off = measure()
            if off is not None:
                if _state["offset"] is None or abs(off - _state["offset"]) > 2:
                    log.info("Real time: the PC's clock is %+.0f s off", -off)
                _state["offset"] = off
            due = time.monotonic() + (REFRESH if off is not None else 60)
            wall, mono = time.time(), time.monotonic()
        time.sleep(5)


def start():
    threading.Thread(target=_loop, name="nettime", daemon=True).start()
