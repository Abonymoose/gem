"""Working with text: selection and clipboard tools, typing, and dictation."""
import logging
import re
import time

from .. import safety
from ..actions import ActionError, action
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
    paste_text(result)
    return None


@action("type_text", "Type text into the focused app. Never sends: to send a message use send_message.", "text: str")
def type_into_app(text=""):
    if not text:
        raise ActionError("What should I type?")
    release_modifiers()
    _type(text, safety.window_kind(foreground_window()) == "messaging")
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


def _type(text, chat):
    """In a chat app a line break would be Enter, which sends: there new lines are Shift+Enter."""
    if chat:
        type_plain(text, soft_newlines=True)
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
    chat = safety.window_kind(foreground_window()) == "messaging"
    if plain in ("new line", "next line", "new paragraph", "next paragraph"):
        _type("\n" if plain.endswith("line") else "\n\n", chat)
        return None
    if plain in ENTER_WORDS:
        press("enter")
        return None
    chunk = re.sub(r"\s*\b(new line|next line)\b\s*", "\n", text, flags=re.I)
    chunk = re.sub(r"\s*\b(new paragraph)\b\s*", "\n\n", chunk, flags=re.I)
    chunk = chunk.strip() + " "
    release_modifiers()
    _type(chunk, chat)
    _last_chunk = chunk
    time.sleep(0.05)
    return None
