"""To-do list, notes, focus sessions, the daily briefing and long-term memory."""
import datetime
import difflib
import logging
import os
import time

from ..actions import ActionError, action
from ..cards import card
from ..config import NOTES_FILE, JsonStore
from ..runtime import svc

log = logging.getLogger("gem.productivity")

todos = JsonStore("todo.json", {"items": []})
memory = JsonStore("memory.json", {"facts": []})


# ── To-do ────────────────────────────────────────────────────────────────────

def _open_items():
    return [i for i in todos.data["items"] if not i.get("done")]


def _todo_card(text, just_done=None):
    """Open items plus whatever was just ticked off, for the checklist card."""
    rows = [{"text": i["text"], "done": False} for i in _open_items()]
    if just_done:
        rows.insert(0, {"text": just_done, "done": True})
    return card("todo", text, items=rows)


def _best(text, items):
    text = text.lower().strip()
    names = [i["text"].lower() for i in items]
    for i, n in zip(items, names):
        if text == n or text in n:
            return i
    close = difflib.get_close_matches(text, names, n=1, cutoff=0.5)
    return items[names.index(close[0])] if close else None


@action("todo_add", "Add to-do items.", "items: [str]")
def todo_add(items=None, item=None):
    items = items or ([item] if item else [])
    if isinstance(items, str):
        items = [items]
    items = [i.strip().rstrip(".") for i in items if i and i.strip()]
    if not items:
        raise ActionError("What should I add?")
    with todos as data:
        for text in items:
            data["items"].append({"text": text, "done": False, "created": time.time()})
    return _todo_card("Added %s." % " and ".join(items) if len(items) <= 2 else "Added %d items." % len(items))


@action("todo_list", "Read the to-do list.")
def todo_list():
    items = _open_items()
    if not items:
        return _todo_card("Your to-do list is empty.")
    names = [i["text"] for i in items[:8]]
    more = ", and %d more" % (len(items) - 8) if len(items) > 8 else ""
    return _todo_card("You have %d thing%s to do: %s%s." % (len(items), "" if len(items) == 1 else "s",
                                                           ", ".join(names), more))


@action("todo_done", "Mark a to-do done.", "item: str")
def todo_done(item=""):
    with todos as data:
        hit = _best(item, [i for i in data["items"] if not i.get("done")])
        if not hit:
            return "I couldn't find %s on your list." % item
        hit["done"] = True
        hit["done_at"] = time.time()
    left = len(_open_items())
    return _todo_card("Done: %s. %s" % (hit["text"], "That's everything." if not left else "%d left." % left),
                      just_done=hit["text"])


@action("todo_remove", "Delete a to-do, or clear finished ones.", "item?: str, clear_done?: bool")
def todo_remove(item="", clear_done=False):
    with todos as data:
        if clear_done:
            before = len(data["items"])
            data["items"] = [i for i in data["items"] if not i.get("done")]
            return "Cleared %d finished item%s." % (before - len(data["items"]), "" if before - len(data["items"]) == 1 else "s")
        hit = _best(item, data["items"])
        if not hit:
            return "I couldn't find %s on your list." % item
        data["items"].remove(hit)
    return "Removed %s." % hit["text"]


# ── Notes ────────────────────────────────────────────────────────────────────

@action("note_add", "Save a note.", "text: str")
def note_add(text=""):
    text = (text or "").strip()
    if not text:
        raise ActionError("What should the note say?")
    with open(NOTES_FILE, "a", encoding="utf-8") as f:
        f.write("- %s  %s\n" % (datetime.datetime.now().strftime("%Y-%m-%d %H:%M"), text))
    return "Noted."


@action("notes_read", "Read recent notes.", "count?: number")
def notes_read(count=3):
    if not os.path.exists(NOTES_FILE):
        return "You don't have any notes yet."
    with open(NOTES_FILE, "r", encoding="utf-8") as f:
        lines = [l.strip()[2:] for l in f if l.startswith("- ")]
    if not lines:
        return "You don't have any notes yet."
    recent = [l.split("  ", 1)[-1] for l in lines[-int(count or 3):]]
    return "Your latest notes: " + ". ".join(recent) + "."


@action("notes_open", "Open the notes file.", ai=False)
def notes_open():
    if not os.path.exists(NOTES_FILE):
        open(NOTES_FILE, "a", encoding="utf-8").close()
    os.startfile(NOTES_FILE)
    return "Opening your notes."


# ── Focus sessions ───────────────────────────────────────────────────────────

@action("focus_start", "Start a focus/pomodoro session.", "minutes?: number")
def focus_start(minutes=None):
    minutes = float(minutes or svc.config["focus"].get("work_minutes", 25))
    svc.state.update(focus_until=time.time() + minutes * 60)
    return card("focus", "Focus session started for %g minute%s." % (minutes, "" if minutes == 1 else "s"),
                ends_at=svc.state.focus_until,
                total=minutes * 60, phase="focus")


@action("focus_stop", "End the focus session.")
def focus_stop():
    if not svc.state.focusing:
        return "No focus session is running."
    svc.state.update(focus_until=0.0)
    return "Focus session ended."


@action("focus_status", "How long is left in the focus session.", ai=False)
def focus_status():
    if not svc.state.focusing:
        return "No focus session is running."
    from ..parse import duration_phrase
    left = svc.state.focus_until - time.time()
    total = float(svc.config["focus"].get("work_minutes", 25)) * 60
    return card("focus", "%s left in this session." % duration_phrase(left - left % 60 or left).capitalize(),
                ends_at=svc.state.focus_until, total=max(total, left), phase="focus")


# ── Briefing ─────────────────────────────────────────────────────────────────

@action("briefing", "Daily briefing: date, weather, schedule, reminders, to-dos.")
def briefing():
    from . import timers, web
    now = datetime.datetime.now()
    part = "evening" if now.hour < 5 else "morning" if now.hour < 12 else "afternoon" if now.hour < 18 else "evening"
    name = svc.config.get("user_name") or ""
    greeting = "Good %s%s" % (part, ", " + name if name else "")
    lines = ["%s. It's %s, %s." % (greeting, now.strftime("%A, %B %d").replace(" 0", " "),
                                   now.strftime("%I:%M %p").lstrip("0"))]
    rows = []
    if svc.config.get("home_city"):
        try:
            w = web.weather()
            lines.append(w)
            wc = getattr(w, "card", None) or {}
            if wc.get("kind") == "weather":
                rows.append({"icon": "weather", "code": wc.get("code", 1),
                             "text": "%d° and %s · high %d°, %d%% rain" % (
                                 wc.get("temp", 0), wc.get("desc", ""), wc.get("high", 0), wc.get("rain", 0))})
        except Exception as e:
            log.warning("Briefing weather failed: %s", e)
    sched = timers.schedule_list("today")
    lines.append(sched)
    for r in (getattr(sched, "card", None) or {}).get("rows", []):
        rows.append({"icon": "class", "text": "%s  %s" % (r["time"], r["name"].capitalize())})
    today_items = [i for i in timers._items() if datetime.datetime.fromtimestamp(i["at"]).date() == now.date()]
    if today_items:
        lines.append("You also have " + ", ".join(timers._describe(i, now) for i in today_items[:3]) + ".")
        for i in today_items[:3]:
            rows.append({"icon": "bell", "text": timers._describe(i, now).capitalize()})
    open_todos = _open_items()
    if open_todos:
        lines.append("%d thing%s on your to-do list, starting with %s." % (
            len(open_todos), "" if len(open_todos) == 1 else "s", open_todos[0]["text"]))
        rows.append({"icon": "todo", "text": "%d to-do%s · %s" % (len(open_todos), "" if len(open_todos) == 1 else "s",
                                                                 ", ".join(i["text"] for i in open_todos[:3]))})
    if not rows:
        rows.append({"icon": "todo", "text": "Nothing scheduled. A clear day."})
    return card("briefing", " ".join(lines), greeting=greeting + ".", rows=rows)


# ── Memory ───────────────────────────────────────────────────────────────────

@action("remember", "Remember a fact about the user.", "fact: str")
def remember(fact=""):
    fact = (fact or "").strip().rstrip(".")
    if not fact:
        raise ActionError("What should I remember?")
    with memory as data:
        if fact not in data["facts"]:
            data["facts"].append(fact)
    return "Got it, I'll remember that."


@action("forget", "Forget remembered facts.", "about: str")
def forget(about=""):
    about = about.lower().strip()
    with memory as data:
        before = len(data["facts"])
        if about in ("everything", "all"):
            data["facts"] = []
        else:
            data["facts"] = [f for f in data["facts"] if about not in f.lower()]
        removed = before - len(data["facts"])
    return "Forgotten." if removed else "I didn't have anything about that."


@action("memories", "List remembered facts.")
def memories():
    facts = memory.data.get("facts") or []
    if not facts:
        return "I haven't been asked to remember anything yet."
    return "I remember that " + "; ".join(facts[-6:]) + "."
