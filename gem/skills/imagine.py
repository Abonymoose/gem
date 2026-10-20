"""Make images by voice: "make me a wallpaper of a neon city at night", "draw a cat in a space suit", then
"set it as my wallpaper". Uses Pollinations' free image service; nothing to sign up for."""
import ctypes
import datetime
import logging
import os
import re
import time
import urllib.parse

import requests

from ..actions import ActionError, action
from ..cards import card
from ..runtime import svc
from ..winapi import known_folder

log = logging.getLogger("gem.imagine")

URL = "https://image.pollinations.ai/prompt/%s"
last = {"path": None}


def _screen_size():
    u = ctypes.windll.user32                    # Gem is DPI aware (Qt), so these are real pixels
    return u.GetSystemMetrics(0), u.GetSystemMetrics(1)


def _generate(prompt, width, height):
    from io import BytesIO
    from PIL import Image
    # Ask for a little extra height, then crop the strip where the free service puts its small logo.
    tall = int(height * 1.08)
    params = {"width": width, "height": tall, "nologo": "true", "model": "flux", "enhance": "true", "safe": "true",
              "seed": int(datetime.datetime.now().timestamp()) % 100000}
    for attempt in range(2):
        r = requests.get(URL % urllib.parse.quote(prompt), params=params, timeout=120)
        wait = re.search(r"[Rr]etry after (\d+)s", r.text) if r.status_code in (402, 429) else None
        if wait and attempt == 0 and int(wait.group(1)) <= 50:
            time.sleep(int(wait.group(1)) + 1)          # the free tier allows one image every ~45 seconds
            continue
        break
    if r.status_code != 200 or not r.headers.get("content-type", "").startswith("image/"):
        raise ActionError("The image service didn't come through. Try again in a minute.")
    img = Image.open(BytesIO(r.content)).convert("RGB")
    keep = int(img.height * height / tall)
    img = img.crop((0, 0, img.width, keep))
    folder = os.path.join(known_folder("pictures"), "Gem")
    os.makedirs(folder, exist_ok=True)
    slug = re.sub(r"[^a-z0-9]+", "-", prompt.lower()).strip("-")[:40] or "image"
    path = os.path.join(folder, "%s_%s.jpg" % (datetime.datetime.now().strftime("%Y%m%d_%H%M%S"), slug))
    img.save(path, "JPEG", quality=93)
    last["path"] = path
    return path


@action("imagine", "Generate an image from a description (a wallpaper if asked). Saved to Pictures/Gem and shown.",
        "prompt: str, wallpaper?: bool")
def imagine(prompt="", wallpaper=False):
    prompt = (prompt or "").strip()
    if not prompt:
        raise ActionError("What should I make?")
    svc.state.update(thinking=True)
    if wallpaper:
        w, h = _screen_size()
        scale = 1920.0 / max(w, 1) if w > 1920 else 1.0          # the service caps the size; keep the shape
        path = _generate(prompt + ", stunning desktop wallpaper, highly detailed, cinematic lighting",
                         int(w * scale), int(h * scale))
        return card("image", "Here it is. Say set it as my wallpaper if you like it.", path=path,
                    header="Wallpaper", note=prompt[:60])
    path = _generate(prompt, 1024, 1024)
    try:
        from .extras import _copy_image
        _copy_image(path)
    except Exception:
        pass
    return card("image", "Here you go. It's saved in Pictures, and copied.", path=path, header="Made for you",
                note=prompt[:60])


@action("set_wallpaper", "Set the image Gem just made (or the latest saved screen) as the desktop wallpaper.")
def set_wallpaper():
    path = last["path"]
    if not path or not os.path.exists(path):
        raise ActionError("Make one first, like: make me a wallpaper of a misty forest.")
    if not ctypes.windll.user32.SystemParametersInfoW(20, 0, path, 3):      # SPI_SETDESKWALLPAPER, save + broadcast
        raise ActionError("Windows didn't accept that wallpaper.")
    return "Done. New wallpaper."
