"""Offline speech recognition (Vosk), for when the internet or Groq is down, and for spotting hype words locally.

The small English model (40 MB) is downloaded once into the data folder. It's less accurate than Whisper,
so it's only used as a fallback, or with a short list of phrases (keyword spotting), where it's very good.
"""
import io
import json
import logging
import os
import shutil
import threading
import zipfile

import requests

from .config import DATA_DIR

log = logging.getLogger("gem.offline")

RATE = 16000
MODEL_NAME = "vosk-model-small-en-us-0.15"
MODEL_DIR = os.path.join(DATA_DIR, "models", MODEL_NAME)
MODEL_URL = "https://alphacephei.com/vosk/models/%s.zip" % MODEL_NAME

_model = None
_lock = threading.Lock()


def available():
    try:
        import vosk  # noqa: F401
    except Exception:
        return False
    return os.path.exists(os.path.join(MODEL_DIR, "am", "final.mdl"))


def ensure_model():
    """Download and unpack the model once. Returns True when it's ready."""
    if available():
        return True
    with _lock:
        if available():
            return True
        try:
            import vosk  # noqa: F401
        except Exception as e:
            log.error("Offline recognition isn't installed: %s", e)
            return False
        try:
            log.info("Downloading the offline speech model")
            r = requests.get(MODEL_URL, timeout=60)
            r.raise_for_status()
            root = os.path.dirname(MODEL_DIR)
            tmp = MODEL_DIR + ".part"
            shutil.rmtree(tmp, ignore_errors=True)
            with zipfile.ZipFile(io.BytesIO(r.content)) as z:
                for info in z.infolist():
                    parts = info.filename.replace("\\", "/").split("/")
                    # Only files inside the model's own folder; nothing that climbs out of it.
                    if parts[0] != MODEL_NAME or ".." in parts or info.is_dir():
                        continue
                    dest = os.path.join(tmp, *parts[1:])
                    os.makedirs(os.path.dirname(dest), exist_ok=True)
                    with z.open(info) as src, open(dest, "wb") as out:
                        shutil.copyfileobj(src, out)
            os.makedirs(root, exist_ok=True)
            shutil.rmtree(MODEL_DIR, ignore_errors=True)
            os.replace(tmp, MODEL_DIR)
            return available()
        except Exception as e:
            log.error("Could not download the offline speech model: %s", e)
            return False


def _get_model():
    global _model
    if _model is None:
        import vosk
        vosk.SetLogLevel(-1)
        _model = vosk.Model(MODEL_DIR)
    return _model


def prepare():
    if ensure_model():
        try:
            with _lock:
                _get_model()
            log.info("Offline speech ready")
        except Exception as e:
            log.error("Couldn't load the offline speech model: %s", e)


def transcribe(pcm):
    """Full offline transcription (lower accuracy than Whisper). '' if nothing was understood."""
    if not available():
        return ""
    import vosk
    with _lock:
        rec = vosk.KaldiRecognizer(_get_model(), RATE)
        rec.AcceptWaveform(pcm)
        return json.loads(rec.FinalResult()).get("text", "")


def spot(pcm, phrases):
    """Which of `phrases` was said (or None), using a grammar limited to them, which is fast and accurate."""
    if not available():
        return None
    import vosk
    with _lock:
        rec = vosk.KaldiRecognizer(_get_model(), RATE, json.dumps(list(phrases) + ["[unk]"]))
        rec.AcceptWaveform(pcm)
        text = json.loads(rec.FinalResult()).get("text", "")
    for p in sorted(phrases, key=len, reverse=True):
        if p in text:
            return p
    return None
