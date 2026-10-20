"""Microphone capture and speech segmentation.

One thread reads 30 ms frames from the mic. Depending on the state it either
collects a push-to-talk recording (while Caps Lock is held) or, in
always-listening mode, cuts the stream into utterances with a voice-activity
detector. Nothing leaves this module unless the ears are open.
"""
import collections
import logging
import threading
import time
from dataclasses import dataclass, field

import numpy as np

log = logging.getLogger("gem.audio")

RATE = 16000
FRAME_MS = 30
FRAME_SAMPLES = RATE * FRAME_MS // 1000
PREROLL_FRAMES = 12            # ~360 ms kept before a press / speech start
PTT_TAIL_S = 0.25              # people let go of the key a bit early
MAX_UTTERANCE_FRAMES = 1000    # 30 s
OPEN_MAX_FRAMES = 500          # 15 s
END_SILENCE_FRAMES = 26        # ~780 ms of silence ends an utterance
ECHO_GUARD_S = 0.45            # ignore the mic briefly after Gem stops talking

try:
    import webrtcvad
except ImportError:            # energy-only fallback
    webrtcvad = None


@dataclass
class Utterance:
    source: str                 # "ptt", "open" or "typed"
    audio: bytes = b""
    text: str = ""
    created: float = field(default_factory=time.time)

    @property
    def seconds(self):
        return len(self.audio) / 2 / RATE


class Listener:
    def __init__(self, state, on_utterance, input_device="", vad_aggressiveness=2):
        self.state = state
        self.on_utterance = on_utterance
        self.input_device = input_device
        self.vad = webrtcvad.Vad(int(vad_aggressiveness)) if webrtcvad else None
        self.level = 0.0                     # 0..1, for the overlay
        self.device_name = ""

        self._lock = threading.Lock()
        self._ring = collections.deque(maxlen=PREROLL_FRAMES)
        self._hold = None                    # frames while push-to-talk is held
        self._closing = None                 # (frames, deadline) during the tail
        self._seg = None                     # always-listening utterance in progress
        self._recent = collections.deque(maxlen=10)
        self._silence = 0
        self._noise = 120.0
        # Auto-clip: short bursts of speech while a game is in front (see hype.py).
        self.on_hype = None                  # callback(pcm, loudness)
        self.hype_active = None              # () -> bool
        self._hseg = None
        self._hsil = 0

    def start(self):
        threading.Thread(target=self._run, name="mic", daemon=True).start()

    # ── Push-to-talk control (called from the Caps Lock worker) ──────────────

    def begin_hold(self, talk):
        with self._lock:
            self._seg = None
            self._recent.clear()
            if talk:
                self._hold = list(self._ring)
                self._closing = None
            else:
                self._hold = None

    def end_hold(self, discard):
        with self._lock:
            frames, self._hold = self._hold, None
            if frames is not None and not discard:
                self._closing = (frames, time.time() + PTT_TAIL_S)

    # ── Capture ──────────────────────────────────────────────────────────────

    def _find_device(self, pa):
        if not self.input_device:
            return None
        want = self.input_device.lower()
        for i in range(pa.get_device_count()):
            info = pa.get_device_info_by_index(i)
            if info.get("maxInputChannels", 0) > 0 and want in info["name"].lower():
                return i
        log.warning("Microphone %r not found; using the default", self.input_device)
        return None

    def _run(self):
        import pyaudio
        while True:
            pa = stream = None
            try:
                pa = pyaudio.PyAudio()
                index = self._find_device(pa)
                info = pa.get_device_info_by_index(index) if index is not None else pa.get_default_input_device_info()
                self.device_name = info["name"]
                stream = pa.open(format=pyaudio.paInt16, channels=1, rate=RATE, input=True,
                                 input_device_index=index, frames_per_buffer=FRAME_SAMPLES)
                log.info("Microphone: %s", self.device_name)
                while True:
                    frame = stream.read(FRAME_SAMPLES, exception_on_overflow=False)
                    self._process(frame)
            except Exception as e:
                log.error("Microphone error: %s; retrying in 3 s", e)
                time.sleep(3)
            finally:
                try:
                    if stream:
                        stream.close()
                    if pa:
                        pa.terminate()
                except Exception:
                    pass

    def _is_speech(self, frame, rms):
        loud = rms > max(180.0, self._noise * 2.2)
        if self.vad:
            try:
                return loud and self.vad.is_speech(frame, RATE)
            except Exception:
                return loud
        return rms > max(300.0, self._noise * 3.0)

    def _process(self, frame):
        samples = np.frombuffer(frame, dtype=np.int16).astype(np.float32)
        rms = float(np.sqrt(np.mean(samples * samples))) if len(samples) else 0.0
        self.level = min(1.0, rms / 4000.0)
        speech = self._is_speech(frame, rms)
        if not speech:
            self._noise = self._noise * 0.995 + rms * 0.005

        emit = None
        with self._lock:
            self._ring.append(frame)

            if self._closing is not None:
                frames, deadline = self._closing
                frames.append(frame)
                if time.time() >= deadline:
                    self._closing = None
                    emit = ("ptt", frames)

            if self._hold is not None:
                if len(self._hold) < MAX_UTTERANCE_FRAMES:
                    self._hold.append(frame)
            elif emit is None:
                emit = self._open_mode(frame, speech)
            hype = self._hype_mode(frame, speech, rms) if self._hold is None else None

        if emit:
            self._emit(*emit)
        if hype:
            self.on_hype(b"".join(hype[0]), float(np.mean(hype[1])))

    def _hype_mode(self, frame, speech, rms):
        """Cut short bursts (up to ~4.5 s) of speech while a game is in front, for auto-clip."""
        if self.on_hype is None or not self.hype_active or not self.hype_active() or self.state.speaking:
            self._hseg = None
            return None
        if self._hseg is None:
            if speech:
                self._hseg = (list(self._ring)[-6:], [rms])
                self._hsil = 0
            return None
        frames, levels = self._hseg
        frames.append(frame)
        if speech:
            levels.append(rms)
            self._hsil = 0
        else:
            self._hsil += 1
        if self._hsil >= 12 or len(frames) >= 150:
            seg, self._hseg = self._hseg, None
            return seg if len(seg[1]) >= 8 else None
        return None

    def _open_mode(self, frame, speech):
        st = self.state
        gem_talking = st.speaking or time.time() - st.last_speech_end < ECHO_GUARD_S
        if not st.ears_open() or gem_talking or st.effective_mode != "always_listening":
            self._seg = None
            self._recent.clear()
            return None
        if self._seg is None:
            self._recent.append(speech)
            if sum(self._recent) >= 6:
                self._seg = list(self._ring)
                self._silence = 0
            return None
        self._seg.append(frame)
        self._silence = 0 if speech else self._silence + 1
        if self._silence >= END_SILENCE_FRAMES or len(self._seg) >= OPEN_MAX_FRAMES:
            frames, self._seg = self._seg, None
            self._recent.clear()
            return ("open", frames)
        return None

    def _emit(self, source, frames):
        voiced = 0
        for f in frames:
            samples = np.frombuffer(f, dtype=np.int16).astype(np.float32)
            rms = float(np.sqrt(np.mean(samples * samples)))
            if self._is_speech(f, rms):
                voiced += 1
        if voiced < (5 if source == "ptt" else 8):
            log.debug("Dropped %s clip with %d voiced frames", source, voiced)
            return
        self.on_utterance(Utterance(source=source, audio=b"".join(frames)))
