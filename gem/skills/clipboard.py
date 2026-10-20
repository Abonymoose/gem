"""Clipboard history, reading text aloud, and copying Gem's answers.

The history lives in memory only (never written to disk) and skips anything
that looks like a password or API key.
"""
import logging
import re
import threading
import time
from collections import deque

from .. import winapi
from ..actions import ActionError, action
from ..cards import card
from ..runtime import svc

log = logging.getLogger("gem.clipboard")

_history = deque(maxlen=50)          # newest last: (time, text)
_SECRET = re.compile(r"^(?:gsk_|sk-|sk_|ghp_|gho_|github_pat_|xox[abprs]-|AKIA|AIza|eyJ)[\w\-.]{10,}$")


def looks_secret(text):
    t = text.strip()
    if _SECRET.match(t):
        return True
    if " " not in t and "\n" not in t and 8 <= len(t) <= 128 and not t.startswith(("http://", "https://", "www.")):
        kinds = sum(bool(re.search(p, t)) for p in (r"[a-z]", r"[A-Z]", r"\d", r"[^\w]"))
        return kinds >= 4 or (kinds >= 3 and len(t) >= 20 and not re.search(r"[aeiou]{2}", t.lower()))
    return False


def start_watcher():
    def run():
        seq = winapi.user32.GetClipboardSequenceNumber()
        while True:
            time.sleep(0.8)
            try:
                now = winapi.user32.GetClipboardSequenceNumber()
                if now == seq:
                    continue
                seq = now
                text = winapi.get_clipboard()
                if not text or not text.strip() or len(text) > 10000 or text == winapi.last_set_text:
                    continue
                if looks_secret(text):
                    continue
                if _history and _history[-1][1] == text:
                    continue
                _history.append((time.time(), text))
            except Exception:
                log.debug("Clipboard watch failed", exc_info=True)

    threading.Thread(target=run, name="clipboard", daemon=True).start()


def _items():
    return list(reversed(_history))              # newest first


@action("clipboard_history", "List the last few things the user copied.")
def clipboard_history():
    items = _items()[:8]
    if not items:
        return "Nothing copied yet since I started."
    rows = [{"n": i + 1, "text": re.sub(r"\s+", " ", t)[:90], "ago": int(time.time() - at)} for i, (at, t) in
            enumerate(items)]
    return card("clips", "Here's what you copied recently. Say paste number two, for example.", items=rows)


@action("clipboard_paste", "Paste something copied earlier: number (1 = latest, 2 = the one before) or matching text.",
        "number?: number, match?: str")
def clipboard_paste(number=None, match=""):
    items = _items()
    if not items:
        raise ActionError("I haven't seen anything copied yet.")
    if match:
        words = [w for w in re.findall(r"\w+", match.lower())
                 if len(w) > 2 and w not in ("the", "and", "for", "with", "that", "this", "about", "from", "my")]
        hit = next((t for _, t in items if all(w in t.lower() for w in words)), None)
        if not hit:
            raise ActionError("Nothing you copied mentions %s." % match)
        text = hit
    else:
        n = int(number or 2)
        if n < 1 or n > len(items):
            raise ActionError("I only have %d things in your clipboard history." % len(items))
        text = items[n - 1][1]
    winapi.paste_text(text)
    preview = re.sub(r"\s+", " ", text)
    return card("draft", "Pasted.", note=preview[:300] + ("…" if len(preview) > 300 else ""), title="Pasted")


@action("clipboard_clear", "Forget the clipboard history.")
def clipboard_clear():
    _history.clear()
    return "Clipboard history cleared."


@action("read_aloud", "Read the selected text (or the clipboard) out loud.")
def read_aloud():
    text = (winapi.copy_selection() or winapi.get_clipboard() or "").strip()
    if not text:
        raise ActionError("Select some text first.")
    text = re.sub(r"\s+", " ", text)[:3000]
    return card("reading", text, note=text[:220] + ("…" if len(text) > 220 else ""))


@action("copy_answer", "Copy Gem's last answer to the clipboard.")
def copy_answer():
    last = svc.voice.last_text if svc.voice else ""
    if not last:
        raise ActionError("I haven't said anything to copy yet.")
    winapi.set_clipboard(last)
    return "Copied."
