"""Groq-powered understanding.

One request per utterance: the model returns JSON saying whether the speech
was meant for Gem, which actions to run and what to say. Models are tried in
order and skipped while rate limited, so the free tier stretches further.
When every Groq model is limited, a backup service (Gemini, OpenRouter) takes
over if you've given Gem a key for it.
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


def secret(name):
    """An API key from the environment, or from your saved user variables (so a key set while Gem runs works
    without a restart)."""
    if not name:
        return ""
    value = os.environ.get(name, "")
    if value:
        return value
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as k:
            return str(winreg.QueryValueEx(k, name)[0] or "")
    except OSError:
        return ""


def save_secret(name, value):
    """Save a key as a user environment variable (what setx does) and use it right away."""
    import winreg
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment", 0, winreg.KEY_SET_VALUE) as k:
        if value:
            winreg.SetValueEx(k, name, 0, winreg.REG_SZ, value)
        else:
            try:
                winreg.DeleteValue(k, name)
            except OSError:
                pass
    if value:
        os.environ[name] = value
    else:
        os.environ.pop(name, None)


SYSTEM_PROMPT = """You are Gem, the voice assistant on {name}'s Windows PC. Turn speech into actions and short spoken replies.
Style: calm, friendly, professional, brief. No sarcasm or filler. Replies are spoken: one or two short plain sentences, no markdown, lists, emojis or URLs.

Reply with JSON only: {{"addressed": true, "actions": [{{"name": "...", "args": {{}}}}], "reply": "", "continue": false}}
- addressed: true for push-to-talk and typed input. In always-listening mode set false (and nothing else) if the speech isn't for you: talking to others, calls, media audio, thinking aloud, fragments, vague remarks ("let's improve", "that's cool"). Only clear requests or questions an assistant could act on, or mentions of Gem, are addressed. A recent reply makes a follow-up likely only if it clearly continues that exchange. If unsure, false.
- actions: in order, only from the list. They announce their own results, so leave reply "" when you use them unless you must add something.
- reply: answer questions from your knowledge. For live or recent facts you can't know (news, scores, prices, schedules), use web_answer. Prefer a fitting action (e.g. weather) over it; web_search only opens results in the browser. If something essential is missing, ask one short question.
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
    # A web answer speaks for itself; the model's own guess would be stale. The planner can't see the screen,
    # so anything it says about it would be made up: the screen actions answer for themselves.
    if any(a["name"] in ("web_answer", "explain_screen", "copy_screen_text", "screen_save", "screen_find",
                         "read_screen", "read_aloud", "timeline_at", "timeline_app", "timeline_day", "recent_files")
           for a in acts):
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
        self._limits = {}               # model -> (tokens left this minute, minute allowance, refill time)
        self.speaker = None             # set when a known person other than the user is talking
        self.last_service = "Groq"      # who answered last, for the dashboard
        self._plain = set()             # backup models that refused extra options

    @property
    def key(self):
        return os.environ.get("GROQ_API_KEY", "")

    def backups(self):
        """Backup services that have a key: [(service settings, key)]."""
        return [(b, secret(b.get("key_env"))) for b in self.cfg.get("backups") or []
                if b.get("url") and secret(b.get("key_env"))]

    def available(self):
        return bool(self.key or self.backups())

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

    def _note_limits(self, model, headers):
        """Remember how many tokens a model has left this minute (Groq sends it with every reply)."""
        try:
            left = int(headers.get("x-ratelimit-remaining-tokens"))
            limit = int(headers.get("x-ratelimit-limit-tokens"))
        except (TypeError, ValueError):
            return
        m = re.match(r"(?:(\d+)m)?([\d.]+)s", headers.get("x-ratelimit-reset-tokens") or "")
        reset = (int(m.group(1) or 0) * 60 + float(m.group(2))) if m else 60.0
        self._limits[model] = (left, limit, time.time() + reset)

    def _count(self, model, tokens):
        """Add to today's token count for a model (the free tier also has a daily cap per model)."""
        from .config import runtime
        today = datetime.date.today().isoformat()
        with runtime as d:
            usage = d.setdefault("ai_usage", {})
            if usage.get("day") != today:
                usage.clear()
                usage["day"] = today
            usage[model] = int(usage.get(model, 0)) + int(tokens)

    def used_today(self, model):
        from .config import runtime
        usage = runtime.data.get("ai_usage") or {}
        return int(usage.get(model, 0)) if usage.get("day") == datetime.date.today().isoformat() else 0

    def budget(self, model):
        """Tokens a model can probably still take this minute (its full allowance if we haven't heard)."""
        left, limit, refill_at = self._limits.get(model, (None, None, 0))
        if left is None:
            return 10 ** 6
        if self._cooldown.get(model, 0) > time.time():
            return 0
        return limit if time.time() >= refill_at else left

    def _routes(self, models, vision):
        """Everything to try, in order: (service, url, key, model, extra body fields)."""
        routes = [("Groq", CHAT_URL, self.key, m, None) for m in models or self.cfg.get("models", [])] \
            if self.key else []
        for b, key in self.backups():
            for m in (b.get("vision_models") if vision else b.get("models")) or []:
                routes.append((b.get("name") or "Backup", b["url"], key, m, b.get("extra") or {}))
        return routes

    def _post(self, messages, json_mode=False, max_tokens=500, temperature=0.3, models=None, vision=False):
        if not self.available():
            raise BrainUnavailable("Set the GROQ_API_KEY environment variable so I can answer that.")
        last_error = "no model available"
        for service, url, key, model, extra in self._routes(models, vision):
            groq = extra is None
            slot = model if groq else "%s:%s" % (service, model)
            if self._cooldown.get(slot, 0) > time.time():
                continue
            if groq:
                body = self._body(model, messages, json_mode, max_tokens, temperature)
            else:
                body = {"model": model, "messages": messages, "max_tokens": max_tokens, "temperature": temperature}
                if slot not in self._plain:
                    body.update(extra)
                    if json_mode:
                        body["response_format"] = {"type": "json_object"}
            try:
                r = self.session.post(url, headers={"Authorization": "Bearer " + key}, json=body, timeout=20)
                if r.status_code == 400 and not groq and slot not in self._plain and (extra or json_mode):
                    # Services differ in which options they accept; from now on send that model just the basics.
                    log.info("%s %s refused the options (%s); retrying plainly", service, model, r.text[:120])
                    self._plain.add(slot)
                    for k in list(extra) + ["response_format"]:
                        body.pop(k, None)
                    r = self.session.post(url, headers={"Authorization": "Bearer " + key}, json=body, timeout=20)
            except requests.RequestException as e:
                last_error = "network: %s" % e
                log.warning("%s %s request failed: %s", service, model, e)
                if isinstance(e, (requests.ConnectionError,)) and groq:
                    break
                continue
            if groq:
                self._note_limits(model, r.headers)
            if r.status_code == 429:
                wait = float(r.headers.get("retry-after") or (20 if groq else 60))
                self._cooldown[slot] = time.time() + wait
                log.warning("%s %s rate limited for %.0fs", service, model, wait)
                last_error = "rate limited"
                continue
            if r.status_code >= 400:
                last_error = "%s %s" % (r.status_code, r.text[:200])
                log.warning("%s %s error: %s", service, model, last_error)
                if r.status_code in (401, 403):
                    if groq:
                        raise BrainUnavailable("My Groq API key was rejected. Check GROQ_API_KEY.")
                    self._cooldown[slot] = time.time() + 600        # a bad backup key shouldn't slow every request
                elif r.status_code == 404 and not groq:
                    self._cooldown[slot] = time.time() + 3600       # that model name isn't offered there
                continue
            try:
                data = r.json()
                content = data["choices"][0]["message"].get("content") or ""
            except Exception:
                continue
            self._count(slot, (data.get("usage") or {}).get("total_tokens") or 0)
            if json_mode and _parse_json(content) is None:
                log.warning("%s %s returned invalid JSON: %r", service, model, content[:200])
                continue
            if service != self.last_service:
                log.info("Answering with %s (%s)", service, model)
                self.last_service = service
            return content, slot
        if "network" in last_error:
            raise BrainUnavailable("I'm offline right now, so I can only do the basics: timers, alarms, volume, "
                                   "music and apps.")
        if "rate limited" in last_error:
            raise BrainUnavailable("I've hit the free AI limit for the moment. Basic commands still work; try "
                                   "questions again in a minute.")
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
        tag = self._tag(source)
        if self.speaker:
            tag += " [speaking: %s, not %s; address them by name]" % (self.speaker, self.user_name)
        messages = [{"role": "system", "content": self._system()}, *self.history,
                    {"role": "user", "content": "%s %s" % (tag, text)}]
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

    def complete(self, instruction, text="", max_tokens=700, json_mode=False, temperature=0.4, models=None):
        messages = [{"role": "system", "content": instruction}]
        if text:
            messages.append({"role": "user", "content": text})
        content, _ = self._post(messages, json_mode=json_mode, max_tokens=max_tokens, temperature=temperature,
                                models=models)
        return _parse_json(content) if json_mode else content.strip()

    def see(self, instruction, question, image_url, max_tokens=400):
        """Answer a question about an image (a data: URL, or a list of them) with a vision model."""
        urls = image_url if isinstance(image_url, (list, tuple)) else [image_url]
        messages = [{"role": "system", "content": instruction},
                    {"role": "user", "content": [{"type": "text", "text": question}] +
                     [{"type": "image_url", "image_url": {"url": u}} for u in urls]}]
        content, _ = self._post(messages, max_tokens=max_tokens, temperature=0.2,
                                models=self.cfg.get("vision_models") or ["qwen/qwen3.8-27b"], vision=True)
        return content.strip()
