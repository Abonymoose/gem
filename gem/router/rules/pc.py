"""Commands: what this PC is (maker or motherboard, CPU, GPU, RAM, Windows)."""
from ..core import Match


def register(rule):
    @rule(r"^(?:what (?:pc|computer|laptop|motherboard|cpu|processor|gpu|graphics card|graphics) (?:do i have|is this|"
          r"am i using|is in (?:my|this) (?:pc|computer))|what(?:'s| is| are) (?:my|this) (?:pc|computer|laptop)(?:'s)? "
          r"(?:model|specs)|(?:what are )?my (?:pc |computer )?specs|how much ram do i have|what(?:'s| is) my "
          r"(?:gpu|graphics card|processor|motherboard))$")
    def _(m, t):
        return Match("pc_specs")
