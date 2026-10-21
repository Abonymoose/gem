"""Commands: Web answers."""
from ..core import Match


def register(rule):
    # Web
    @rule(r"^(?:search wikipedia for|wikipedia)\s+(.+)$")
    def _(m, t):
        return Match("wikipedia", {"topic": m.group(1)})

    @rule(r"^(?:google|search google for|open results for|show me results for)\s+(?:for\s+)?(.+)$", safe=False)
    def _(m, t):
        return Match("web_search", {"query": m.group(1)}, False)

    @rule(r"^(?:search|look up|search for|search the web for|look up online|find out|check online)\s+"
          r"(?:for\s+)?(.+)$", safe=False)
    def _(m, t):
        return Match("web_answer", {"query": m.group(1)}, False)
