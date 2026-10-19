"""Groq-powered understanding.

One request per utterance: the model returns JSON saying whether the speech
was meant for Gem, which actions to run and what to say. Models are tried in
order and skipped while rate limited, so the free tier stretches further.
"""
import collections
import datetime
import json
import logging
import os
import re
import time

import requests

from . import actions

log = logging.getLogger("gem.brain")

CHAT_URL = "https://api.groq.com/openai/v1/chat/completions"


class BrainUnavailable(Exception):
    pass


SYSTEM_PROMPT = """You are Gem, the voice assistant on {name}'s Windows PC. Turn speech into actions and short spoken replies.
Style: calm, friendly, professional, brief. No sarcasm or filler. Replies are spoken: one or two short plain sentences, no markdown, lists, emojis or URLs.

Reply with JSON only: {{"addressed": true, "actions": [{{"name": "...", "args": {{}}}}], "reply": "", "continue": false}}
- addressed: true for push-to-talk and typed input. In always-listening mode set false (and nothing else) if the speech isn't for you: talking to others, calls, media audio, thinking aloud, fragments, vague remarks ("let's improve", "that's cool"). Only clear requests or questions an assistant could act on, or mentions of Gem, are addressed. A recent reply makes a follow-up likely only if it clearly continues that exchange. If unsure, false.
- actions: in order, only from the list. They announce their own results, so leave reply "" when you use them unless you must add something.
- reply: answer questions from your knowledge. Prefer a fitting action (e.g. weather) over web_search, which is only for live facts you can't know. If something essential is missing, ask one short question.
- continue: true only if you need the action results to finish (e.g. check weather, then advise). You'll get them.

Actions:
{catalog}"""


def _now_text():
    now = datetime.datetime.now()
    return now.strftime("%A %d %B %Y, %I:%M %p").replace(" 0", " ")


def _parse_json(text):
    text = (text or "").strip()
    try:
        return json.loads(text)
    except Exception:
        m = re.search(r"\{.*\}", text, re.S)
        if m:
            try:
                return json.loads(m.group(0))
            except Exception:
                pass
    return None


def _clean_plan(raw, source):
    if not isinstance(raw, dict):
        return None
    acts = []
    for a in raw.get("actions") or []:
        if isinstance(a, dict) and actions.exists(str(a.get("name"))):
            acts.append({"name": a["name"], "args": a.get("args") if isinstance(a.get("args"), dict) else {}})
        elif isinstance(a, dict):
            log.warning("Model asked for unknown action %r", a.get("name"))
    addressed = bool(raw.get("addressed", True)) or source != "open"
    reply = str(raw.get("reply") or "").strip() if addressed else ""
    cont = bool(raw.get("continue")) and bool(acts)
    # Actions confirm themselves; drop a bare "Done." / "Class added." on top.
    if acts and not cont and reply and "?" not in reply and len(reply.split()) <= 5:
        reply = ""
    return {
        "addressed": addressed,
        "actions": acts if addressed else [],
        "reply": reply,
        "continue": cont,
    }


class Brain:
    def __init__(self, cfg, state, user_name, memory):
        self.cfg = cfg
        self.state = state
        self.user_name = user_name or "the user"
        self.memory = memory
        self.session = requests.Session()
        self.history = collections.deque(maxlen=int(cfg.get("history_turns", 6)) * 2)
        self._cooldown = {}

    @property
    def key(self):
        return os.environ.get("GROQ_API_KEY", "")

    def available(self):
        return bool(self.key)

    # ── Transport ────────────────────────────────────────────────────────────

    def _body(self, model, messages, json_mode, max_tokens, temperature):
        body = {"model": model, "messages": messages, "max_completion_tokens": max_tokens,
                "temperature": temperature}
        if json_mode:
            body["response_format"] = {"type": "json_object"}
        if "gpt-oss" in model:
            body["reasoning_effort"] = self.cfg.get("reasoning_effort", "low")
            body["include_reasoning"] = False
        elif "qwen" in model:
            body["reasoning_format"] = "hidden"
        return body

    def _post(self, messages, json_mode=False, max_tokens=500, temperature=0.3):
        if not self.key:
            raise BrainUnavailable("Set the GROQ_API_KEY environment variable so I can answer that.")
        last_error = "no model available"
        for model in self.cfg.get("models", []):
            if self._cooldown.get(model, 0) > time.time():
                continue
            try:
                r = self.session.post(CHAT_URL, headers={"Authorization": "Bearer " + self.key},
                                      json=self._body(model, messages, json_mode, max_tokens, temperature),
                                      timeout=15)
            except requests.RequestException as e:
                last_error = "network: %s" % e
                log.warning("Groq %s request failed: %s", model, e)
                if isinstance(e, (requests.ConnectionError,)):
                    break
                continue
            if r.status_code == 429:
                wait = float(r.headers.get("retry-after") or 20)
                self._cooldown[model] = time.time() + wait
                log.warning("Groq %s rate limited for %.0fs", model, wait)
                last_error = "rate limited"
                continue
            if r.status_code >= 400:
                last_error = "%s %s" % (r.status_code, r.text[:200])
                log.warning("Groq %s error: %s", model, last_error)
                if r.status_code in (401, 403):
                    raise BrainUnavailable("My Groq API key was rejected. Check GROQ_API_KEY.")
                continue
            try:
                content = r.json()["choices"][0]["message"].get("content") or ""
            except Exception:
                continue
            if json_mode and _parse_json(content) is None:
                log.warning("Groq %s returned invalid JSON: %r", model, content[:200])
                continue
            return content, model
        if "network" in last_error:
            raise BrainUnavailable("I can't reach the internet right now.")
        if "rate limited" in last_error:
            raise BrainUnavailable("I've hit the free AI limit for the moment. Try again in a minute.")
        raise BrainUnavailable("The AI service isn't responding right now.")

    # ── Planning ─────────────────────────────────────────────────────────────

    def _system(self):
        parts = [SYSTEM_PROMPT.format(name=self.user_name, catalog=actions.catalog()),
                 "\nNow: %s. Gem: %s." % (_now_text(), self.state.describe())]
        facts = (self.memory.data.get("facts") or [])[-25:]
        if facts:
            parts.append("Things the user asked you to remember:\n" + "\n".join("- " + f for f in facts))
        return "\n".join(parts)

    def _tag(self, source):
        if source == "ptt":
            return "[push-to-talk]"
        if source == "typed":
            return "[typed]"
        ago = time.time() - self.state.last_reply_at
        if ago < 120:
            return "[always-listening, you replied %ds ago]" % ago
        return "[always-listening]"

    def plan(self, text, source):
        messages = [{"role": "system", "content": self._system()}, *self.history,
                    {"role": "user", "content": "%s %s" % (self._tag(source), text)}]
        content, model = self._post(messages, json_mode=True, max_tokens=500, temperature=0.2)
        plan = _clean_plan(_parse_json(content), source)
        log.info("Plan from %s: %s", model, plan)
        if plan is None:
            raise BrainUnavailable("I didn't understand that.")
        plan["_messages"] = messages
        plan["_raw"] = content
        return plan

    def follow_up(self, plan, results):
        lines = "\n".join("- %s: %s" % (name, res or "done") for name, res in results)
        messages = plan["_messages"] + [
            {"role": "assistant", "content": plan["_raw"]},
            {"role": "user", "content": "Action results:\n%s\nNow answer with the final JSON. "
                                        "Set continue to false." % lines},
        ]
        content, model = self._post(messages, json_mode=True, max_tokens=400, temperature=0.2)
        final = _clean_plan(_parse_json(content), "ptt") or {"actions": [], "reply": ""}
        final["continue"] = False
        return final

    def remember_exchange(self, text, source, reply, action_names):
        self.history.append({"role": "user", "content": "%s %s" % (self._tag(source), text)})
        self.history.append({"role": "assistant", "content": json.dumps(
            {"addressed": True, "actions": [{"name": n} for n in action_names], "reply": reply})})

    def clear_history(self):
        self.history.clear()

    # ── Plain completions for text tools ─────────────────────────────────────

    def complete(self, instruction, text="", max_tokens=700):
        messages = [{"role": "system", "content": instruction}]
        if text:
            messages.append({"role": "user", "content": text})
        content, _ = self._post(messages, max_tokens=max_tokens, temperature=0.4)
        return content.strip()
