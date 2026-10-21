"""Always-listening mode runs "safe" matches without asking the AI whether the speech was for Gem. These guard
against everyday conversation (or a video playing) setting off commands by itself."""
import unittest

from . import svc  # noqa: F401  (sets up the test environment)
from .test_router import route

# Said to other people, or heard from a video. None of these may run on their own.
CHATTER = [
    "he turned the volume up so loud last night",
    "the volume went down when i joined",
    "my volume is at 100 and i still can't hear",
    "volume 2 is better than volume 1",
    "play it again",
    "play that again",
    "let's play a game",
    "play with me",
    "remember that",
    "remember this",
    "take a screenshot and send it to me",
    "show me where the bathroom is",
    "highlight the main points in your essay",
    "what's this error",
    "what did you say",
    "what can you do",
    "help me",
    "solve this",
    "copy the text from the page",
    "i'm going to the store in 10 minutes",
    "he told me to stop",
    "i'll call you back in 5 minutes",
    # questions about what you've been doing get answered out loud
    "what was i doing at 3",
    "what was i working on",
    "when did i start valorant",
    "when was i last on discord",
    "how long have i been playing",
    "how long have i been on the computer",
    "show my timeline",
    "show my recent files",
    "how long is it",
]

# Anything that sends the screen to the AI.
SCREEN = ["explain_screen", "autofill", "screen_save", "read_screen", "copy_screen_text"]


class ChatterTest(unittest.TestCase):
    def test_chatter_never_runs_by_itself(self):
        for said in CHATTER:
            with self.subTest(said=said):
                m = route(said)
                self.assertFalse(m and m.safe, "runs without asking: %s %s" % (m and m.action, m and m.args))

    def test_screen_is_never_safe(self):
        for said in ("what's this error", "explain my screen", "where's the save button", "autofill",
                     "remember this", "read my screen", "look at my screen and tell me what to click",
                     "take a screenshot and tell me what's wrong", "highlight the error", "copy the text from my screen"):
            with self.subTest(said=said):
                m = route(said)
                self.assertIn(m.action, SCREEN)
                self.assertFalse(m.safe)


class VolumeTest(unittest.TestCase):
    def test_commands(self):
        cases = {
            "volume 40": {"level": 40},
            "volume 40 percent": {"level": 40},
            "set the volume to 40": {"level": 40},
            "turn the volume down to 20": {"level": 20},
            "volume to max": {"level": 100},
            "turn the volume up": {"change": 10},
            "can you turn the volume up a bit": {"change": 10},
            "lower the volume": {"change": -10},
            "raise the volume by 20": {"change": 20},
            "reduce volume by 5": {"change": -5},
            "spotify volume 30": {"level": 30, "app": "spotify"},
            "set spotify's volume to 30": {"level": 30, "app": "spotify"},
        }
        for said, args in cases.items():
            with self.subTest(said=said):
                m = route(said)
                self.assertEqual(m.action, "volume")
                for k, v in args.items():
                    self.assertEqual(m.args.get(k), v)


class MediaTest(unittest.TestCase):
    def test_play_words(self):
        cases = {
            "play it again": "previous",
            "replay that": "previous",
            "play the next one": "next",
            "play some music": "play_pause",
            "play something": "play_pause",
        }
        for said, command in cases.items():
            with self.subTest(said=said):
                m = route(said)
                self.assertEqual((m.action, m.args), ("media", {"command": command}))
        self.assertEqual(route("play despacito").args, {"query": "despacito"})
        self.assertIsNone(route("play with me"))


if __name__ == "__main__":
    unittest.main()
