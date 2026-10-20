"""Gaming helpers: clip the last 30 seconds, Discord mute/deafen, and an internet speed test."""
import logging
import os
import threading
import time
import winreg

import psutil
import requests

from ..actions import ActionError, action
from ..cards import card
from ..runtime import caption, chime, svc
from ..winapi import known_folder, press

log = logging.getLogger("gem.gaming")


# ── Clip that ────────────────────────────────────────────────────────────────

def _game_dvr():
    """(background recording on, buffer seconds)."""
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\GameDVR") as k:
            on = winreg.QueryValueEx(k, "HistoricalCaptureEnabled")[0]
            try:
                length = winreg.QueryValueEx(k, "HistoricalBufferLength")[0]
                unit = winreg.QueryValueEx(k, "HistoricalBufferLengthUnit")[0]      # 1 = seconds, 2 = minutes
            except OSError:
                length, unit = 30, 1
        return bool(on), int(length) * (60 if unit == 2 else 1)
    except OSError:
        return False, 30


def _watch_for_clip(folder, before, seconds):
    end = time.time() + 15
    while time.time() < end:
        time.sleep(0.5)
        try:
            new = [f for f in os.listdir(folder) if f.lower().endswith(".mp4") and f not in before]
        except OSError:
            new = []
        if new:
            log.info("Clip saved: %s", new[0])
            caption("Clipped the last %d seconds" % seconds, seconds=3)        # a small toast, not a card
            return
    log.info("No clip appeared in %s", folder)
    caption("No clip saved. Game Bar only records apps", seconds=4)


@action("clip_that", "Save the last 30 seconds of gameplay as a clip (Xbox Game Bar).")
def clip_that():
    on, seconds = _game_dvr()
    if not on:
        raise ActionError("Background recording is off. Turn on Record what happened in Settings, Gaming, "
                          "Captures, and then I can clip.")
    folder = os.path.join(known_folder("videos"), "Captures")
    try:
        before = set(os.listdir(folder))
    except OSError:
        before = set()
    press("win", "alt", "g")
    chime("ack")
    if svc.lights:
        svc.lights.flash("ack")
    threading.Thread(target=_watch_for_clip, args=(folder, before, seconds), daemon=True).start()
    return None


# ── Discord ──────────────────────────────────────────────────────────────────

def _discord_running():
    for p in psutil.process_iter(["name"]):
        if (p.info["name"] or "").lower() in ("discord.exe", "discordptb.exe", "discordcanary.exe"):
            return True
    return False


@action("discord_toggle", "Toggle mute or deafen for the user in Discord.", "what: mute|deafen")
def discord_toggle(what="mute"):
    what = "deafen" if str(what).lower().startswith(("deaf", "undeaf")) else "mute"
    if not _discord_running():
        raise ActionError("Discord isn't open.")
    keys = (svc.config.get("discord") or {}).get(what + "_keys") or ("ctrl+shift+d" if what == "deafen" else "ctrl+shift+m")
    press(*[k.strip() for k in keys.lower().split("+") if k.strip()])
    chime("ack")
    # Silent toast on purpose: you're probably in a call.
    caption("Discord %s toggled" % what, seconds=2)
    return None


# ── Speed test ───────────────────────────────────────────────────────────────

SPEED = "https://speed.cloudflare.com"


def _ping(s):
    times = []
    for _ in range(6):
        t = time.perf_counter()
        s.get(SPEED + "/__down?bytes=0", timeout=5)
        times.append((time.perf_counter() - t) * 1000)
    times = sorted(times[1:])                     # the first one pays for the connection
    return times[len(times) // 2]


def _measure(worker, streams, seconds, warmup=1.0):
    """Run `streams` workers for `seconds`; megabits per second after the warm-up."""
    count, lock, stop = [0], threading.Lock(), threading.Event()

    def add(n):
        with lock:
            count[0] += n

    threads = [threading.Thread(target=worker, args=(add, stop), daemon=True) for _ in range(streams)]
    for t in threads:
        t.start()
    time.sleep(warmup)
    b1, t1 = count[0], time.perf_counter()
    time.sleep(seconds - warmup)
    b2, t2 = count[0], time.perf_counter()
    stop.set()
    for t in threads:
        t.join(3)
    return (b2 - b1) * 8 / max(0.001, t2 - t1) / 1e6


def _download_worker(add, stop):
    while not stop.is_set():
        try:
            with requests.get(SPEED + "/__down?bytes=50000000", stream=True, timeout=10) as r:
                for chunk in r.iter_content(65536):
                    add(len(chunk))
                    if stop.is_set():
                        return
        except requests.RequestException:
            time.sleep(0.2)


_BLOB = os.urandom(1_000_000)


def _upload_worker(add, stop):
    s = requests.Session()
    while not stop.is_set():
        try:
            s.post(SPEED + "/__up", data=_BLOB, timeout=10)
            add(len(_BLOB))
        except requests.RequestException:
            time.sleep(0.2)


def _fmt(mbps):
    return "%.0f" % mbps if mbps >= 10 else "%.1f" % mbps


@action("speed_test", "Test the internet speed: download, upload and ping.")
def speed_test():
    svc.state.update(thinking=True)
    try:
        ping = _ping(requests.Session())
    except requests.RequestException:
        raise ActionError("I can't reach the internet right now.")
    down = _measure(_download_worker, 4, 7)
    up = _measure(_upload_worker, 3, 6)
    log.info("Speed test: %.1f down, %.1f up, %.0f ms", down, up, ping)
    if down >= 25 and ping <= 50:
        verdict = "Good for gaming and streaming."
    elif down >= 10:
        verdict = "Fine for streaming, but games may lag." if ping > 80 else "Fine for most things."
    else:
        verdict = "That's slow. Video and games will struggle."
    return card("speed", "%s megabits down, %s up, and %d milliseconds ping. %s" % (_fmt(down), _fmt(up), ping, verdict),
                down=round(down, 1), up=round(up, 1), ping=round(ping), verdict=verdict)
