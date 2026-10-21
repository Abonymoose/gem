"""Instant, offline understanding of common commands.

Anything matched here runs without calling the AI, which makes it fast and
saves free-tier requests. Anything not matched goes to the AI planner.

safe=True marks commands that are harmless to run even if the speech wasn't
meant for Gem (always-listening mode); the rest need Gem's name, push-to-talk
or an ongoing conversation.
"""
from .core import Match, match, normalize
from .repair import repair

__all__ = ["Match", "match", "normalize", "repair"]
