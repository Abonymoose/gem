"""Fixing what Gem heard from the typing bar, "the AI is busy" with a countdown, and "confirm all" in a macro run.
Nothing is sent anywhere: the network and answers are faked."""
import os
import threading
import time
import types
import unittest
from unittest import mock

from . import svc  # noqa: F401  (sets up the test environment)
from gem import brain as brain_mod, config, safety
from gem.assistant import Assistant
from gem.skills import hearing


class EditFixTest(unittest.TestCase):
    def setUp(self):
        with hearing.store as data:
            data["fixes"], data["edits"] = {}, {}

    def test_learned_on_the_second_same_fix(self):
        self.assertIsNone(hearing.learn_from_edit("conform", "confirm"))
        self.assertEqual(hearing.learn_from_edit("conform", "confirm"), "I'll hear conform as confirm from now on.")
        self.assertEqual(hearing.apply("conform"), "confirm")

    def test_not_learned(self):
        for heard, fixed in (("open spotify", "play some music instead"),     # a different request, not a fix
                             ("set a timer for ten minutes", "set the timer for ten minutes"),   # a common word
                             ("jem open discord", "gem open discord")):                         # Gem's own name
            with self.subTest(heard=heard):
                hearing.learn_from_edit(heard, fixed)
                self.assertIsNone(hearing.learn_from_edit(heard, fixed))
        self.assertEqual(hearing.store.data["fixes"], {})

    def test_recent_voice(self):
        a = Assistant.__new__(Assistant)
        a.last_voice = ("Weather in Mahadevra Buddha", time.time() - 10)
        self.assertEqual(a.recent_voice(), "Weather in Mahadevra Buddha")
        a.last_voice = ("old", time.time() - 120)
        self.assertEqual(a.recent_voice(), "")


class _Response:
    status_code, text = 429, ""

    def __init__(self, wait):
        self.headers = {"retry-after": str(wait)}


class BusyTest(unittest.TestCase):
    def test_countdown_when_every_model_is_limited(self):
        b = brain_mod.Brain(dict(config.DEFAULTS["ai"]), mock.Mock(), "Parshv", mock.Mock(data={}))
        waits = iter([20, 35, 50])
        with mock.patch.dict(os.environ, {"GROQ_API_KEY": "groq"}), \
                mock.patch.object(brain_mod, "secret", return_value=""), \
                mock.patch.object(b.session, "post", side_effect=lambda *a, **k: _Response(next(waits))):
            with self.assertRaises(brain_mod.BrainUnavailable) as e:
                b._post([{"role": "user", "content": "hi"}], json_mode=True)
        self.assertIn("busy for about 20 seconds", str(e.exception))           # the first one back
        self.assertAlmostEqual(b.busy_until - time.time(), 20, delta=2)
        with mock.patch.dict(os.environ, {"GROQ_API_KEY": "groq"}), \
                mock.patch.object(brain_mod, "secret", return_value=""):
            with self.assertRaises(brain_mod.BrainUnavailable) as e:              # still cooling down: no request
                b._post([{"role": "user", "content": "hi"}], json_mode=True)
        self.assertIn("busy for about", str(e.exception))


def _answer(text):
    """Typed in the command bar just now (typed answers count: you're at the keyboard)."""
    return types.SimpleNamespace(source="typed", audio=None, created=time.time() + 1, unattended=False)


class ConfirmAllTest(unittest.TestCase):
    TITLE = "Click in Discord (it could send something)"

    def _in_macro(self, approved, titles, results):
        def run():
            with safety.context(approved_all=approved):
                for t in titles:
                    results.append(safety.ask(t, lambda t=t: "did " + t, phrase="confirm"))
        th = threading.Thread(target=run, name="macro", daemon=True)
        th.start()
        return th

    def _wait_for_question(self):
        for _ in range(100):
            if safety.current() is not None:
                return safety.current()
            time.sleep(0.02)
        self.fail("nothing was asked")

    def test_confirm_all_covers_the_same_step(self):
        approved, results = set(), []
        th = self._in_macro(approved, [self.TITLE, self.TITLE, "Click in Slack (it could send something)"], results)
        req = self._wait_for_question()
        self.assertIn("confirm all", req.data["hint"])
        self.assertEqual(safety.hear(_answer("confirm all"), "confirm all", False), "")
        req = self._wait_for_question()                     # the same step again isn't asked; a different one is
        self.assertEqual(req.title, "Click in Slack (it could send something)")
        self.assertEqual(results, ["did " + self.TITLE] * 2)
        safety.hear(_answer("cancel"), "cancel", False)
        th.join(2)
        self.assertEqual(approved, {self.TITLE})

    def test_never_for_power_or_outside_a_macro(self):
        results = []
        th = self._in_macro(set(), ["Should I restart the computer"], results)
        req = self._wait_for_question()
        self.assertNotIn("confirm all", req.data["hint"])
        reply = safety.hear(_answer("confirm all"), "confirm all", False)
        self.assertIn("works for steps in a macro", str(reply))
        safety.hear(_answer("cancel"), "cancel", False)
        th.join(2)
        self.assertEqual(len(results), 1)
        self.assertFalse(results[0].startswith("did "), results[0])      # cancelled: the step didn't run


if __name__ == "__main__":
    unittest.main()
