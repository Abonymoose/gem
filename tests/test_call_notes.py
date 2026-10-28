"""Call notes: the commands, resampling, finding speech, mapping its times back to the call, the transcript and the
files written. Whisper and the AI are faked; nothing is recorded or sent."""
import os
import shutil
import tempfile
import time
import unittest
from unittest import mock

import numpy as np

from . import svc  # noqa: F401  (sets up the test environment)
from .test_router import route
from gem.runtime import svc as runtime_svc
from gem.skills import call_notes as cn


def _speech(seconds, freq=220.0, level=4000):
    t = np.arange(int(cn.RATE * seconds)) / cn.RATE
    return (level * np.sin(2 * np.pi * freq * t)).astype(np.int16)


def _silence(seconds):
    return np.zeros(int(cn.RATE * seconds), np.int16)


class RoutesTest(unittest.TestCase):
    def test_commands(self):
        for said in ("take notes", "Gem, take notes on this call", "start taking notes", "record this meeting",
                     "take notes during the class"):
            with self.subTest(said=said):
                m = route(said)
                self.assertEqual(m.action, "call_notes_start")
                self.assertFalse(m.safe)                       # overheard "take notes" never starts recording
        for said in ("stop taking notes", "stop notes", "that's it for notes", "stop recording this call"):
            with self.subTest(said=said):
                self.assertEqual(route(said).action, "call_notes_stop")
        self.assertEqual(route("take a note buy milk").action, "note_add")


class AudioTest(unittest.TestCase):
    def test_resample_48k(self):
        r = cn._Resampler(48000)
        t = np.arange(48000) / 48000.0
        x = (8000 * np.sin(2 * np.pi * 440 * t)).astype(np.float32)
        out = np.concatenate([r(x[i:i + 4800]) for i in range(0, 48000, 4800)])
        self.assertAlmostEqual(len(out), 16000, delta=3)
        crossings = np.sum(np.diff(np.sign(out[200:-200])) != 0)
        self.assertAlmostEqual(crossings / (len(out) - 400) * cn.RATE / 2, 440, delta=10)   # still 440 Hz

    def test_speech_regions_and_times(self):
        track = np.concatenate([_silence(5), _speech(2), _silence(10), _speech(3), _silence(1)])
        regions = cn._speech_regions(track)
        self.assertEqual(len(regions), 2)
        self.assertAlmostEqual(regions[0][0] / cn.RATE, 4.75, delta=0.1)
        audio, where = cn._compact(track, cn._pieces(regions)[0])
        self.assertLess(len(audio) / cn.RATE, 7)               # 18 s of call, about 6 s sent
        self.assertAlmostEqual(cn._to_call_time(0.5, where), 5.25, delta=0.1)
        second = where[1][0] + 1.0                              # a second into the second stretch
        self.assertAlmostEqual(cn._to_call_time(second, where), regions[1][0] / cn.RATE + 1.0, delta=0.05)

    def test_pieces_split_long_speech(self):
        regions = [(i * cn.RATE * 100, i * cn.RATE * 100 + cn.RATE * 90) for i in range(20)]
        pieces = cn._pieces(regions, limit=600)
        self.assertTrue(all(sum((e - s) / cn.RATE + cn.GAP for s, e in p) <= 600 for p in pieces))
        self.assertEqual(sum(len(p) for p in pieces), 20)

    def test_merge(self):
        mine = [(10.0, "You", "Sounds good, I'll do the slides"), (31.0, "You", "and the homework is page 12")]
        theirs = [(11.0, "Others", "Can you do the slides by Friday?"),
                  (30.5, "Others", "And the homework is page 12."),   # your mic heard the speakers
                  (33.0, "Others", "Right.")]
        lines = cn._merge(mine, theirs)
        self.assertEqual([who for _, who, _ in lines], ["You", "Others", "Others"])   # the echo of page 12 is gone
        self.assertIn("page 12. Right.", lines[2][2])                  # same speaker, close together: one line


class WriteUpTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.dir, True)
        patches = [mock.patch.object(cn, "folder", return_value=self.dir),
                   mock.patch.object(runtime_svc, "brain", mock.Mock()),
                   mock.patch.object(cn.os, "startfile", create=True),
                   mock.patch.object(cn, "say"), mock.patch.object(cn, "notify")]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)

    def test_notes_file_and_mp3(self):
        rec = cn.Recorder.__new__(cn.Recorder)
        rec.stamp = __import__("datetime").datetime(2026, 10, 28, 18, 5)
        rec.started, rec.ended, rec.app = time.time() - 125, time.time(), "Google Meet"
        rec.tmp = tempfile.mkdtemp(dir=self.dir)
        rec.mic = mock.Mock(path=os.path.join(rec.tmp, "mic.raw"), written=1)
        rec.pc = mock.Mock(path=os.path.join(rec.tmp, "pc.raw"), written=1)
        np.concatenate([_silence(1), _speech(2), _silence(3)]).tofile(rec.mic.path)
        np.concatenate([_silence(3), _speech(2, 330), _silence(1)]).tofile(rec.pc.path)
        runtime_svc.brain.complete.return_value = (
            "TITLE: Science group project\n\nSUMMARY\n- Slides due Friday\n\nACTION ITEMS\n- You: slides by Friday\n\n"
            "DATES\n- Friday")
        heard = {"You": [{"start": 0.1, "end": 1.5, "text": "I'll do the slides"}],
                 "Others": [{"start": 0.2, "end": 1.8, "text": "Great, by Friday please."}]}
        calls = []

        def whisper(mp3):
            calls.append(len(mp3))
            return heard["You" if len(calls) == 1 else "Others"]
        with mock.patch.object(cn, "_whisper", side_effect=whisper), \
                mock.patch.object(runtime_svc, "state", mock.Mock()), \
                mock.patch.dict("sys.modules", {"webrtcvad": None}):     # test tones aren't speech to webrtcvad
            cn._process(rec)
        files = sorted(os.listdir(self.dir))
        self.assertIn("2026-10-28 18-05 Google Meet notes.mp3", files)
        with open(os.path.join(self.dir, "2026-10-28 18-05 Google Meet notes.txt"), encoding="utf-8") as f:
            text = f.read()
        self.assertTrue(text.startswith("Science group project\n"))
        self.assertIn("2 minutes · Google Meet", text)
        self.assertLess(text.index("SUMMARY"), text.index("TRANSCRIPT"))          # the summary is at the top
        self.assertIn("[00:00] You: I'll do the slides", text)
        self.assertIn("[00:02] Others: Great, by Friday please.", text)
        self.assertFalse(os.path.exists(rec.tmp))                                 # the raw recording is cleaned up
        self.assertGreater(os.path.getsize(os.path.join(self.dir, "2026-10-28 18-05 Google Meet notes.mp3")), 1000)


if __name__ == "__main__":
    unittest.main()
