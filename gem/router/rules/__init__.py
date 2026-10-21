"""All command rules, one module per feature. Order matters: the first rule that matches wins, so the
modules are registered in this order (the same order the rules always had)."""
from . import (control, hearing, quick, world, insights, timers, productivity,
               voices, extras, screen, gem_voice, pc, files, power,
               media_extras, life, gaming, screen_explain, system, text,
               small, web)  # noqa: F401

ORDER = [control, hearing, quick, world, insights, timers, productivity,
         voices, extras, screen, gem_voice, pc, files, power,
         media_extras, life, gaming, screen_explain, system, text,
         small, web]


def register_all(rule):
    for module in ORDER:
        module.register(rule)
