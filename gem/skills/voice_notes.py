"""Voice notes: "record a voice note", talk hands-free until you stop, and Gem saves the audio with a transcript.
"Play my last voice note", "read my voice notes", "find my voice note about the trip"."""
import datetime
import logging
import os
import re
import threading
import time
import wave

from ..actions import ActionError, action
from ..cards import card
from ..config import DATA_DIR, JsonStore
from ..runtime import caption, svc

log = logging.getLogger("gem.voice_notes")

NOTES_DIR = os.path.join(DATA_DIR, "voice_notes")
index = JsonStore("voice_notes.json", {"items": []})
recording = {"on": False}


def _when(t):
    dt = datetime.datetime.fromtimestamp(t)
    day = "today" if dt.date() == datetime.date.today() else dt.strftime("%A %b %d")
    return "%s at %s" % (day, dt.strftime("%I:%M %p").lstrip("0"))


def _record():
    try:
        end = time.time() + 6
        while svc.state.speaking and time.time() < end:            # don't record Gem's own voice
            time.sleep(0.1)
        time.sleep(0.25)
        if svc.sounds:
            svc.sounds.play("listen_start", force=True)
        pcm = svc.listener.capture()
        if svc.sounds:
            svc.sounds.play("listen_end", force=True)
        if not pcm:
            caption("No voice note, I didn't hear anything", seconds=3)
            return
        os.makedirs(NOTES_DIR, exist_ok=True)
        stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        path = os.path.join(NOTES_DIR, "note_%s.wav" % stamp)
        with wave.open(path, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(16000)
            w.writeframes(pcm)
        text = svc.stt.transcribe(pcm) or ""
        secs = len(pcm) / 32000
        with index as data:
            data["items"].append({"t": time.time(), "path": path, "text": text, "seconds": round(secs, 1)})
        preview = text if len(text) <= 60 else text[:57] + "..."
        caption("Voice note saved" + (": " + preview if preview else ""), seconds=4,
                card={"kind": "alert", "title": "Voice note · %ds" % secs, "message": preview or "Saved."})
        log.info("Voice note saved (%.1fs)", secs)
    finally:
        recording["on"] = False


@action("voice_note", "Record a voice note hands-free (stops when the user stops talking), saved with a transcript.")
def voice_note():
    if recording["on"]:
        return None
    if not svc.listener:
        raise ActionError("The microphone isn't ready.")
    recording["on"] = True
    threading.Thread(target=_record, name="voice-note", daemon=True).start()
    caption("Recording, go ahead. I'll stop when you do.", seconds=4)
    return None


def _items():
    return [i for i in index.data.get("items") or [] if os.path.exists(i["path"])]


def _play(path):
    import miniaudio
    stream = miniaudio.stream_file(path)
    dev = miniaudio.PlaybackDevice(app_name="Gem")
    dev.start(stream)
    with wave.open(path) as w:
        time.sleep(w.getnframes() / float(w.getframerate()) + 0.4)
    dev.close()


@action("voice_note_play", "Play a voice note: the latest, or one matching a search.", "query?: str")
def voice_note_play(query=""):
    items = _items()
    if not items:
        return "You don't have any voice notes yet. Say record a voice note."
    item = _search(items, query) if query else items[-1]
    if not item:
        return "I couldn't find a voice note like that."
    threading.Thread(target=_play, args=(item["path"],), daemon=True).start()
    return None


def _search(items, query):
    words = {w for w in re.findall(r"[a-z0-9]+", query.lower()) if len(w) > 2 and w not in ("about", "the", "note")}
    scored = [(sum(1 for w in words if w in i["text"].lower()), n, i) for n, i in enumerate(items)]
    scored = [s for s in scored if s[0]]
    return max(scored)[2] if scored else None


@action("voice_notes_list", "Read out the latest voice notes (or ones about something).", "query?: str")
def voice_notes_list(query=""):
    items = _items()
    if query:
        hit = _search(items, query)
        items = [hit] if hit else []
    if not items:
        return "No voice notes%s." % (" about that" if query else " yet")
    recent = items[-5:][::-1]
    rows = [{"icon": "dot", "text": "%s · %s" % (_when(i["t"]), (i["text"] or "(no words)")[:80])} for i in recent]
    spoken = "Your latest voice note, from %s: %s" % (_when(recent[0]["t"]), recent[0]["text"] or "no words in it.")
    return card("briefing", spoken, greeting="Voice notes", rows=rows)
