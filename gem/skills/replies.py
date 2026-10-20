"""Reply mode: away notes and reply drafts.

Gem never sends anything itself. It types the text into the message box you're
in and you press Enter.

- Away note: "I'm stepping away for 30 minutes", then "tell them I'm away" types
  "<name> isn't here right now, this is his voice assistant speaking. He'll be
  back in about 25 minutes."
- Drafts: copy or select the conversation, click in the reply box and say
  "reply to this". Gem writes a reply that sounds like you. "Make it shorter",
  "more casual" or "try again" rewrite it in place.
"""
import logging
import math
import time

from ..actions import ActionError, action
from ..cards import card
from ..parse import duration_phrase, parse_duration, parse_when
from ..runtime import svc
from ..winapi import copy_selection, get_clipboard, press, release_modifiers, set_clipboard

log = logging.getLogger("gem.replies")

MAX_CONTEXT = 6000
DEFAULT_AWAY = "{name} isn't here right now, this is his voice assistant speaking. He'll be back {when}."

_last = {"conversation": "", "draft": "", "at": 0.0}


def _name():
    return svc.config.get("user_name") or "He"


def _when():
    until = svc.state.away_until
    if not until or until == math.inf:
        return "soon"
    left = until - time.time()
    if left <= 60:
        return "any minute now"
    if left > 2 * 3600:
        return "at " + time.strftime("%I:%M %p", time.localtime(until)).lstrip("0")
    minutes = int(round(left / 60.0))
    if minutes > 10:
        minutes = int(round(minutes / 5.0) * 5)
    return "in about " + duration_phrase(minutes * 60)


def _put_in_box(text, replace=False):
    """Paste into the focused message box and leave it on the clipboard as a backup."""
    set_clipboard(text)
    release_modifiers()
    if replace:
        press("ctrl", "a")
        time.sleep(0.05)
    press("ctrl", "v")


# ── Away ─────────────────────────────────────────────────────────────────────

@action("away_start", "Mark the user as away (for minutes or until a time) so away notes say when he's back.",
        "minutes?: number, until?: str")
def away_start(minutes=None, until=None):
    at = None
    if minutes:
        try:
            at = time.time() + float(minutes) * 60
        except (TypeError, ValueError):
            secs = parse_duration(str(minutes))
            at = time.time() + secs if secs else None
    if at is None and until:
        dt, _ = parse_when(str(until))
        at = dt.timestamp() if dt else None
    svc.state.update(away_until=at or math.inf)
    when = _when()
    return card("alarm", "Got it, you're away. I'll say you're back %s." % when if at else "Got it, you're away.",
                title="Away", at=at or time.time(), subtitle="Say \"tell them I'm away\" in a chat")


@action("away_end", "The user is back; stop saying he's away.")
def away_end():
    was = bool(svc.state.away_until)
    svc.state.update(away_until=0.0)
    return "Welcome back." if was else "You weren't marked as away."


@action("away_note", "Type the away note into the message box the user is in (he presses Enter).")
def away_note():
    template = svc.config.get("away_message") or DEFAULT_AWAY
    text = template.format(name=_name(), when=_when())
    _put_in_box(text)
    return card("draft", "Typed your away note. Press Enter to send it.", note=text, title="Away note")


# ── Drafts ───────────────────────────────────────────────────────────────────

def _conversation():
    text = copy_selection() or get_clipboard()
    text = (text or "").strip()
    if not text:
        raise ActionError("Copy or select the conversation first, click in the reply box, then ask me again.")
    return text[-MAX_CONTEXT:]


def _write(conversation, instruction=""):
    name = svc.config.get("user_name") or "the user"
    away = ""
    if svc.state.away_until:
        away = " %s is away right now and will be back %s; only mention that if it fits." % (name, _when())
    prompt = ("You write a reply for %s to send in this conversation. Copy how %s writes in it: length, tone, "
              "capitalization, punctuation and slang. Use emoji only if %s uses them in the conversation. If it's an "
              "email, write a proper email body without a subject line. Don't invent plans, promises or facts %s "
              "hasn't stated; keep it non-committal instead.%s Output only the message text, nothing else.%s"
              % (name, name, name, name, away, (" Change requested: %s." % instruction) if instruction else ""))
    text = svc.brain.complete(prompt, conversation, max_tokens=400).strip().strip('"')
    # Plain characters, like someone typing on a keyboard.
    return text.translate({0x202F: " ", 0x00A0: " ", 0x2009: " ", 0x2019: "'", 0x2018: "'", 0x201C: '"', 0x201D: '"'})


@action("reply_draft", "Draft a reply to the copied or selected conversation and type it into the message box "
        "(the user presses Enter).", "instruction?: str")
def reply_draft(instruction=""):
    conversation = _conversation()
    draft = _write(conversation, instruction)
    if not draft:
        raise ActionError("I couldn't come up with a reply.")
    _last.update(conversation=conversation, draft=draft, at=time.time())
    _put_in_box(draft)
    return card("draft", "Draft is in the box. Press Enter to send, or tell me to change it.", note=draft,
                title="Reply draft")


@action("reply_revise", "Rewrite the reply draft Gem just typed (e.g. shorter, more casual, different).",
        "instruction: str")
def reply_revise(instruction="try a different version"):
    if not _last["draft"] or time.time() - _last["at"] > 600:
        raise ActionError("There's no recent draft to change. Say reply to this first.")
    if instruction.lower() in ("try again", "another one", "redo it", "rewrite it", "different one", "change it"):
        instruction = "write a noticeably different version with different wording"
    change = "Previous draft: %s\nNew request: %s" % (_last["draft"], instruction)
    draft = _write(_last["conversation"], change)
    _last.update(draft=draft, at=time.time())
    _put_in_box(draft, replace=True)
    return card("draft", "Updated. Press Enter to send.", note=draft, title="Reply draft")


def recent_draft():
    return bool(_last["draft"]) and time.time() - _last["at"] < 600
