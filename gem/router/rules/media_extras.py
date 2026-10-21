"""Commands: Video controls, trivia, ambient sounds, voice notes, images, audio output, recording."""
import re

from ...parse import parse_duration
from ...skills import ambient
from ..core import Match, said


def register(rule):
    # Video
    @rule(r"^(?:skip|skip ahead|skip forward|fast forward|go forward|jump ahead|jump forward|forward)(?: by)? "
          r"(.+?)(?: forward| ahead)?$")
    def _(m, t):
        secs = parse_duration(m.group(1))
        return Match("video_seek", {"seconds": secs}) if secs else None

    @rule(r"^(?:rewind|go back|jump back|skip back|skip backward|back)(?: by)? (.+?)(?: back)?$")
    def _(m, t):
        secs = parse_duration(m.group(1))
        return Match("video_seek", {"seconds": -secs}) if secs else None

    @rule(r"^(?:make (?:it|the video|this) |go |video )?full ?screen$")
    def _(m, t):
        return Match("video_key", {"what": "fullscreen"})

    @rule(r"^(?:turn on |turn off |toggle |show |hide |put on |enable |disable )?(?:the )?(?:captions|subtitles|subs|cc)"
          r"(?: on| off)?$")
    def _(m, t):
        return Match("video_key", {"what": "captions"})

    # Games and sounds
    @rule(r"^(?:let's play|lets play|play|start|can we play|i want to play|do) (?:a |some )?(?:game of |round of )?"
          r"trivia(?: about (.+)| on (.+))?$|^trivia(?: time)?(?: about (.+))?$|^quiz me(?: on| about)? ?(.*)$")
    def _(m, t):
        return Match("trivia_start", {"topic": next((g for g in m.groups() if g), "")})

    @rule(r"^(?:play|put on|start|turn on)(?: some| the)? (rain|ocean waves|ocean|waves|sea waves|sea|beach|fan|"
          r"thunderstorm|storm|brown noise|pink noise|white noise|brown|pink|white)(?: sounds?| noise)?(?: for (.+))?$")
    def _(m, t):
        what = m.group(1)
        if what in ("brown", "pink", "white", "fan", "storm", "sea") and not re.search(r"\b(?:noise|sounds?)\b", t):
            return None                                 # "play white" is more likely a song
        secs = parse_duration(m.group(2) or "")
        return Match("ambient_play", {"sound": what, "minutes": secs / 60.0 if secs else None})

    @rule(r"^(?:stop|turn off|end|kill) (?:the )?(?:(?:rain|ocean|ambient|background|fan|wave|waves) )?(?:sounds?|noise)$|"
          r"^(?:stop|turn off|end|kill) (?:the )?(?:white|brown|pink) noise(?: sounds?)?$")
    def _(m, t):
        return Match("ambient_stop")

    @rule(r"^(?:stop|turn off|end|kill) (?:the )?(?:rain|ocean|ocean waves|waves|sea|fan|storm|thunderstorm)$")
    def _(m, t):
        return Match("ambient_stop") if ambient.player["stop"] else None

    @rule(r"^(?:make )?(?:the )?(?:rain|ocean|waves|fan|storm|ambient|background|noise|sounds?|white noise|brown noise|"
          r"pink noise) (?:a (?:bit|little) )?(louder|quieter|softer)$")
    def _(m, t):
        return Match("ambient_volume", {"direction": "up" if m.group(1) == "louder" else "down"})

    @rule(r"^make it (?:a (?:bit|little) )?(louder|quieter|softer)$")
    def _(m, t):
        up = m.group(1) == "louder"
        if ambient.player["stop"]:
            return Match("ambient_volume", {"direction": "up" if up else "down"})
        return Match("volume", {"change": 10 if up else -10})

    # Voice notes
    @rule(r"^(?:record|take|make|start|leave) (?:a |me a )?voice (?:note|memo|message)$")
    def _(m, t):
        return Match("voice_note")

    @rule(r"^(?:play|listen to) (?:my |the )?(?:last |latest )?voice (?:note|memo)(?: about (.+))?$")
    def _(m, t):
        return Match("voice_note_play", {"query": m.group(1) or ""})

    @rule(r"^(?:read|show|list|what are|what's in) (?:me )?(?:my )?(?:latest )?voice (?:notes|memos|note)"
          r"(?: about (.+))?$|^what did i say in my voice note(?: about (.+))?$")
    def _(m, t):
        return Match("voice_notes_list", {"query": m.group(1) or m.group(2) or ""})

    # Images
    @rule(r"^(?:make|create|generate|draw|design|paint|give)(?: me)? (?:a |an |some )?(?:new )?"
          r"(wallpaper|background|desktop background|image|picture|drawing|painting|art|artwork|pic)"
          r"(?: of| with| showing| that shows)? (.+)$")
    def _(m, t):
        raw = re.search(r"(?:wallpaper|background|image|picture|drawing|painting|art|artwork|pic)"
                        r"(?:\s+(?:of|with|showing|that shows))?\s+(.+?)[.!?]*$", said(), re.I)
        return Match("imagine", {"prompt": raw.group(1) if raw else m.group(2),
                                 "wallpaper": m.group(1) in ("wallpaper", "background", "desktop background")})

    @rule(r"^draw (?:me )?(?:a |an )?(.+)$")
    def _(m, t):
        return Match("imagine", {"prompt": m.group(1)})

    @rule(r"^(?:set|make|use|put) (?:it|that|this|that one|this one|the image|the picture) (?:as )?(?:my |the )?"
          r"(?:wallpaper|background|desktop(?: background)?)$")
    def _(m, t):
        return Match("set_wallpaper")

    # Audio output
    @rule(r"^(?:switch|change|move|swap|put) (?:the )?(?:audio|sound|output|speaker)(?: output)? (?:to|over to) "
          r"(?:my |the )?(.+)$|^(?:switch|change) to (?:my |the )?(headphones|headset|speakers|earphones|earbuds)$|"
          r"^(?:use|play (?:sound|audio) (?:through|on|from)) (?:my |the )?(headphones|headset|speakers|earphones|"
          r"earbuds|monitor|tv)$")
    def _(m, t):
        return Match("audio_output", {"device": next(g for g in m.groups() if g)})

    @rule(r"^(?:what(?:'s| is| am i) (?:my )?(?:audio|sound) (?:output|playing through|coming out of)|which "
          r"(?:speakers|audio device|output) (?:is|am i using)(?: on)?|where is (?:the )?sound coming from)$")
    def _(m, t):
        return Match("audio_output", {"device": ""})

    # Screen recording
    @rule(r"^(?:start |begin )?(?:screen )?recording(?: my screen| the screen| this)?$|"
          r"^record (?:my |the )?(?:screen|gameplay|game)$|^start recording (?:my |the )?(?:screen|game|gameplay)$")
    def _(m, t):
        return Match("record_screen", {"on": True})

    @rule(r"^(?:stop|end|finish) (?:the )?(?:screen )?recording$")
    def _(m, t):
        return Match("record_screen", {"on": False})
