"""Speech to text: Groq Whisper first, Google's free recognizer as backup."""
import io
import logging
import os
import re
import time
import wave

import requests

from .audio import RATE

log = logging.getLogger("gem.stt")

GROQ_URL = "https://api.groq.com/openai/v1/audio/transcriptions"

# Whisper invents these on silence, breathing and keyboard noise.
HALLUCINATIONS = {
    "you", "thank you", "thanks", "thanks for watching", "thank you for watching", "bye",
    "bye bye", "the end", "so", "uh", "um", "hmm", "mm", "oh", "ah", "", "subtitles by the amara org community",
    "please subscribe", "music", "silence", "applause", "laughter", "i", "a", "the",
}

# Vocabulary hint so names and Gem's control words come out spelled right.
PROMPT = "Gem, open Spotify. Ruhig. Weiter. Sperren. Schluss. Discord, Brave, VS Code, YouTube."


def to_wav(pcm):
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(pcm)
    return buf.getvalue()


def _plain(text):
    return re.sub(r"[^a-z0-9' ]+", "", text.lower()).strip()


class Transcriber:
    def __init__(self, cfg):
        self.backends = cfg.get("backends", ["groq", "google"])
        self.models = cfg.get("groq_models", ["whisper-large-v3-turbo"])
        self.language = cfg.get("language", "en")
        self.session = requests.Session()
        self._cooldown = {}
        self._recognizer = None

    @property
    def key(self):
        return os.environ.get("GROQ_API_KEY", "")

    def transcribe(self, pcm):
        seconds = len(pcm) / 2 / RATE
        for backend in self.backends:
            try:
                if backend == "groq" and self.key:
                    text = self._groq(pcm)
                elif backend == "google":
                    text = self._google(pcm)
                else:
                    continue
            except Exception as e:
                log.warning("%s transcription failed: %s", backend, e)
                continue
            if text is None:
                continue
            text = re.sub(r"\s+", " ", text).strip()
            plain = _plain(text)
            if plain in HALLUCINATIONS and seconds < 3.5:
                log.debug("Dropped likely hallucination %r", text)
                return ""
            if len(plain.split()) > 2 and plain in _plain(PROMPT):
                log.debug("Dropped echo of the vocabulary hint %r", text)
                return ""
            return text
        return ""

    def _groq(self, pcm):
        wav = to_wav(pcm)
        for model in self.models:
            if self._cooldown.get(model, 0) > time.time():
                continue
            data = {"model": model, "response_format": "verbose_json", "temperature": "0", "prompt": PROMPT}
            if self.language:
                data["language"] = self.language
            r = self.session.post(GROQ_URL, headers={"Authorization": "Bearer " + self.key},
                                  files={"file": ("speech.wav", wav, "audio/wav")}, data=data, timeout=15)
            if r.status_code == 429:
                wait = float(r.headers.get("retry-after", 60))
                self._cooldown[model] = time.time() + wait
                log.warning("Whisper %s rate limited for %.0fs", model, wait)
                continue
            if r.status_code >= 400:
                log.warning("Whisper %s error %s: %s", model, r.status_code, r.text[:200])
                continue
            body = r.json()
            segments = body.get("segments") or []
            if segments:
                kept = [s["text"] for s in segments
                        if not (s.get("no_speech_prob", 0) > 0.6 and s.get("avg_logprob", 0) < -0.7)]
                return " ".join(t.strip() for t in kept)
            return body.get("text", "")
        return None

    def _google(self, pcm):
        import speech_recognition as sr
        if self._recognizer is None:
            self._recognizer = sr.Recognizer()
        audio = sr.AudioData(pcm, RATE, 2)
        try:
            return self._recognizer.recognize_google(audio, language="en-US")
        except sr.UnknownValueError:
            return ""
