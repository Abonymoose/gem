"""Reply mode: away notes and reply drafts.

Gem types the text into the message box you're in. You press Enter, or, in chat
and email apps Gem knows, say "send it" and Gem sends it (messaging.offer_send,
which checks it's still the same chat first).

- Away note: "I'm stepping away for 30 minutes", then "tell them I'm away" types
  "<name> isn't here right now, this is his voice assistant speaking. He'll be
  back in about 25 minutes."
- Drafts: copy or select the conversation, click in the reply box and say
  "reply to this". Gem writes a reply that sounds like you. "Make it shorter",
  "more casual" or "try again" rewrite it in place.
"""
import logging
import math
import re
import time

from ..actions import ActionError, action
from ..cards import card
from . import messaging
from ..parse import duration_phrase, parse_duration, parse_when
from ..runtime import svc
from ..winapi import copy_selection, foreground_window, get_clipboard, press, release_modifiers, set_clipboard

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
    return messaging.offer_send(text, "away note") or \
        card("draft", "Typed your away note. Press Enter to send it.", note=text, title="Away note")


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
    return messaging.offer_send(draft) or \
        card("draft", "Draft is in the box. Press Enter to send, or tell me to change it.", note=draft,
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
    return messaging.offer_send(draft) or \
        card("draft", "Updated. Press Enter to send.", note=draft, title="Reply draft")


def recent_draft():
    return bool(_last["draft"]) and time.time() - _last["at"] < 600


# ── Emails to school staff ───────────────────────────────────────────────────

EMAIL_RULES = """# EMAIL RULES

You write and rewrite emails for me. I am a student writing to school staff, so I am **junior to the recipient**. Follow every rule below exactly.

## 1. TONE
1. **Short.** The body is usually 2 to 4 lines. Long emails get trimmed.
2. **Formal but simple.** Plain, natural wording.
3. **Never** use "May I please...", "I would like to request...", "Could we...", or "I would need...". Use a direct question instead, e.g. "Can we meet on Thursday during Period 5?"
4. **Never sound bossy.** No instructions, no hard deadlines, no "please let me know by...". If timing matters, give a light hint only.

## 2. STRUCTURE
5. **Greeting:** "Dear <Name> Sir," or "Dear <Name> Ma'am," for one person. "Dear All," for a group.
6. **One courtesy line at the start** (e.g. "I hope you are doing well." or "Thank you for getting back to me."). Never two at the start.
7. Then the **ask or the information**. One ask per email.
8. **One courtesy line at the end:** "Thank you for your time and support."
9. **Sign-off:** "Regards," then "Parshv Mehta".
10. No other padding or filler.

## 3. SUBJECT
11. **Replying on a thread:** "Re: <original subject>". **New email:** short and plain.

## 4. CONTENT
12. **Use only what I gave you.** Never invent times, dates, rooms, names or promises.
13. **Don't add detail** I didn't include.
14. If something essential is missing, **ask me one short question** instead of guessing.

## 5. HUMAN VOICE
15. Write the way a **school student** writes: plain words, short sentences, simple structure.
16. **No** em dashes, semicolons or exclamation marks.
17. **No** bullet points, bold, headers or emojis **inside the email**. Plain text only.
18. Never use stock AI or corporate phrases: "I hope this email finds you well", "I wanted to reach out", "kindly", "touch base", "circle back", "at your earliest convenience", "do not hesitate to", "I would be grateful", "delve", "streamline", "ensure", "moreover", "furthermore".
19. **No** lists of three, and no "not only... but also".
20. **Don't smooth my wording** into something nicer than I would write. If my sentence is plain and correct, leave it.

## 6. REWRITING MY DRAFTS
21. **Keep my meaning and my wording** as much as possible. Change only what breaks a rule above.
22. If my draft **already follows the rules**, say it's fine and don't rewrite it.

## 7. SORTING
23. If more than one person is CC'd, **remind me to reply-all.**

## 8. OUTPUT
24. Output **only the email** (subject + body). One version. No explanation unless I ask.
"""

EMAIL_ASK = EMAIL_RULES + (
    "\nYou get my email, and maybe a request (a change, or my answer to your question). Always write the email "
    "first, even when unsure: never ask instead of writing. With a request, start from my email and change only what "
    "the request is about, keeping everything else it says; capitalize names properly, and don't ask about anything "
    "my request already answered. Before replying, check the body again: exactly one ask, said once as one plain "
    "question (\"Can you tell me...\", not \"Can we have confirmation...\"; no second line like \"Please let me "
    "know your availability\"); the ask names each thing once, plainly, without \"including ...\", examples or other "
    "side details (\"the student data, including parent emails\" becomes \"the student data\"); no "
    "instructions; no deadline, day or time to reply by, at most a vague hint like \"this week\". Reply with JSON "
    "only: {\"fine\": true only if my draft "
    "already follows every rule and there's no request (then subject and body are empty), \"subject\": \"...\", "
    "\"body\": \"greeting to sign-off, plain text, lines separated by \\n\", \"question\": \"one short question about "
    "anything essential that's missing or unclear (a greeting without the person's name always is), or empty\", "
    "\"reply_all\": true if more than one person is CC'd}")

_email = {"text": "", "at": 0.0, "hwnd": 0, "with_subject": False, "group": False, "reply_all": False}


def _people(text, field):
    """Names on a "To:" or "CC:" line of the selected email."""
    m = re.search(r"^%s\s*:\s*(.+)$" % field, text, re.I | re.M)
    return [p for p in re.split(r"[,;]|\band\b", m.group(1)) if p.strip()] if m else []


@action("email_rewrite", "Rewrite the selected email to school staff by the user's email rules and paste it over "
        "the selection. Also for the user's answer to Gem's question about that email, or a change to it.",
        "instruction?: str")
def email_rewrite(instruction=""):
    hwnd = foreground_window()
    text = (copy_selection() or "").strip()
    # Nothing selected right after a rewrite: it's an answer or a change, for the email Gem just pasted.
    again = not text and _email["text"] and time.time() - _email["at"] < 600 and hwnd == _email["hwnd"]
    text = _email["text"] if again else text
    if not text:
        raise ActionError("Select the email first, then ask me again.")
    request = "My email:\n%s%s" % (text[:MAX_CONTEXT], "\n\nRequest: %s" % instruction if instruction else "")
    out = svc.brain.complete(EMAIL_ASK, request, max_tokens=900, json_mode=True, temperature=0.3) or {}
    question = (out.get("question") or "").strip()
    if out.get("fine") or not (out.get("body") or "").strip():
        return ("That email already follows your rules, so I left it. " + question).strip()
    if again:
        with_subject, group, reply_all = _email["with_subject"], _email["group"], _email["reply_all"]
    else:
        # Selected with its subject line: it gets one back. Just the body (a compose box): the subject's on the card.
        with_subject = bool(re.search(r"^subject\s*:", text, re.I | re.M))
        cc = _people(text, "cc")
        group, reply_all = len(_people(text, "to")) + len(cc) > 1, len(cc) > 1 or bool(out.get("reply_all"))
    lines = [line.strip() for line in out["body"].splitlines() if line.strip()]
    if group and lines[0].startswith("Dear "):
        lines[0] = "Dear All,"                                               # rule 5: a group
    body = "\n\n".join(lines).replace("Regards,\n\n", "Regards,\n")         # a blank line between the parts
    subject = (out.get("subject") or "").strip()
    email = ("Subject: %s\n\n" % subject if subject else "") + body
    _email.update(text=email, at=time.time(), hwnd=hwnd, with_subject=with_subject, group=group, reply_all=reply_all)
    if not question and re.match(r"Dear (?:Sir|Ma'am),", body):
        question = "What's their name, for the greeting?"                     # never guessed (rule 12)
    spoken = "Rewritten." + (" The subject's on the card." if subject and not with_subject else "")
    if reply_all:
        spoken += " More than one person is CC'd, so reply all."
    paste = email if with_subject else body
    if foreground_window() != hwnd:
        set_clipboard(paste)
        spoken = "You switched windows, so it's on your clipboard instead. " + spoken
    else:
        _put_in_box(paste, replace=again)
    return card("draft", (spoken + " " + question).strip(), note=email, title="Email")
