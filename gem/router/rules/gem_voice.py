"""Commands: Gem's own voice volume."""
from ..core import Match


def register(rule):
    # Gem's own voice volume (not the PC's)
    @rule(r"\b(?:your|gem'?s|gems) (?:voice |own |speaking )?volume\b.*?\b(?:to|at) (\d{1,3})(?: percent|%)?$")
    def _(m, t):
        return Match("voice_volume", {"level": int(m.group(1))})

    @rule(r"^(?:reduce|lower|decrease|turn down) (?:your|gem'?s|gems) (?:voice |own )?volume$|^(?:talk|speak) "
          r"(?:a (?:bit|little) )?(?:quieter|softer|more quietly|more softly)$|^(?:be|get) quieter$")
    def _(m, t):
        return Match("voice_volume", {"change": -15})

    @rule(r"^(?:increase|raise|turn up) (?:your|gem'?s|gems) (?:voice |own )?volume$|^(?:talk|speak) "
          r"(?:a (?:bit|little) )?(?:louder|up)$|^(?:be|get) louder$")
    def _(m, t):
        return Match("voice_volume", {"change": 15})
