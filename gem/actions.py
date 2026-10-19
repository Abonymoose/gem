"""Registry of everything Gem can do.

Skills register functions with @action. The local router and the AI planner
both call actions by name, so every feature works whether a request is
matched instantly or understood by the model. Actions return the sentence
Gem should say (or None).
"""
import inspect
import logging

log = logging.getLogger("gem.actions")

REGISTRY = {}


class Action:
    __slots__ = ("name", "fn", "args", "doc", "ai")

    def __init__(self, name, fn, args, doc, ai):
        self.name, self.fn, self.args, self.doc, self.ai = name, fn, args, doc, ai


class ActionError(Exception):
    """Raise with a short sentence to say it to the user."""


def action(name, doc, args="", ai=True):
    """ai=False keeps an action out of the model's catalog (router only)."""
    def deco(fn):
        REGISTRY[name] = Action(name, fn, args, doc, ai)
        return fn
    return deco


def catalog():
    return "\n".join("%s(%s): %s" % (a.name, a.args, a.doc) for a in REGISTRY.values() if a.ai)


def exists(name):
    return name in REGISTRY


def run(name, args=None):
    a = REGISTRY.get(name)
    if a is None:
        log.warning("Unknown action %r", name)
        return None
    args = dict(args or {})
    params = inspect.signature(a.fn).parameters
    accepted = {k: v for k, v in args.items() if k in params}
    dropped = set(args) - set(accepted)
    if dropped:
        log.debug("Action %s ignored args %s", name, dropped)
    log.info("Action %s %s", name, accepted)
    try:
        return a.fn(**accepted)
    except ActionError as e:
        return str(e)
    except TypeError as e:
        log.warning("Action %s bad arguments %s: %s", name, accepted, e)
        return "I couldn't do that, something was missing."
    except Exception:
        log.exception("Action %s failed", name)
        return "Sorry, that didn't work."
