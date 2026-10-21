"""Commands: Air quality and other people's dates."""
from ..core import Match


def register(rule):
    # Air
    @rule(r"^(?:how(?:'s| is) the |what(?:'s| is) the |check the )?(?:air quality|aqi|pollution|air)(?: like)?"
          r"(?: in (.+?))?(?: today| right now| now| outside)?$|^is the air (?:bad|good|safe|clean|polluted)"
          r"(?: today| outside)?$|^(?:what(?:'s| is) the )?uv(?: index)?(?: today| right now)?$")
    def _(m, t):
        if t in ("air",):
            return None
        return Match("air_quality", {"city": m.group(1) or ""})

    # Other people's dates
    @rule(r"^([a-z]+(?: [a-z]+)?)'s (birthday|bday|anniversary) is (?:on )?(.+)$")
    def _(m, t):
        from ...skills import world
        if not world.parse_date(m.group(3)):
            return None
        kind = "birthday" if m.group(2) == "bday" else m.group(2)
        return Match("save_date", {"name": "%s's %s" % (m.group(1), kind), "date": m.group(3)})
