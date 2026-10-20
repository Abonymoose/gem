"""Auto-clip hype moments: in a game, shout "let's go" (or say "clip that") and Gem saves the last 30 seconds.

Runs only while a game is in front. Short bursts of speech are checked locally with offline keyword
spotting (nothing is sent anywhere), must be louder than how you normally talk in games (except for an
explicit "clip that"), and must be your voice if Gem knows it.
"""
import logging
import queue
import threading
import time

import numpy as np

from .runtime import caption, svc

log = logging.getLogger("gem.hype")

GAMES = {
    "fortniteclient-win64-shipping.exe", "valorant-win64-shipping.exe", "robloxplayerbeta.exe", "javaw.exe",
    "minecraft.windows.exe", "rocketleague.exe", "aoe2de_s.exe", "geometrydash.exe", "brawlhalla.exe",
    "stardew valley.exe", "cs2.exe", "r5apex.exe", "overwatch.exe", "gta5.exe", "gta5_enhanced.exe",
    "rainbowsix.exe", "eldenring.exe", "terraria.exe", "among us.exe", "fallguys_client.exe",
    "fallguys_client_game.exe", "destiny2.exe", "leagueoflegends.exe", "league of legends.exe", "dota2.exe",
    "cod.exe", "modernwarfare.exe", "bf2042.exe", "pubg.exe", "tslgame.exe", "hollow_knight.exe", "celeste.exe",
    "worldbox.exe", "backrooms escape together.exe", "lethal company.exe", "phasmophobia.exe", "repo.exe",
}
# Fullscreen apps that aren't games.
NOT_GAMES = {"brave.exe", "chrome.exe", "msedge.exe", "firefox.exe", "opera.exe", "vlc.exe", "explorer.exe",
             "code.exe", "powerpnt.exe", "winword.exe", "excel.exe", "spotify.exe", "discord.exe", "obs64.exe",
             "applicationframehost.exe", "mpc-hc64.exe", "wmplayer.exe", "photos.exe", "gem.exe", "python.exe",
             "pythonw.exe", "claude.exe", "zoom.exe", "ms-teams.exe", "notion.exe", "steamwebhelper.exe"}
DEFAULT_PHRASES = ["let's go", "lets go", "no way", "oh my god", "clip that", "clip it", "what a shot", "insane",
                   "get in", "yes yes yes", "that was crazy", "no shot", "what was that"]
EXPLICIT = {"clip that", "clip it"}

state = {"in_game": False, "game": "", "last_clip": 0.0}
_levels = []                    # loudness of recent in-game speech, to know what "excited" means for you
_queue = queue.Queue(maxsize=4)


def cfg():
    return svc.config.get("auto_clip") or {}


def active():
    return bool(cfg().get("enabled", True)) and state["in_game"]


def _watch_games():
    from .winapi import foreground_is_fullscreen, foreground_window, window_process_name
    while True:
        time.sleep(3)
        try:
            proc = (window_process_name(foreground_window()) or "").lower()
            in_game = proc in GAMES or (proc not in NOT_GAMES and bool(proc) and foreground_is_fullscreen())
            if in_game != state["in_game"]:
                log.info("Game %s: %s", "started" if in_game else "left", proc or "?")
            state.update(in_game=in_game, game=proc if in_game else "")
        except Exception:
            log.debug("Game check failed", exc_info=True)


def start():
    threading.Thread(target=_watch_games, name="game-watch", daemon=True).start()
    threading.Thread(target=_worker, name="hype", daemon=True).start()


def on_segment(pcm, loudness):
    """Called from the mic thread with a short burst of speech heard during a game."""
    try:
        _queue.put_nowait((pcm, loudness))
    except queue.Full:
        pass


def _excited(loudness):
    typical = float(np.median(_levels)) if len(_levels) >= 6 else None
    _levels.append(loudness)
    del _levels[:-40]
    return typical is None or loudness >= typical * float(cfg().get("loudness_ratio", 1.35))


def _worker():
    from . import offline, voiceprint
    from .skills import gaming, voice_id
    while True:
        pcm, loudness = _queue.get()
        try:
            excited = _excited(loudness)
            if time.time() - state["last_clip"] < float(cfg().get("cooldown_seconds", 25)):
                continue
            phrases = cfg().get("phrases") or DEFAULT_PHRASES
            said = offline.spot(pcm, phrases)
            if not said or (said not in EXPLICIT and not excited):
                continue
            if cfg().get("only_my_voice", True) and voiceprint.ready():
                who, sc = voiceprint.hear(pcm, voice_id.base_threshold())
                if who != "me":
                    log.info("Heard %r in game, but not your voice (%s)", said, who)
                    continue
            log.info("Auto-clip: %r in %s", said, state["game"])
            state["last_clip"] = time.time()
            try:
                gaming.clip_that()
            except Exception as e:
                caption(str(e), seconds=4)
        except Exception:
            log.exception("Auto-clip failed")
