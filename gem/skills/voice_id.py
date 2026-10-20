"""Voice lock and family voices: learn who's talking, only respond to the right people, ignore the blocked ones."""
import logging
import random
import threading
import time

from .. import voiceprint
from ..actions import ActionError, action
from ..cards import card
from ..runtime import say, svc
from ..state import PUSH_TO_TALK

log = logging.getLogger("gem.voice_id")

PHRASES = [
    "Hey Gem, what's the weather like this afternoon?",
    "Set a timer for twenty minutes and remind me to stretch.",
    "Open Spotify and play something chill.",
    "What time is it in Tokyo right now?",
    "Add milk, eggs and bread to my shopping list.",
]
CANCEL = {"cancel", "stop", "never mind", "nevermind", "stop training", "cancel training", "quit", "exit"}
RELATIONS = ("sister", "brother", "mom", "mum", "mother", "dad", "father", "friend", "cousin", "grandma", "grandpa",
             "aunt", "uncle", "roommate")

# What Gem says (at most once every 20 minutes) when a blocked person talks to it.
BLOCKED_LINES = [
    "Oh wait, is that {name}? Hi {name}! ... Anyway.",
    "Hey {name}! ... Anyway, where was I.",
    "Oh hi {name}. ... Anyway.",
    "Is that {name}? Hello! ... Okay, anyway.",
]
GREET_EVERY_S = 20 * 60

training = {"step": None, "until": 0.0, "person": None, "relation": None}
_greeted = {}


def cfg():
    return svc.config.get("voice_lock") or {}


def base_threshold():
    return float(cfg().get("threshold", 0.45))


def training_active():
    if training["step"] is not None and time.time() > training["until"]:
        training["step"] = None
    return training["step"] is not None


def display(key):
    p = voiceprint.person(key) or {}
    return p.get("name") or key.title()


def describe(key):
    """'Freya, Parshv's sister' for the AI, so it can answer them by name."""
    p = voiceprint.person(key) or {}
    owner = svc.config.get("user_name") or "the user"
    return "%s, %s's %s" % (display(key), owner, p["relation"]) if p.get("relation") else display(key)


def split_name(text):
    """'my sister Freya' -> ('Freya', 'sister'); 'freya' -> ('Freya', None)."""
    words = (text or "").replace("'s", "").split()
    words = [w for w in words if w.lower() not in ("my", "the", "our", "little", "younger", "older", "big", "baby")]
    relation = next((w.lower() for w in words if w.lower() in RELATIONS), None)
    name = " ".join(w for w in words if w.lower() not in RELATIONS).strip()
    if not name and relation:
        name = relation                         # "block my mom"
    return name.title(), relation


def _how():
    return "Hold Caps Lock and read it out" if svc.state.mode == PUSH_TO_TALK else "Read it out loud"


def _step_card(text, hint=None):
    i = training["step"]
    who = training["person"]
    return card("voice", text, phrase=PHRASES[i], step=i, total=len(PHRASES), hint=hint or _how(),
                person=display(who) if who else None)


def train_step(pcm, plain):
    """One training utterance. Returns what to say/show next."""
    if plain in CANCEL:
        training["step"] = None
        return "Okay, I stopped voice training."
    who = training["person"]
    ok = voiceprint.add_person_audio(who, pcm, training["relation"]) if who else voiceprint.add(pcm, "trained")
    if not ok:
        return _step_card("That was a bit short. Try the whole line.", hint="Say the full sentence at a normal pace")
    training["step"] += 1
    training["until"] = time.time() + 180
    if training["step"] < len(PHRASES):
        return _step_card("Got it. Next one.")
    training["step"] = None
    if who:
        name = display(who)
        blocked = (voiceprint.person(who) or {}).get("blocked")
        tail = " I'll keep ignoring them." if blocked else " Say block %s if you want me to ignore them." % name
        log.info("Learned %s's voice", name)
        return card("voice", "Got it, I know %s's voice now.%s" % (name, tail), done=True, step=len(PHRASES),
                    total=len(PHRASES), person=name)
    voiceprint.set_locked(True)
    log.info("Voice training done (%d samples)", voiceprint.sample_count())
    tail = " Switch to always listening with a triple tap on Caps Lock." if svc.state.mode == PUSH_TO_TALK else ""
    return card("voice", "Got it, I know your voice now. When I'm always listening, I'll only respond to you.%s" % tail,
                done=True, step=len(PHRASES), total=len(PHRASES))


def greet_blocked(key):
    """A blocked person spoke: say hi once in a while, otherwise stay silent."""
    now = time.time()
    if now - _greeted.get(key, 0) < GREET_EVERY_S:
        return
    _greeted[key] = now
    say(random.choice(BLOCKED_LINES).format(name=display(key)))


def learn_async(pcm, who=None):
    """Push-to-talk is you, so it quietly improves your voiceprint (in the background) unless it was someone else."""
    if (not cfg().get("learn_from_push_to_talk", True) or training_active() or not voiceprint.model_ready()
            or who not in (None, "me")):
        return
    threading.Thread(target=voiceprint.add, args=(pcm, "learned", base_threshold()), daemon=True).start()


# ── Actions ──────────────────────────────────────────────────────────────────

@action("voice_train", "Learn a voice with a short read-aloud: the user's own (then only respond to them when always "
        "listening), or a family member's or friend's by name.", "person?: str")
def voice_train(person=""):
    svc.state.update(thinking=True)
    if not voiceprint.ensure_model():
        raise ActionError("I couldn't download the voice model. Check the internet and try again.")
    name, relation = split_name(person) if person and person.lower() not in ("me", "my", "mine") else ("", None)
    training.update(step=0, until=time.time() + 180, person=name.lower() or None, relation=relation)
    if name:
        return _step_card("%s, read these five short lines. Say cancel to stop." % name)
    return _step_card("Let's learn your voice: five short lines. Say cancel to stop.")


@action("voice_lock", "Only respond to the user's own voice when always listening (on), or to anyone (off).", "on: bool")
def voice_lock(on=True):
    if on and not voiceprint.ready():
        return voice_train()
    voiceprint.set_locked(bool(on))
    if on:
        return "Okay. When I'm always listening, I'll only respond to your voice."
    return "Okay, I'll listen to everyone again."


@action("voice_label", "The user says who the last voice Gem heard belonged to, e.g. 'that was my sister Freya'.",
        "person: str")
def voice_label(person=""):
    name, relation = split_name(person)
    if not name:
        raise ActionError("Who was it?")
    if not voiceprint.model_ready():
        raise ActionError("I need to learn voices first. Say learn my voice.")
    n = voiceprint.label_recent(name, relation)
    if not n:
        return "I haven't heard anyone else in the last few minutes."
    blocked = (voiceprint.person(name) or {}).get("blocked")
    if blocked:
        return "Got it, that was %s. I'll keep ignoring them." % name
    return "Got it, that was %s. I'll recognise them now. Say block %s if you want me to ignore them." % (name, name)


@action("voice_block", "Ignore (block) or stop ignoring a family member or friend by voice, e.g. 'block Freya'.",
        "person: str, on?: bool")
def voice_block(person="", on=True):
    name, relation = split_name(person)
    if not name:
        raise ActionError("Who should I ignore?")
    known = voiceprint.set_blocked(name, on, relation)
    if not on:
        return "Okay, I'll listen to %s again." % name
    if known:
        return "Okay, I'll ignore %s." % name
    return ("Okay, I'll ignore %s once I know their voice. Next time they talk, say that was %s, or say learn "
            "%s's voice." % (name, name, name))


@action("voice_people", "List whose voices Gem knows and who is blocked.")
def voice_people():
    ppl = voiceprint.people()
    me = "your voice" if voiceprint.ready() else None
    if not ppl:
        return ("I only know %s so far." % me) if me else "I don't know anyone's voice yet. Say learn my voice."
    rows = []
    for k, p in ppl.items():
        state = "blocked" if p.get("blocked") else "allowed"
        if not p.get("samples"):
            state += ", voice not learned yet"
        rows.append({"name": p.get("name") or k.title(), "relation": p.get("relation") or "", "state": state})
    names = ", ".join("%s (%s)" % (r["name"], r["state"].split(",")[0]) for r in rows)
    return card("people", "I know %s%s." % (("your voice and " if me else ""), names), rows=rows,
                me=bool(me), locked=voiceprint.locked())


@action("voice_status", "Say whether Gem knows the user's voice, if voice lock is on, and who the last speech matched.")
def voice_status():
    n = voiceprint.sample_count()
    if not voiceprint.ready():
        return "I don't know your voice yet. Say learn my voice and read five short lines."
    parts = ["I know your voice from %d samples, and voice lock is %s." % (n, "on" if voiceprint.locked() else "off")]
    last = voiceprint.last
    if last["score"] is not None and time.time() - last["t"] < 600:
        who = last.get("who")
        if who == "me":
            parts.append("The last thing I heard was you, a %d percent match." % round(last["score"] * 100))
        elif who:
            parts.append("The last thing I heard was %s." % display(who))
        else:
            parts.append("The last thing I heard didn't match anyone I know.")
    return " ".join(parts)


@action("voice_forget", "Delete a voiceprint: the user's own (turns voice lock off) or a named person's.",
        "person?: str")
def voice_forget(person=""):
    name, _ = split_name(person) if person and person.lower() not in ("me", "my", "mine") else ("", None)
    if name:
        return ("Done, I've forgotten %s's voice." % name) if voiceprint.forget_person(name) \
            else "I don't know %s's voice." % name

    def do():
        voiceprint.forget()
        return "Done. I've forgotten your voice."
    svc.assistant.confirm("Should I forget your voice? Voice lock will turn off.", do)
    return None
