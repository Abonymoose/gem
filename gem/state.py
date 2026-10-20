"""Gem's live state, shared by every thread, with change notifications."""
import logging
import math
import threading
import time

log = logging.getLogger("gem.state")

PUSH_TO_TALK = "push_to_talk"
ALWAYS_LISTENING = "always_listening"

MODE_NAMES = {PUSH_TO_TALK: "Push to talk", ALWAYS_LISTENING: "Always listening"}


class State:
    def __init__(self, mode=PUSH_TO_TALK, conversation_window=25):
        self._lock = threading.RLock()
        self._listeners = []
        self.conversation_window = conversation_window

        self.mode = mode
        self.key_held = False        # Caps Lock is physically held
        self.speaking = False
        self.thinking = False
        self.in_call = False
        self.call_app = ""
        self.snoozed_until = 0.0     # epoch seconds; math.inf = until you say "I'm back"
        self.gaming = False
        self.dictating = False
        self.focus_until = 0.0
        self.voice_enabled = True
        self.speak_in_calls = False
        self.speak_in_gaming = False
        self.hidden = False          # panic hides the overlay
        self.last_reply_at = 0.0
        self.last_speech_end = 0.0

    # ── Change notification ──────────────────────────────────────────────────

    def subscribe(self, callback):
        self._listeners.append(callback)

    def update(self, **changes):
        changed = {}
        with self._lock:
            for key, value in changes.items():
                if getattr(self, key) != value:
                    setattr(self, key, value)
                    changed[key] = value
        if changed:
            for cb in list(self._listeners):
                try:
                    cb(self, changed)
                except Exception:
                    log.exception("State listener failed")
        return changed

    # ── Derived state ────────────────────────────────────────────────────────

    @property
    def snoozed(self):
        return time.time() < self.snoozed_until

    @property
    def quiet_indefinitely(self):
        return self.snoozed_until == math.inf

    @property
    def focusing(self):
        return time.time() < self.focus_until

    @property
    def effective_mode(self):
        """Calls, snooze and gaming fall back to push-to-talk."""
        if self.mode == PUSH_TO_TALK or self.in_call or self.snoozed or self.gaming:
            return PUSH_TO_TALK
        return ALWAYS_LISTENING

    def ears_open(self):
        if self.effective_mode == PUSH_TO_TALK:
            return self.key_held
        return not self.key_held

    def can_speak(self):
        if not self.voice_enabled or self.snoozed:
            return False
        if self.in_call and not self.speak_in_calls:
            return False
        if self.gaming and not self.speak_in_gaming:
            return False
        return True

    def quiet_alerts(self):
        """True when alerts should be silent popups instead of sounds."""
        return self.in_call or self.snoozed or self.gaming

    def in_conversation(self):
        return time.time() - self.last_reply_at < self.conversation_window

    def describe(self):
        parts = [MODE_NAMES[self.mode]]
        if self.quiet_indefinitely:
            parts.append("quiet until you say I'm back")
        elif self.snoozed:
            parts.append("quiet until " + time.strftime("%H:%M", time.localtime(self.snoozed_until)))
        if self.in_call:
            parts.append("on a call")
        if self.gaming:
            parts.append("gaming")
        if self.focusing:
            parts.append("focus session")
        if not self.voice_enabled:
            parts.append("voice off")
        return " · ".join(parts)
