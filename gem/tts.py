"""Gem's voice: Microsoft neural voices via edge-tts, Windows SAPI offline.

Every reply is also shown as a caption. When Gem shouldn't make noise (calls,
snooze, gaming, voice off) the caption is all you get. Speech can be cut off
at any moment with stop() — tapping Caps Lock does that.
"""
import asyncio
import concurrent.futures
import hashlib
import io
import logging
import os
import queue
import re
import threading
import time

from .config import VOICE_CACHE_DIR

log = logging.getLogger("gem.tts")

os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

_CACHE_MAX_CHARS = 120
_CACHE_MAX_FILES = 400


def clean_for_speech(text):
    text = re.sub(r"https?://\S+", "the link", text)
    text = re.sub(r"[*_`#>|~]+", "", text)
    text = re.sub(r"^\s*[-•]\s+", "", text, flags=re.M)
    text = re.sub(r"[\U0001F000-\U0001FFFF☀-➿]", "", text)
    return re.sub(r"\s+", " ", text).strip()


def split_sentences(text, limit=220):
    parts = re.split(r"(?<=[.!?])\s+", text)
    chunks, cur = [], ""
    for p in parts:
        if cur and len(cur) + len(p) > limit:
            chunks.append(cur)
            cur = p
        else:
            cur = (cur + " " + p).strip()
    if cur:
        chunks.append(cur)
    return chunks


class Voice:
    def __init__(self, state, cfg, on_caption=None):
        self.state = state
        self.cfg = cfg
        self.on_caption = on_caption
        self.last_text = ""
        self._queue = queue.Queue()
        self._gen = 0
        self._pool = concurrent.futures.ThreadPoolExecutor(max_workers=2, thread_name_prefix="tts-synth")
        self._edge_down_until = 0.0
        self._mixer_ready_at = 0.0
        self._sapi = None
        os.makedirs(VOICE_CACHE_DIR, exist_ok=True)
        threading.Thread(target=self._run, name="voice", daemon=True).start()

    # ── Public API ───────────────────────────────────────────────────────────

    def say(self, text, caption_only=False):
        text = clean_for_speech(text or "")
        if not text:
            return
        self.last_text = text
        speaking = not caption_only and self.state.can_speak()
        if self.on_caption:
            # Longer on screen when it's the only way you'll see the answer.
            seconds = max(4.0, len(text) / 12.0) * (1.0 if speaking else 1.8)
            self.on_caption(text, seconds)
        if speaking:
            self._queue.put((self._gen, text))

    def stop(self):
        self._gen += 1
        try:
            while True:
                self._queue.get_nowait()
        except queue.Empty:
            pass
        try:
            import pygame
            if pygame.mixer.get_init():
                pygame.mixer.music.stop()
        except Exception:
            pass

    @property
    def busy(self):
        return self.state.speaking or not self._queue.empty()

    # ── Worker ───────────────────────────────────────────────────────────────

    def _run(self):
        try:
            import pythoncom
            pythoncom.CoInitialize()
        except Exception:
            pass
        while True:
            gen, text = self._queue.get()
            if gen != self._gen:
                continue
            self.state.update(speaking=True)
            try:
                self._speak(gen, text)
            except Exception:
                log.exception("Speech failed")
            finally:
                self.state.last_speech_end = time.time()
                if self._queue.empty():
                    self.state.update(speaking=False)

    def _speak(self, gen, text):
        use_edge = self.cfg.get("engine", "edge") == "edge" and time.time() > self._edge_down_until
        if use_edge:
            chunks = split_sentences(text)
            futures = [self._pool.submit(self._edge_audio, c) for c in chunks[:2]]
            for i, chunk in enumerate(chunks):
                if gen != self._gen:
                    return
                if i + 2 < len(chunks):
                    futures.append(self._pool.submit(self._edge_audio, chunks[i + 2]))
                try:
                    mp3 = futures[i].result(timeout=8)
                except Exception as e:
                    log.warning("Neural voice unavailable (%s); using the offline voice", e)
                    self._edge_down_until = time.time() + 120
                    self._sapi_say(gen, " ".join(chunks[i:]))
                    return
                if gen != self._gen:
                    return
                self._play_mp3(gen, mp3)
        else:
            self._sapi_say(gen, text)

    # ── edge-tts ─────────────────────────────────────────────────────────────

    def _cache_path(self, text):
        key = "%s|%s|%s" % (self.cfg.get("edge_voice"), self.cfg.get("rate"), text)
        return os.path.join(VOICE_CACHE_DIR, hashlib.sha1(key.encode("utf-8")).hexdigest() + ".mp3")

    def _edge_audio(self, text):
        path = self._cache_path(text) if len(text) <= _CACHE_MAX_CHARS else None
        if path and os.path.exists(path):
            with open(path, "rb") as f:
                return f.read()
        import edge_tts

        async def synth():
            com = edge_tts.Communicate(text, self.cfg.get("edge_voice", "en-US-AvaMultilingualNeural"),
                                       rate=self.cfg.get("rate", "+0%"))
            buf = bytearray()
            async for chunk in com.stream():
                if chunk["type"] == "audio":
                    buf.extend(chunk["data"])
            return bytes(buf)

        data = asyncio.run(synth())
        if not data:
            raise RuntimeError("no audio returned")
        if path:
            try:
                with open(path, "wb") as f:
                    f.write(data)
                self._prune_cache()
            except Exception:
                pass
        return data

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

    def _play_mp3(self, gen, data):
        import pygame
        # Re-open the output now and then so Gem follows a changed default
        # device (e.g. headphones plugged in).
        if not pygame.mixer.get_init() or time.time() - self._mixer_ready_at > 60:
            if pygame.mixer.get_init():
                pygame.mixer.quit()
            pygame.mixer.init()
            self._mixer_ready_at = time.time()
        pygame.mixer.music.load(io.BytesIO(data), "mp3")
        pygame.mixer.music.set_volume(float(self.cfg.get("volume", 0.9)))
        pygame.mixer.music.play()
        while pygame.mixer.music.get_busy():
            if gen != self._gen:
                pygame.mixer.music.stop()
                return
            time.sleep(0.03)

    # ── SAPI ─────────────────────────────────────────────────────────────────

    def _sapi_say(self, gen, text):
        import win32com.client
        if self._sapi is None:
            self._sapi = win32com.client.Dispatch("SAPI.SpVoice")
            self._sapi.Rate = 1
        self._sapi.Volume = int(float(self.cfg.get("volume", 0.9)) * 100)
        self._sapi.Speak(text, 1)                  # SVSFlagsAsync
        while not self._sapi.WaitUntilDone(40):
            if gen != self._gen:
                self._sapi.Speak("", 3)            # async + purge
                return
