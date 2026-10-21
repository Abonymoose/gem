"""Commands: Volume, media, windows, system info and windows by app name."""
import re

from ...parse import parse_percent, words_to_numbers
from ...skills import apps
from ..core import Match, _known_app, _openable

_VOLUME_WORDS = {"set", "change", "turn", "put", "make", "bring", "the", "my", "volume", "sound", "level", "to", "at",
                 "up", "down", "by", "percent", "%", "a", "bit", "little", "lot", "raise", "lower", "increase",
                 "decrease", "reduce", "boost", "louder", "quieter", "higher", "more", "it", "of", "pc", "computer",
                 "system", "master", "main", "overall", "'s", "s", "notch", "tad", "slightly", "some"}


def register(rule):
    # Undo Gem's last change (volume, brightness, theme, a cancelled timer)
    @rule(r"^(?:undo(?: that| it| the last (?:thing|change)| what you (?:just )?did)?|put it back(?: how it was)?|"
          r"change it back|revert(?: that| it)?|set it back|go back to how it was|bring (?:it|that) back)$", safe=False)
    def _(m, t):
        return Match("undo", {}, False)

    # Volume
    @rule(r"^(?:what's|what is|check) (?:the |my )?volume(?: level)?$|^how loud is it$|^volume level$")
    def _(m, t):
        return Match("volume")

    @rule(r"^(mute|unmute)(?: the)?(?: (?:sound|volume|audio|pc|computer|everything|speakers))?$", safe=False)
    def _(m, t):
        return Match("volume", {"mute": m.group(1) == "mute"}, False)

    @rule(r"^(mute|unmute)\s+(.+)$", safe=False)
    def _(m, t):
        return Match("volume", {"mute": m.group(1) == "mute", "app": m.group(2)}, False) \
            if _known_app(m.group(2)) else None

    @rule(r"^(?:max|maximum|full) volume$|^volume (?:max|maximum|full)$|^(?:turn it|volume) all the way up$|"
          r"^(?:set |turn |put )?(?:the )?volume (?:to |at |up to )?(?:max|maximum|full)$")
    def _(m, t):
        return Match("volume", {"level": 100})

    @rule(r"volume")
    def _(m, t):
        tn = words_to_numbers(t)
        app = None
        am = re.search(r"(?:set |change |turn )?(?:the )?(.+?)(?:'s)? volume", tn)
        if am and am.group(1) not in ("the", "my", "set", "change", "turn", "set the", "your") and _known_app(am.group(1)):
            app = am.group(1)
        # Only a sentence made of volume words is a command; "he turned the volume up so loud" is a story.
        rest = tn.replace(app, " ") if app else tn
        if set(rest.split()) - _VOLUME_WORDS - {w for w in rest.split() if re.fullmatch(r"\d{1,3}%?", w)}:
            return None
        to = re.search(r"\b(?:down|up) to (\d{1,3})\b", tn)
        if to:
            return Match("volume", {"level": min(100, int(to.group(1))), "app": app})
        if re.search(r"\b(?:up|increase|raise|louder|higher|boost)\b", tn):
            n = re.search(r"\bby (\d+)", tn)
            return Match("volume", {"change": int(n.group(1)) if n else 10, "app": app})
        if re.search(r"\b(?:down|decrease|lower|reduce|quieter)\b", tn):
            n = re.search(r"\bby (\d+)", tn)
            return Match("volume", {"change": -(int(n.group(1)) if n else 10), "app": app})
        pct = parse_percent(tn)
        if pct is not None:
            return Match("volume", {"level": pct, "app": app})
        return None

    @rule(r"^(?:louder|turn it up|turn up the sound|turn the sound up)$")
    def _(m, t):
        return Match("volume", {"change": 10})

    @rule(r"^(?:quieter|softer|turn it down|turn down the sound|turn the sound down)$")
    def _(m, t):
        return Match("volume", {"change": -10})

    @rule(r"^(?:turn|lower|raise) (?:down |up )?(.+?)(?: (down|up))?$")
    def _(m, t):
        name = re.sub(r"^(?:down|up)\s+", "", m.group(1))
        if not _known_app(name) or not re.search(r"\b(?:down|up|lower|raise)\b", t):
            return None
        up = " up" in " " + t or t.startswith("raise")
        return Match("volume", {"change": 15 if up else -15, "app": name})

    # Media
    @rule(r"^(?:pause|play|resume|unpause)(?: the)?(?: music| song| track| video| it| spotify| that)?$")
    def _(m, t):
        return Match("media", {"command": "play_pause"})

    @rule(r"^(?:next|skip)(?: this)?(?: song| track| one| video)?$|^play (?:the )?next (?:song|track)$")
    def _(m, t):
        return Match("media", {"command": "next"})

    @rule(r"^(?:previous|go back|last)(?: a)?(?: song| track)$|^previous$|^play (?:the )?(?:previous|last) (?:song|track)$")
    def _(m, t):
        return Match("media", {"command": "previous"})

    @rule(r"^stop (?:the )?(?:music|song|video|playback)$")
    def _(m, t):
        return Match("media", {"command": "play_pause"})

    @rule(r"^(?:what's playing|what is playing|what song is this|what's this song|who sings this|"
          r"what's the song|current song)$")
    def _(m, t):
        return Match("now_playing")

    @rule(r"^(?:play|put on|watch)\s+(.+?)\s+on\s+(?:youtube|yt)$|^(?:youtube|search youtube for)\s+(.+)$")
    def _(m, t):
        return Match("youtube", {"query": m.group(1) or m.group(2)})

    @rule(r"^play\s+(.+?)\s+on spotify$")
    def _(m, t):
        return Match("spotify_search", {"query": m.group(1)})

    @rule(r"^(?:play (?:it|that|this|the (?:last )?song) again|replay (?:it|that|this|the song)|"
          r"(?:restart|start over) (?:the |this )?(?:song|track))$", safe=False)
    def _(m, t):
        return Match("media", {"command": "previous"})       # players restart the track when it's past the start

    @rule(r"^play (?:the )?next (?:one|video)$")
    def _(m, t):
        return Match("media", {"command": "next"})

    @rule(r"^(?:play|put on) (?:some )?(?:music|something|songs?|a song|some tunes|tunes)$")
    def _(m, t):
        return Match("media", {"command": "play_pause"})

    @rule(r"^(?:play|put on)\s+(.+)$")
    def _(m, t):
        if re.fullmatch(r"(?:it|that|this|them|him|her|again|along|around|with (?:it|that|me|them)|outside|now|"
                        r"the game|a game|games?|fair|nice|dumb|dead|catch|ball|tag)(?: again| now| later| with \w+)?",
                        m.group(1)):
            return None                                         # not something to look up on YouTube
        return Match("youtube", {"query": m.group(1)})

    # Screens and windows
    @rule(r"^(?:take a |grab a |take an? )?(?:screenshot|screen shot|screen capture|capture (?:my |the )?screen|"
          r"print screen)(?: of)?(?: (?:this|the|my))?( window)?$")
    def _(m, t):
        return Match("screenshot", {"region": "window" if m.group(1) else "screen"})

    @rule(r"^(?:snip|snipping tool|screenshot (?:an area|part of the screen)|clip (?:part of )?(?:my |the )?screen)$")
    def _(m, t):
        return Match("screenshot", {"region": "snip"})

    @rule(r"^(?:show (?:the |my )?desktop|minimi[sz]e (?:everything|all(?: windows)?)|hide (?:all )?(?:the )?windows)$")
    def _(m, t):
        return Match("window", {"command": "show_desktop"})

    @rule(r"^(minimi[sz]e|maximi[sz]e)(?: (?:this|it|the window|this window|window))?$")
    def _(m, t):
        return Match("window", {"command": "minimize" if "min" in m.group(1) else "maximize"})

    @rule(r"^(?:snap|move|put) (?:this |it |the window |this window )?(?:to the )?(left|right)$")
    def _(m, t):
        return Match("window", {"command": "snap_" + m.group(1)})

    @rule(r"^(?:task view|show (?:me )?all (?:my )?windows)$")
    def _(m, t):
        return Match("window", {"command": "task_view"})

    @rule(r"^(?:lock|lock (?:my |the )?(?:pc|computer|screen|laptop|windows|it))$", safe=False)
    def _(m, t):
        return Match("power", {"command": "lock"}, False)

    @rule(r"^(?:put (?:my |the )?(?:pc|computer|laptop) to sleep|sleep (?:the )?(?:pc|computer|laptop))$", safe=False)
    def _(m, t):
        return Match("power", {"command": "sleep"}, False)

    @rule(r"^(?:restart|reboot) (?:my |the )?(?:pc|computer|laptop|windows)$", safe=False)
    def _(m, t):
        return Match("power", {"command": "restart"}, False)

    @rule(r"^(?:sign out|log out|log off)$", safe=False)
    def _(m, t):
        return Match("power", {"command": "sign_out"}, False)

    @rule(r"^(?:cancel|abort|stop) (?:the )?(?:shutdown|restart)$", safe=False)
    def _(m, t):
        return Match("power", {"command": "cancel_shutdown"}, False)

    @rule(r"^(?:close|quit|exit|kill|shut down|shutdown|terminate|end)\s+(.+)$", safe=False)
    def _(m, t):
        target = re.sub(r"^(?:the|my)\s+", "", m.group(1))
        if target in ("this", "this window", "window", "it", "that", "current window", "that window", "the window"):
            return Match("close_window", {}, False)
        if target in ("pc", "computer", "laptop", "windows") and "shut" in t:
            return Match("power", {"command": "shutdown"}, False)
        if target in ("gem", "jem", "yourself"):
            return Match("quit_gem", {}, False)
        if re.match(r"^(?:gaming|game) mode$", target):
            return Match("gaming_mode", {"on": False})
        return Match("close_app", {"name": target}, False) if _known_app(target) else None

    @rule(r"^(?:switch to|go to|bring up|focus on|show me)\s+(.+)$")
    def _(m, t):
        target = re.sub(r"^(?:the|my)\s+", "", m.group(1))
        if apps.running(target):
            return Match("switch_to", {"name": target})
        if _openable(target):
            return Match("open_app", {"name": target})
        return None

    @rule(r"^(?:open|launch|start|run|fire up|boot up|load|pull up|bring up)\s+(?:up\s+)?(.+)$")
    def _(m, t):
        target = m.group(1)
        if re.match(r"^(?:a |the )?(?:dictation|focus|timer|pomodoro)", target):
            return None
        return Match("open_app", {"name": target}) if _openable(target) else None

    @rule(r"^(?:what(?:'s| is) (?:this|this window|in front|open)|which (?:app|window) is this)$")
    def _(m, t):
        return Match("what_window")

    @rule(r"^(?:open|show) (?:my |the )?(?:latest|last|newest|most recent) download$")
    def _(m, t):
        return Match("open_latest_download")

    @rule(r"^(?:find|open|search for) (?:my |the )?file (?:called |named )?(.+)$", safe=False)
    def _(m, t):
        return Match("find_file", {"name": m.group(1)}, False)

    # System info
    @rule(r"^(?:cpu(?: usage)?|how's my cpu|what's my cpu(?: usage| at)?|processor usage)$")
    def _(m, t):
        return Match("system_info", {"what": "cpu"})

    @rule(r"^(?:ram(?: usage)?|memory usage|how much (?:ram|memory)(?: am i using| is used)?)$")
    def _(m, t):
        return Match("system_info", {"what": "ram"})

    @rule(r"^(?:disk space|storage|how much (?:disk )?space(?: do i have)?(?: left)?|free space|"
          r"how much storage(?: do i have)?(?: left)?)$")
    def _(m, t):
        return Match("system_info", {"what": "disk"})

    @rule(r"^(?:battery(?: level| status)?|how much battery(?: do i have)?(?: left)?|what's my battery(?: at)?)$")
    def _(m, t):
        return Match("system_info", {"what": "battery"})

    @rule(r"^(?:uptime|pc uptime|how long has (?:my |the )?(?:pc|computer|laptop) been (?:on|running))$")
    def _(m, t):
        return Match("system_info", {"what": "uptime"})

    @rule(r"^what's (?:using|eating) (?:my |all my )?(?:memory|ram|cpu)$|^what's slowing (?:down )?my (?:pc|computer)$")
    def _(m, t):
        return Match("system_info", {"what": "top_processes"})

    @rule(r"^what's my (?:ip|ip address)$|^what is my ip(?: address)?$")
    def _(m, t):
        return Match("system_info", {"what": "ip"})

    @rule(r"^(?:system stats|pc stats|system status|system info|how's my pc(?: doing)?|computer stats)$")
    def _(m, t):
        return Match("system_info", {"what": "overview"})

    @rule(r"^(?:ping|test (?:my )?internet|is (?:my )?internet working|"
          r"check (?:my )?(?:internet|connection|wifi))$")
    def _(m, t):
        return Match("ping")

    @rule(r"^(?:turn on |enable |switch to )?dark mode(?: on)?$")
    def _(m, t):
        return Match("dark_mode", {"on": True})

    @rule(r"^(?:turn on |enable |switch to )?light mode(?: on)?$|^(?:turn off|disable) dark mode$|^dark mode off$")
    def _(m, t):
        return Match("dark_mode", {"on": False})

    @rule(r"^(?:set )?(?:the )?(?:screen |monitor )?brightness (?:to |at )?(.+)$")
    def _(m, t):
        what = m.group(1)
        if re.match(r"^(?:up|higher|more)$", what):
            return Match("brightness", {"change": 15})
        if re.match(r"^(?:down|lower|less)$", what):
            return Match("brightness", {"change": -15})
        pct = parse_percent(what)
        return Match("brightness", {"level": pct}) if pct is not None else None

    @rule(r"^(?:make (?:the |my )?(?:screen|monitor|display) |turn (?:the )?(?:screen|monitor) )?(brighter|dimmer|darker)"
          r"(?: (?:a bit|a little|a lot|please))?$|^(dim|brighten) (?:the |my )?(?:screen|monitor|display)"
          r"(?: (?:a bit|a little|a lot))?$|^turn (?:the )?brightness (up|down)$")
    def _(m, t):
        word = next(g for g in m.groups() if g)
        step = 30 if "a lot" in t else 10 if ("a bit" in t or "a little" in t) else 15
        return Match("brightness", {"change": step if word in ("brighter", "brighten", "up") else -step})

    @rule(r"^(?:what(?:'s| is) (?:the |my )?(?:screen |monitor )?brightness|how bright is (?:the |my )?"
          r"(?:screen|monitor))$")
    def _(m, t):
        return Match("brightness")

    # Windows by app name
    @rule(r"^(?:minimi[sz]e|hide) (?!everything|all\b|this|it$|the window|window)(?:my |the )?(.+?)(?: window| app)?$")
    def _(m, t):
        name = m.group(1)
        return Match("minimize_app", {"name": name}) if apps.running(name) or _known_app(name) else None

    @rule(r"^(?:restore|unminimi[sz]e|bring back|bring up|show|maximi[sz]e) (?:my |the )?(.+?)(?: window| app)?"
          r"(?: again| back)?$")
    def _(m, t):
        name = m.group(1)
        if name in ("this", "it", "the window", "window", "desktop", "me"):
            return None
        return Match("restore_app", {"name": name}) if apps.running(name) else None

    @rule(r"^(?:minimi[sz]e|hide) (?:everything|all(?: windows)?|all the windows) (?:except|but|apart from) "
          r"(?:my |the )?(.+)$|^(?:focus on|just show|only show) (?:my |the )?(.+?) only$")
    def _(m, t):
        return Match("minimize_others", {"name": m.group(1) or m.group(2)})
