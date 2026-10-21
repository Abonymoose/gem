"""Small things that are just there when you need them: QR codes (and Wi-Fi QR for guests), the Wi-Fi password,
copying text off the screen, the colour under the mouse, reminders for when you open an app, short links."""
import ctypes
import ctypes.wintypes as wt
import logging
import os
import re
import subprocess
import time

import requests

from ..actions import ActionError, action
from ..brain import BrainUnavailable
from ..cards import card
from ..config import DATA_DIR
from ..runtime import svc
from ..winapi import copy_selection, foreground_window, get_clipboard, set_clipboard

log = logging.getLogger("gem.extras")

QR_DIR = os.path.join(DATA_DIR, "qr")
NO_WINDOW = subprocess.CREATE_NO_WINDOW


def _copy_image(path):
    from io import BytesIO
    import win32clipboard
    from PIL import Image
    out = BytesIO()
    Image.open(path).convert("RGB").save(out, "BMP")
    win32clipboard.OpenClipboard()
    try:
        win32clipboard.EmptyClipboard()
        win32clipboard.SetClipboardData(win32clipboard.CF_DIB, out.getvalue()[14:])
    finally:
        win32clipboard.CloseClipboard()


def _qr_png(payload, name):
    import segno
    os.makedirs(QR_DIR, exist_ok=True)
    path = os.path.join(QR_DIR, name + ".png")
    segno.make(payload, error="m").save(path, scale=12, border=3, dark="#111111", light="#ffffff")
    _copy_image(path)
    return path


# ── Wi-Fi ────────────────────────────────────────────────────────────────────

def _netsh(*args):
    return subprocess.run(["netsh", "wlan", *args], capture_output=True, text=True, creationflags=NO_WINDOW).stdout


def _last_connected():
    """The Wi-Fi profile you connected to most recently (from the WLAN event log), or ''."""
    out = subprocess.run(["wevtutil", "qe", "Microsoft-Windows-WLAN-AutoConfig/Operational",
                          "/q:*[System[(EventID=8001)]]", "/c:1", "/rd:true", "/f:text"],
                         capture_output=True, text=True, creationflags=NO_WINDOW).stdout
    m = re.search(r"Profile Name:\s+(.+)$", out, re.M)
    return m.group(1).strip() if m else ""


def _wifi(network=""):
    """(network name, password or None). Current network, a named one, or the one you used last."""
    name = network.strip()
    if not name:
        m = re.search(r"^\s+Profile\s+:\s+(.+)$", _netsh("show", "interfaces"), re.M)
        name = m.group(1).strip() if m else ""
    profiles = re.findall(r"All User Profile\s+:\s+(.+)$", _netsh("show", "profiles"), re.M)
    profiles = [p.strip() for p in profiles]
    if not name and len(profiles) > 1:
        last = _last_connected()
        if last in profiles:
            name = last
    if name:
        match = next((p for p in profiles if p.lower() == name.lower()), None) or \
            next((p for p in profiles if name.lower() in p.lower()), None)
        if not match:
            raise ActionError("I don't have a saved Wi-Fi network called %s." % name)
        name = match
    elif len(profiles) == 1:
        name = profiles[0]
    elif profiles:
        raise ActionError("You're not on Wi-Fi right now. Which network? For example %s." % ", ".join(profiles[:3]))
    else:
        raise ActionError("There are no saved Wi-Fi networks on this PC.")
    m = re.search(r"Key Content\s+:\s+(.+)$", _netsh("show", "profile", "name=%s" % name, "key=clear"), re.M)
    return name, (m.group(1).strip() if m else None)


@action("wifi_password", "Show the Wi-Fi password (current network or a saved one by name) and copy it.",
        "network?: str")
def wifi_password(network=""):
    name, key = _wifi(network)
    if not key:
        return "%s doesn't have a password saved." % name
    set_clipboard(key)
    # Shown and copied, not read out, in case someone's listening.
    return card("alert", "The %s password is on screen and copied." % name, title=name, message=key)


@action("wifi_qr", "Make a QR code guests can scan to join the Wi-Fi.", "network?: str")
def wifi_qr(network=""):
    name, key = _wifi(network)
    esc = lambda s: re.sub(r"([\\;,:\"])", r"\\\1", s)
    payload = "WIFI:T:%s;S:%s;P:%s;;" % ("WPA" if key else "nopass", esc(name), esc(key or ""))
    path = _qr_png(payload, "wifi")
    return card("image", "Here's a QR code for %s. Scan it with a phone camera to join." % name, path=path,
                header="Join %s" % name, note="Copied · scan with a phone camera")


# ── QR codes and links ───────────────────────────────────────────────────────

def _selected_or_clipboard():
    text = (copy_selection() or "").strip() or (get_clipboard() or "").strip()
    return text


@action("qr_code", "Make a QR code for a link or text (the selection or clipboard if none given).", "text?: str")
def qr_code(text=""):
    text = (text or "").strip()
    if not text or text.lower() in ("this", "that", "it", "this link", "that link"):
        text = _selected_or_clipboard()
    if not text:
        raise ActionError("Select or copy what the QR code should hold.")
    path = _qr_png(text[:1500], "qr")
    short = text if len(text) <= 48 else text[:45] + "..."
    return card("image", "Here's the QR code. It's copied too.", path=path, header="QR code", note=short)


@action("shorten_link", "Shorten a link (the selection or clipboard if none given) and copy it.", "url?: str")
def shorten_link(url=""):
    url = (url or "").strip()
    if not url.startswith("http"):
        url = _selected_or_clipboard()
    m = re.search(r"https?://\S+", url or "")
    if not m:
        raise ActionError("Select or copy a link first.")
    r = requests.get("https://is.gd/create.php", params={"format": "simple", "url": m.group(0)}, timeout=8)
    short = r.text.strip()
    if r.status_code != 200 or not short.startswith("http"):
        raise ActionError("The link shortener didn't work just now.")
    set_clipboard(short)
    return card("alert", "Short link copied.", title="Short link", message=short)


# ── Screen text ──────────────────────────────────────────────────────────────

@action("copy_screen_text", "Copy the text that's on screen (in the active window, an image, a video frame...) to the "
        "clipboard.", "what?: str")
def copy_screen_text(what=""):
    from .screen import data_url, grab
    svc.state.update(thinking=True)
    img, title = grab()
    ask = ("Transcribe the text %s exactly as written, keeping line breaks. Output only the text, nothing else."
           % (("of " + what) if what else "in the main window or image the user is looking at"))
    try:
        text = svc.brain.see("You copy text out of screenshots precisely. The active window is: %s." % title, ask,
                             data_url(img), max_tokens=1200)
    except BrainUnavailable as e:
        raise ActionError(str(e))
    text = re.sub(r"^```\w*\n|\n```$", "", text.strip())
    if not text:
        return "I couldn't find any text to copy."
    set_clipboard(text)
    words = len(text.split())
    return "Copied %d word%s from your screen." % (words, "" if words == 1 else "s")


# ── Reading the screen out loud ──────────────────────────────────────────────

READ_ASK = ("Transcribe the main readable content in the active window, in reading order, so it can be read aloud: "
            "the article, document, message thread, email or question the user is looking at. Leave out menus, "
            "toolbars, tabs, buttons, ads, URLs, timestamps and other page furniture. Copy the words exactly; don't "
            "summarize, explain or add anything. Plain text only, one paragraph per line. If there's no real text, "
            "reply NONE.")
READ_TILES = (" There are {n} pictures of the same window from left to right, overlapping in the middle: text that "
              "appears in two pictures is the same text, so include it once.")
READ_CHUNK = 2200
_reading = {"rest": "", "t": 0.0}


def _say_chunk(text):
    """Read up to about two minutes; keep the rest for "keep reading"."""
    if len(text) <= READ_CHUNK:
        _reading.update(rest="", t=time.time())
        return card("reading", text, note=text[:220] + ("…" if len(text) > 220 else ""))
    cut = max(text.rfind("\n", 0, READ_CHUNK), text.rfind(". ", 0, READ_CHUNK) + 1)
    cut = cut if cut > READ_CHUNK // 2 else READ_CHUNK
    _reading.update(rest=text[cut:].strip(), t=time.time())
    part = text[:cut].strip()
    return card("reading", part + " … Say keep reading for the rest.", note=part[:220] + "…")


@action("read_screen", "Read the text in the active window out loud (an article, document, email, messages...).",
        "what?: str")
def read_screen(what=""):
    from ..winapi import window_rect_physical
    from .screen import TILES_COST, _pieces, data_url, grab
    svc.state.update(thinking=True)
    img, title, box = grab(with_box=True, full=True)
    hwnd = foreground_window()
    if hwnd and box:
        # Just the window you're reading, not the whole monitor.
        wl, wt_, wr, wb = window_rect_physical(hwnd)
        crop = (max(0, wl - box[0]), max(0, wt_ - box[1]), min(img.width, wr - box[0]), min(img.height, wb - box[1]))
        if crop[2] - crop[0] > 200 and crop[3] - crop[1] > 150:
            img = img.crop(crop)
    model = (svc.config["ai"].get("vision_models") or ["qwen/qwen3.8-27b"])[0]
    pieces = _pieces(img)
    daily_ok = svc.brain.used_today(model) < float(svc.config["ai"].get("vision_daily_tokens", 200000)) * 0.6
    ask = READ_ASK + (" Only this part: %s." % what if what else "")
    try:
        if len(pieces) > 1 and daily_ok and svc.brain.budget(model) >= TILES_COST:
            text = svc.brain.see("You read screens aloud for the user. The active window is: %s." % title,
                                 ask + READ_TILES.format(n=len(pieces)), [data_url(p) for _, p in pieces],
                                 max_tokens=1800)
        else:
            img.thumbnail((1600, 1600))
            text = svc.brain.see("You read screens aloud for the user. The active window is: %s." % title, ask,
                                 data_url(img), max_tokens=1800)
    except BrainUnavailable as e:
        raise ActionError(str(e))
    text = re.sub(r"^```\w*\n|\n```$", "", (text or "").strip())
    if not text or text.strip().upper().rstrip(".") == "NONE":
        return "I don't see any text to read there."
    return _say_chunk(text)


@action("read_more", "Keep reading what Gem was reading from the screen.", ai=False)
def read_more():
    if not _reading["rest"] or time.time() - _reading["t"] > 1800:
        return "There's nothing left to read."
    return _say_chunk(_reading["rest"])


# ── Colour picker ────────────────────────────────────────────────────────────

COLOURS = {
    "black": (0, 0, 0), "white": (255, 255, 255), "grey": (128, 128, 128), "light grey": (211, 211, 211),
    "dark grey": (64, 64, 64), "red": (220, 20, 60), "dark red": (139, 0, 0), "pink": (255, 105, 180),
    "light pink": (255, 182, 193), "orange": (255, 140, 0), "peach": (255, 218, 185), "yellow": (255, 215, 0),
    "cream": (255, 253, 208), "gold": (212, 175, 55), "brown": (139, 69, 19), "tan": (210, 180, 140),
    "olive": (128, 128, 0), "lime": (50, 205, 50), "green": (34, 139, 34), "dark green": (0, 100, 0),
    "mint": (152, 255, 152), "teal": (0, 128, 128), "turquoise": (64, 224, 208), "cyan": (0, 255, 255),
    "sky blue": (135, 206, 235), "blue": (30, 100, 255), "royal blue": (65, 105, 225), "navy": (0, 0, 128),
    "indigo": (75, 0, 130), "purple": (128, 0, 128), "violet": (138, 92, 246), "lavender": (196, 160, 240),
    "magenta": (255, 0, 255), "maroon": (128, 0, 0), "beige": (245, 245, 220), "charcoal": (40, 44, 52),
}


class POINT(ctypes.Structure):
    _fields_ = [("x", wt.LONG), ("y", wt.LONG)]


@action("color_picker", "Say and copy the colour under the mouse pointer (hex code).")
def color_picker():
    from PIL import ImageGrab
    pt = POINT()
    if not ctypes.windll.user32.GetPhysicalCursorPos(ctypes.byref(pt)):
        ctypes.windll.user32.GetCursorPos(ctypes.byref(pt))
    r, g, b = ImageGrab.grab(bbox=(pt.x, pt.y, pt.x + 1, pt.y + 1), all_screens=True).convert("RGB").getpixel((0, 0))
    hexcode = "#%02X%02X%02X" % (r, g, b)
    name = min(COLOURS, key=lambda n: sum((a - c) ** 2 for a, c in zip(COLOURS[n], (r, g, b))))
    set_clipboard(hexcode)
    return card("color", "That's %s. The hex code is copied." % name, hex=hexcode, rgb=[r, g, b], name=name)


# ── Reminders for when you open an app ───────────────────────────────────────

@action("remind_on_open", "Remind the user of something the next time they open an app, e.g. 'remind me to reply to "
        "Aarav when I open Discord'.", "app: str, message: str")
def remind_on_open(app="", message=""):
    from ..headsup import app_reminders
    app, message = (app or "").strip(), (message or "").strip().rstrip(".")
    if not app or not message:
        raise ActionError("Which app, and what should I remind you about?")
    with app_reminders as data:
        data["items"].append({"app": app, "message": message, "created": time.time()})
    return "Okay, next time you open %s I'll remind you to %s." % (app.title() if app.islower() else app, message)
