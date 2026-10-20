"""Video controls for whatever you're watching in front: skip or rewind by seconds, fullscreen, captions.

Uses each player's own keyboard shortcuts, only when a video player or a streaming site is in front.
"""
import logging
import re
import time

from ..actions import ActionError, action
from ..winapi import foreground_window, press, release_modifiers, window_process_name, window_title

log = logging.getLogger("gem.video")

BROWSERS = {"brave.exe", "chrome.exe", "msedge.exe", "firefox.exe", "opera.exe"}
# (title pattern, seconds per Right-arrow press, keys for forward, keys for back)
SITES = [
    (r"youtube", 5, ("right",), ("left",)),
    (r"netflix", 10, ("right",), ("left",)),
    (r"prime video|primevideo", 10, ("right",), ("left",)),
    (r"disney|hotstar|jiocinema", 10, ("right",), ("left",)),
    (r"twitch", 10, ("right",), ("left",)),
]
PLAYERS = {
    "vlc.exe": (10, ("alt", "right"), ("alt", "left")),
    "mpc-hc64.exe": (5, ("right",), ("left",)),
    "mpc-hc.exe": (5, ("right",), ("left",)),
    "potplayermini64.exe": (5, ("right",), ("left",)),
    "wmplayer.exe": (10, ("ctrl", "shift", "f"), ("ctrl", "shift", "b")),
    "video.ui.exe": (10, ("right",), ("left",)),
    "applicationframehost.exe": (10, ("right",), ("left",)),
}


def _player():
    """(kind, step seconds, forward keys, back keys) for the window in front, or None."""
    hwnd = foreground_window()
    proc = window_process_name(hwnd)
    if proc in PLAYERS:
        step, fwd, back = PLAYERS[proc]
        return proc, step, fwd, back
    if proc in BROWSERS:
        title = window_title(hwnd).lower()
        for pattern, step, fwd, back in SITES:
            if re.search(pattern, title):
                return pattern.split("|")[0], step, fwd, back
        return "browser", 5, ("right",), ("left",)          # most web players: arrows jump 5 seconds
    return None


@action("video_seek", "Skip forward (positive seconds) or back (negative) in the video in front.", "seconds: number")
def video_seek(seconds=10):
    p = _player()
    if not p:
        raise ActionError("I don't see a video in front.")
    kind, step, fwd, back = p
    secs = float(seconds or 10)
    presses = max(1, min(40, int(round(abs(secs) / step))))
    keys = fwd if secs > 0 else back
    release_modifiers()
    for _ in range(presses):
        press(*keys)
        time.sleep(0.04)
    log.info("Video seek %+.0fs in %s (%d x %s)", secs, kind, presses, "+".join(keys))
    return None


@action("video_key", "Fullscreen or captions in the video in front.", "what: fullscreen|captions")
def video_key(what="fullscreen"):
    p = _player()
    if not p:
        raise ActionError("I don't see a video in front.")
    kind = p[0]
    release_modifiers()
    if what == "captions":
        press("c" if kind in ("youtube", "browser") else "v")          # VLC and most players: V for subtitles
    elif kind in ("mpc-hc64.exe", "mpc-hc.exe"):
        press("alt", "enter")
    else:
        press("f")
    return None
