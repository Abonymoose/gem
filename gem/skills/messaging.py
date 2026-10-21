"""Sending messages and emails: Discord, Google Chat and Gmail in the browser.

Gem gets everything ready (opens the app, finds the person, puts the text in the box) and then waits: nothing is sent
until you say "send it" (safety.py). Before pressing Send it checks the same window is still in front and still
showing the same chat, and it double-checks the recipient from the window title or, failing that, from a look at
the screen. Contacts ("Aarav's email is ...") live in contacts.json in the data folder.
"""
import difflib
import logging
import re
import time
import urllib.parse
import webbrowser

from .. import safety
from ..actions import ActionError, action
from ..brain import BrainUnavailable
from ..config import JsonStore
from ..runtime import svc
from ..winapi import (focus_window, foreground_window, paste_text, press, release_modifiers, top_windows, type_text,
                      window_process_name, window_title)
from . import apps

log = logging.getLogger("gem.messaging")

contacts = JsonStore("contacts.json", {"people": {}})

DISCORD = {"discord.exe", "discordptb.exe", "discordcanary.exe"}
APP_LABELS = {"discord": "Discord", "google_chat": "Google Chat"}
EMAIL_RE = re.compile(r"^[\w.+-]+@[\w-]+(?:\.[\w-]+)+$")

LOOK = ("This is a screenshot of the user's {app} window. Reply with JSON only: {{\"conversation\": \"the name of the "
        "person, group or channel whose chat is open (as shown at the top of the chat), or empty\", \"draft\": \"the "
        "text in the message box at the bottom, or empty\"}}. Read names exactly as written; never guess.")


# ── Contacts ─────────────────────────────────────────────────────────────────

def _key(name):
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", "", (name or "").lower())).strip()


def contact(name):
    """A saved person ({"name", "email", "discord", "google_chat"}) by name, or None."""
    key = _key(name)
    people = contacts.data.get("people") or {}
    if not key:
        return None
    if key in people:
        return people[key]
    close = difflib.get_close_matches(key, list(people), n=1, cutoff=0.82)
    return people[close[0]] if close else None


def spoken_email(text):
    """'aarav dot shah at gmail dot com' or 'aarav@gmail.com' -> 'aarav.shah@gmail.com', or None."""
    t = " " + (text or "").strip().lower().rstrip(".") + " "
    t = re.sub(r"\s+at\s+", "@", t)
    t = re.sub(r"\s+dot\s+", ".", t)
    t = re.sub(r"\s+(?:underscore|under score)\s+", "_", t)
    t = re.sub(r"\s+(?:dash|hyphen)\s+", "-", t)
    t = re.sub(r"\s+", "", t)
    return t if EMAIL_RE.match(t) else None


@action("contact_save", "Save someone's email address, Discord name or Google Chat name/email, for sending them "
        "messages later.", "name: str, email?: str, discord?: str, google_chat?: str")
def contact_save(name="", email="", discord="", google_chat=""):
    key = _key(name)
    if not key:
        raise ActionError("Whose details are these?")
    fields = {}
    if email:
        fields["email"] = spoken_email(email)
        if not fields["email"]:
            raise ActionError("That doesn't sound like an email address. Try spelling it with at and dot.")
    if discord:
        fields["discord"] = discord.strip().lstrip("@")
    if google_chat:
        fields["google_chat"] = spoken_email(google_chat) or google_chat.strip()
    if not fields:
        raise ActionError("What should I save for %s?" % name)
    with contacts as d:
        person = d.setdefault("people", {}).setdefault(key, {"name": name.strip().title()})
        person.update(fields)
    what = {"email": "email", "discord": "Discord name", "google_chat": "Google Chat name"}
    shown = " and ".join("%s %s" % (what[k], v) for k, v in fields.items())
    return "Saved %s's %s." % (name.strip().title(), shown)


# ── Understanding requests (on the words as said, so the message keeps its capitals and punctuation) ──

_APP = r"(?P<app>discord|google chat|g ?chat|hangouts)"
_SAYING = (r"(?:\s*,?\s+(?:saying that|saying|that says|which says|to say that|to say|telling (?:them|him|her) "
           r"that|telling (?:them|him|her)|that)\s+|\s*:\s*)")
_MESSAGE = [
    r"^(?:send|write) (?P<to>.+?) an? (?:message|msg|dm|text|note),? (?:on|in|over|via|through|using) " + _APP +
    _SAYING + r"(?P<text>.+)$",
    r"^(?:send|write)(?: a| an)? (?:message|msg|dm|text|note)? ?(?:to )?(?P<to>.+?),? (?:on|in|over|via|through|using) "
    + _APP + _SAYING + r"(?P<text>.+)$",
    r"^(?:message|msg|dm|text|ping|tell)\s+(?P<to>.+?),? (?:on|in|over|via|through) " + _APP +
    r"(?:" + _SAYING + r"|\s*,?\s+)(?P<text>.+)$",
    r"^(?:on|in) " + _APP + r",? (?:send|message|tell|text|dm|ping)(?: a message to)? (?P<to>.+?)" + _SAYING +
    r"(?P<text>.+)$",
    r"^(?:send|post)(?: a)? (?:message|msg) (?:on|in) " + _APP + _SAYING + r"(?P<text>.+)$",
    r"^(?:send|post|say|write) (?P<text>.+?) (?:to (?P<to>.+?) )?(?:on|in) " + _APP + r"$",
]
_EMAIL = r"(?:send |write )?(?:an? )?e-?mail"
_EMAILS = [
    r"^" + _EMAIL + r" (?:to )?(?P<to>.+?),? (?:with the subject|subject|titled) (?P<subject>.+?)" + _SAYING +
    r"(?P<body>.+)$",
    r"^" + _EMAIL + r" (?:to )?(?P<to>.+?)" + _SAYING + r"(?P<body>.+)$",
]
_CONTACT = (r"^(?:the )?(?P<name>[a-z]+(?: [a-z]+)?)(?:'s| s) (?P<what>e-?mail(?: address)?|discord(?: name| username|"
            r" handle| tag)?|google chat(?: name| email)?|g ?chat(?: name| email)?)\s+(?:is|=)\s+(?P<value>.+?)$")


def _clean(raw):
    t = re.sub(r"^\s*(?:(?:hey|hi|ok|okay|yo)\s+)?(?:gem|jem)\b[,.!]?\s*", "", (raw or "").strip(), flags=re.I)
    for _ in range(2):
        t = re.sub(r"^(?:please|can you|could you|would you|will you|i want you to|i need you to|go ahead and|just)\s+",
                   "", t, flags=re.I)
    return t.strip()


def _body(text):
    t = (text or "").strip()
    q = re.match(r'^(["“\'])(.*)(["”\'])[.!?]?$', t, re.S)
    if q:
        return q.group(2).strip()
    return re.sub(r"\s*[,;]\s*$", "", t)


def parse_message(raw):
    """'Message Aarav on Discord saying I'm late' -> {"app", "to", "text"}, or None."""
    t = _clean(raw)
    for pattern in _MESSAGE:
        m = re.match(pattern, t, re.I | re.S)
        if m:
            text = _body(m.group("text"))
            if re.match(r"^(?:a |an )?(?:message|msg|dm|text)$", text, re.I):
                text = ""
            to = (m.groupdict().get("to") or "").strip(" ,")
            return {"app": m.group("app").lower(), "to": to, "text": text}
    return None


def parse_email(raw):
    """'Email Aarav saying the notes are up' -> {"to", "subject", "body"}, or None (e.g. "email Aarav about X", which
    the AI writes properly instead)."""
    t = _clean(raw)
    for pattern in _EMAILS:
        m = re.match(pattern, t, re.I | re.S)
        if m:
            subject = (m.groupdict().get("subject") or "").strip(" ,")
            return {"to": m.group("to").strip(" ,"), "subject": subject, "body": _body(m.group("body"))}
    return None


def parse_contact(raw):
    """"Aarav's email is aarav at gmail dot com" -> contact_save args, or None."""
    m = re.match(_CONTACT, _clean(raw).rstrip("."), re.I)
    if not m or m.group("name").lower() in ("my", "your", "his", "her", "their", "our", "the"):
        return None
    what = m.group("what").lower()
    field = "email" if "mail" in what and "chat" not in what else "discord" if what.startswith("discord") \
        else "google_chat"
    return {"name": m.group("name"), field: m.group("value").strip()}


# ── Windows ──────────────────────────────────────────────────────────────────

def _plain_title(title):
    """A window title without unread counts and dots, which change on their own."""
    t = re.sub(r"^\s*(?:\(\d+\+?\)|\[\d+\]|•|●)\s*", "", title or "")
    return re.sub(r"\s+", " ", t).strip()


def _is_discord(hwnd):
    return window_process_name(hwnd) in DISCORD and bool(window_title(hwnd))


def _is_gchat(hwnd):
    title = (window_title(hwnd) or "").lower()
    return window_process_name(hwnd) in safety.BROWSERS and bool(re.search(r"\b(?:google )?chat\b", title)) \
        and "chatgpt" not in title


def _bring(match, open_name=None, url=None, wait=25):
    """The app's window in front: focus it if it's open, otherwise open it and wait. Returns the hwnd or 0."""
    fg = foreground_window()
    if fg and match(fg):
        return fg
    for hwnd, _, _ in top_windows():
        if match(hwnd):
            focus_window(hwnd)
            time.sleep(0.4)
            if foreground_window() == hwnd:
                return hwnd
    if open_name:
        apps.open_app(open_name)
    elif url:
        webbrowser.open(url)
    else:
        return 0
    end = time.time() + wait
    while time.time() < end:
        time.sleep(0.5)
        fg = foreground_window()
        if fg and match(fg):
            time.sleep(1.5)                          # let it finish loading
            return fg
    return 0


def _check_front(hwnd, label):
    if foreground_window() != hwnd:
        raise ActionError("%s isn't in front any more, so I stopped." % label)


def _same(a, b):
    a, b = _key(a), _key(b)
    if not a or not b:
        return False
    if a in b or b in a:
        return True
    if difflib.SequenceMatcher(None, a, b).ratio() >= 0.75:
        return True
    return any(len(w) >= 3 and w in b.split() for w in a.split())


def _discord_where(title):
    t = _plain_title(title)
    t = re.sub(r"\s*[-|]\s*discord\s*$", "", t, flags=re.I)
    t = re.sub(r"^\s*discord\s*[-|]\s*", "", t, flags=re.I)
    return "" if t.lower() in ("", "discord", "friends") else t


def _gchat_where(title):
    t = _plain_title(title)
    t = re.sub(r"\s*-\s*(?:google chat|chat)(?:\s*-.*)?$", "", t, flags=re.I)
    return "" if t.lower() in ("", "chat", "google chat", "home") else t


def _look(app):
    """What the vision model sees in the chat in front: {"conversation", "draft"}, or None if it can't look now."""
    from ..brain import _parse_json
    from .screen import data_url, grab
    try:
        img, _ = grab()
        out = _parse_json(svc.brain.see(LOOK.format(app=app), "Which chat is open, and what's in the message box?",
                                        data_url(img), max_tokens=160))
    except BrainUnavailable:
        return None
    except Exception:
        log.exception("Looking at %s failed", app)
        return None
    return out if isinstance(out, dict) else None


def _verify(hwnd, label, names, text, where):
    """After the text is in the box: is this the right chat? Returns (where, warning). Raises if it's the wrong one."""
    names = [n for n in names if n]
    if not names or (where and any(_same(n, where) for n in names)):
        return where, ""                             # the chat you're in, or the title already shows who
    seen = _look(label)
    if seen is None:
        return where, "I couldn't double-check who this goes to. Look at %s before you say send it." % label
    convo = str(seen.get("conversation") or "").strip()
    draft = str(seen.get("draft") or "").strip()
    if convo and not any(_same(n, convo) for n in names):
        raise ActionError("The chat that opened is %s, not %s, so I won't send it. The text is in the box if you "
                          "want it." % (convo, names[-1]))
    warning = ""
    if not convo:
        warning = "I couldn't see whose chat this is. Look at %s before you say send it." % label
    elif draft and not _same(text[:40], draft[:60]):
        warning = "The box seems to have other text in it too. Check it before you say send it."
    elif not draft:
        warning = "I couldn't see the message in the box. Check it before you say send it."
    return convo or where, warning


def _press_send(hwnd, ready_title, chord, label):
    """The approved send: only if the same window, showing the same chat, is in front."""
    if foreground_window() != hwnd:
        focus_window(hwnd)
        time.sleep(0.4)
    if foreground_window() != hwnd:
        raise ActionError("I couldn't bring %s back to the front, so I didn't send it." % label)
    if _plain_title(window_title(hwnd)) != ready_title:
        raise ActionError("%s changed since I got it ready, so I didn't send it. Check what's in the box." % label)
    release_modifiers()
    press(*chord)
    log.info("Sent in %s (%s)", label, "+".join(chord))
    return "Sent."


def _short(text, n=40):
    text = re.sub(r"\s+", " ", text or "").strip()
    return text if len(text) <= n else text[:n - 1].rstrip() + "…"


# ── Chat messages ────────────────────────────────────────────────────────────

def _which_app(app):
    a = (app or "").lower().replace("_", " ").strip()
    if a in ("discord", "dc"):
        return "discord"
    if a in ("google chat", "gchat", "g chat", "chat", "hangouts", "google hangouts", "gmail chat"):
        return "google_chat"
    raise ActionError("I can send messages on Discord or Google Chat.")


def _ready_discord(handle, names, text):
    if len(text) > 2000:
        raise ActionError("That's too long for one Discord message.")
    hwnd = _bring(_is_discord, open_name="discord")
    if not hwnd:
        raise ActionError("I couldn't get Discord in front.")
    release_modifiers()
    if handle:
        press("ctrl", "k")                           # quick switcher
        time.sleep(0.6)
        _check_front(hwnd, "Discord")
        type_text(handle)
        time.sleep(1.2)
        _check_front(hwnd, "Discord")
        press("enter")                               # opens the top match; nothing is sent
        time.sleep(1.3)
    _check_front(hwnd, "Discord")
    where = _discord_where(window_title(hwnd))
    if names and where and not any(_same(n, where) for n in names):
        press("esc")
        raise ActionError("Discord opened %s, which doesn't look like %s, so I stopped. Nothing was typed."
                          % (where, names[-1]))
    paste_text(text)
    time.sleep(0.4)
    return hwnd, where


def _ready_gchat(handle, names, text):
    hwnd = _bring(_is_gchat, url="https://chat.google.com")
    if not hwnd:
        raise ActionError("I couldn't get Google Chat open in your browser.")
    release_modifiers()
    if handle:
        press("ctrl", "shift", "k")                  # new chat: find a person
        time.sleep(1.3)
        _check_front(hwnd, "Google Chat")
        type_text(handle)
        time.sleep(2.0)
        _check_front(hwnd, "Google Chat")
        press("enter")                               # opens the chat with them; nothing is sent
        time.sleep(2.5)
    _check_front(hwnd, "Google Chat")
    where = _gchat_where(window_title(hwnd))
    paste_text(text)
    time.sleep(0.4)
    return hwnd, where


@action("send_message", "Send a chat message on Discord or Google Chat to a person or channel (or the chat that's "
        "open if no one is named). Gem shows it and only sends after the user says 'send it'.",
        "app: discord|google_chat, to?: str, text: str")
def send_message(app="discord", to="", text=""):
    text = (text or "").strip()
    if not text:
        raise ActionError("What should the message say?")
    which = _which_app(app)
    label = APP_LABELS[which]
    to = (to or "").strip()
    person = contact(to) if to else None
    handle = ((person or {}).get(which) or to).lstrip("@#") if to else ""
    shown = (person or {}).get("name") or to
    if safety.unattended():
        return safety.skip("Send “%s” to %s on %s" % (_short(text), shown or "the open chat", label))
    names = [n for n in (handle, shown) if n]
    if which == "discord":
        hwnd, where = _ready_discord(handle, names, text)
    else:
        hwnd, where = _ready_gchat(handle, names, text)
    where, warning = _verify(hwnd, label, names, text, where)
    ready = _plain_title(window_title(hwnd))
    return safety.ask("Send on %s" % label, lambda: _press_send(hwnd, ready, ("enter",), label), app=label,
                      to=where or shown or "the open chat", message=text, warning=warning,
                      on_cancel=lambda: "The message is still in the box.")


# ── Email ────────────────────────────────────────────────────────────────────

def _subject_for(body):
    try:
        subject = svc.brain.complete("Write a short, plain email subject line (at most 6 words) for this email. "
                                     "Output only the subject.", body, max_tokens=30, temperature=0.3)
        subject = subject.strip().strip('"').splitlines()[0] if subject else ""
    except (BrainUnavailable, IndexError):
        subject = ""
    if not subject:
        words = body.split()
        subject = " ".join(words[:6]) + ("…" if len(words) > 6 else "")
    return subject[:80]


def _ready_gmail(address, subject, body):
    before = {(h, t) for h, t, p in top_windows() if p in safety.BROWSERS}
    query = urllib.parse.urlencode({"view": "cm", "fs": "1", "tf": "1", "to": address, "su": subject, "body": body},
                                   quote_via=urllib.parse.quote)
    webbrowser.open("https://mail.google.com/mail/?" + query)
    end, hwnd = time.time() + 25, 0
    while time.time() < end:
        time.sleep(0.5)
        fg = foreground_window()
        title = window_title(fg)
        if window_process_name(fg) in safety.BROWSERS and "gmail" in title.lower() and (fg, title) not in before:
            hwnd = fg
            break
    if not hwnd:
        raise ActionError("Gmail didn't open in your browser. Are you signed in?")
    settle = time.time() + 6
    while time.time() < settle and "compose" not in window_title(hwnd).lower():
        time.sleep(0.4)                              # wait for the draft to finish loading
    time.sleep(1.0)
    _check_front(hwnd, "Gmail")
    return hwnd, _plain_title(window_title(hwnd))


def _send_gmail(hwnd, ready_title):
    _press_send(hwnd, ready_title, ("ctrl", "enter"), "Gmail")
    end = time.time() + 6
    while time.time() < end:
        time.sleep(0.4)
        if _plain_title(window_title(hwnd)) != ready_title:
            return "Sent. Gmail lets you undo it for a few seconds."
    return "I pressed Send, but Gmail still shows the draft. Have a look at it."


def _email_for(to):
    to = (to or "").strip()
    address = spoken_email(to)
    if address:
        return address, ""
    person = contact(to)
    if person and person.get("email"):
        return person["email"], person.get("name") or to.title()
    return None, to


@action("send_email", "Write an email in Gmail (in the browser) and send it after the user says 'send it'. 'to' is a "
        "saved contact's name or an email address.", "to: str, subject?: str, body: str")
def send_email(to="", subject="", body=""):
    body = (body or "").strip()
    if not body:
        raise ActionError("What should the email say?")
    address, name = _email_for(to)
    if not address:
        who = name or "them"
        raise ActionError("I don't have an email address for %s. Say “%s's email is …” first, then ask again."
                          % (who, who))
    subject = (subject or "").strip() or _subject_for(body)
    if safety.unattended():
        return safety.skip("Email %s about “%s”" % (name or address, _short(subject)))
    hwnd, ready = _ready_gmail(address, subject, body)
    return safety.ask("Send email", lambda: _send_gmail(hwnd, ready), app="Gmail",
                      to=("%s <%s>" % (name, address)) if name else address, subject=subject, message=body,
                      on_cancel=lambda: "The draft is still open in Gmail.")


# ── Text Gem typed into the box in front (reply drafts, away notes) ──────────

def send_keys(hwnd):
    """The keys that send what's typed in this window, or None if Gem doesn't know this app."""
    proc = window_process_name(hwnd)
    title = (window_title(hwnd) or "").lower()
    if proc in ("outlook.exe", "olk.exe", "hxoutlook.exe", "thunderbird.exe", "mailspring.exe") or \
            (proc in safety.BROWSERS and re.search(r"\b(?:gmail|outlook|mail|inbox)\b", title)):
        return ("ctrl", "enter")
    if safety.window_kind(hwnd) == "messaging":
        return ("enter",)
    return None


def offer_send(text, what="reply"):
    """Gem just put text in the message box in front: let "send it" send it. Returns the approve card, or None when
    Gem doesn't know how this app sends (then the user presses Enter themselves)."""
    hwnd = foreground_window()
    keys = send_keys(hwnd)
    if not keys or safety.unattended():
        return None
    label = apps.friendly_name(hwnd).capitalize() or "this app"
    ready = _plain_title(window_title(hwnd))
    return safety.ask("Send this %s" % what, lambda: _press_send(hwnd, ready, keys, label), app=label,
                      to=_short(ready, 50), message=text, on_cancel=lambda: "It's still in the box.")
