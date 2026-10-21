"""Macros: one phrase runs a list of steps, including typing, keys and clicks in other apps.

A macro is a routine (routines.json) whose steps can also be "type ...", "press ...", "click ...", "wait ...",
"switch to ..." and "ask me first", next to any of Gem's own commands. Make one by voice ("create a macro called
..."), by recording ("record a macro", do the task, "stop recording"), or let Gem work one out ("figure out how to
..."). Macros run on their own thread, so Gem keeps listening: "stop", a Caps Lock tap or typing yourself stops one.

Big steps (sending, Enter in a chat or a terminal, deleting, risky clicks, power) wait for "send it" / "confirm"
(safety.py). A scheduled run skips them and says so afterwards. Before every key press, typed text or click the
runner checks the app it's working in is still in front; if not, it stops rather than typing somewhere else.
"""
import logging
import os
import re
import threading
import time

from .. import actions, router, safety
from ..actions import ActionError, action
from ..brain import BrainUnavailable
from ..cards import card
from ..runtime import caption, notify, say, svc
from ..winapi import (click_at, focus_window, foreground_window, parse_chord, press, release_modifiers, type_plain,
                      window_at, window_class, window_owner, window_pid, window_process_name, window_rect_physical,
                      window_title)
from . import apps, routines

log = logging.getLogger("gem.macros")

OK = "\x00ok"                   # what a step's own action returns when it worked

PLAN = """You plan steps for Gem, a voice assistant, to do a task on {name}'s Windows PC by itself. Each step is one short line:
- one of Gem's own commands, said plainly: "open discord", "open gmail", "volume 30", "start a focus session"
- "send a discord message to NAME saying TEXT", "send a google chat message to NAME saying TEXT", "email NAME saying TEXT": the only way to send anything (Gem shows it and waits for the user's OK)
- "switch to APP", "wait 2 seconds", "wait for APP"
- "type TEXT": types into the app in front (never put line breaks in it)
- "press KEYS": e.g. "press ctrl+k", "press tab", "press enter"
- "click DESCRIPTION": a button, link or field you expect to be visible, e.g. "click the compose button"
Rules: at most 12 steps. Open or switch to an app before typing in it, and wait for slow apps to load. Prefer Gem's own commands over typing and clicking. Never invent passwords, payment details, addresses or message text the user didn't give. Never delete, buy, or change account or security settings unless that is exactly the task. If something essential is missing, or this can't be done with these steps, return no steps and ask one short question.
Reply with JSON only: {{"title": "two to four words", "steps": ["..."], "question": ""}}
Gem's commands:
{catalog}"""


def cfg():
    return (svc.config or {}).get("macros") or {}


def _short(text, n=40):
    text = re.sub(r"\s+", " ", text or "").strip()
    return text if len(text) <= n else text[:n - 1].rstrip() + "…"


# ── Steps ────────────────────────────────────────────────────────────────────

_NUM = r"(\d+(?:\.\d+)?)"
_TIMES = {"twice": 2, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "ten": 10}


def parse_step(text):
    """A step line -> {"do": wait|wait_for|focus|type|keys|click_at|click|checkpoint|command, ...}."""
    raw = (text or "").strip()
    t = re.sub(r"\s+", " ", raw.lower()).strip().rstrip(".")
    m = re.match(r"^(?:wait|waits|pause|sleep)(?: for)? %s ?(ms|milliseconds?|s|secs?|seconds?|mins?|minutes?)?$"
                 % _NUM, t)
    if m:
        n, unit = float(m.group(1)), m.group(2) or "s"
        secs = n / 1000.0 if unit in ("ms", "millisecond", "milliseconds") else n * 60 if unit.startswith("min") else n
        return {"do": "wait", "seconds": min(secs, 600.0)}
    m = re.match(r"^(?:wait|waits) (?:for|until) (?:the )?(.+?)(?: app| window)?(?: (?:is|to be|to) (?:open|opened|"
                 r"ready|in front|load|loaded|show up|shows up|appear))?$", t)
    if m:
        return {"do": "wait_for", "app": m.group(1)}
    m = re.match(r"^(?:switch|switches|go back) to (?:the )?(.+?)(?: app| window)?$|^focus(?: on)? (?:the )?(.+?)"
                 r"(?: app| window)?$", t)
    if m:
        return {"do": "focus", "app": m.group(1) or m.group(2)}
    m = re.match(r"^(?:type|types|write|writes) (.+)$", raw, re.I | re.S)
    if m and not re.match(r"^(?:this|that|what i say)(?: down)?$", m.group(1).lower()):
        text = m.group(1)
        q = re.match(r'^\s*(["“\'])(.*)(["”\'])\s*$', text, re.S)
        return {"do": "type", "text": q.group(2) if q else text}
    m = re.match(r"^(?:press|presses|hit|hits|tap|taps)(?: the)? (.+?)(?: keys?)?(?: (\d+|%s) times| (twice))?$"
                 % "|".join(_TIMES), t)
    if m:
        n = m.group(2) or m.group(3)
        times = int(n) if n and n.isdigit() else _TIMES.get(n or "", 1)
        return {"do": "keys", "keys": m.group(1), "chord": parse_chord(m.group(1)), "times": max(1, min(times, 20))}
    m = re.match(r"^(double |right )?clicks? (?:at |on )?%s ?%%,? %s ?%%(?: (?:in|on) (?:the )?(.+?)"
                 r"(?: app| window)?)?$" % (_NUM, _NUM), t)
    if m:
        return {"do": "click_at", "button": "right" if m.group(1) == "right " else "left",
                "double": m.group(1) == "double ", "x": float(m.group(2)), "y": float(m.group(3)), "app": m.group(4)}
    m = re.match(r"^(double |right )?clicks? (?:on )?(.+)$", raw, re.I)
    if m:
        kind = (m.group(1) or "").lower()
        return {"do": "click", "button": "right" if kind == "right " else "left", "double": kind == "double ",
                "target": m.group(2).strip()}
    m = re.match(r"^(?:ask me(?: first)?|check with me|confirm(?: with me)?|ask (?:before|first)|pause and ask)"
                 r"(?: (?:before|then) (?:continuing|going on|you continue|you go on))?(?:[:,]? (.+))?$", t)
    if m:
        return {"do": "checkpoint", "text": m.group(1) or ""}
    return {"do": "command", "text": raw}


# ── Running ──────────────────────────────────────────────────────────────────

class _Stop(ActionError):
    """Stops the macro, with the sentence to say."""


class Run:
    def __init__(self, name, steps, unattended):
        self.name = name
        self.steps = steps[:int(cfg().get("max_steps", 60) or 60)]
        self.unattended = unattended
        self.abort = threading.Event()
        self.reason = ""
        self.waiting = False         # waiting for the user's OK on a big step
        self.target = 0              # the window the macro is working in
        self.last_typed = ""
        self.skipped = []
        self.typing_since = time.monotonic()
        self.card = {"kind": "macro", "name": name, "done": False, "current": 0, "note": "",
                     "steps": [{"text": s, "state": "pending"} for s in self.steps]}
        self.thread = threading.Thread(target=self._main, name="macro", daemon=True)

    # ── Thread ──

    def _main(self):
        try:
            import pythoncom
            pythoncom.CoInitialize()             # volume and audio steps use COM
        except Exception:
            pass
        svc.state.update(macro_running=self.name)
        caption("Running %s." % self.name, card=self.card)
        stopped = None
        with safety.context(unattended=self.unattended, skipped=self.skipped):
            try:
                self._run_steps(self.steps, top=True)
            except _Stop as e:
                stopped = str(e)
            except Exception:
                log.exception("Macro %s failed", self.name)
                stopped = "Sorry, %s stopped because something went wrong." % self.name
            finally:
                release_modifiers()
        svc.state.update(macro_running="")
        self._finish(stopped)

    def _run_steps(self, steps, top=False, depth=0):
        delay = float(cfg().get("step_delay", 0.15) or 0.15)
        for i, text in enumerate(steps):
            self._check_abort()
            row = self.card["steps"][i] if top else None
            if row:
                self.card["current"] = i
                row["state"] = "running"
            safety.reset_outcome()
            try:
                state = self._step(text, depth)
            except _Stop:
                if row:
                    row["state"] = "failed"
                raise
            if row:
                row["state"] = state
            log.info("Macro %s step %r: %s", self.name, text, state)
            if self.abort.wait(delay):
                self._check_abort()

    def _finish(self, stopped):
        rows = self.card["steps"]
        skipped = [r["text"] for r in rows if r["state"] == "skipped"] or self.skipped
        name = self.name
        if stopped:
            text = stopped
        elif skipped:
            text = "%s is done, but I skipped %s because nobody was here to OK %s." % (
                name.capitalize(), ", ".join("“%s”" % _short(s) for s in skipped),
                "it" if len(skipped) == 1 else "them")
        elif name.endswith("mode"):
            text = "%s is on." % name.capitalize()
        else:
            text = "Done: %s." % name
        final = dict(self.card, done=True, steps=[dict(r) for r in rows])
        if self.unattended and (stopped or skipped):
            notify("Macro: %s" % name, text, speak=False)    # also kept for "while you were away"
        say(text, card=final)

    def _check_abort(self):
        if self.abort.is_set():
            raise _Stop(self.reason or "Stopped %s." % self.name)

    # ── One step ──

    def _step(self, text, depth):
        s = parse_step(text)
        do = s["do"]
        if do == "wait":
            if self.abort.wait(s["seconds"]):
                self._check_abort()
            return "done"
        if do == "wait_for":
            self._wait_for(s["app"])
            return "done"
        if do == "focus":
            self._focus(s["app"])
            return "done"
        if do == "type":
            return self._type(s["text"])
        if do == "keys":
            return self._keys(s)
        if do == "click_at":
            return self._click_at(s)
        if do == "click":
            return self._click(s)
        if do == "checkpoint":
            return self._gate(s["text"] or "Keep going with %s" % self.name, lambda: OK, phrase="confirm",
                              chip="Keep going")
        return self._command(s["text"], depth)

    def _gate(self, title, run, **kw):
        """A big step: wait for the user's OK (or skip it when nobody's here). Returns the step's state."""
        def go():
            self.typing_since = time.monotonic()      # editing the message before saying "send it" is fine
            return run()
        self.waiting = True
        try:
            result = safety.ask(title, go, should_stop=self.abort.is_set, **kw)
        finally:
            self.waiting = False
        outcome = safety.last_outcome()
        if outcome == "skipped":
            return "skipped"
        self._check_abort()
        if outcome != "approved":
            raise _Stop({"expired": "I didn't hear your OK for “%s”, so I stopped %s." % (title, self.name),
                         "replaced": "Something else needed your OK, so I stopped %s." % self.name}.get(
                outcome, "Okay, I stopped %s." % self.name))
        caption("", card=self.card)                   # back to the progress card
        if result != OK:
            raise _Stop(result or "That didn't work, so I stopped %s." % self.name)
        return "done"

    def _ready_for_input(self):
        """The window to type or click in: the macro's app, still in front. Stops the macro otherwise."""
        self._check_abort()
        keys = svc.keys
        if keys is not None and getattr(keys, "last_user_key", 0.0) > self.typing_since:
            raise _Stop("You started typing, so I stopped %s." % self.name)
        fg = foreground_window()
        if not fg or window_process_name(fg) in ("lockapp.exe", "logonui.exe"):
            raise _Stop("The PC is locked, so I stopped %s." % self.name)
        if window_pid(fg) == os.getpid():
            if self.target and self._refocus(self.target):
                return self.target
            raise _Stop("Gem's own window was in front, so I stopped. Start %s from the app it's for, or begin it "
                        "with a “switch to …” step." % self.name)
        if not self.target or fg == self.target:
            self.target = fg
            return fg
        if window_pid(fg) == window_pid(self.target) and (window_owner(fg) == self.target or
                                                          window_class(fg) == "#32770"):
            self.target = fg                              # a dialog of the same app (Save As, a prompt)
            return fg
        if self._refocus(self.target):
            return self.target
        raise _Stop("%s isn't in front any more, so I stopped %s." % (apps.friendly_name(self.target).capitalize()
                                                                        or "The app", self.name))

    @staticmethod
    def _refocus(hwnd):
        focus_window(hwnd)
        time.sleep(0.35)
        return foreground_window() == hwnd

    def _wait_for(self, app, seconds=15.0):
        end = time.time() + seconds
        while time.time() < end:
            self._check_abort()
            wins = [w[0] for w in apps.app_windows(app)]
            fg = foreground_window()
            if fg in wins:
                self.target = fg
                return fg
            if wins and self._refocus(wins[0]):
                self.target = wins[0]
                return wins[0]
            if self.abort.wait(0.5):
                self._check_abort()
        raise _Stop("%s didn't show up, so I stopped %s." % (app.capitalize(), self.name))

    def _focus(self, app):
        if not apps.app_windows(app):
            try:
                apps.open_app(app)
            except ActionError:
                raise _Stop("I couldn't find %s, so I stopped %s." % (app, self.name))
            return self._wait_for(app, 25.0)
        return self._wait_for(app, 5.0)

    def _type(self, text):
        hwnd = self._ready_for_input()
        release_modifiers()
        type_plain(text, soft_newlines=safety.window_kind(hwnd) == "messaging")   # never presses Enter
        self.last_typed = text
        return "done"

    def _keys(self, s):
        chord = s["chord"]
        if not chord:
            raise _Stop("I don't know the keys in “press %s”, so I stopped %s." % (s["keys"], self.name))
        if chord[-1] in ("caps", "num", "scroll") or _gem_hotkey(chord):
            raise _Stop("“press %s” would press one of Gem's own keys, so I stopped %s." % (s["keys"], self.name))
        hwnd = self._ready_for_input()
        big = safety.big_key(chord, hwnd)

        def go():
            if big and self._ready_for_input() != hwnd:
                raise ActionError("The window changed, so I didn't do it.")
            release_modifiers()
            for _ in range(s["times"]):
                press(*chord)
                time.sleep(0.05)
            return OK
        if not big:
            go()
            return "done"
        sending = big.startswith("Send")
        return self._gate(big, go, app=apps.friendly_name(hwnd).capitalize(), to=_short(window_title(hwnd), 50),
                          message=self.last_typed if sending else "", phrase="send it" if sending else "confirm")

    def _click_at(self, s):
        if s.get("app"):
            self._focus(s["app"])
        hwnd = self._ready_for_input()
        left, top, right, bottom = window_rect_physical(hwnd)
        x = left + (right - left) * min(max(s["x"], 0.0), 100.0) / 100.0
        y = top + (bottom - top) * min(max(s["y"], 0.0), 100.0) / 100.0
        under = window_at(x, y)
        if under and window_pid(under) != window_pid(hwnd):
            raise _Stop("Something is covering that spot in %s, so I stopped %s." % (
                apps.friendly_name(hwnd) or "the app", self.name))
        big = safety.big_click("", hwnd, at_position=True)

        def go():
            if self._ready_for_input() != hwnd or window_rect_physical(hwnd) != (left, top, right, bottom):
                raise ActionError("The window moved, so I didn't click.")
            click_at(x, y, s["button"], s["double"])
            return OK
        if not big:
            go()
            return "done"
        return self._gate(big, go, app=apps.friendly_name(hwnd).capitalize(), to=_short(window_title(hwnd), 50),
                          phrase="confirm")

    def _click(self, s):
        from .screen import point_at
        what = s["target"]
        hwnd = self._ready_for_input()
        try:
            found = point_at(what)
        except BrainUnavailable as e:
            raise _Stop("%s So I stopped %s." % (e, self.name))
        if not found:
            raise _Stop("I couldn't find %s on the screen, so I stopped %s." % (what, self.name))
        x, y, box, monitor, label = found
        under = window_at(x, y)
        if not under or window_pid(under) == os.getpid():
            raise _Stop("I couldn't find %s on the screen, so I stopped %s." % (what, self.name))
        rect = window_rect_physical(hwnd)
        big = safety.big_click("%s %s" % (what, label), hwnd)
        show = bool(svc.overlay) and (svc.config.get("appearance") or {}).get("screen_highlights", True)
        if show:
            seconds = float(safety.cfg().get("confirm_seconds", 45)) if big else 1.2
            svc.overlay.highlight(monitor, [(box, label or what)], seconds=seconds)

        def go():
            if self._ready_for_input() != hwnd or window_rect_physical(hwnd) != rect:
                raise ActionError("The window moved, so I didn't click.")
            click_at(x, y, s["button"], s["double"])
            return OK
        if not big:
            time.sleep(1.0)                           # a moment to see what Gem is about to click
            go()
            return "done"
        return self._gate(big, go, app=apps.friendly_name(hwnd).capitalize(), to=_short(window_title(hwnd), 50),
                          phrase="confirm")

    def _command(self, text, depth):
        norm, _ = router.normalize(text)
        nested = routines.find(norm) if norm else None
        m = router.match(norm, text) if norm and not nested else None
        if m and m.action == "routine_run":
            nested = routines.lookup(m.args.get("name", ""))
            if not nested:
                raise _Stop("I don't have a macro called %s, so I stopped %s." % (m.args.get("name", ""), self.name))
        if nested:
            if depth >= 2:
                raise _Stop("Macros inside macros only go two deep, so I stopped %s." % self.name)
            self._run_steps(nested.get("steps") or [], depth=depth + 1)
            return "done"
        if m and m.action in ("macro_record", "macro_auto", "macro_save", "quit_gem", "voice_train"):
            raise _Stop("“%s” can't be a step in a macro, so I stopped %s." % (text, self.name))
        if m and m.action == "power" and m.args.get("command") not in ("lock", "cancel_shutdown"):
            from .system import POWER_WORDS, _do_power
            command = m.args.get("command")
            if command not in POWER_WORDS:
                raise _Stop("I can't do “%s”, so I stopped %s." % (text, self.name))
            return self._gate(POWER_WORDS[command].capitalize(), lambda: _said(_do_power(command)), phrase="confirm")
        if m and m.action == "power_when":
            return self._gate("Turn off the PC later (%s)" % text, lambda: _said(actions.run(m.action, m.args)),
                              phrase="confirm")
        before = foreground_window()
        before = (before, window_title(before))
        ok, results = svc.assistant.execute(text)
        outcome = safety.last_outcome()
        if outcome == "skipped":
            return "skipped"
        self._check_abort()
        if outcome in ("cancelled", "expired", "replaced", "aborted"):
            raise _Stop("Okay, I stopped %s." % self.name if outcome == "cancelled" else
                        "I didn't get your OK, so I stopped %s." % self.name)
        said = " ".join(str(r) for r in results if r)
        if outcome == "approved":
            caption("", card=self.card)
            if not said.startswith("Sent"):
                raise _Stop("%s So I stopped %s." % (said or "That didn't work.", self.name))
        if not ok:
            raise _Stop("“%s” didn't work%s, so I stopped %s." % (text, (": " + _short(said, 80)) if said else "",
                                                                  self.name))
        if m and m.action in ("open_app", "switch_to", "restore_app"):
            name = m.args.get("name", "")
            if apps.resolve_site(name.lower()):
                self._settle(before)
            else:
                self._wait_for(name, 25.0)
        elif m and m.action in ("open_url", "youtube", "web_search", "spotify_search", "open_latest_download",
                                "find_file", "open_result", "open_folder", "open_settings"):
            self._settle(before)
        return "done"

    def _settle(self, before, seconds=8.0):
        """After opening something in a browser or another app: work in whatever comes to the front."""
        end = time.time() + seconds
        while time.time() < end:
            fg = foreground_window()
            if fg and (fg, window_title(fg)) != before and window_pid(fg) != os.getpid():
                self.abort.wait(1.0)                  # let it finish loading
                self.target = foreground_window()
                return
            if self.abort.wait(0.3):
                self._check_abort()
        self.target = 0                               # nothing new came up: use whatever is in front next


def _said(text):
    """A big step's own result, said out loud (the step itself counts as done)."""
    if text:
        say(str(text))
    return OK


def _gem_hotkey(chord):
    keys = (svc.config or {}).get("keys") or {}
    for combo in (keys.get("command_bar"), keys.get("panic")):
        parts = {{"control": "ctrl", "windows": "win"}.get(p, p) for p in re.split(r"\s*\+\s*", (combo or "").lower())
                 if p}
        if parts and parts == set(chord):
            return True
    return False


_run = None
_lock = threading.Lock()


def start(routine):
    """Run a routine or macro on its own thread. Returns what to say now (usually nothing)."""
    global _run
    steps = [str(s) for s in routine.get("steps") or [] if s and str(s).strip()]
    name = routine.get("name") or "the macro"
    if not steps:
        return "%s has no steps." % name.capitalize()
    with _lock:
        r = _run
        inside = r is not None and r.thread.is_alive() and threading.current_thread() is r.thread
        if not inside:
            if r is not None and r.thread.is_alive():
                return "%s is still running. Say stop the macro first." % r.name.capitalize()
            _run = Run(name, steps, safety.unattended())
            _run.thread.start()
            return None
    r._run_steps(steps, depth=1)          # a macro step running another macro (outside the lock, so stop works)
    return None


def running():
    return _run is not None and _run.thread.is_alive()


def abort(reason=""):
    """Stop the running macro. Returns True if one was running."""
    with _lock:
        r = _run
    if r is None or not r.thread.is_alive():
        return False
    r.reason = reason or "Stopped %s." % r.name
    r.abort.set()
    return True


def on_tap():
    """Caps Lock tap: stops a macro that's busy typing or clicking (not one waiting for your OK)."""
    with _lock:
        r = _run
    if r is not None and r.thread.is_alive() and not r.waiting:
        abort("Stopped %s." % r.name)


@action("macro_stop", "Stop the macro or routine that's running.")
def macro_stop():
    if abort():
        return None                    # the macro says "Stopped ..." itself
    return "No macro is running."


# ── Recording ────────────────────────────────────────────────────────────────

_rec = {"recorder": None, "name": "", "pending": None}      # pending: (steps, notes, time) waiting for a name
NOT_STEPS = {"macro_record", "macro_name", "macro_save", "macro_stop", "stop", "snooze", "repeat", "approve",
             "confirm", "what_did_you_hear", "clear_conversation", "voice_replies", "set_mode", "help", "resume",
             "quiet_until_resumed", "open_dashboard", "open_gem_settings"}


def recording():
    r = _rec["recorder"]
    return r is not None and r.active()


def awaiting_name():
    p = _rec["pending"]
    return bool(p) and time.time() - p[2] < 600


def plan_recent():
    """Gem worked out a plan in the last half hour (so "save that as ..." means it)."""
    return bool(_last_plan["steps"]) and time.time() - _last_plan["t"] < 1800


def note_command(text, action_names):
    """A command you gave while recording becomes a step, as you said it."""
    r = _rec["recorder"]
    if r is None or not r.active() or not action_names or set(action_names) & NOT_STEPS:
        return
    r.add_command(text.strip().rstrip("."))


def _on_limit():
    threading.Thread(target=lambda: say(_record_stop()), name="macro-record-stop", daemon=True).start()


def _record_stop(name=""):
    r, _rec["recorder"] = _rec["recorder"], None
    svc.state.update(macro_recording=0.0)
    if r is None:
        return "I'm not recording a macro."
    steps, notes = r.stop()
    name = (name or _rec["name"]).strip()
    _rec["name"] = ""
    if not steps:
        return "I didn't catch any steps, so there's nothing to save."
    if not name:
        _rec["pending"] = (steps, notes, time.time())
        return card("macro", "Got %d steps. What should I call it? Say call it, then a name." % len(steps),
                    name="new macro", done=True, current=0, note=" ".join(notes),
                    steps=[{"text": s, "state": "done"} for s in steps])
    return _save(name, steps, notes)


def _save(name, steps, notes=()):
    _rec["pending"] = None
    saved = routines.routine_create(name=name, steps=steps)
    extra = " ".join(notes)
    return card("macro", ("%s %s" % (saved, extra)).strip(), name=routines._norm(name), done=True, current=0,
                note=extra, steps=[{"text": s, "state": "done"} for s in steps])


@action("macro_record", "Record a macro by watching what the user does (keys, typing, clicks, app switches): start, "
        "stop (and save) or cancel. Say 'stop recording' to finish.", "command: start|stop|cancel, name?: str")
def macro_record(command="start", name=""):
    from ..recorder import Recorder
    if command == "stop":
        return _record_stop(name)
    if command == "cancel":
        r, _rec["recorder"] = _rec["recorder"], None
        svc.state.update(macro_recording=0.0)
        if r is None:
            return "I'm not recording a macro."
        r.cancel()
        return "Okay, I threw that recording away."
    if recording():
        return "I'm already recording. Say stop recording when you're done."
    if running():
        return "A macro is running. Stop it first."
    if safety.unattended():
        return None
    r = Recorder(on_limit=_on_limit, max_seconds=float(cfg().get("record_minutes", 10) or 10) * 60)
    r.start()
    _rec.update(recorder=r, name=(name or "").strip(), pending=None)
    svc.state.update(macro_recording=time.time())
    return ("Recording. Do the steps, then say stop recording. You can ask me for things too, and they'll become "
            "steps. I don't record anything you type in sign-in or password windows.")


@action("macro_name", "Name the macro the user just recorded, or save the plan Gem just worked out, as a macro.",
        "name: str")
def macro_name(name=""):
    name = (name or "").strip()
    if not name:
        raise ActionError("What should I call it?")
    if awaiting_name():
        steps, notes, _ = _rec["pending"]
        return _save(name, steps, notes)
    if plan_recent():
        return _save(name, _last_plan["steps"])
    return "There's nothing new to save. Say record a macro first."


# ── Gem works it out ─────────────────────────────────────────────────────────

_last_plan = {"steps": [], "title": "", "t": 0.0}


@action("macro_auto", "Do a multi-step task on the PC that no single action covers (opening apps, typing, pressing "
        "keys, clicking things on screen): Gem plans the steps, shows them and runs them after the user OKs it. "
        "Not for sending messages or emails (use send_message / send_email).", "goal: str")
def macro_auto(goal=""):
    goal = (goal or "").strip()
    if not goal:
        raise ActionError("What should I work out?")
    if safety.unattended():
        return safety.skip("Work out and run: %s" % _short(goal))
    svc.state.update(thinking=True)
    try:
        plan = svc.brain.complete(PLAN.format(name=svc.config.get("user_name") or "the user",
                                              catalog=actions.catalog()),
                                  goal, json_mode=True, max_tokens=700, temperature=0.2)
    except BrainUnavailable as e:
        raise ActionError(str(e))
    plan = plan if isinstance(plan, dict) else {}
    steps = [str(s).strip() for s in plan.get("steps") or [] if str(s).strip()][:12]
    if not steps:
        return str(plan.get("question") or "I couldn't work out how to do that.")
    title = _short(str(plan.get("title") or goal), 40)
    _last_plan.update(steps=steps, title=title, t=time.time())
    routine = {"name": title.lower(), "steps": steps}
    log.info("Plan for %r: %s", goal, steps)
    if safety.cfg().get("confirm_ai_plans", True):
        return safety.ask("Run this plan", lambda: start(routine) or "Starting.", to=title, lines=steps,
                          phrase="confirm", chip="Run it")
    return start(routine)
