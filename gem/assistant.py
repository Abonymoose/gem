"""The request pipeline: speech -> text -> (router | AI) -> actions -> reply."""
import json
import logging
import math
import os
import queue
import re
import threading
import time
from collections import deque

from . import actions, automemory, eggs, router, safety, voiceprint
from .audio import Utterance
from .brain import BrainUnavailable
from .cards import card_of
from .config import DATA_DIR
from .runtime import caption, say, svc
from .skills import hearing, macros, power_auto, routines, text as text_skill, trivia, voice_id
from .state import ALWAYS_LISTENING

log = logging.getLogger("gem.assistant")

YES = {"yes", "yeah", "yep", "yup", "sure", "confirm", "do it", "go ahead", "yes please", "okay", "ok",
       "correct", "please do", "yes do it", "affirmative"}
NO = {"no", "nope", "cancel", "don't", "dont", "stop", "never mind", "nevermind", "no thanks", "don't do it"}
POWER_CANCEL = {"cancel", "stop", "cancel it", "don't", "dont", "no", "wait", "never mind", "nevermind", "stop it",
                "don't do it", "dont do it", "don't turn it off", "i'm still watching", "im still watching"}

FILLER = {"yeah", "yes", "no", "okay", "ok", "lol", "bro", "what", "huh", "right", "sure", "nice", "cool", "wow",
          "yep", "nope", "hello", "hi", "hey", "thanks", "alright", "oh", "damn", "bruh", "um", "uh", "like",
          "so", "and", "the", "i", "it", "is", "that", "this", "you", "a"}

HISTORY_FILE = os.path.join(DATA_DIR, "history.jsonl")
HISTORY_MAX = 2000


def _failed(result):
    return isinstance(result, actions.Failure) or str(result or "").startswith(("Sorry", "I couldn't", "I can't"))


def _trim_history():
    try:
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            lines = f.readlines()
        if len(lines) > HISTORY_MAX:
            with open(HISTORY_FILE, "w", encoding="utf-8") as f:
                f.writelines(lines[-HISTORY_MAX // 2:])
    except OSError:
        pass


class Assistant:
    def __init__(self, on_quit):
        self.on_quit = on_quit
        self.last_heard = deque(maxlen=20)
        self.last_heard_at = 0.0
        self.last_voice = ("", 0.0)     # the last spoken request Gem acted on, for fixing it in the typing bar
        self._queue = queue.Queue()
        self._pending = None            # (callback, expires_at)
        self._panicked_at = 0.0

    def start(self):
        _trim_history()
        threading.Thread(target=self._worker, name="assistant", daemon=True).start()

    def submit(self, utterance):
        self._queue.put(utterance)

    def submit_text(self, text, unattended=False):
        """Typed commands; unattended=True for ones Gem queues itself (scheduled), which can never approve anything."""
        if text and text.strip():
            self._queue.put(Utterance(source="typed", text=text.strip(), unattended=unattended))

    # ── Helpers other modules use ───────────────────────────────────────────

    def confirm(self, question, callback, timeout=20):
        """Ask a yes/no question; callback runs (and its result is spoken) on yes. Only one question is ever open:
        this one replaces any "send it" / "confirm" card, so an answer can't land on a question you can't see."""
        safety.replace()
        self._pending = (callback, time.time() + timeout)
        say(question, card={"kind": "confirm"})
        svc.state.update(last_reply_at=time.time())

    def recent_voice(self, seconds=60):
        """What Gem heard you say last, if it was in the last minute (the typing bar offers it to fix)."""
        text, at = self.last_voice
        return text if text and time.time() - at < seconds else ""

    def resend(self, heard, text):
        """You fixed what Gem heard in the typing bar: run the fixed version, and learn a fix made twice."""
        self.last_voice = ("", 0.0)
        learned = hearing.learn_from_edit(heard, text)
        if learned:
            caption(learned, seconds=3)
        self.submit_text(text)

    def drop_question(self):
        """Forget an open yes/no question (a "send it" / "confirm" card replaces it)."""
        self._pending = None

    def execute(self, command):
        """Run one command without speaking (routine steps). Returns (worked, results)."""
        norm, _ = router.normalize(command)
        m = router.match(norm, command) if norm else None
        try:
            if m:
                safety.before_input(m.action)
                res = actions.run(m.action, m.args)
                return not _failed(res), [res]
            plan = svc.brain.plan(command, "typed")
            if not plan["actions"]:
                return bool(plan.get("reply")), [plan["reply"]] if plan.get("reply") else []
            results = self._run_actions(plan["actions"], [])
            return not any(_failed(r) for r in results), results
        except Exception as e:
            log.warning("Routine step %r failed: %s", command, e)
            return False, []

    def quit(self):
        say("Goodbye.")
        threading.Thread(target=self._quit_after_speech, daemon=True).start()

    def _quit_after_speech(self):
        time.sleep(0.3)
        end = time.time() + 4
        while svc.voice.busy and time.time() < end:
            time.sleep(0.1)
        self.on_quit()

    def panic(self):
        try:
            import pythoncom
            pythoncom.CoInitialize()        # runs on the hotkey thread; volume control needs COM
        except Exception:
            pass
        cfg = svc.config.get("panic", {})
        self._panicked_at = time.time()         # requests said before the panic are dropped, not run after it
        svc.voice.stop()
        macros.abort("Stopped.")
        safety.cancel("aborted")
        if macros.recording():
            actions.run("macro_record", {"command": "cancel"})
        for app in cfg.get("close_apps") or []:
            actions.run("close_app", {"name": app})
        if cfg.get("mute", True):
            actions.run("volume", {"mute": True})
        if cfg.get("minimize_all", True):
            actions.run("window", {"command": "show_desktop"})
        if cfg.get("open_url"):
            actions.run("open_url", {"url": cfg["open_url"]})
        svc.state.update(hidden=True, snoozed_until=math.inf)
        log.info("Panic: done")

    # ── Worker ───────────────────────────────────────────────────────────────

    def _worker(self):
        try:
            import pythoncom
            pythoncom.CoInitialize()
        except Exception:
            pass
        while True:
            item = self._queue.get()
            try:
                self._handle(item)
            except Exception:
                log.exception("Handling failed")
                if item.source != "open":
                    say("Sorry, something went wrong with that.")
            finally:
                svc.state.update(thinking=False)

    def _handle(self, item):
        if item.created < self._panicked_at:
            log.info("Dropped a request from before the panic")
            return
        with safety.context(unattended=item.unattended):
            self._process(item)

    def _process(self, item):
        st = svc.state
        explicit = item.source in ("ptt", "typed")
        text = item.text
        who = None
        svc.brain.speaker = None
        if not text:
            proceed, who = self._who_is_speaking(item)
            if not proceed:
                return
            if who not in (None, "me"):
                svc.brain.speaker = voice_id.describe(who)
            if explicit:
                st.update(thinking=True)
            text = svc.stt.transcribe(item.audio)
            if text and item.source == "ptt":
                voice_id.learn_async(item.audio, who)
        if not text:
            if item.source == "ptt":
                caption("I didn't catch that.", seconds=2.5)
            return

        text = hearing.apply(text)                  # words you taught Gem it keeps mishearing
        self.last_heard.append(text)
        self.last_heard_at = time.time()
        norm, by_name = router.normalize(text)
        plain = re.sub(r"[^a-z' ]", "", norm).strip()
        log.info("Heard [%s]: %s", item.source, text)
        if explicit or by_name or st.in_conversation():
            caption(None, you=text)
        if not norm:
            if by_name or explicit:
                self._respond("Yes?", text, item.source, [])
            return

        if plain in (svc.config.get("panic", {}).get("voice_phrases") or []):
            return self.panic()

        # "Cancel" during the shutdown warning is about the shutdown, whatever else is waiting.
        if plain in POWER_CANCEL and power_auto.warning() and not item.unattended:
            safety.hear(item, plain, by_name)
            return self._respond(power_auto.power_when_cancel(), text, item.source, ["power_when_cancel"])

        # A big step waiting for "send it" / "confirm" (safety.py). Plain "yes" still answers an ordinary question.
        if not item.unattended:
            reply = safety.hear(item, plain, by_name, other_pending=bool(self._pending))
            if reply is not None:
                if plain in safety.CANCEL:
                    self._pending = None
                    if macros.abort():                  # "stop" / "cancel" also stops a macro that's running
                        svc.voice.stop()
                return self._respond(reply, text, item.source, ["approve"])
            if safety.is_phrase(plain) and not self._pending and not st.dictating and \
                    (explicit or by_name or st.in_conversation()):
                return self._respond("There's nothing waiting for your OK right now.", text, item.source, [])

        if self._pending and not item.unattended:
            callback, expires = self._pending
            self._pending = None
            if time.time() < expires:
                if plain in YES:
                    return self._respond(callback(), text, item.source, ["confirm"])
                if plain in NO:
                    return self._respond("Okay, I won't.", text, item.source, [])

        if plain in POWER_CANCEL and power_auto.pending() and not item.unattended:
            return self._respond(power_auto.power_when_cancel(), text, item.source, ["power_when_cancel"])

        if trivia.active() and (explicit or st.in_conversation()) and not item.unattended:
            reply = trivia.answer(text, plain)              # None: not an answer, handle it normally
            if reply is not None:
                return self._respond(reply, text, item.source, ["trivia"])

        if voice_id.training_active() and item.audio and item.source in ("ptt", "open"):
            return self._respond(voice_id.train_step(item.audio, plain), text, item.source, ["voice_train"])

        if st.dictating and (explicit or st.effective_mode == ALWAYS_LISTENING) and not item.unattended:
            if plain in text_skill.ENTER_WORDS:
                if safety.current() is not None:     # a card is up: Enter could send what it's asking about
                    caption("Answer the card first. Say it again once it's up.", seconds=3)
                    return
                ok, why = safety.trusted(item, by_name)
                if not ok:
                    caption(why or "That didn't sound like you, so I didn't press Enter.", seconds=3)
                    return
            result = text_skill.handle_dictation(text)
            if result:
                say(result)
            return

        addressed = explicit or by_name or st.in_conversation()

        # Your own routines, by name or trigger phrase.
        routine = routines.find(norm)
        if routine and (addressed or len(norm.split()) >= 2):
            if not addressed:
                caption(None, you=text)
            st.update(thinking=True)
            macros.note_command(text, ["routine_run"])
            return self._respond(routines.run(routine), text, item.source, ["routine_run"])

        # Fast path
        m = router.match(norm, text) if norm else None
        if not m and norm and addressed:
            m, _ = router.repair(norm, text)          # a misheard word or name, when clearly talking to Gem
        if m and (addressed or (m.safe and len(norm.split()) >= 2)):
            if not addressed:
                caption(None, you=text)
            macros.note_command(text, [m.action])
            result = actions.run(m.action, m.args)
            return self._respond(result, text, item.source, [m.action], acts=[{"name": m.action, "args": m.args}])

        # AI path
        if not addressed and self._probably_chatter(norm):
            log.debug("Ignored chatter: %s", text)
            return
        if not svc.brain.available():
            if explicit:
                say("I need a Groq API key for that. Set GROQ_API_KEY and restart me.")
            return
        if explicit:
            st.update(thinking=True)
        try:
            plan = svc.brain.plan(text, item.source)
        except BrainUnavailable as e:
            if addressed:
                say(str(e))
            return
        if not plan["addressed"]:
            log.info("Not for Gem: %s", text)
            return
        if not addressed:
            caption(None, you=text)

        names, ran = [], []
        macros.note_command(text, [a["name"] for a in plan["actions"]])
        safety.reset_outcome()
        done = self._run_actions(plan["actions"], names, ran)
        results = list(zip(names, done))
        cards = [card_of(r) for _, r in results if card_of(r)]
        reply = plan["reply"]
        if plan["continue"] and safety.last_outcome() != "asked":
            try:
                final = svc.brain.follow_up(plan, results)
                first = len(names)
                done = self._run_actions(final.get("actions", []), names, ran)
                results = list(zip(names[first:], done))   # the first results were for the model
                cards = [card_of(r) for _, r in results if card_of(r)] or cards
                reply = final.get("reply", "")
            except BrainUnavailable as e:
                reply = str(e)
        if safety.last_outcome() == "asked":
            # A big step is waiting for "send it": show its card, whatever else the plan did.
            cards = [c for c in cards if c.get("kind") == "approve"][-1:] or cards
        spoken = " ".join([r for _, r in results if r] + ([reply] if reply else []))
        if not spoken and not names and explicit:
            spoken = "Sorry, I didn't get that."        # never leave a push-to-talk request hanging
        self._respond(spoken, text, item.source, names, card=cards[0] if cards else None, acts=ran)

    @staticmethod
    def _run_actions(acts, names, ran=None):
        """Run a plan's actions in order. Only one big step per request: once one is waiting for the user's OK,
        the rest isn't done (doing it would replace what's on the card). ran collects {"name", "args"} of each."""
        results = []
        for a in acts:
            if safety.stopping() or safety.last_outcome() in ("cancelled", "expired", "replaced", "aborted"):
                break                               # you said stop, or no to a big step: not the rest of the plan
            safety.before_input(a["name"])          # inside a macro: still its window, and you haven't typed
            if safety.last_outcome() == "asked":
                results.append("I'll do one thing at a time: OK this one first, then ask me for the rest.")
                names.append("approve_one_at_a_time")
                break
            names.append(a["name"])
            if ran is not None:
                ran.append({"name": a["name"], "args": a["args"]})
            results.append(actions.run(a["name"], a["args"]))
        return results

    @staticmethod
    def _who_is_speaking(item):
        """Voice lock and family voices, before anything is transcribed. Returns (go ahead, who):
        who is "me", a known person's key, or None when nobody was identified."""
        if not item.audio or voice_id.training_active() or not voiceprint.model_ready():
            return True, None
        ptt, lock, blocked = item.source == "ptt", voiceprint.locked(), voiceprint.blocked_names()
        strict_ptt = ptt and lock and voice_id.cfg().get("in_push_to_talk")
        if item.source == "open":
            needed = lock or bool(voiceprint.people())
        else:
            needed = bool(blocked) or strict_ptt
        if not needed:
            return True, None
        who, sc = voiceprint.hear(item.audio, voice_id.base_threshold())
        score_txt = "too short to tell" if sc is None else "%.2f" % sc
        if who in blocked:
            log.info("Ignored %s (blocked, %s)", voice_id.display(who), score_txt)
            voice_id.greet_blocked(who)
            return False, who
        if item.source == "open" and lock and who in ("?", None):
            log.info("Voice lock: ignored speech that doesn't sound like you (%s)", score_txt)
            return False, None
        # Push-to-talk: holding the key is already a good sign, so only a clear mismatch is refused.
        if strict_ptt and who is None and sc is not None and sc < voice_id.base_threshold() - 0.08:
            log.info("Voice lock (push-to-talk): refused a voice that isn't yours (%s)", score_txt)
            caption("That didn't sound like you", seconds=2.5)
            return False, None
        if who not in ("?", None, "me"):
            log.info("Speaking: %s (%s)", voice_id.display(who), score_txt)
        return True, (None if who == "?" else who)

    @staticmethod
    def _probably_chatter(norm):
        words = norm.split()
        return len(words) < 3 or all(w in FILLER for w in words)

    def _respond(self, spoken, text, source, action_names, card=None, acts=None):
        card = card or card_of(spoken)
        if spoken:
            say(spoken, card=card)
        if action_names != ["snooze"]:
            svc.state.update(last_reply_at=time.time())
        if source in ("ptt", "open"):
            self.last_voice = (text, time.time())
        svc.brain.remember_exchange(text, source, str(spoken or ""), action_names, acts)
        automemory.consider(text, action_names, source)
        if spoken or action_names:
            eggs.after_reply(source)
        try:
            with open(HISTORY_FILE, "a", encoding="utf-8") as f:
                f.write(json.dumps({"t": time.time(), "source": source, "you": text, "gem": str(spoken or ""),
                                    "actions": action_names}) + "\n")
        except OSError:
            pass
