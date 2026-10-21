"""Tests for Gem's offline logic: command routing, time and number parsing, maths.

Run from the project folder:   python -m unittest tests

They run on Windows and, with the Windows APIs stubbed out, on Linux and macOS too. Gem's data folder
points at a temporary folder for the run, so your real ~/.gem is never touched.
"""
import os
import sys
import tempfile

_home = tempfile.mkdtemp(prefix="gem-tests-")
os.environ["HOME"] = os.environ["USERPROFILE"] = _home

if sys.platform != "win32":
    from . import _winstubs
    _winstubs.install()

from gem import config  # noqa: E402
from gem.runtime import svc  # noqa: E402

svc.config = config.load_settings()

import gem.skills  # noqa: E402,F401  (registers every action)
from gem.skills import apps  # noqa: E402

apps.index.ready.set()          # no Start Menu scan in tests


def load_tests(loader, tests, pattern):
    """`python -m unittest tests` runs every test module in this folder."""
    here = os.path.dirname(os.path.abspath(__file__))
    tests.addTests(loader.discover(here, pattern or "test*.py", os.path.dirname(here)))
    return tests
