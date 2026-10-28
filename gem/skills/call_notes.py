"""Call notes: "take notes" records the call, your mic and what the PC plays (the others, a class, a video), and
when it ends Gem writes a notes file, summary at the top and the transcript below, next to an MP3 of the whole call.

Both go to Documents\\Gem Notes and the notes file opens in Notepad. The two sides are transcribed separately, so
the transcript says who spoke ("You" or "Others"); silence is cut out first, which keeps it inside Groq's free
speech-to-text allowance. The recording stays on the PC: only the speech goes to Groq, and the transcript to the AI
for the summary.
"""
import datetime
import difflib
import logging
import os
import queue
import re
import shutil
import threading
import time

import numpy as np
import requests

from ..actions import ActionError, action
from ..brain import BrainUnavailable
from ..config import DATA_DIR
from ..runtime import caption, notify, say, svc

log = logging.getLogger("gem.call_notes")

RATE = 16000                    # both tracks, the MP3 and what's sent to be transcribed
GROQ_URL = "https://api.groq.com/openai/v1/audio/transcriptions"
PIECE_SECONDS = 600             # speech sent to Whisper per request
GAP = 0.4                       # silence put between the stretches of speech in what's sent

_rec = None                     # the Recorder while taking notes
_lock = threading.Lock()


def cfg():
    return (svc.config or {}).get("call_notes") or {}


def folder():
    from ..winapi import known_folder
    return os.path.join(known_folder("documents"), "Gem Notes")


# ── Recording ────────────────────────────────────────────────────────────────

class _Resampler:
    """Any rate (the speakers' 48 kHz, say) to 16 kHz, chunk by chunk: low-pass, then interpolate."""

    def __init__(self, src_rate, dst_rate=RATE):
        self.step = float(src_rate) / dst_rate
        n = np.arange(63) - 31
        fc = 7000.0 / src_rate
        self.kernel = (2 * fc * np.sinc(2 * fc * n) * np.hamming(63)).astype(np.float32)
        self.tail = np.zeros(62, np.float32)
        self.prev = np.zeros(0, np.float32)
        self.pos = 0.0

    def __call__(self, x):
        buf = np.concatenate([self.tail, x.astype(np.float32)])
        self.tail = buf[-62:]
        z = np.concatenate([self.prev, np.convolve(buf, self.kernel, "valid")])
        idx = np.arange(self.pos, len(z) - 1, self.step)
        out = np.interp(idx, np.arange(len(z)), z) if len(idx) else np.zeros(0, np.float32)
        nxt = idx[-1] + self.step if len(idx) else self.pos
        keep = int(nxt)
        self.prev, self.pos = z[keep:], nxt - keep
        return out


class _Track:
    """One side of the call written to a raw 16 kHz file. Stretches with no sound (the speakers send nothing while
    nothing plays) are filled with silence by the clock, so both sides stay in step."""

    def __init__(self, path, start):
        self.path, self.start = path, start
        self.f = open(path, "wb")
        self.written = 0
        self.q = queue.Queue()

    def put(self, samples):
        self.q.put(samples)

    def drain(self, final_samples=None):
        while True:
            try:
                chunk = self.q.get_nowait()
            except queue.Empty:
                break
            due = int((time.time() - self.start) * RATE) - len(chunk)
            if due - self.written > RATE * 0.3:
                self._write(np.zeros(due - self.written, np.int16))
            self._write(chunk)
        if final_samples is not None and final_samples > self.written:
            self._write(np.zeros(final_samples - self.written, np.int16))

    def _write(self, a):
        self.f.write(a.astype(np.int16).tobytes())
        self.written += len(a)

    def close(self):
        self.f.close()


class Recorder:
    def __init__(self):
        self.started = time.time()
        self.stamp = datetime.datetime.now()
        self.tmp = os.path.join(DATA_DIR, "call_notes_tmp", self.stamp.strftime("%Y%m%d-%H%M%S"))
        os.makedirs(self.tmp, exist_ok=True)
        self.mic = _Track(os.path.join(self.tmp, "mic.raw"), self.started)
        self.pc = _Track(os.path.join(self.tmp, "pc.raw"), self.started)
        self.app = getattr(svc.state, "call_app", "") if svc.state and svc.state.in_call else ""
        self.saw_call = bool(svc.state and svc.state.in_call)
        self.stopped = threading.Event()
        self.ended = 0.0
        self._pa = None
        self._streams = []

    def start(self):
        import pyaudiowpatch as pyaudio
        self._pa = pa = pyaudio.PyAudio()
        mic_index = _find_mic(pa, ((svc.config or {}).get("listening") or {}).get("input_device", ""))

        def on_mic(data, frames, info, status):
            self.mic.put(np.frombuffer(data, np.int16).copy())
            return None, pyaudio.paContinue
        self._streams.append(pa.open(format=pyaudio.paInt16, channels=1, rate=RATE, input=True,
                                     input_device_index=mic_index, frames_per_buffer=1600, stream_callback=on_mic))
        try:
            lb = pa.get_default_wasapi_loopback()
            ch, rate = max(1, int(lb["maxInputChannels"])), int(lb["defaultSampleRate"])
            resample = _Resampler(rate)

            def on_pc(data, frames, info, status):
                x = np.frombuffer(data, np.int16).reshape(-1, ch).astype(np.float32).mean(axis=1)
                self.pc.put(np.clip(resample(x), -32768, 32767).astype(np.int16))
                return None, pyaudio.paContinue
            self._streams.append(pa.open(format=pyaudio.paInt16, channels=ch, rate=rate, input=True,
                                         input_device_index=lb["index"], frames_per_buffer=int(rate / 10),
                                         stream_callback=on_pc))
            log.info("Taking notes: mic and %s", lb["name"])
        except Exception:
            log.exception("Couldn't record the PC's sound; taking notes from the mic only")
        threading.Thread(target=self._write_loop, name="notes-rec", daemon=True).start()

    def _write_loop(self):
        while not self.stopped.wait(0.25):
            self.mic.drain()
            self.pc.drain()

    def stop(self):
        self.ended = time.time()
        self.stopped.set()
        for s in self._streams:
            try:
                s.stop_stream()
                s.close()
            except Exception:
                pass
        if self._pa:
            self._pa.terminate()
        total = int((self.ended - self.started) * RATE)
        for t in (self.mic, self.pc):
            t.drain(total)
            t.close()


def _find_mic(pa, want):
    want = (want or "").lower()
    if want:
        for i in range(pa.get_device_count()):
            info = pa.get_device_info_by_index(i)
            if info.get("maxInputChannels", 0) > 0 and want in info["name"].lower() and \
                    not info.get("isLoopbackDevice"):
                return i
    return None


# ── Turning it into notes ────────────────────────────────────────────────────

def _speech_regions(track, vad=None, frame=480):
    """[(start, end)] in samples where someone is talking: loud enough, and speech to webrtcvad when there is one."""
    n = len(track) // frame
    talk = np.zeros(n, bool)
    for i in range(n):
        f = track[i * frame:(i + 1) * frame]
        if np.sqrt(np.mean(f.astype(np.float32) ** 2)) > 250:
            talk[i] = vad.is_speech(f.tobytes(), RATE) if vad else True
    regions, start, quiet = [], None, 0
    for i, t in enumerate(talk):
        if t:
            start = i if start is None else start
            quiet = 0
        elif start is not None:
            quiet += 1
            if quiet * frame > RATE * 0.6:
                regions.append((start, i - quiet + 1))
                start, quiet = None, 0
    if start is not None:
        regions.append((start, n))
    pad = int(RATE * 0.25)
    out = [(max(0, s * frame - pad), min(len(track), e * frame + pad)) for s, e in regions
           if (e - s) * frame >= RATE * 0.4]
    merged = []
    for s, e in out:
        if merged and s <= merged[-1][1]:
            merged[-1] = (merged[-1][0], e)
        else:
            merged.append((s, e))
    return merged


def _pieces(regions, limit=PIECE_SECONDS):
    """Group speech into requests of at most `limit` seconds: [[(start, end), ...], ...]."""
    out, cur, length = [], [], 0.0
    for s, e in regions:
        dur = (e - s) / RATE + GAP
        if cur and length + dur > limit:
            out.append(cur)
            cur, length = [], 0.0
        cur.append((s, e))
        length += dur
    if cur:
        out.append(cur)
    return out


def _compact(track, piece):
    """The piece's speech back to back (GAP apart), and how its times map to the call: [(at, call_start, len)]."""
    gap = np.zeros(int(RATE * GAP), np.int16)
    parts, where, at = [], [], 0.0
    for s, e in piece:
        parts += [np.asarray(track[s:e], np.int16), gap]
        where.append((at, s / RATE, (e - s) / RATE))
        at += (e - s) / RATE + GAP
    return np.concatenate(parts) if parts else np.zeros(0, np.int16), where


def _to_call_time(t, where):
    for at, start, length in where:
        if t < at + length + GAP:
            return start + max(0.0, min(t - at, length))
    return where[-1][1] + where[-1][2] if where else t


def _mp3(samples, kbps=32):
    import lameenc
    enc = lameenc.Encoder()
    enc.set_bit_rate(kbps)
    enc.set_in_sample_rate(RATE)
    enc.set_channels(1)
    enc.set_quality(2)
    out = bytearray()
    for i in range(0, len(samples), RATE * 30):
        out += enc.encode(np.asarray(samples[i:i + RATE * 30], np.int16).tobytes())
    return bytes(out + enc.flush())


def _whisper(mp3):
    """Segments [{start, end, text, ...}] for one piece, waiting out rate limits a few times."""
    key = os.environ.get("GROQ_API_KEY", "")
    if not key:
        raise RuntimeError("no Groq key")
    models = ((svc.config or {}).get("stt") or {}).get("groq_models") or ["whisper-large-v3-turbo"]
    for attempt in range(6):
        wait = 20.0
        for model in models:
            r = requests.post(GROQ_URL, headers={"Authorization": "Bearer " + key}, timeout=180,
                              files={"file": ("call.mp3", mp3, "audio/mpeg")},
                              data={"model": model, "response_format": "verbose_json", "temperature": "0"})
            if r.status_code == 429:
                wait = min(wait, float(r.headers.get("retry-after") or 20))
                log.info("Whisper %s busy for %.0fs", model, wait)
                continue
            if r.status_code >= 400:
                log.warning("Whisper %s error %s: %s", model, r.status_code, r.text[:200])
                continue
            return r.json().get("segments") or []
        time.sleep(min(60.0, wait + 1))
    raise RuntimeError("speech-to-text kept refusing")


def _transcribe(track, speaker):
    """[(call seconds, speaker, text)] for one side of the call."""
    from ..stt import HALLUCINATIONS, _plain
    try:
        import webrtcvad
        vad = webrtcvad.Vad(2)
    except Exception:
        vad = None
    lines = []
    for piece in _pieces(_speech_regions(track, vad)):
        audio, where = _compact(track, piece)
        try:
            segments = _whisper(_mp3(audio))
        except Exception as e:
            log.warning("Couldn't transcribe part of the call (%s): %s", speaker, e)
            lines.append((where[0][1], speaker, "[this part couldn't be transcribed]"))
            continue
        for seg in segments:
            text = (seg.get("text") or "").strip()
            if not text or (seg.get("no_speech_prob", 0) > 0.6 and seg.get("avg_logprob", 0) < -0.7):
                continue
            if _plain(text) in HALLUCINATIONS and seg.get("end", 0) - seg.get("start", 0) < 3:
                continue
            lines.append((_to_call_time(float(seg.get("start", 0)), where), speaker, text))
    return lines


def _merge(mine, theirs):
    """One transcript in time order. Your lines that repeat the others' words at the same moment are the speakers
    leaking into your mic, so they go; back-to-back lines from the same person are joined."""
    def norm(s):
        return re.sub(r"[^a-z0-9 ]", "", s.lower())
    kept = [m for m in mine if not any(abs(m[0] - o[0]) < 4 and difflib.SequenceMatcher(
        None, norm(m[2]), norm(o[2])).ratio() > 0.6 for o in theirs)]
    out = []
    for t, who, text in sorted(kept + theirs, key=lambda x: x[0]):
        if out and out[-1][1] == who and t - out[-1][3] < 8:
            out[-1] = (out[-1][0], who, out[-1][2] + " " + text, t)
        else:
            out.append((t, who, text, t))
    return [(t, who, text) for t, who, text, _ in out]


def _clock(seconds):
    s = int(seconds)
    return "%d:%02d:%02d" % (s // 3600, s // 60 % 60, s % 60) if s >= 3600 else "%02d:%02d" % (s // 60, s % 60)


def _ask_ai(instruction, text, max_tokens=700):
    """The AI's answer, waiting out per-minute limits for up to a few minutes (the notes aren't urgent)."""
    for _ in range(10):
        try:
            return svc.brain.complete(instruction, text, max_tokens=max_tokens, temperature=0.2)
        except BrainUnavailable:
            time.sleep(min(60.0, max(5.0, getattr(svc.brain, "busy_until", 0) - time.time() + 1)))
    raise BrainUnavailable("busy")


SUMMARY_PROMPT = (
    "These are notes from a call or class. Lines marked You are the user; Others are everyone else (the PC's sound). "
    "Write the top of a plain-text notes file, exactly in this shape:\n"
    "TITLE: a short title\n\nSUMMARY\n- three to six short points\n\nACTION ITEMS\n- what needs doing, by whom "
    "and by when (or \"- None\")\n\nDATES\n- deadlines, meetings and dates mentioned (or \"- None\")\n"
    "No markdown, no bold, nothing else.")


def _summary(lines):
    text = "\n".join("[%s] %s: %s" % (_clock(t), who, said) for t, who, said in lines)
    parts, cur = [], ""
    for line in text.splitlines():
        if len(cur) + len(line) > 10000 and cur:
            parts.append(cur)
            cur = ""
        cur += line + "\n"
    parts.append(cur)
    if len(parts) > 1:            # a long call: notes on each part first, then on the whole
        text = "\n\n".join(_ask_ai("Make detailed notes of this part of a call or class: the points made, "
                                   "decisions, homework and dates. Plain text, short lines.", p) for p in parts)
    return _ask_ai(SUMMARY_PROMPT, text)


def _write_files(rec, lines, summary, mix):
    os.makedirs(folder(), exist_ok=True)
    name = rec.stamp.strftime("%Y-%m-%d %H-%M") + (" %s" % re.sub(r'[\\/:*?"<>|]', "", rec.app) if rec.app else "")
    base = os.path.join(folder(), name + " notes")
    n = 2
    while os.path.exists(base + ".txt") or os.path.exists(base + ".mp3"):
        base = os.path.join(folder(), "%s notes (%d)" % (name, n))
        n += 1
    with open(base + ".mp3", "wb") as f:
        f.write(_mp3(mix, kbps=48))
    title = "Call notes"
    m = re.match(r"\s*TITLE:\s*(.+)", summary or "")
    if m:
        title, summary = m.group(1).strip(), summary[m.end():].strip()
    minutes = max(1, int(round((rec.ended - rec.started) / 60)))
    head = [title, "%s · %d minute%s%s" % (rec.stamp.strftime("%A %d %B %Y, %I:%M %p").replace(" 0", " "), minutes,
                                           "" if minutes == 1 else "s", " · " + rec.app if rec.app else ""),
            "Recording: " + os.path.basename(base + ".mp3"), ""]
    body = (summary or "The summary couldn't be written (the AI wasn't available), but the transcript is below.")
    transcript = ["[%s] %s: %s" % (_clock(t), who, said) for t, who, said in lines] or ["No speech was heard."]
    with open(base + ".txt", "w", encoding="utf-8") as f:
        f.write("\n".join(head + [body, "", "-" * 60, "TRANSCRIPT", ""] + transcript) + "\n")
    return base + ".txt", title


def _process(rec):
    svc.state.update(notes_writing=True)
    try:
        mic = np.memmap(rec.mic.path, np.int16, mode="r") if rec.mic.written else np.zeros(0, np.int16)
        pc = np.memmap(rec.pc.path, np.int16, mode="r") if rec.pc.written else np.zeros(0, np.int16)
        n = max(len(mic), len(pc))
        mix = np.zeros(n, np.int16)
        for i in range(0, n, RATE * 60):          # a minute at a time: long calls don't need much memory
            a = np.zeros(min(RATE * 60, n - i), np.int32)
            a[:max(0, min(len(mic) - i, len(a)))] += mic[i:i + len(a)]
            a[:max(0, min(len(pc) - i, len(a)))] += pc[i:i + len(a)]
            mix[i:i + len(a)] = np.clip(a, -32768, 32767)
        lines, summary = [], ""
        try:
            lines = _merge(_transcribe(mic, "You"), _transcribe(pc, "Others"))
        except Exception:
            log.exception("Transcribing the call failed")
        if lines:
            try:
                summary = _summary(lines)
            except Exception:
                log.exception("Summarizing the call failed")
        path, title = _write_files(rec, lines, summary, mix)
        del mic, pc
        shutil.rmtree(rec.tmp, ignore_errors=True)
        log.info("Call notes saved: %s", path)
        try:
            os.startfile(path)
        except Exception:
            pass
        notify("Call notes ready", "%s, saved in Documents\\Gem Notes." % title, speak=False)
        say("Your notes are ready: %s." % title)
    except Exception:
        log.exception("Writing the call notes failed")
        say("Sorry, I couldn't finish the notes. The recording is in %s." % rec.tmp)
    finally:
        svc.state.update(notes_writing=False)


# ── Starting and stopping ────────────────────────────────────────────────────

def _on_state(state, changed):
    rec = _rec
    if rec is None:
        return
    if changed.get("in_call"):
        rec.saw_call = True
        rec.app = rec.app or getattr(state, "call_app", "")
    elif "in_call" in changed and rec.saw_call:
        # The call ended: wait a moment in case it's only switching devices, then finish.
        threading.Timer(8.0, lambda: (not svc.state.in_call and _rec is rec) and _finish("The call ended")).start()


_subscribed = [False]


def _finish(why=""):
    global _rec
    with _lock:
        rec, _rec = _rec, None
    if rec is None:
        return None
    rec.stop()
    svc.state.update(notes_since=0.0)
    log.info("Stopped taking notes (%s)", why or "asked")
    threading.Thread(target=_process, args=(rec,), name="notes", daemon=True).start()
    text = "%s. I'm writing your notes; they'll open when they're ready." % (why or "Done")
    if why:                                         # stopped by itself: nobody asked, so show it
        caption(text, seconds=5)
    return text


def _watchdog(rec):
    limit = float(cfg().get("max_minutes", 180) or 180) * 60
    while not rec.stopped.wait(5):
        if time.time() - rec.started > limit:
            _finish("That's %d minutes, the most I record at once" % (limit // 60))
            return


@action("call_notes_start", "Take notes on a call, class or video: record it (mic and PC sound) until it ends or the "
        "user says stop, then save a transcript with a summary on top and an MP3.")
def call_notes_start():
    global _rec
    with _lock:
        if _rec is not None:
            return "I'm already taking notes."
        rec = Recorder()
        try:
            rec.start()
        except Exception as e:
            log.exception("Couldn't start recording")
            shutil.rmtree(rec.tmp, ignore_errors=True)
            raise ActionError("I couldn't start recording: %s" % e)
        _rec = rec
    if not _subscribed[0]:
        svc.state.subscribe(_on_state)
        _subscribed[0] = True
    svc.state.update(notes_since=rec.started)
    threading.Thread(target=_watchdog, args=(rec,), name="notes-watch", daemon=True).start()
    when = "when the call ends" if rec.saw_call else "when you say stop taking notes"
    return "Taking notes. I'll stop %s. Let the others know it's being recorded." % when


@action("call_notes_stop", "Stop taking call notes and write them up.")
def call_notes_stop():
    if _rec is None:
        return "I'm not taking notes right now."
    return _finish()


def taking_notes():
    return _rec is not None
