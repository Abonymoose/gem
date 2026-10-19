"""The request pipeline: speech -> text -> (router | AI) -> actions -> reply."""
import logging
import math
import queue
import re
import threading
import time
from collections import deque

from . import actions, router
from .audio import Utterance
from .brain import BrainUnavailable
from .runtime import caption, say, svc
from .skills import control, text as text_skill
from .state import ALWAYS_LISTENING

log = logging.getLogger("gem.assistant")

YES = {"yes", "yeah", "yep", "yup", "sure", "confirm", "do it", "go ahead", "yes please", "okay", "ok",
       "correct", "please do", "yes do it", "affirmative"}
NO = {"no", "nope", "cancel", "don't", "dont", "stop", "never mind", "nevermind", "no thanks", "don't do it"}

FILLER = {"yeah", "yes", "no", "okay", "ok", "lol", "bro", "what", "huh", "right", "sure", "nice", "cool", "wow",
          "yep", "nope", "hello", "hi", "hey", "thanks", "alright", "oh", "damn", "bruh", "um", "uh", "like",
          "so", "and", "the", "i", "it", "is", "that", "this", "you", "a"}


class Assistant:
    def __init__(self, on_quit):
        self.on_quit = on_quit
        self.last_heard = deque(maxlen=20)
        self._queue = queue.Queue()
        self._pending = None            # (callback, expires_at)

    def start(self):
        threading.Thread(target=self._worker, name="assistant", daemon=True).start()

    def submit(self, utterance):
        self._queue.put(utterance)

    def submit_text(self, text):
        if text and text.strip():
            self._queue.put(Utterance(source="typed", text=text.strip()))

    # ── Helpers other modules use ───────────────────────────────────────────

    def confirm(self, question, callback, timeout=20):
        """Ask a yes/no question; callback runs (and its result is spoken) on yes."""
        self._pending = (callback, time.time() + timeout)
        say(question)
        svc.state.update(last_reply_at=time.time())

    def quit(self):
        say("Auf Wiedersehen.")
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
        svc.voice.stop()
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

    def _control_word(self, plain):
        words = svc.config.get("control_words", {})
        for kind in ("quit", "lock", "ruhig", "weiter"):
            if plain in (words.get(kind) or []):
                return kind
        return None

    def _handle(self, item):
        st = svc.state
        explicit = item.source in ("ptt", "typed")
        text = item.text
        if not text:
            if explicit:
                st.update(thinking=True)
            text = svc.stt.transcribe(item.audio)
        if not text:
            if item.source == "ptt":
                caption("I didn't catch that.", seconds=2.5)
            return

        self.last_heard.append(text)
        norm, by_name = router.normalize(text)
        plain = re.sub(r"[^a-z' ]", "", norm).strip()
        log.info("Heard [%s]: %s", item.source, text)
        if explicit or by_name or st.in_conversation():
            caption(None, you=text)
        if not norm:
            if by_name or explicit:
                self._respond("Yes?", text, item.source, [])
            return

        # Control words work in every mode and never need the AI.
        kind = self._control_word(plain)
        if kind == "quit":
            return self.quit()
        if kind == "lock":
            return actions.run("power", {"command": "lock"})
        if kind == "ruhig":
            return control.ruhig()
        if kind == "weiter":
            was_quiet = st.snoozed
            st.update(snoozed_until=0.0, hidden=False)
            return say("Ich bin wieder da." if was_quiet else "Ich bin da.")

        if plain in (svc.config.get("panic", {}).get("voice_phrases") or []):
            return self.panic()

        if self._pending:
            callback, expires = self._pending
            self._pending = None
            if time.time() < expires:
                if plain in YES:
                    return self._respond(callback(), text, item.source, ["confirm"])
                if plain in NO:
                    return self._respond("Okay, I won't.", text, item.source, [])

        if st.dictating and (explicit or st.effective_mode == ALWAYS_LISTENING):
            result = text_skill.handle_dictation(text)
            if result:
                say(result)
            return

        # Fast path
        m = router.match(norm, text) if norm else None
        addressed = explicit or by_name or st.in_conversation()
        if m and (addressed or (m.safe and len(norm.split()) >= 2)):
            if not addressed:
                caption(None, you=text)
            result = actions.run(m.action, m.args)
            return self._respond(result, text, item.source, [m.action])

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

        names, results = [], []
        for a in plan["actions"]:
            names.append(a["name"])
            results.append((a["name"], actions.run(a["name"], a["args"])))
        reply = plan["reply"]
        if plan["continue"]:
            try:
                final = svc.brain.follow_up(plan, results)
                results = []        # the first results were for the model; its final reply covers them
                for a in final.get("actions", []):
                    names.append(a["name"])
                    results.append((a["name"], actions.run(a["name"], a["args"])))
                reply = final.get("reply", "")
            except BrainUnavailable as e:
                reply = str(e)
        spoken = " ".join([r for _, r in results if r] + ([reply] if reply else []))
        self._respond(spoken, text, item.source, names)

    @staticmethod
    def _probably_chatter(norm):
        words = norm.split()
        return len(words) < 3 or all(w in FILLER for w in words)

    def _respond(self, spoken, text, source, action_names):
        if spoken:
            say(spoken)
        if action_names != ["snooze"]:
            svc.state.update(last_reply_at=time.time())
        svc.brain.remember_exchange(text, source, spoken or "", action_names)
