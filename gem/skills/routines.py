"""Routines: one phrase runs a list of ordinary commands.

Steps are written the way you'd say them ("close fortnite", "start a focus
session"), so they can be made by voice or typed in the dashboard. Each step
goes through the normal pipeline: the instant router first, the AI if needed.
"""
import difflib
import logging
import re

from ..actions import ActionError, action
from ..cards import card
from ..config import JsonStore
from ..runtime import svc

log = logging.getLogger("gem.routines")

EXAMPLES = [
    {"name": "study mode", "phrases": ["study mode", "time to study", "start studying"],
     "steps": ["close fortnite", "close roblox", "open google classroom", "set discord volume to 20",
               "start a focus session"]},
]

store = JsonStore("routines.json", {"routines": EXAMPLES})


def _norm(text):
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9' ]+", " ", (text or "").lower())).strip()


def all_routines():
    with store as data:
        return [dict(r) for r in data.get("routines", [])]


def find(norm_text):
    """The routine whose name or trigger phrase is exactly what was said (also "run X")."""
    t = re.sub(r"^(?:run|start|do|activate|begin)\s+(?:my\s+|the\s+)?", "", _norm(norm_text))
    t = re.sub(r"\s+routine$", "", t)
    for r in all_routines():
        names = [_norm(r["name"])] + [_norm(p) for p in r.get("phrases", [])]
        if t in names:
            return r
    return None


def _lookup(name):
    routines = all_routines()
    names = [_norm(r["name"]) for r in routines]
    n = _norm(name)
    if n in names:
        return routines[names.index(n)]
    close = difflib.get_close_matches(n, names, n=1, cutoff=0.6)
    return routines[names.index(close[0])] if close else None


def run(routine):
    steps, done = [], 0
    for step in routine.get("steps", []):
        ok, _ = svc.assistant.execute(step)
        steps.append({"text": step, "ok": ok})
        done += ok
    name = routine["name"]
    if done == len(steps):
        text = "%s is on." % name.capitalize() if name.endswith("mode") else "Done: %s." % name
    else:
        text = "%s: %d of %d steps worked." % (name.capitalize(), done, len(steps))
    return card("routine", text, name=name, steps=steps)


@action("routine_run", "Run one of the user's routines.", "name: str")
def routine_run(name=""):
    r = _lookup(name)
    if not r:
        raise ActionError("I don't have a routine called %s." % name)
    return run(r)


@action("routine_create", "Create or replace a routine: a name, the commands it runs in order (as the user would "
        "say them), and optional extra trigger phrases.", "name: str, steps: [str], phrases?: [str]")
def routine_create(name="", steps=None, phrases=None):
    if isinstance(steps, str):
        steps = [s.strip() for s in re.split(r",|\bthen\b|\band then\b", steps) if s.strip()]
    steps = [s.strip() for s in (steps or []) if s and s.strip()]
    name = _norm(name)
    if not name or not steps:
        raise ActionError("I need a name and at least one step for the routine.")
    phrases = [_norm(p) for p in (phrases or []) if p and _norm(p)]
    with store as data:
        data["routines"] = [r for r in data["routines"] if _norm(r["name"]) != name]
        data["routines"].append({"name": name, "phrases": phrases, "steps": steps})
    return card("routine", "Saved. Say %s to run it." % name, name=name,
                steps=[{"text": s, "ok": True} for s in steps])


@action("routine_delete", "Delete a routine.", "name: str")
def routine_delete(name=""):
    r = _lookup(name)
    if not r:
        return "I don't have a routine called %s." % name
    with store as data:
        data["routines"] = [x for x in data["routines"] if _norm(x["name"]) != _norm(r["name"])]
    name = r["name"]
    return "Deleted %s." % name if name.endswith("routine") else "Deleted the %s routine." % name


@action("routine_list", "List the user's routines.")
def routine_list():
    routines = all_routines()
    if not routines:
        return "You don't have any routines yet."
    return "Your routines: %s." % ", ".join(r["name"] for r in routines)
