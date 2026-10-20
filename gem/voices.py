"""Local neural voices (Piper): downloaded once into the data folder, then fully offline."""
import json
import logging
import os
import threading

import requests

from .config import DATA_DIR

log = logging.getLogger("gem.voices")

VOICE_DIR = os.path.join(DATA_DIR, "voices")
HF = "https://huggingface.co/rhasspy/piper-voices/resolve/main/en/{lang}/{speaker}/{quality}/{lang}-{speaker}-{quality}{ext}"

PIPER_VOICES = [
    ("Amy", "en_US-amy-medium"),
    ("Kristin", "en_US-kristin-medium"),
    ("Jenny (British)", "en_GB-jenny_dioco-medium"),
    ("HFC", "en_US-hfc_female-medium"),
    ("Lessac", "en_US-lessac-medium"),
]

_lock = threading.Lock()


def model_path(name):
    return os.path.join(VOICE_DIR, name + ".onnx")


def available(name):
    p = model_path(name)
    return os.path.exists(p) and os.path.exists(p + ".json") and os.path.getsize(p) > 1_000_000


def ensure(name):
    """Download a Piper voice if it isn't here yet. Returns True when it's ready."""
    if available(name):
        return True
    with _lock:
        if available(name):
            return True
        try:
            lang, speaker, quality = name.split("-", 2)
            os.makedirs(VOICE_DIR, exist_ok=True)
            for ext in (".onnx.json", ".onnx"):
                url = HF.format(lang=lang, speaker=speaker, quality=quality, ext=ext)
                tmp = model_path(name) + ext[len(".onnx"):] + ".part"
                log.info("Downloading voice %s%s", name, ext)
                with requests.get(url, stream=True, timeout=30) as r:
                    r.raise_for_status()
                    with open(tmp, "wb") as f:
                        for chunk in r.iter_content(1 << 16):
                            f.write(chunk)
                os.replace(tmp, model_path(name) + ext[len(".onnx"):])
            json.load(open(model_path(name) + ".json", encoding="utf-8"))
            return True
        except Exception as e:
            log.error("Could not download voice %s: %s", name, e)
            return False
