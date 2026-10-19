"""Gem's sound design: soft listening cues and bell-like alerts.

Sounds are synthesized once into small WAV files in the data folder and played
asynchronously, so they never block and never touch the voice output.
"""
import logging
import os
import wave

import numpy as np

from .config import DATA_DIR

log = logging.getLogger("gem.sounds")

SR = 44100
SOUND_DIR = os.path.join(DATA_DIR, "sounds")
_VERSION = 2


def _env(n, attack, release):
    env = np.ones(n)
    a, r = int(SR * attack), int(SR * release)
    if a:
        env[:a] = np.linspace(0, 1, a) ** 2
    if r:
        env[-r:] *= np.linspace(1, 0, r) ** 2
    return env


def _glide(f0, f1, dur, vol):
    n = int(SR * dur)
    freq = np.geomspace(f0, f1, n)
    phase = 2 * np.pi * np.cumsum(freq) / SR
    sig = np.sin(phase) + 0.18 * np.sin(2 * phase)
    return sig * _env(n, 0.012, dur * 0.6) * vol


def _bell(freq, dur, vol, decay=5.0, bright=0.35):
    n = int(SR * dur)
    t = np.arange(n) / SR
    partials = [(1.0, 1.0, decay), (2.0, bright, decay * 1.8), (3.01, bright * 0.45, decay * 2.6),
                (4.2, bright * 0.2, decay * 3.5)]
    sig = sum(a * np.sin(2 * np.pi * freq * k * t) * np.exp(-t * d) for k, a, d in partials)
    return sig * _env(n, 0.004, 0.05) * vol


def _place(total, parts):
    """Mix [(start_seconds, signal)] into one buffer `total` seconds long."""
    out = np.zeros(int(SR * total))
    for start, sig in parts:
        i = int(SR * start)
        j = min(len(out), i + len(sig))
        out[i:j] += sig[:j - i]
    return out


def _designs():
    c6, e6, g6, c7 = 1046.5, 1318.5, 1568.0, 2093.0
    return {
        # Short, so it's over before you start talking and never smears your first word.
        "listen_start": _glide(600, 980, 0.065, 0.16),
        "listen_end": _glide(880, 560, 0.08, 0.15),
        "ack": _bell(c6 * 0.75, 0.35, 0.18, decay=9),
        "alert": _place(1.1, [(0.0, _bell(e6 * 0.5, 0.9, 0.25)), (0.16, _bell(g6 * 0.5, 0.9, 0.22))]),
        "alarm": _place(3.4, [(0.55 * r + 0.13 * i, _bell(f * 0.5, 0.8, 0.24, decay=4.5))
                               for r in range(4) for i, f in enumerate((c6, e6, g6, c7))]),
    }


def _write(path, sig):
    peak = max(1e-6, float(np.max(np.abs(sig))))
    if peak > 0.95:
        sig = sig / peak * 0.95
    data = (sig * 32767).astype(np.int16)
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(data.tobytes())


class Sounds:
    def __init__(self, cfg, state):
        self.cfg = cfg
        self.state = state
        self.paths = {}
        try:
            os.makedirs(SOUND_DIR, exist_ok=True)
            for f in os.listdir(SOUND_DIR):               # sounds from older designs
                if not f.endswith("_v%d.wav" % _VERSION):
                    os.remove(os.path.join(SOUND_DIR, f))
            for name, sig in _designs().items():
                path = os.path.join(SOUND_DIR, "%s_v%d.wav" % (name, _VERSION))
                if not os.path.exists(path):
                    _write(path, sig)
                self.paths[name] = path
        except Exception as e:
            log.error("Could not prepare sounds: %s", e)

    def play(self, name, force=False):
        """Play a sound unless Gem should be silent right now."""
        if not force:
            if not self.cfg.get("cues", True) and name in ("listen_start", "listen_end", "ack"):
                return
            if self.state.quiet_alerts():
                return
        path = self.paths.get(name)
        if not path:
            return
        try:
            import winsound
            winsound.PlaySound(path, winsound.SND_FILENAME | winsound.SND_ASYNC | winsound.SND_NODEFAULT)
        except Exception as e:
            log.debug("Sound %s failed: %s", name, e)
