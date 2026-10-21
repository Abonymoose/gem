"""Commands: Gaming and PC."""
from ..core import Match


def register(rule):
    # Gaming and PC
    @rule(r"^(?:(?:un)?mute|(?:un)?deafen) (?:me|myself|my mic(?:rophone)?)(?: (?:on|in) discord)?$|"
          r"^(?:(?:un)?mute|(?:un)?deafen) (?:me |myself )?(?:on|in) discord$|^discord (?:un)?(?:mute|deafen)$|"
          r"^toggle (?:discord )?(?:mute|deafen)$", safe=False)
    def _(m, t):
        return Match("discord_toggle", {"what": "deafen" if "deaf" in m.group(0) else "mute"}, False)

    @rule(r"^(?:clip (?:that|it|this)|clip the last (?:\d+ |thirty |30 )?seconds?|save (?:that|a|the) clip|"
          r"save the last (?:\d+ |thirty )?seconds|record (?:that|what just happened))(?: please)?$")
    def _(m, t):
        return Match("clip_that")

    @rule(r"^(?:run an? |do an? |start an? )?(?:internet |wifi |wi-fi |network )?speed ?test$|"
          r"^(?:how fast is|what's the speed of|check the speed of|test the speed of) (?:my |the )?"
          r"(?:internet|wifi|wi-fi|connection|network)(?: right now)?$|"
          r"^(?:my )?(?:internet|wifi|wi-fi|network|download) speed$|^test (?:my )?(?:internet|wifi|wi-fi) speed$")
    def _(m, t):
        return Match("speed_test")

    @rule(r"^(?:clean|clean up|tidy|tidy up|organi[sz]e|sort|sort out) (?:my |the )?downloads(?: folder)?$")
    def _(m, t):
        return Match("tidy_downloads")

    @rule(r"^(?:undo (?:the |that )?(?:tidy|tidy up|cleanup|clean up|organi[sz]ing)|put my downloads back|"
          r"undo (?:the )?downloads (?:tidy|cleanup))$")
    def _(m, t):
        return Match("tidy_undo")

    @rule(r"^(?:what should i|what can i|what do i|give me something to|recommend (?:me )?something to|"
          r"suggest something to|find me something to|i want something to) (watch|play)"
          r"(?: (?:tonight|today|now|later))?(?:,? (?:something )?(.+?))?$")
    def _(m, t):
        return Match("picks", {"kind": m.group(1), "mood": m.group(2) or ""})

    @rule(r"^(?:recommend|suggest)(?: me)? (?:a |an |some )?((?:[a-z-]+ ){0,2})"
          r"(movies?|shows?|series|anime|games?|youtube videos?|youtubers?)(?: to (?:watch|play))?"
          r"(?: (?:tonight|today))?$")
    def _(m, t):
        what = m.group(2)
        return Match("picks", {"kind": "play" if what.startswith("game") else "watch",
                               "mood": (m.group(1) + what).strip()})
