"""Working with text: selection and clipboard tools, typing, and dictation."""
import logging
import re
import time

from .. import safety
from ..actions import ActionError, action
from ..cards import card
from ..runtime import svc
from ..winapi import (copy_selection, foreground_window, get_clipboard, paste_text, press, release_modifiers,
                      set_clipboard, type_plain, type_text)

log = logging.getLogger("gem.text")

MAX_CHARS = 9000


def _source_text(source):
    if source == "clipboard":
        text = get_clipboard()
    else:
        text = copy_selection()
        if not text.strip() and source == "auto":
            text = get_clipboard()
    text = (text or "").strip()
    if not text:
        raise ActionError("Select some text first, or copy it to the clipboard.")
    return text[:MAX_CHARS]


@action("text_tool", "Work on the selected text (or clipboard).", "task: summarize|explain|rewrite|fix_grammar|shorten|translate|reply|custom, instruction?: str, source?: selection|clipboard, output?: speak|replace|clipboard")
def text_tool(task="summarize", instruction="", source="auto", output=None):
    if task in ("summarize", "explain") and source in ("auto", "selection", None, ""):
        # Nothing selected: "explain this" most likely means what's on screen, not an old clipboard.
        text = (copy_selection() or "").strip()
        if not text:
            from .screen import explain_screen
            return explain_screen(instruction or ("Explain what's on screen simply." if task == "explain"
                                                  else "Summarize what's on screen."))
        return _text_task(task, instruction, text[:MAX_CHARS], output)
    return _text_task(task, instruction, _source_text(source), output)


def _text_task(task, instruction, text, output):
    prompts = {
        "summarize": "Summarize this for someone listening, in two or three plain sentences.",
        "explain": "Explain this simply in two to four plain sentences for someone listening.",
        "rewrite": "Rewrite this text. Keep the meaning and the original language unless told otherwise.",
        "fix_grammar": "Fix spelling, grammar and punctuation. Change nothing else.",
        "shorten": "Make this text noticeably shorter while keeping the key points.",
        "translate": "Translate this text.",
        "reply": "Write a reply to this message in the same language and a matching tone.",
        "custom": "Follow the instruction for this text.",
    }
    base = prompts.get(task, prompts["custom"])
    spoken = task in ("summarize", "explain")
    if output is None:
        output = "speak" if spoken else ("clipboard" if task == "reply" else "replace")
    rules = " Output only the result, with no preamble or quotes." if output != "speak" else \
        " No markdown or lists; it will be read aloud."
    prompt = base + (" Instruction: %s." % instruction if instruction else "") + rules
    result = svc.brain.complete(prompt, text, max_tokens=900)
    if output == "speak":
        return result
    if output == "clipboard":
        set_clipboard(result)
        return "Done, it's on your clipboard."
    if safety.paste_runs(result, foreground_window()):
        raise ActionError("Pasting that here would run it, so it's on your clipboard instead.")
    paste_text(result)
    return None


def count_text(text):
    """Words, characters (with and without spaces), sentences, paragraphs and minutes to read."""
    words = len(re.findall(r"[^\W_]+(?:['’.-][^\W_]+)*", text))
    return {"words": words, "chars": len(text), "chars_no_spaces": len(re.sub(r"\s", "", text)),
            "sentences": len(re.findall(r"[^.!?]*[^\W_][^.!?]*(?:[.!?]+|$)", text.strip())),
            "paragraphs": len([p for p in re.split(r"\n\s*\n", text) if p.strip()]),
            "read_minutes": words / 230.0}


@action("text_stats", "Word count (and characters, reading time) of the selected text or clipboard. Local.",
        "source?: selection|clipboard")
def text_stats(source="auto"):
    text = copy_selection() if source != "clipboard" else ""
    if not (text or "").strip() and source in ("auto", "clipboard", None, ""):
        text = get_clipboard()
    text = (text or "").strip()
    if not text:
        raise ActionError("Select some text first, or copy it.")
    c = count_text(text)
    n = "{:,}".format(c["words"])
    words = "%s word%s" % (n, "" if c["words"] == 1 else "s")
    reading = "under a minute to read" if c["read_minutes"] < 1 else "about %d minute%s to read" % (
        round(c["read_minutes"]), "" if round(c["read_minutes"]) == 1 else "s")
    detail = "{:,} characters ({:,} without spaces)".format(c["chars"], c["chars_no_spaces"])
    if c["paragraphs"] > 1:
        detail += ", %d paragraphs" % c["paragraphs"]
    return card("calc", "%s, %s, %s." % (words.capitalize(), detail, reading),
                expression="%s · %s" % (detail, reading), result=words)


def spell_out(word):
    """'necessary' -> 'N, E, C, E, double S, A, R, Y'."""
    letters, out, i = [ch for ch in word if ch.isalpha() or ch in "'-"], [], 0
    while i < len(letters):
        ch = letters[i]
        if ch == "'":
            out.append("apostrophe")
        elif ch == "-":
            out.append("hyphen")
        elif i + 1 < len(letters) and letters[i + 1].lower() == ch.lower():
            out.append("double " + ch.upper())
            i += 1
        else:
            out.append(ch.upper())
        i += 1
    return ", ".join(out)


@action("spell", "Spell a word out letter by letter.", "word: str")
def spell(word=""):
    word = (word or "").strip(" .?!\"")
    if not word or len(word) > 40:
        raise ActionError("Which word?")
    words = word.split()
    spoken = "; ".join(spell_out(w) for w in words)
    return card("calc", "%s is spelled %s." % (word[:1].upper() + word[1:], spoken), expression="How to spell it",
                result=" ".join(w.upper() for w in words) if len(word) <= 18 else word)


@action("type_text", "Type text into the focused app. Never sends: to send a message use send_message.", "text: str")
def type_into_app(text=""):
    if not text:
        raise ActionError("What should I type?")
    hwnd = foreground_window()
    if safety.window_kind(hwnd) == "delete dialog":
        raise ActionError("The box asking to delete files is in front, so I didn't type there.")
    release_modifiers()
    _type(text, hwnd)
    return None


@action("read_clipboard", "Read the clipboard text aloud.", ai=False)
def read_clipboard():
    text = get_clipboard().strip()
    if not text:
        return "The clipboard is empty."
    return text[:600] + ("..." if len(text) > 600 else "")


# ── Dictation ────────────────────────────────────────────────────────────────

_last_chunk = ""

STOP_WORDS = {"stop dictation", "stop dictating", "end dictation", "done dictating", "finish dictation",
              "stop typing", "dictation off", "that's it", "done"}
ENTER_WORDS = {"press enter", "send it"}     # the assistant checks it's really you first


@action("dictation", "Dictation mode on/off.", "on: bool")
def dictation(on=True):
    svc.state.update(dictating=bool(on))
    if on:
        return "Dictation on. Say stop dictation when you're done."
    return "Dictation off."


def _enter_is_big(hwnd):
    """Enter here sends, runs or submits something (a chat, a terminal, a checkout page...)."""
    return safety.big_key(["enter"], hwnd) is not None


def _type(text, hwnd):
    """Where Enter would send, run or submit, a line break is never Enter: Shift+Enter in chats, a space elsewhere."""
    if _enter_is_big(hwnd):
        type_plain(text, soft_newlines=safety.window_kind(hwnd) == "messaging")
    else:
        type_text(text)


def handle_dictation(text):
    """Called by the assistant for every utterance while dictating."""
    global _last_chunk
    plain = re.sub(r"[^a-z' ]+", "", text.lower()).strip()
    if plain in STOP_WORDS:
        svc.state.update(dictating=False)
        return "Dictation off."
    if plain in ("delete that", "scratch that", "undo that"):
        if _last_chunk:
            release_modifiers()
            for _ in range(len(_last_chunk)):
                press("backspace")
            _last_chunk = ""
        return None
    hwnd = foreground_window()
    if plain in ("new line", "next line", "new paragraph", "next paragraph"):
        if _enter_is_big(hwnd) and safety.window_kind(hwnd) != "messaging":
            return "That would press Enter here. Say press enter if you mean it."
        _type("\n" if plain.endswith("line") else "\n\n", hwnd)
        return None
    if plain in ENTER_WORDS:
        press("enter")
        return None
    chunk = re.sub(r"\s*\b(new line|next line)\b\s*", "\n", text, flags=re.I)
    chunk = re.sub(r"\s*\b(new paragraph)\b\s*", "\n\n", chunk, flags=re.I)
    chunk = chunk.strip() + " "
    release_modifiers()
    _type(chunk, hwnd)
    _last_chunk = chunk
    time.sleep(0.05)
    return None
