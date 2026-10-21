"""Ambient sounds made on the spot (no YouTube, no ads): rain, ocean, fan, brown, pink and white noise.

A 24-second stereo loop is shaped in the frequency domain once, then played seamlessly with fades. It dips
while Gem talks and can stop on a timer.
"""
import logging
import threading
import time

import numpy as np

from ..actions import ActionError, action
from ..parse import parse_duration
from ..runtime import svc

log = logging.getLogger("gem.ambient")

RATE = 44100
LOOP_S = 24
SOUNDS = {"rain": "rain", "rainfall": "rain", "storm": "rain", "thunderstorm": "rain", "ocean": "ocean",
          "ocean waves": "ocean", "sea waves": "ocean", "waves": "ocean", "sea": "ocean", "beach": "ocean", "fan": "fan", "air conditioner": "fan", "ac": "fan",
          "brown noise": "brown", "brown": "brown", "pink noise": "pink", "pink": "pink", "white noise": "white",
          "white": "white", "noise": "brown", "static": "white"}

player = {"device": None, "sound": None, "until": None, "stop": None, "volume": 0.35}


def _shaped(n, shape, rng):
    """Noise with a given spectral slope, as one long FFT so it loops cleanly."""
    spec = np.fft.rfft(rng.standard_normal(n))
    f = np.fft.rfftfreq(n, 1.0 / RATE)
    f[0] = f[1]
    spec *= shape(f)
    x = np.fft.irfft(spec, n)
    return x / (np.abs(x).max() + 1e-9)


def _make(sound):
    rng = np.random.default_rng(int(time.time()))
    n = RATE * LOOP_S
    t = np.arange(n) / RATE
    chans = []
    for _ in range(2):                                          # independent channels sound wide and natural
        if sound == "white":
            x = _shaped(n, lambda f: np.ones_like(f), rng) * 0.5
        elif sound == "pink":
            x = _shaped(n, lambda f: 1 / np.sqrt(f), rng) * 0.8
        elif sound == "brown":
            x = _shaped(n, lambda f: 1 / f, rng)
        elif sound == "fan":
            x = _shaped(n, lambda f: 1 / np.sqrt(f) / (1 + (f / 700.0) ** 2), rng)
            x = 0.9 * x + 0.04 * np.sin(2 * np.pi * 50 * t)        # a faint motor hum
        elif sound == "ocean":
            x = _shaped(n, lambda f: 1 / np.sqrt(f) / (1 + (f / 1200.0) ** 2), rng)
            swell = 0.25 + 0.75 * (0.5 - 0.5 * np.cos(2 * np.pi * t / (LOOP_S / 3))) ** 2   # three waves a loop
            x *= swell
        else:                                                   # rain: soft hiss plus random drops
            x = _shaped(n, lambda f: (f / 4000.0) ** 0.3 / (1 + (f / 9000.0) ** 2), rng) * 0.5
            drops = np.zeros(n)
            idx = rng.integers(0, n - 400, size=LOOP_S * 90)
            for i in idx:
                drops[i:i + 300] += rng.uniform(0.05, 0.3) * np.exp(-np.arange(300) / 40.0) * rng.choice([-1, 1])
            x = x + drops * 0.6
        chans.append(x / (np.abs(x).max() + 1e-9))
    data = np.stack(chans, axis=1)
    # Crossfade the end into the start so the loop has no seam.
    k = RATE // 2
    fade = np.linspace(0, 1, k)[:, None]
    data[:k] = data[:k] * fade + data[-k:] * (1 - fade)
    data = data[:-k]
    data *= 0.18 / (np.sqrt((data ** 2).mean()) + 1e-9)            # every sound at the same loudness
    return np.clip(data, -0.95, 0.95).astype(np.float32)


def _gen(loop, stop):
    pos, gain = 0, 0.0
    required = yield b""
    while True:
        frames = required
        idx = (np.arange(frames) + pos) % len(loop)
        pos = (pos + frames) % len(loop)
        target = 0.0 if stop.is_set() else player["volume"] * (0.35 if svc.state and svc.state.speaking else 1.0)
        ramp = np.linspace(gain, gain + (target - gain) * min(1.0, frames / (RATE * 2.5)), frames)[:, None]
        gain = float(ramp[-1, 0])
        chunk = (loop[idx] * ramp * 32767).astype(np.int16)
        required = yield chunk.tobytes()


def _run(sound, stop):
    import miniaudio
    loop = _make(sound)
    dev = miniaudio.PlaybackDevice(output_format=miniaudio.SampleFormat.SIGNED16, nchannels=2, sample_rate=RATE,
                                   buffersize_msec=200, app_name="Gem ambient")
    g = _gen(loop, stop)
    next(g)
    player["device"] = dev
    dev.start(g)
    try:
        while not stop.is_set():
            if player["until"] and time.time() >= player["until"]:
                stop.set()
                break
            time.sleep(0.25)
        time.sleep(3.0)                                         # let it fade out
    finally:
        dev.close()
        if player["stop"] is stop:
            player.update(device=None, sound=None, until=None, stop=None)


@action("ambient_play", "Play a calming background sound (rain, ocean, fan, brown/pink/white noise), optionally for "
        "a while.", "sound?: str, minutes?: number")
def ambient_play(sound="rain", minutes=None):
    key = (sound or "rain").lower().strip().replace(" sounds", "").replace(" sound", "")
    kind = SOUNDS.get(key) or next((v for k, v in SOUNDS.items() if k in key), None)
    if not kind:
        raise ActionError("I can do rain, ocean, fan, or brown, pink and white noise.")
    ambient_stop(quiet=True)
    stop = threading.Event()
    player.update(sound=kind, stop=stop, until=time.time() + float(minutes) * 60 if minutes else None)
    threading.Thread(target=_run, args=(kind, stop), name="ambient", daemon=True).start()
    name = {"rain": "Rain", "ocean": "Ocean waves", "fan": "Fan", "brown": "Brown noise", "pink": "Pink noise",
            "white": "White noise"}[kind]
    if minutes:
        return "%s for %d minutes." % (name, int(float(minutes)))
    return "%s. Say stop the sounds when you're done." % name


@action("ambient_stop", "Stop the background sound.")
def ambient_stop(quiet=False):
    if not player["stop"]:
        return None if quiet else "Nothing's playing."
    player["stop"].set()
    return None if quiet else "Okay."


@action("ambient_volume", "Make the background sound louder or softer.", "direction: up|down")
def ambient_volume(direction="down"):
    if not player["stop"]:
        raise ActionError("Nothing's playing.")
    player["volume"] = max(0.05, min(1.0, player["volume"] * (1.4 if direction == "up" else 0.7)))
    return None


def parse(text):
    """'rain sounds for 30 minutes' -> ('rain', 30)."""
    secs = parse_duration(text)
    return text, (secs / 60.0 if secs else None)
