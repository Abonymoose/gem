"""Gem's voice.

Default engine: Piper, a neural voice that runs on this PC. It starts speaking
in a fraction of a second, works offline and always sounds the same. The
online Microsoft voices (edge-tts) are still available in Settings; they
sound a little richer but can take seconds to start.

Every reply also appears in the island. When Gem is speaking, the card shows
the moment the voice starts so the two line up. Speech can be cut off at any
moment with stop() — tapping Caps Lock does that.
"""
import asyncio
import hashlib
import logging
import os
import queue
import re
import threading
import time

import miniaudio
import numpy as np

from . import voices
from .config import VOICE_CACHE_DIR

log = logging.getLogger("gem.tts")

_CACHE_MAX_CHARS = 120
_CACHE_MAX_FILES = 400
_EDGE_RATE = 24000            # edge-tts sends 24 kHz mono MP3
_FIRST_AUDIO_TIMEOUT = 2.5    # seconds before a stuck online request is retried
_START_BUFFER = 5000          # MP3 bytes (~0.8 s) buffered before online playback starts
_CAPTION_WAIT = 1.2           # longest the card waits for the voice
DEFAULT_PIPER = "en_US-amy-medium"


def clean_for_speech(text):
    text = re.sub(r"https?://\S+", "the link", text)
    text = re.sub(r"[*_`#>|~]+", "", text)
    text = re.sub(r"^\s*[-•]\s+", "", text, flags=re.M)
    text = re.sub(r"[\U0001F000-\U0001FFFF☀-➿]", "", text)
    return re.sub(r"\s+", " ", text).strip()


def split_sentences(text, limit=220):
    """Sentence chunks; the first is kept short so the voice starts quickly."""
    parts = re.split(r"(?<=[.!?])\s+", text)
    chunks, cur = [], ""
    for p in parts:
        cap = 90 if not chunks else limit
        if cur and len(cur) + len(p) > cap:
            chunks.append(cur)
            cur = p
        else:
            cur = (cur + " " + p).strip()
    if cur:
        chunks.append(cur)
    if chunks and len(chunks[0]) > 110:
        head, sep, tail = chunks[0].partition(", ")
        if sep and 15 < len(head) < 90:
            chunks[0:1] = [head + ",", tail]
    return chunks


def _speed(rate):
    m = re.match(r"([+-]\d+)%", rate or "+0%")
    return 1.0 + (int(m.group(1)) / 100.0 if m else 0.0)


class _Mp3Stream(miniaudio.StreamableSource):
    """MP3 bytes arriving from the network, readable by the decoder as they come in."""

    def __init__(self):
        self._q = queue.Queue()
        self._buf = bytearray()
        self.data = bytearray()
        self.eof = False
        self.failed = False
        self.first = threading.Event()
        self.done = threading.Event()

    def feed(self, chunk):
        self.data.extend(chunk)
        self._q.put(chunk)
        self.first.set()

    def end(self, failed=False):
        self.failed = self.failed or failed
        self._q.put(None)
        self.first.set()
        self.done.set()

    def buffered(self):
        return len(self.data)

    def read(self, num_bytes):
        while len(self._buf) < num_bytes and not self.eof:
            item = self._q.get()
            if item is None:
                self.eof = True
            else:
                self._buf.extend(item)
        out = bytes(self._buf[:num_bytes])
        del self._buf[:num_bytes]
        return out


class _Pcm:
    """16-bit mono PCM chunks from the local voice, handed to the player as they're made."""

    def __init__(self):
        self.q = queue.Queue()
        self.first = threading.Event()
        self.cancelled = False

    def put(self, data):
        self.q.put(data)
        self.first.set()

    def end(self):
        self.q.put(None)
        self.first.set()


class Voice:
    def __init__(self, state, cfg, on_caption=None):
        self.state = state
        self.cfg = cfg
        self.on_caption = on_caption
        self.last_text = ""
        self._queue = queue.Queue()
        self._gen = 0
        self._device = None
        self._streams = []
        self._current_pcm = None
        self._sapi = None
        self._piper = None
        self._piper_name = None
        self._piper_loading = False
        self._loop = asyncio.new_event_loop()
        os.makedirs(VOICE_CACHE_DIR, exist_ok=True)
        threading.Thread(target=self._loop.run_forever, name="voice-net", daemon=True).start()
        threading.Thread(target=self._run, name="voice", daemon=True).start()
        self._ensure_piper()

    # ── Public API ───────────────────────────────────────────────────────────

    def say(self, text, caption_only=False, card=None):
        text = clean_for_speech(text or "")
        if not text:
            return
        self.last_text = text
        speaking = not caption_only and self.state.can_speak()
        seconds = max(4.0, len(text) / 12.0) * (1.0 if speaking else 1.8)
        if not speaking:
            if self.on_caption:
                self.on_caption(text, seconds, card)
            return
        self._queue.put((self._gen, text, card, seconds))

    def stop(self):
        self._gen += 1
        try:
            while True:
                _, text, card, seconds = self._queue.get_nowait()
                if self.on_caption:                 # still show what was going to be said
                    self.on_caption(text, seconds, card)
        except queue.Empty:
            pass
        for s in list(self._streams):
            s.end()
        if self._current_pcm is not None:
            self._current_pcm.cancelled = True
            self._current_pcm.end()
        dev = self._device
        if dev is not None:
            try:
                dev.stop()
            except Exception:
                pass
        if self._sapi is not None:
            try:
                self._sapi.Speak("", 3)
            except Exception:
                pass

    @property
    def busy(self):
        return self.state.speaking or not self._queue.empty()

    def preview(self, text):
        """Speak a sample in the currently chosen voice, waiting for a local voice to load first."""
        def run():
            if self._engine() == "piper":
                want = self.cfg.get("piper_voice") or DEFAULT_PIPER
                end = time.time() + 60
                while self._piper_name != want and time.time() < end:
                    self._ensure_piper()
                    time.sleep(0.1)
            self.stop()
            self.say(text)
        threading.Thread(target=run, name="voice-preview", daemon=True).start()

    # ── Local voice (Piper) ──────────────────────────────────────────────────

    def _engine(self):
        return self.cfg.get("engine", "piper")

    def _ensure_piper(self):
        """Load (downloading if needed) the chosen local voice in the background."""
        name = self.cfg.get("piper_voice") or DEFAULT_PIPER
        if self._engine() != "piper" or self._piper_loading or (self._piper is not None and self._piper_name == name):
            return
        self._piper_loading = True

        def load():
            try:
                if not voices.ensure(name):
                    return
                from piper import PiperVoice
                t = time.time()
                v = PiperVoice.load(voices.model_path(name))
                for _ in v.synthesize("Ready."):        # the first run is slow; get it out of the way
                    pass
                self._piper, self._piper_name = v, name
                log.info("Local voice %s ready in %.1fs", name, time.time() - t)
            except Exception:
                log.exception("Could not load local voice %s", name)
            finally:
                self._piper_loading = False

        threading.Thread(target=load, name="voice-load", daemon=True).start()

    def _speak_piper(self, gen, text, show):
        from piper import SynthesisConfig
        voice, name = self._piper, self._piper_name
        pcm = _Pcm()
        self._current_pcm = pcm
        rate = self.cfg.get("rate")
        syn = SynthesisConfig(length_scale=1.0 / max(0.5, _speed(rate)))
        key = "%s|%s|%s" % (name, rate, text)
        path = os.path.join(VOICE_CACHE_DIR, hashlib.sha1(key.encode("utf-8")).hexdigest() + ".pcm") \
            if len(text) <= _CACHE_MAX_CHARS else None

        def produce():
            made = bytearray()
            try:
                if path and os.path.exists(path):          # said this before: instant
                    with open(path, "rb") as f:
                        pcm.put(f.read())
                    return
                for part in self._piper_parts(text):
                    for chunk in voice.synthesize(part, syn_config=syn):
                        if pcm.cancelled:
                            return
                        pcm.put(chunk.audio_int16_bytes)
                        made.extend(chunk.audio_int16_bytes)
                if path and made:
                    with open(path, "wb") as f:
                        f.write(bytes(made))
                    self._prune_cache()
            except Exception:
                log.exception("Local voice failed")
            finally:
                pcm.end()

        threading.Thread(target=produce, name="voice-synth", daemon=True).start()
        try:
            if not pcm.first.wait(6) or gen != self._gen:
                return
            show()
            self._play(gen, self._pcm_frames(pcm), voice.config.sample_rate)
        finally:
            self._current_pcm = None

    @staticmethod
    def _piper_parts(text):
        """Speak the opening clause on its own so audio starts sooner; the rest follows seamlessly."""
        if len(text) <= 50:
            return [text]
        m = re.match(r"(.{12,70}?[,;:—])\s+(.+)$", text, re.S)
        if m:
            return [m.group(1), m.group(2)]
        # No punctuation early on: break before a joining word, where a speaker would breathe anyway.
        m = re.match(r"(.{25,75}?)\s+((?:until|because|which|when|while|so that|but|and then|by|after|before)\s.+)$",
                     text, re.S)
        if m and len(m.group(2)) > 10:
            return [m.group(1), m.group(2)]
        return [text]

    @staticmethod
    def _pcm_frames(pcm):
        """Generator of PCM bytes in the shape the player asks for; pads gaps with silence."""
        buf = bytearray()
        done = False
        required = yield b""
        while True:
            need = required * 2
            while len(buf) < need and not done:
                try:
                    item = pcm.q.get(timeout=0.05)
                except queue.Empty:
                    break
                if item is None:
                    done = True
                else:
                    buf.extend(item)
            if done and not buf:
                return
            out = bytes(buf[:need])
            del buf[:need]
            if len(out) < need:
                out += b"\x00" * (need - len(out))
            required = yield out

    # ── Worker ───────────────────────────────────────────────────────────────

    def _run(self):
        try:
            import pythoncom
            pythoncom.CoInitialize()
        except Exception:
            pass
        while True:
            gen, text, card, seconds = self._queue.get()
            shown = threading.Event()

            def show():
                if not shown.is_set():
                    shown.set()
                    if self.on_caption:
                        self.on_caption(text, seconds, card)

            if gen != self._gen:
                show()
                continue
            timer = threading.Timer(_CAPTION_WAIT, show)
            timer.start()
            self.state.update(speaking=True)
            try:
                self._speak(gen, text, show)
            except Exception:
                log.exception("Speech failed")
            finally:
                timer.cancel()
                show()
                self.state.last_speech_end = time.time()
                if self._queue.empty():
                    self.state.update(speaking=False)

    def _speak(self, gen, text, show):
        engine = self._engine()
        if engine == "piper":
            self._ensure_piper()                       # picks up a voice changed in Settings
            end = time.time() + 25
            while self._piper is None and self._piper_loading and time.time() < end and gen == self._gen:
                show()                                 # still loading at startup: wait rather than switch voices
                time.sleep(0.1)
            if gen != self._gen:
                return
            if self._piper is not None:
                return self._speak_piper(gen, text, show)
            if self._speak_edge(gen, text, show):      # local voice unavailable (e.g. download failed)
                return
        elif engine == "edge":
            if self._speak_edge(gen, text, show):
                return
            if self._piper is not None:
                return self._speak_piper(gen, text, show)
        show()
        self._sapi_say(gen, text)

    # ── Online voice (edge-tts) ──────────────────────────────────────────────

    def _speak_edge(self, gen, text, show):
        """True if it spoke (or was interrupted); False if the service failed."""
        chunks = split_sentences(text)
        upcoming = self._synth(chunks[0])
        for i, chunk in enumerate(chunks):
            stream = upcoming
            upcoming = self._synth(chunks[i + 1]) if i + 1 < len(chunks) else None
            if not stream.first.wait(_FIRST_AUDIO_TIMEOUT) or (stream.failed and not stream.data):
                log.warning("Online voice slow; retrying")
                stream.end()
                stream = self._synth(chunk)
                if not stream.first.wait(_FIRST_AUDIO_TIMEOUT + 1.0) or (stream.failed and not stream.data):
                    log.warning("Online voice unavailable for this reply")
                    stream.end()
                    if upcoming:
                        upcoming.end()
                    if i == 0:
                        return False
                    show()
                    self._sapi_say(gen, " ".join(chunks[i:]))
                    return True
            if gen != self._gen:
                return True
            end = time.time() + 1.0
            while stream.buffered() < _START_BUFFER and not stream.done.is_set() and time.time() < end:
                time.sleep(0.01)
            show()
            decoded = miniaudio.stream_any(stream, source_format=miniaudio.FileFormat.MP3, nchannels=1,
                                           sample_rate=_EDGE_RATE, frames_to_read=1024)
            if not self._play(gen, self._decoded_frames(decoded), _EDGE_RATE):
                if upcoming:
                    upcoming.end()
                return True
        return True

    @staticmethod
    def _decoded_frames(decoded):
        required = yield b""
        while True:
            try:
                frames = decoded.send(required)
            except StopIteration:
                return
            required = yield frames

    def _cache_path(self, text):
        key = "%s|%s|%s" % (self.cfg.get("edge_voice"), self.cfg.get("rate"), text)
        return os.path.join(VOICE_CACHE_DIR, hashlib.sha1(key.encode("utf-8")).hexdigest() + ".mp3")

    def _synth(self, text):
        stream = _Mp3Stream()
        path = self._cache_path(text) if len(text) <= _CACHE_MAX_CHARS else None
        if path and os.path.exists(path):
            with open(path, "rb") as f:
                stream.feed(f.read())
            stream.end()
            return stream
        self._streams.append(stream)
        asyncio.run_coroutine_threadsafe(self._fetch(text, stream, path), self._loop)
        return stream

    async def _fetch(self, text, stream, path):
        import edge_tts
        ok = False
        try:
            com = edge_tts.Communicate(text, self.cfg.get("edge_voice", "en-US-AvaMultilingualNeural"),
                                       rate=self.cfg.get("rate", "+0%"), connect_timeout=4, receive_timeout=8)
            async for chunk in com.stream():
                if stream.done.is_set():            # cancelled
                    return
                if chunk["type"] == "audio":
                    stream.feed(chunk["data"])
            ok = bool(stream.data)
        except Exception as e:
            log.debug("edge-tts error: %s", e)
        finally:
            stream.end(failed=not ok)
            if stream in self._streams:
                self._streams.remove(stream)
        if ok and path:
            try:
                with open(path, "wb") as f:
                    f.write(bytes(stream.data))
                self._prune_cache()
            except Exception:
                pass

    def _prune_cache(self):
        files = [os.path.join(VOICE_CACHE_DIR, f) for f in os.listdir(VOICE_CACHE_DIR)]
        if len(files) <= _CACHE_MAX_FILES:
            return
        files.sort(key=os.path.getmtime)
        for f in files[:len(files) - _CACHE_MAX_FILES]:
            try:
                os.remove(f)
            except OSError:
                pass

    # ── Playback ─────────────────────────────────────────────────────────────

    def _play(self, gen, frames, rate):
        """Play 16-bit mono frames from a primed-on-start generator. False if interrupted."""
        volume = float(self.cfg.get("volume", 0.9))
        finished = threading.Event()

        def feeder():
            required = yield b""
            next(frames)
            while True:
                try:
                    data = frames.send(required)
                except StopIteration:
                    finished.set()
                    return
                if volume < 0.999:
                    data = (np.frombuffer(data, dtype=np.int16) * volume).astype(np.int16).tobytes()
                required = yield data

        gen_obj = feeder()
        next(gen_obj)
        device = miniaudio.PlaybackDevice(nchannels=1, sample_rate=rate, buffersize_msec=120, app_name="Gem")
        self._device = device
        try:
            device.start(gen_obj)
            while not finished.wait(0.03):
                if gen != self._gen:
                    return False
            time.sleep(0.15)                       # let the device drain its buffer
            return gen == self._gen
        finally:
            self._device = None
            try:
                device.close()
            except Exception:
                pass

    # ── SAPI (last resort) ───────────────────────────────────────────────────

    def _sapi_say(self, gen, text):
        import win32com.client
        if self._sapi is None:
            self._sapi = win32com.client.Dispatch("SAPI.SpVoice")
            self._sapi.Rate = 1
            want = (self.cfg.get("sapi_voice") or "Zira").lower()
            vs = self._sapi.GetVoices()
            for i in range(vs.Count):
                if want in vs.Item(i).GetDescription().lower():
                    self._sapi.Voice = vs.Item(i)
                    break
        self._sapi.Volume = int(float(self.cfg.get("volume", 0.9)) * 100)
        self._sapi.Speak(text, 1)                  # SVSFlagsAsync
        while not self._sapi.WaitUntilDone(40):
            if gen != self._gen:
                self._sapi.Speak("", 3)            # async + purge
                return
