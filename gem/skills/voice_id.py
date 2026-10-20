"""Voice lock: learn the user's voice and, when always listening, only respond to it."""
import logging
import threading
import time

from .. import voiceprint
from ..actions import ActionError, action
from ..cards import card
from ..runtime import svc
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

training = {"step": None, "until": 0.0}


def cfg():
    return svc.config.get("voice_lock") or {}


def base_threshold():
    return float(cfg().get("threshold", 0.45))


def training_active():
    if training["step"] is not None and time.time() > training["until"]:
        training["step"] = None
    return training["step"] is not None


def _how():
    return "Hold Caps Lock and read it out" if svc.state.mode == PUSH_TO_TALK else "Read it out loud"


def _step_card(text, hint=None):
    i = training["step"]
    return card("voice", text, phrase=PHRASES[i], step=i, total=len(PHRASES), hint=hint or _how())


def train_step(pcm, plain):
    """One training utterance. Returns what to say/show next."""
    if plain in CANCEL:
        training["step"] = None
        return "Okay, I stopped voice training."
    if not voiceprint.add(pcm, "trained"):
        return _step_card("That was a bit short. Try the whole line.", hint="Say the full sentence at a normal pace")
    training["step"] += 1
    training["until"] = time.time() + 180
    if training["step"] < len(PHRASES):
        return _step_card("Got it. Next one.")
    training["step"] = None
    voiceprint.set_locked(True)
    log.info("Voice training done (%d samples)", voiceprint.sample_count())
    tail = " Switch to always listening with a triple tap on Caps Lock." if svc.state.mode == PUSH_TO_TALK else ""
    return card("voice", "Got it, I know your voice now. When I'm always listening, I'll only respond to you.%s" % tail,
                done=True, step=len(PHRASES), total=len(PHRASES))


@action("voice_train", "Learn the user's voice (a short read-aloud), then only respond to them when always listening.")
def voice_train():
    svc.state.update(thinking=True)
    if not voiceprint.ensure_model():
        raise ActionError("I couldn't download the voice model. Check the internet and try again.")
    training.update(step=0, until=time.time() + 180)
    return _step_card("Let's learn your voice: five short lines. Say cancel to stop.")


@action("voice_lock", "Only respond to the user's own voice when always listening (on), or to anyone (off).", "on: bool")
def voice_lock(on=True):
    if on and not voiceprint.ready():
        return voice_train()
    voiceprint.set_locked(bool(on))
    if on:
        return "Okay. When I'm always listening, I'll only respond to your voice."
    return "Okay, I'll listen to everyone again."


@action("voice_status", "Say whether Gem knows the user's voice, if voice lock is on, and how well the last speech matched.")
def voice_status():
    n = voiceprint.sample_count()
    if not voiceprint.ready():
        return "I don't know your voice yet. Say learn my voice and read five short lines."
    parts = ["I know your voice from %d samples, and voice lock is %s." % (n, "on" if voiceprint.locked() else "off")]
    last = voiceprint.last
    if last["score"] is not None and time.time() - last["t"] < 600:
        parts.append("The last thing I heard was a %d percent match, so I %s it." % (
            round(max(0.0, last["score"]) * 100), "accepted" if last["accepted"] else "ignored"))
    return " ".join(parts)


@action("voice_forget", "Delete the user's voiceprint and turn voice lock off.")
def voice_forget():
    def do():
        voiceprint.forget()
        return "Done. I've forgotten your voice."
    svc.assistant.confirm("Should I forget your voice? Voice lock will turn off.", do)
    return None


def learn_async(pcm):
    """Push-to-talk is always you, so it quietly improves the voiceprint (in the background)."""
    if not cfg().get("learn_from_push_to_talk", True) or training_active() or not voiceprint.model_ready():
        return
    threading.Thread(target=voiceprint.add, args=(pcm, "learned", base_threshold()), daemon=True).start()
