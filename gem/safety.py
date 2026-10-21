"""The safety gate: big steps wait for your OK.

Sending a message or email, pressing Enter in a chat or a terminal, deleting files, clicking a Send- or Delete-like
button, power actions and running a plan Gem worked out are big steps. Gem shows exactly what will happen and only
goes ahead when you say a set phrase ("send it" / "confirm"); "yes" or "okay" is not enough. If Gem knows your voice,
it has to be your voice. Typing the phrase in the command bar works too (you're at the keyboard).

Nothing scheduled or overheard can approve. When nobody is there to answer (a scheduled command or macro), big steps
are skipped and you're told afterwards.
"""
import logging
import re
import threading
import time
from contextlib import contextmanager

from .actions import ActionError, Failure
from .cards import card
from .runtime import caption, notify, say, svc
from .winapi import window_class, window_process_name, window_title

log = logging.getLogger("gem.safety")

DEFAULT_PHRASES = ["send it", "confirm"]
CANCEL = {"cancel", "cancel it", "no", "nope", "no thanks", "don't", "dont", "don't send it", "dont send it",
          "don't send", "dont send", "don't do it", "dont do it", "stop", "stop it", "wait", "hold on", "abort",
          "never mind", "nevermind", "no don't", "no dont", "forget it"}
# Plain agreement: not enough for a big step, so Gem says what to say instead.
NOT_ENOUGH = {"yes", "yeah", "yep", "yup", "sure", "ok", "okay", "do it", "go ahead", "yes please", "correct",
              "send", "go", "affirmative", "please do", "yes do it"}

# Apps where Enter (or Ctrl+Enter) sends what you typed.
MESSAGING_APPS = {"discord.exe", "discordptb.exe", "discordcanary.exe", "whatsapp.exe", "whatsapp.root.exe",
                  "telegram.exe", "slack.exe", "ms-teams.exe", "teams.exe", "outlook.exe", "olk.exe", "signal.exe",
                  "messenger.exe", "thunderbird.exe", "skype.exe", "element.exe", "zoom.exe", "mailspring.exe",
                  "hxoutlook.exe"}
BROWSERS = {"brave.exe", "chrome.exe", "msedge.exe", "firefox.exe", "opera.exe", "opera_gx.exe", "vivaldi.exe",
            "arc.exe", "iexplore.exe"}
MESSAGING_TITLES = re.compile(
    r"\b(?:gmail|google chat|chat|mail|inbox|outlook|whatsapp|messenger|messages?|instagram|facebook|slack|teams|"
    r"discord|telegram|linkedin|twitter|reddit|proton ?mail|yahoo|compose|dm|direct)\b|\bx\.com\b|/ x\b", re.I)
# Browser pages where Enter or a click can buy, pay, or change an account.
RISKY_PAGES = re.compile(r"\b(?:checkout|check out|cart|basket|payment|pay|paypal|bank|banking|billing|order|purchase|"
                         r"transfer|wallet|account|security|password|settings|delete)\b", re.I)
TERMINALS = {"cmd.exe", "powershell.exe", "pwsh.exe", "windowsterminal.exe", "wt.exe", "conhost.exe",
             "openconsole.exe", "mintty.exe", "bash.exe", "wsl.exe", "putty.exe", "alacritty.exe", "wezterm-gui.exe",
             "powershell_ise.exe"}
# Words on a button or link that mean clicking it does something you can't take back.
RISKY_CLICK = re.compile(
    r"\b(?:send|post|submit|publish|tweet|reply|forward|share|delete|remove|erase|trash|bin|discard|empty|wipe|"
    r"format|uninstall|install|buy|purchase|pay|payment|checkout|check out|order|subscribe|unsubscribe|donate|"
    r"transfer|withdraw|confirm|accept|agree|approve|allow|grant|sign out|log out|logout|sign off|leave|kick|ban|"
    r"block|report|reset|overwrite|deactivate|cancel (?:my |the )?(?:subscription|order|account|plan))\b", re.I)

_lock = threading.RLock()
_current = None                 # the Request waiting for an answer
_local = threading.local()      # per thread: unattended, outcome, skipped, should_stop
_stops = [0]                    # bumped by every stop / panic, so work that started earlier can tell


def cfg():
    return (svc.config or {}).get("safety") or {}


# ── Who is asking ────────────────────────────────────────────────────────────

@contextmanager
def context(unattended=False, skipped=None, should_stop=None):
    """Mark everything run on this thread inside the block as started by the user or not (scheduled). should_stop
    (a macro's abort) ends any wait for an answer inside it."""
    old = (getattr(_local, "unattended", False), getattr(_local, "skipped", None), getattr(_local, "should_stop", None))
    _local.unattended, _local.skipped, _local.should_stop = bool(unattended), skipped, should_stop
    try:
        yield
    finally:
        _local.unattended, _local.skipped, _local.should_stop = old


def stops():
    """How many times the user has said stop (or panicked) so far: compare before and after slow work."""
    return _stops[0]


def stopping():
    """True if the macro running this thread has been told to stop."""
    should_stop = getattr(_local, "should_stop", None)
    return bool(should_stop and should_stop())


def unattended():
    """True while running something nobody is here to answer for (a scheduled command or macro)."""
    return getattr(_local, "unattended", False)


def last_outcome():
    """What happened to the last big step on this thread: asked, approved, cancelled, expired, replaced, aborted,
    skipped, or "" if there wasn't one."""
    return getattr(_local, "outcome", "")


def reset_outcome():
    _local.outcome = ""


def skip(title):
    """A big step with nobody here to OK it: don't do it, and keep a note for the report."""
    _local.outcome = "skipped"
    skipped = getattr(_local, "skipped", None)
    if skipped is not None:
        skipped.append(title)
    text = "I skipped “%s” because nobody was here to OK it." % title
    log.info("Skipped big step (unattended): %s", title)
    if threading.current_thread().name == "assistant":
        notify("Skipped", text, speak=False)        # a scheduled command: show it, kept for "while you were away"
    return text


# ── What counts as a big step ────────────────────────────────────────────────

def window_kind(hwnd):
    """"messaging", "risky page", "terminal", "files" or "" for the app that owns a window."""
    proc = window_process_name(hwnd)
    if proc in MESSAGING_APPS:
        return "messaging"
    if proc in BROWSERS and MESSAGING_TITLES.search(window_title(hwnd) or ""):
        return "messaging"
    if proc in BROWSERS and RISKY_PAGES.search(window_title(hwnd) or ""):
        return "risky page"
    if proc in TERMINALS:
        return "terminal"
    cls = window_class(hwnd)
    if cls == "#32770" and re.match(r"(?:delete|permanently delete|confirm (?:file|folder|multiple file) delete)",
                                    window_title(hwnd) or "", re.I):
        return "delete dialog"
    if proc == "explorer.exe":
        if cls == "#32770" and (window_title(hwnd) or "").lower() == "run":
            return "terminal"
        if cls in ("CabinetWClass", "ExploreWClass", "Progman", "WorkerW"):
            return "files"                       # File Explorer and the desktop
    return ""


def big_key(chord, hwnd):
    """What pressing these keys in this window would do if it's a big step ("send what's typed"), else None."""
    keys = [k for k in chord if k]
    main = keys[-1] if keys else ""
    mods = set(keys[:-1])
    kind = window_kind(hwnd)
    if kind == "messaging" and main == "enter" and "shift" not in mods:
        return "Send what's typed"
    if kind == "messaging" and keys in (["alt", "s"], ["ctrl", "shift", "s"]):
        return "Send what's typed"
    if kind == "terminal" and main == "enter":
        return "Run the command that's typed"
    if kind == "risky page" and main == "enter":
        return "Press Enter on %s" % (window_title(hwnd) or "this page")[:60]
    if kind == "files" and (main == "delete" or keys == ["ctrl", "d"]):
        return "Delete the selected files" + (" for good" if "shift" in mods else "")
    if kind == "delete dialog" and (main in ("enter", "space") or keys in (["y"], ["alt", "y"])):
        return "Confirm deleting the files"
    if main == "delete" and mods >= {"ctrl", "shift"}:
        return "Clear browsing data"
    return None


def big_click(description, hwnd, at_position=False):
    """What a click would do if it's a big step, else None. A click at a recorded position in a chat or email app
    counts, because it could be the Send button."""
    if description and RISKY_CLICK.search(description):
        return "Click %s" % description
    kind = window_kind(hwnd) if at_position else ""
    if kind == "messaging":
        return "Click in %s (it could send something)" % (window_process_name(hwnd).replace(".exe", "").capitalize()
                                                         or "this app")
    if kind == "risky page":
        return "Click on %s" % (window_title(hwnd) or "this page")[:60]
    if kind in ("files", "delete dialog"):
        return "Click in %s (it could delete something)" % ("File Explorer" if kind == "files" else "the delete box")
    return None


# ── Phrases ──────────────────────────────────────────────────────────────────

def phrases():
    return [re.sub(r"[^a-z' ]", "", p.lower()).strip() for p in (cfg().get("confirm_phrases") or DEFAULT_PHRASES)
            if p and p.strip()] or DEFAULT_PHRASES


def is_phrase(plain):
    """Any of the approval phrases (also "yes, send it", "send it now")."""
    return any(_says(plain, p) for p in phrases())


def _says(plain, phrase):
    return plain in (phrase, "yes " + phrase, "yeah " + phrase, "ok " + phrase, "okay " + phrase, phrase + " now",
                     "yes " + phrase + " now")


def _phrase_for(kind):
    """The phrase that approves a "send it" or "confirm" step, as set in settings."""
    ps = phrases()
    return kind if kind in ps else ps[0] if kind == "send it" else ps[-1]


def _name_needed():
    from . import voiceprint
    from .state import ALWAYS_LISTENING
    return bool(cfg().get("name_needed_without_voice_lock", True)) and svc.state is not None and \
        svc.state.effective_mode == ALWAYS_LISTENING and not voiceprint.ready()


def _say_it(phrase):
    return ("Gem, " + phrase) if _name_needed() else phrase


def hint(kind="send it"):
    """The exact instruction for the card, matching what hear() will accept right now."""
    return "Say “%s” to %s · “cancel” to stop" % (_say_it(_phrase_for(kind)), "send" if kind == "send it" else
                                                  "go ahead")


# ── Requests ─────────────────────────────────────────────────────────────────

class Request:
    def __init__(self, title, run, data, kind, on_cancel, blocking):
        self.title, self.run, self.data, self.kind = title, run, data, kind
        self.phrase = _phrase_for(kind)     # the one phrase that approves this request
        self.on_cancel = on_cancel          # () -> sentence to add when it doesn't happen
        self.blocking = blocking            # a macro thread is waiting on it
        self.created = time.time()
        self.done = threading.Event()
        self.approved = False
        self.reason = ""

    def finish(self, approved, reason=""):
        global _current
        with _lock:
            if self.done.is_set():
                return False
            self.approved, self.reason = approved, reason or ("approved" if approved else "cancelled")
            self.done.set()
            if _current is self:
                _current = None
        log.info("Big step %r: %s", self.title, self.reason)
        return True

    def not_done_note(self):
        lead = {"expired": "I didn't hear “%s”, so I didn't do it." % self.phrase,
                "replaced": "Something else came up, so I didn't do it."}.get(self.reason, "Okay, I didn't do it.")
        if self.kind == "send it":
            lead = lead.replace("didn't do it", "didn't send it")
        extra = ""
        if self.on_cancel:
            try:
                extra = self.on_cancel() or ""
            except Exception:
                log.exception("Cancel note failed")
        return (lead + " " + extra).strip()

    def go(self):
        """Do the big step (after approval). Returns what to say (a Failure if it didn't happen)."""
        try:
            return self.run()
        except ActionError as e:
            return Failure(str(e))
        except Exception:
            log.exception("Big step %r failed", self.title)
            return Failure("Sorry, that didn't work.")


def current():
    with _lock:
        req = _current
    if req is not None and req.done.is_set():
        return None
    return req


def ask(title, run, *, app="", to="", subject="", message="", lines=None, warning="", phrase="send it", chip=None,
        on_cancel=None, should_stop=None):
    """Ask before a big step and only do it (run()) once the user says the phrase. phrase is "send it" for sending
    and "confirm" for everything else (the user's own phrases from settings are shown).

    On the assistant thread this returns the question (with its card) at once; run() happens when the user answers.
    On any other thread (a macro) it waits for the answer and returns run()'s result, or a note that it didn't happen.
    last_outcome() tells which. When unattended, nothing is asked: the step is skipped."""
    global _current
    if unattended():
        return skip(title)
    kind = "send it" if phrase == "send it" else "confirm"
    seconds = float(cfg().get("confirm_seconds", 45) or 45)
    data = {"title": title, "app": app, "to": to, "subject": subject, "message": message, "lines": list(lines or []),
            "warning": warning, "hint": hint(kind), "seconds": seconds,
            "chip": chip or ("Send it" if kind == "send it" else "Confirm")}
    blocking = threading.current_thread().name != "assistant"
    should_stop = should_stop or getattr(_local, "should_stop", None)
    req = Request(title, run, data, kind, on_cancel, blocking)
    with _lock:
        old, _current = _current, req
    if old is not None and old.finish(False, "replaced") and not old.blocking and \
            (old.title, old.data.get("to")) != (title, to):            # a revised draft replaces its own quietly
        caption(old.not_done_note(), seconds=3)
    _local.outcome = "asked"
    timer = threading.Timer(seconds, _expire, args=(req,))
    timer.daemon = True
    timer.start()
    question = _question(title, app, to, req)
    if not blocking:
        return card("approve", question, **data)
    say(question, card=dict(data, kind="approve"))
    while not req.done.wait(0.2):
        if should_stop and should_stop():
            req.finish(False, "aborted")
    _local.outcome = req.reason
    if req.approved:
        return req.go()
    return req.not_done_note()


def _question(title, app, to, req):
    # Spoken. It never ends with the phrase itself: push-to-talk keeps a moment of sound from before the key press.
    where = (" to %s" % to) if to and len(to) <= 40 else ""
    on = (" on %s" % app) if app and app.lower() not in title.lower() else ""
    if req.kind == "send it":
        return "Ready to send%s%s. Say %s when it looks right, or cancel." % (where, on, _say_it(req.phrase))
    return "%s%s? Say %s when you're sure, or cancel." % (title.rstrip(".?"), on, _say_it(req.phrase))


def _expire(req):
    if not req.finish(False, "expired"):
        return
    if not req.blocking:
        say(req.not_done_note())


def cancel(reason="cancelled"):
    """Stop or panic: drop the waiting request, if any, and let slow work that started earlier know. Returns True if
    a request was waiting."""
    _stops[0] += 1
    req = current()
    return bool(req and req.finish(False, reason))


# ── Answers ──────────────────────────────────────────────────────────────────

def trusted(item, by_name, phrase="send it"):
    """(ok, why not) for whether an utterance can approve a big step: it must really be the user."""
    if getattr(item, "unattended", False):
        return False, ""
    if not item.audio:
        return item.source == "typed", ""
    from . import voiceprint
    from .skills import voice_id
    ptt = item.source == "ptt"
    if voiceprint.ready():
        ok, score = voiceprint.check(item.audio, voice_id.base_threshold())
        if ok or (ptt and score is None):           # too short to judge, but you're holding Caps Lock
            return True, ""
        if score is None:
            return False, "I couldn't tell it was you from that. Hold Caps Lock and say it, or say it a bit longer."
        return False, "That didn't sound like you, so I'm still waiting."
    if ptt or not _name_needed() or by_name:
        return True, ""
    return False, "Say “Gem, %s” so I know it's you and not a video, or hold Caps Lock and say it." % phrase


def _started(item):
    """When the user started saying (or sent) it: the clip ends after a pause, so count back its length."""
    return item.created - (len(item.audio) / 2 / 16000.0 if item.audio else 0.0)


def hear(item, plain, by_name, other_pending=False):
    """Handle an utterance while a big step is waiting. Returns what to say, or None if it isn't an answer."""
    req = current()
    if req is None or getattr(item, "unattended", False):
        return None
    if plain in CANCEL:
        if not req.finish(False, "cancelled"):
            return None
        if req.blocking:
            caption("Cancelled.", seconds=2)
            return ""
        return req.not_done_note()
    if is_phrase(plain):
        if _started(item) < req.created + 0.3:
            return None                              # started before this question was asked: meant for another
        if not _says(plain, req.phrase):
            return _again(req, "This one needs %s. Or say cancel." % _say_it(req.phrase))
        ok, why = trusted(item, by_name, req.phrase)
        if not ok:
            log.info("Big step %r: refused an answer (%s)", req.title, why or "not the user")
            return _again(req, why) if why else None
        if not req.finish(True):
            return None
        if req.blocking:
            caption("Okay.", seconds=1.5)
            return ""
        return req.go()
    if plain in NOT_ENOUGH and not other_pending:
        return _again(req, "To go ahead, say %s. Or say cancel." % _say_it(req.phrase))
    return None


def _again(req, text):
    """The request's card again (it may have been dismissed), for however long it has left."""
    left = max(5.0, req.created + req.data["seconds"] - time.time())
    return card("approve", text, **dict(req.data, seconds=left, hint=hint(req.kind)))
