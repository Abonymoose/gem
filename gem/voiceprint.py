"""Voiceprint: recognise the user's voice, so always-listening mode ignores everyone else.

A WeSpeaker ResNet34 model (ONNX, downloaded once into the data folder) turns a few seconds of speech
into a 256-number voice embedding. Gem keeps embeddings of your voice (from voice training and from
push-to-talk, which is always you) and compares new speech against them before transcribing it.
Everything runs on this PC; no audio leaves it for this.
"""
import collections
import hashlib
import logging
import os
import threading
import time

import numpy as np
import requests

from .config import DATA_DIR, JsonStore

log = logging.getLogger("gem.voiceprint")

RATE = 16000
MODEL_DIR = os.path.join(DATA_DIR, "models")
MODEL_PATH = os.path.join(MODEL_DIR, "voxceleb_resnet34_LM.onnx")
MODEL_URL = "https://huggingface.co/Wespeaker/wespeaker-voxceleb-resnet34-LM/resolve/main/voxceleb_resnet34_LM.onnx"
MODEL_SHA256 = "7bb2f06e9df17cdf1ef14ee8a15ab08ed28e8d0ef5054ee135741560df2ec068"

MIN_SAMPLES = 4          # embeddings needed before the lock can work
MAX_LEARNED = 40         # rolling samples from push-to-talk
MIN_VOICED_S = 0.6       # shorter than this can't be judged

# Your voice is "trained" + "learned". "people" holds family and friends by name:
# {"freya": {"name": "Freya", "relation": "sister", "samples": [...], "blocked": true}}
store = JsonStore("voiceprint.json", {"locked": False, "trained": [], "learned": [], "people": {}})
MAX_PERSON = 24


# ── Features: Kaldi-style 80-band log-mel filterbank, as the model was trained on ──

def _mel(f):
    return 1127.0 * np.log(1.0 + np.asarray(f, dtype=np.float64) / 700.0)


def _mel_banks(n=80, nfft=512, sr=RATE, low=20.0):
    mel_low, mel_high = _mel(low), _mel(sr / 2)
    delta = (mel_high - mel_low) / (n + 1)
    mels = _mel(sr / nfft * np.arange(nfft // 2))
    left = mel_low + np.arange(n)[:, None] * delta
    center, right = left + delta, left + 2 * delta
    banks = np.maximum(0.0, np.minimum((mels - left) / (center - left), (right - mels) / (right - center)))
    return np.pad(banks, ((0, 0), (0, 1)))                   # (80, 257): the Nyquist bin gets no weight


_BANKS = _mel_banks()
_WINDOW = np.hamming(400)
_EPS = float(np.finfo(np.float32).eps)


def fbank(samples):
    """int16-scale samples -> (frames, 80) mean-normalised log-mel features."""
    x = np.asarray(samples, dtype=np.float64)
    n = 1 + (len(x) - 400) // 160
    if n < 10:
        return None
    frames = x[np.arange(400)[None, :] + 160 * np.arange(n)[:, None]]
    frames = frames - frames.mean(axis=1, keepdims=True)
    frames = np.concatenate([frames[:, :1] * 0.03, frames[:, 1:] - 0.97 * frames[:, :-1]], axis=1)
    power = np.abs(np.fft.rfft(frames * _WINDOW, n=512)) ** 2
    feats = np.log(np.maximum(power @ _BANKS.T, _EPS))
    return (feats - feats.mean(axis=0, keepdims=True)).astype(np.float32)


def voiced(pcm):
    """Only the frames webrtcvad hears speech in, so silence and room noise don't count."""
    import webrtcvad
    vad = webrtcvad.Vad(2)
    step = RATE * 30 // 1000 * 2
    keep = [pcm[i:i + step] for i in range(0, len(pcm) - step + 1, step) if vad.is_speech(pcm[i:i + step], RATE)]
    return np.frombuffer(b"".join(keep), dtype=np.int16)


# ── Model ────────────────────────────────────────────────────────────────────

_session = None
_lock = threading.Lock()


def model_ready():
    return os.path.exists(MODEL_PATH) and os.path.getsize(MODEL_PATH) > 20_000_000


def ensure_model():
    """Download the speaker model once (26 MB). Returns True when it's ready."""
    if model_ready():
        return True
    with _lock:
        if model_ready():
            return True
        try:
            os.makedirs(MODEL_DIR, exist_ok=True)
            tmp = MODEL_PATH + ".part"
            log.info("Downloading the speaker model")
            digest = hashlib.sha256()
            with requests.get(MODEL_URL, stream=True, timeout=30) as r:
                r.raise_for_status()
                with open(tmp, "wb") as f:
                    for chunk in r.iter_content(1 << 16):
                        f.write(chunk)
                        digest.update(chunk)
            if digest.hexdigest() != MODEL_SHA256:
                os.remove(tmp)
                log.error("Speaker model checksum mismatch; not using it")
                return False
            os.replace(tmp, MODEL_PATH)
            return True
        except Exception as e:
            log.error("Could not download the speaker model: %s", e)
            return False


def prepare():
    """Startup, in the background: fetch the model if needed and load it, so the first check is quick."""
    if ensure_model():
        try:
            with _lock:
                _model()
            log.info("Voice model ready (%d voice samples)", sample_count())
        except Exception as e:
            log.error("Couldn't load the voice model: %s", e)


def _model():
    global _session
    if _session is None:
        import onnxruntime as ort
        opts = ort.SessionOptions()
        opts.intra_op_num_threads = 2
        _session = ort.InferenceSession(MODEL_PATH, opts, providers=["CPUExecutionProvider"])
    return _session


def embed(pcm):
    """(unit embedding, seconds of speech) for 16 kHz int16 PCM bytes; embedding None if too little speech."""
    speech = voiced(pcm)
    secs = len(speech) / RATE
    if secs < MIN_VOICED_S or not model_ready():
        return None, secs
    feats = fbank(speech[: RATE * 12])                         # 12 s is plenty
    if feats is None:
        return None, secs
    with _lock:
        e = _model().run(None, {"feats": feats[None]})[0][0]
    return e / (np.linalg.norm(e) + 1e-9), secs


# ── Profile ──────────────────────────────────────────────────────────────────

def _vecs(lst):
    return [np.asarray(v, dtype=np.float32) for v in lst or []]


def _samples():
    d = store.data
    return _vecs((d.get("trained") or []) + (d.get("learned") or []))


def sample_count():
    return len(store.data.get("trained") or []) + len(store.data.get("learned") or [])


def ready():
    return model_ready() and sample_count() >= MIN_SAMPLES


def locked():
    return bool(store.data.get("locked")) and ready()


def set_locked(on):
    with store as d:
        d["locked"] = bool(on)


def score(e, samples=None):
    """How much an embedding sounds like you (or like `samples`): cosine to the average voice, or to the
    closest few samples, whichever is higher."""
    s = _samples() if samples is None else samples
    if not s:
        return 0.0
    m = np.stack(s)
    centroid = m.mean(axis=0)
    centroid /= np.linalg.norm(centroid) + 1e-9
    sims = np.sort(m @ e)[::-1]
    return float(max(centroid @ e, sims[: min(3, len(sims))].mean()))


def threshold(secs, base):
    # Short clips give noisier embeddings, so they get a little more slack.
    return base - (0.06 if secs < 1.5 else 0.0)


last = {"score": None, "secs": 0.0, "t": 0.0, "accepted": None}


def check(pcm, base_threshold):
    """(is it you, score). Unsure (too short to tell) counts as not you."""
    e, secs = embed(pcm)
    if e is None:
        last.update(score=None, secs=secs, t=time.time(), accepted=False)
        return False, None
    sc = score(e)
    ok = sc >= threshold(secs, base_threshold)
    last.update(score=sc, secs=secs, t=time.time(), accepted=ok)
    return ok, sc


def add(pcm, kind="learned", base_threshold=None):
    """Add your speech to the profile. Learned samples must already sound like you, so the print can't drift."""
    e, secs = embed(pcm)
    if e is None or secs < 1.0:
        return False
    if kind == "learned" and ready() and base_threshold is not None and score(e) < base_threshold - 0.1:
        log.info("Not learning from a clip that doesn't sound like you (%.2f)", score(e))
        return False
    with store as d:
        d.setdefault(kind, []).append([round(float(v), 5) for v in e])
        if kind == "learned":
            d["learned"] = d["learned"][-MAX_LEARNED:]
        else:
            d["trained"] = d["trained"][-12:]
    return True


def forget():
    with store as d:
        d.update(locked=False, trained=[], learned=[])


# ── Other people (family, friends) ───────────────────────────────────────────

recent = collections.deque(maxlen=8)        # (time, embedding, who) of the last voices heard


def people():
    return store.data.get("people") or {}


def person(name):
    return people().get(_key(name))


def _key(name):
    return " ".join((name or "").lower().split())


def blocked_names():
    return {k for k, p in people().items() if p.get("blocked")}


def identify(e, secs, base):
    """Best match among you and everyone Gem knows: (who or None, score). who is "me" or a person key."""
    cands = [("me", score(e) if sample_count() >= MIN_SAMPLES else 0.0)]
    for k, p in people().items():
        if p.get("samples"):
            cands.append((k, score(e, _vecs(p["samples"]))))
    who, sc = max(cands, key=lambda c: c[1])
    return (who if sc >= threshold(secs, base) else None), sc


def hear(pcm, base):
    """Who is speaking: ("me" | person key | None for a stranger | "?" when too short to tell, score)."""
    e, secs = embed(pcm)
    if e is None:
        last.update(score=None, secs=secs, t=time.time(), accepted=None, who="?")
        return "?", None
    who, sc = identify(e, secs, base)
    recent.append((time.time(), e, who))
    last.update(score=sc, secs=secs, t=time.time(), who=who)
    if who not in (None, "me") and sc >= threshold(secs, base) + 0.12:
        _add_person(who, [e])                  # confident: keep learning their voice too
    return who, sc


def _add_person(key, embeddings, name=None, relation=None):
    with store as d:
        p = d.setdefault("people", {}).setdefault(key, {"name": name or key.title(), "samples": [], "blocked": False})
        if relation:
            p["relation"] = relation
        p["samples"] = (p.get("samples", []) + [[round(float(v), 5) for v in e] for e in embeddings])[-MAX_PERSON:]


def add_person_audio(name, pcm, relation=None):
    e, secs = embed(pcm)
    if e is None or secs < 1.0:
        return False
    _add_person(_key(name), [e], name=name.strip().title(), relation=relation)
    return True


def label_recent(name, relation=None, within=180):
    """"That was Freya": file the last voices that weren't you under her name. Returns how many."""
    now = time.time()
    picked = [e for t, e, who in reversed(recent) if now - t < within and who != "me"][:3]
    if picked:
        _add_person(_key(name), picked, name=name.strip().title(), relation=relation)
        for i, (t, e, who) in enumerate(recent):
            if any(e is p for p in picked):
                recent[i] = (t, e, _key(name))
    return len(picked)


def set_blocked(name, on, relation=None):
    key = _key(name)
    with store as d:
        p = d.setdefault("people", {}).setdefault(key, {"name": name.strip().title(), "samples": [], "blocked": False})
        p["blocked"] = bool(on)
        if relation:
            p["relation"] = relation
    return bool(person(name).get("samples"))


def forget_person(name):
    with store as d:
        return d.setdefault("people", {}).pop(_key(name), None) is not None
