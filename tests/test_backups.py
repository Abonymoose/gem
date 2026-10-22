"""Backup AI services: Cerebras is offered, saved backup lists still get new services, and a rate-limited Groq
hands over to the backup. The network is faked; nothing is sent anywhere."""
import json
import os
import unittest
from unittest import mock

from . import svc  # noqa: F401  (sets up the test environment)
from gem import brain as brain_mod, config


class _Response:
    def __init__(self, status, body=None, headers=None):
        self.status_code, self._body, self.headers = status, body or {}, headers or {}
        self.text = json.dumps(self._body)

    def json(self):
        return self._body


def _ok(content):
    return _Response(200, {"choices": [{"message": {"content": content}}], "usage": {"total_tokens": 10}})


class BackupsTest(unittest.TestCase):
    def test_cerebras_offered(self):
        cerebras = config.DEFAULTS["ai"]["backups"][0]
        self.assertEqual((cerebras["name"], cerebras["key_env"]), ("Cerebras", "CEREBRAS_API_KEY"))
        self.assertEqual(cerebras["models"][0], "gpt-oss-120b")

    def test_saved_list_gets_new_services(self):
        saved = {"ai": {"backups": [{"name": "Gemini", "key_env": "GEMINI_API_KEY", "url": "https://x", "models": ["g"]}]}}
        with open(config.SETTINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(saved, f)
        self.addCleanup(os.remove, config.SETTINGS_FILE)
        names = [b["name"] for b in config.load_settings()["ai"]["backups"]]
        self.assertEqual(names, ["Gemini", "Cerebras", "OpenRouter"])          # yours first, then the new ones

    def test_hands_over_when_groq_is_limited(self):
        b = brain_mod.Brain(dict(config.DEFAULTS["ai"]), mock.Mock(), "Parshv", mock.Mock(data={}))
        keys = {"GROQ_API_KEY": "groq", "CEREBRAS_API_KEY": "cer"}
        sent = []

        def post(url, headers=None, json=None, timeout=None):
            sent.append((url, headers["Authorization"], dict(json)))
            if "groq.com" in url:
                return _Response(429, headers={"retry-after": "30"})
            if "reasoning_effort" in json and len(sent) == 4:
                return _Response(400, {"error": "unsupported"})          # an option the service refuses
            return _ok('{"addressed": true, "actions": [], "reply": "Hi.", "continue": false}')

        with mock.patch.dict(os.environ, {"GROQ_API_KEY": "groq"}), \
                mock.patch.object(brain_mod, "secret", side_effect=lambda n: keys.get(n, "")), \
                mock.patch.object(b.session, "post", side_effect=post):
            content, slot = b._post([{"role": "user", "content": "hi"}], json_mode=True)
        self.assertEqual(slot, "Cerebras:gpt-oss-120b")
        self.assertEqual([s[0] for s in sent[:3]], [brain_mod.CHAT_URL] * 3)   # every Groq model tried first
        url, auth, body = sent[3]
        self.assertEqual((url, auth), ("https://api.cerebras.ai/v1/chat/completions", "Bearer cer"))
        self.assertEqual((body["reasoning_effort"], body["response_format"]), ("low", {"type": "json_object"}))
        self.assertNotIn("reasoning_effort", sent[4][2])                         # retried with just the basics
        self.assertEqual(b.last_service, "Cerebras")


if __name__ == "__main__":
    unittest.main()
