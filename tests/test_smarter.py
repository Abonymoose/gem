"""Things Gem got wrong in real use: questions sent without the question, web answers, misheard places, maths,
currencies, sound devices and phrases that went to the wrong command. No network or AI calls."""
import json
import unittest
from unittest import mock

from . import svc  # noqa: F401  (sets up the test environment)
from .test_router import route
from gem import brain as brain_mod
from gem.runtime import svc as runtime_svc
from gem.skills import audio_devices, calc, productivity, web


def _brain():
    state = mock.Mock(describe=lambda: "push to talk", last_reply_at=0.0)
    return brain_mod.Brain({"models": ["m"], "history_turns": 6}, state, "Parshv", mock.Mock(data={}))


class ConversationMemoryTest(unittest.TestCase):
    def test_keeps_args(self):
        # With only action names in the history, the model copied that and sent web_answer with no question.
        b = _brain()
        b.remember_exchange("what's bitcoin at", "ptt", "About 81,500 dollars.", ["web_answer"],
                            [{"name": "web_answer", "args": {"query": "bitcoin price"}}])
        b.remember_exchange("type this", "ptt", "", ["type_text"], [{"name": "type_text", "args": {"text": "x" * 900}}])
        first = json.loads(b.history[1]["content"])
        self.assertEqual(first["actions"], [{"name": "web_answer", "args": {"query": "bitcoin price"}}])
        self.assertEqual(first["reply"], "About 81,500 dollars.")
        self.assertLess(len(json.loads(b.history[3]["content"])["actions"][0]["args"]["text"]), 410)

    def test_question_filled_in(self):
        b = _brain()
        raw = '{"addressed": true, "actions": [{"name": "web_answer", "args": {}}], "reply": ""}'
        with mock.patch.object(b, "_post", return_value=(raw, "m")):
            plan = b.plan("What temperature in Rimworld is the minimum before killing someone?", "ptt")
        self.assertEqual(plan["actions"][0]["args"]["query"],
                         "What temperature in Rimworld is the minimum before killing someone?")

    def test_prompt(self):
        prompt = brain_mod.SYSTEM_PROMPT
        for must in ("Jim", "never leave both empty", "fill in every arg", "give one", "macros"):
            self.assertIn(must, prompt)


class WebAnswerTest(unittest.TestCase):
    def setUp(self):
        self.brain = mock.Mock()
        patcher = mock.patch.object(runtime_svc, "brain", self.brain)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_search_answer(self):
        self.brain.browse.return_value = ("Hypothermia starts below **-10 °C** 【3†wiki】.", ["rimworldwiki.com"])
        res = web.web_answer("rimworld minimum temperature")
        self.assertEqual(str(res), "Hypothermia starts below -10 °C.")
        self.brain.complete.assert_not_called()

    def test_falls_back_to_knowledge(self):
        self.brain.browse.side_effect = brain_mod.BrainUnavailable("rate limited")
        self.brain.complete.return_value = "Floor 6 has skeletons."
        with mock.patch.object(web, "_news") as news:
            self.assertEqual(str(web.web_answer("Roblox Rivals floor 6")), "Floor 6 has skeletons.")
            news.assert_not_called()                    # not a news question: no headlines needed
            web.web_answer("latest news about Roblox")
            news.assert_called_once()


class PlaceTest(unittest.TestCase):
    def test_talk_after_the_city(self):
        known = {"tokyo": (35.7, 139.7, "Tokyo"), "bangalore": (12.97, 77.59, "Bangalore")}
        with mock.patch.object(web, "_lookup", side_effect=lambda n: known.get(n)):
            self.assertEqual(web._geocode("tokyo wait for him i don't want to go to tokyo")[2], "Tokyo")
            self.assertEqual(web._geocode("bangalore now such a hot line how is the weather in bangalore")[2],
                             "Bangalore")
            self.assertEqual(web._geocode("Tokyo? Wait for him")[2], "Tokyo")
            self.assertIsNone(web._geocode("mahadevra buddha"))


class MathsTest(unittest.TestCase):
    def test_roots(self):
        for said, result in (("what's the cube root of 8", "2"), ("What is the fourth root of 64?", "2.82843"),
                             ("what's the 5th root of 32", "2"), ("cube root of twenty seven", "3"),
                             ("square root of 16", "4")):
            with self.subTest(said=said):
                self.assertEqual(calc.calculate(said).card["result"], result)
                self.assertEqual(route(said).action, "calculate")

    def test_currency_names(self):
        rates = {"USD": 1.0, "INR": 84.0, "IDR": 16000.0}
        with mock.patch.object(calc, "_rates", return_value=rates):
            res = calc.convert("how much is 1000 indonesian rupees into indian rupees")
            self.assertEqual(res.card["result"], "5.25 INR")
            self.assertEqual(calc.convert("convert indonesian rupiah to inr").card["result"], "0.01 INR")


class AudioOutputTest(unittest.TestCase):
    DEVICES = [("a", "Speakers (Realtek(R) Audio)"), ("b", "Realtek Digital Output (Realtek(R) Audio)"),
               ("c", "1 - BenQ EW2880U (AMD High Definition Audio Device)")]

    def pick(self, want):
        return [n for _, n in audio_devices._pick(want, self.DEVICES, "c")]

    def test_by_number_and_name(self):
        self.assertEqual(self.pick("the third one"), [self.DEVICES[2][1]])
        self.assertEqual(self.pick("first option"), [self.DEVICES[0][1]])
        self.assertEqual(self.pick("2"), [self.DEVICES[1][1]])
        self.assertEqual(self.pick("speakers realtek r audio"), [self.DEVICES[0][1]])
        self.assertEqual(self.pick("realtek digital output"), [self.DEVICES[1][1]])
        self.assertEqual(self.pick("benq"), [self.DEVICES[2][1]])
        self.assertEqual(self.pick("fifth option"), [])
        self.assertEqual(self.pick("banky"), [])
        self.assertEqual(audio_devices._short("Speakers (Realtek(R) Audio)"), "Speakers (Realtek Audio)")


class ConfirmTest(unittest.TestCase):
    def test_misheard_confirm(self):
        from gem import safety
        for heard in ("conform", "perform", "can't form", "good form", "confirmed"):
            with self.subTest(heard=heard):
                self.assertTrue(safety._sounds_like(heard, "confirm"))
        self.assertTrue(safety._sounds_like("send that", "send it"))
        for heard in ("can't fall", "pause", "play music", "confirmation please"):
            with self.subTest(heard=heard):
                self.assertFalse(safety._sounds_like(heard, "confirm"))


class PhrasesTest(unittest.TestCase):
    def test_timer_with_your(self):
        for said in ("Set your timer for 1.5 seconds.", "set my timer for 10 minutes"):
            with self.subTest(said=said):
                self.assertEqual(route(said).action, "set_timer")
        self.assertEqual(route("Set your timer for 1.5 seconds.").args["seconds"], 1.5)

    def tearDown(self):
        with productivity.todos as data:
            data["items"] = []

    def test_i_did_is_about_the_list(self):
        with productivity.todos as data:
            data["items"] = [{"text": "maths homework", "done": False}]
        m = route("I did what? Highlight the most interesting thing in the screen right now.")
        self.assertNotEqual(m and m.action, "todo_done")
        self.assertEqual(route("I did my maths homework").args["item"], "my maths homework")
        self.assertEqual(route("mark wash the car as done").action, "todo_done")      # asked outright


if __name__ == "__main__":
    unittest.main()
