"""Auto memory: lasting facts you mention in conversation ("I main Jett", "my exam is on Friday") are
remembered without saying "remember that". Commands are skipped, and a small toast shows what was noted.
"""
import logging
import re
import threading
import time

from .runtime import caption, svc

log = logging.getLogger("gem.automemory")

FIRST_PERSON = re.compile(r"\b(?:i|i'm|im|i've|ive|i'd|my|mine|me|we|we're|our)\b", re.I)
# Actions after which the words were a command, not a conversation.
CHATTY = {"web_answer", "picks", "wikipedia", "explain_screen"}
INSTRUCTION = """From what {name} just said, pull out lasting personal facts worth remembering for the future:
preferences, favourite things, games they play and how, people in their life (names and who they are), hobbies,
school or work details, and upcoming plans with dates. Ignore requests, questions, moods and anything temporary.
Write each fact as a short plain sentence about {name} (e.g. "Mains Jett in Valorant."). Today is {today}; turn
relative dates into real dates. Skip anything already known.
Already known: {known}
Reply JSON only: {{"facts": []}} with at most 2 facts, usually none."""

_last = {"t": 0.0}


def consider(text, action_names, source):
    """Called after every exchange; does its work in the background."""
    if not (svc.config.get("auto_memory", True) and svc.brain and svc.brain.available()):
        return
    if source not in ("ptt", "typed", "open") or svc.brain.speaker:
        return                                        # someone else talking: not facts about you
    words = text.split()
    if len(words) < 5 or not FIRST_PERSON.search(text):
        return
    if action_names and not set(action_names) <= CHATTY:
        return
    if time.time() - _last["t"] < 20:                 # at most one check every 20 seconds
        return
    _last["t"] = time.time()
    threading.Thread(target=_extract, args=(text,), daemon=True).start()


def _extract(text):
    import datetime
    from .skills.productivity import memory
    known = memory.data.get("facts") or []
    try:
        out = svc.brain.complete(
            INSTRUCTION.format(name=svc.config.get("user_name") or "the user", known="; ".join(known[-40:]) or "nothing",
                               today=datetime.date.today().strftime("%A %B %d, %Y")),
            text, max_tokens=200, json_mode=True, temperature=0.1,
            models=["openai/gpt-oss-20b", "qwen/qwen3.8-27b"])
    except Exception as e:
        log.debug("Auto memory skipped: %s", e)
        return
    facts = [str(f).strip().rstrip(".") for f in (out or {}).get("facts") or [] if str(f).strip()][:2]
    lower = {k.lower() for k in known}
    new = [f for f in facts if f.lower() not in lower and len(f) > 6]
    if not new:
        return
    with memory as data:
        data["facts"].extend(new)
        del data["facts"][:-200]
    log.info("Auto memory: %s", new)
    st = svc.state
    if not (st.in_call or st.gaming):
        caption("Noted: " + new[0][:44].rstrip(), seconds=2.5)
