"""Every phrase here must keep routing to the same action without the AI. Most come from the README."""
import unittest

from . import svc  # noqa: F401  (sets up the test environment)
from gem import router

# (what was said, expected action, args that must be present)
ROUTES = [
    # Quiet time
    ("shut up for a bit", "snooze", {}),
    ("quiet for an hour", "snooze", {"minutes": 60.0}),
    ("be quiet until I say", "quiet_until_resumed", {}),
    ("I'm back", "resume", {}),
    # Apps
    ("open Spotify", "open_app", {"name": "spotify"}),
    ("close Discord", "close_app", {"name": "discord"}),
    ("open bluetooth settings", "open_app", {"name": "bluetooth settings"}),
    ("open my latest download", "open_latest_download", {}),
    ("find the file called resume", "find_file", {"name": "resume"}),
    # Volume and media
    ("volume 40", "volume", {"level": 40}),
    ("turn it down", "volume", {"change": -10}),
    ("mute Spotify", "volume", {"mute": True, "app": "spotify"}),
    ("Spotify volume 30", "volume", {"level": 30, "app": "spotify"}),
    ("pause", "media", {"command": "play_pause"}),
    ("next song", "media", {"command": "next"}),
    ("what's playing", "now_playing", {}),
    ("play lofi beats on YouTube", "youtube", {"query": "lofi beats"}),
    ("play Blinding Lights on Spotify", "spotify_search", {"query": "blinding lights"}),
    # Windows
    ("show desktop", "window", {"command": "show_desktop"}),
    ("snap this left", "window", {"command": "snap_left"}),
    ("close this window", "close_window", {}),
    ("take a screenshot of this window", "screenshot", {"region": "window"}),
    # Timers, alarms, reminders
    ("10 minute timer for pasta", "set_timer", {"seconds": 600, "label": "pasta"}),
    ("set a timer for 5 minutes", "set_timer", {"seconds": 300}),
    ("set a timer for 1.5 minutes", "set_timer", {"seconds": 90}),         # a decimal, not 1:05
    ("set a timer for 2.25 hours", "set_timer", {"seconds": 8100}),
    ("at 7.30 pm open Spotify", "schedule_command", {"command": "open spotify", "time": "7:30 pm"}),
    ("7.30 pm IST in EST", "time_convert", {"time": "7:30 pm"}),
    ("wake me up at 6.30 a.m.", "set_alarm", {}),
    ("set an alarm for half past 6", "set_alarm", {}),
    ("remind me to call dad at quarter to 9", "set_reminder", {"message": "call dad"}),
    ("set an alarm for 6:30 am", "set_alarm", {}),
    ("how much time is left", "time_left", {}),
    ("cancel the timer", "cancel_timer", {"kind": "timer"}),
    ("remind me to call mom in 15 minutes", "set_reminder", {"message": "call mom"}),
    ("remind me tomorrow at 8 am to submit the essay", "set_reminder", {"message": "submit the essay"}),
    ("remind me to reply to Aarav when I open Discord", "remind_on_open", {"app": "Discord", "message": "reply to Aarav"}),
    ("what's my schedule today", "schedule_list", {"day": "today"}),
    ("when is my next class", "next_class", {}),
    # Productivity
    ("add milk, eggs and bread to my list", "todo_add", {"items": ["milk", "eggs", "bread"]}),
    ("what's on my to-do list", "todo_list", {}),
    ("mark math homework as done", "todo_done", {"item": "math homework"}),
    ("read my notes", "notes_read", {}),
    ("focus for 50 minutes", "focus_start", {"minutes": 50.0}),
    ("stop the focus session", "focus_stop", {}),
    ("good morning", "briefing", {}),
    ("what's the weather", "weather", {"when": "now"}),
    ("is it going to rain tomorrow", "weather", {"when": "tomorrow"}),
    ("my city is Toronto", "set_home_city", {"city": "toronto"}),
    # Text
    ("summarize this", "text_tool", {"task": "summarize"}),
    ("fix the grammar", "text_tool", {"task": "fix_grammar"}),
    ("translate this to Spanish", "text_tool", {"task": "translate"}),
    ("start dictation", "dictation", {"on": True}),
    # PC
    ("system stats", "system_info", {"what": "overview"}),
    ("what's using my memory", "system_info", {"what": "top_processes"}),
    ("dark mode", "dark_mode", {"on": True}),
    ("lock my PC", "power", {"command": "lock"}),
    ("restart the computer", "power", {"command": "restart"}),
    # Memory
    ("remember that my locker code is 42", "remember", {"fact": "my locker code is 42"}),
    ("forget my locker code", "forget", {"about": "my locker code"}),
    # Maths and conversions
    ("what's 15% of 80", "calculate", {}),
    ("12 times 7", "calculate", {}),
    ("what's 3.5 times 2", "calculate", {}),
    ("what's 20% off 50", "calculate", {}),
    ("convert 2.5 litres to ml", "convert", {}),
    ("convert 5 miles to km", "convert", {}),
    ("100 dollars to rupees", "convert", {}),
    ("start a stopwatch", "stopwatch", {"command": "start"}),
    # Clipboard and reading
    ("what did I copy", "clipboard_history", {}),
    ("paste clip 3", "clipboard_paste", {"number": 3}),
    ("read this to me", "read_aloud", {}),
    ("read my screen", "read_screen", {}),
    ("keep reading", "read_more", {}),
    ("copy that", "copy_answer", {}),
    # Habits, time zones, countdowns
    ("log 20 pushups", "habit_log", {"habit": "pushups", "amount": 20}),
    ("how much water today", "habit_stats", {"habit": "water"}),
    ("what time is it in Tokyo", "time_in", {"place": "tokyo"}),
    ("3 pm EST in IST", "time_convert", {"from_place": "est", "to_place": "ist"}),
    ("how many days until Christmas", "countdown", {"to": "christmas"}),
    ("in 20 minutes pause the music", "schedule_command", {"command": "pause the music", "minutes": 20.0}),
    # Timeline and screen time
    ("screen time today", "screen_time", {"period": "today"}),
    ("what was I doing at 3", "timeline_at", {}),
    ("how long have I been on Discord today", "screen_time", {"app": "discord"}),
    # Screen
    ("what's this error", "explain_screen", {}),
    ("spotlight this window", "spotlight", {"on": True}),
    ("spotlight off", "spotlight", {"on": False}),
    ("autofill", "autofill", {}),
    ("hide the outlines", "clear_highlights", {}),
    ("remember this", "screen_save", {}),
    # Gaming and extras
    ("clip that", "clip_that", {}),
    ("deafen me", "discord_toggle", {"what": "deafen"}),
    ("speed test", "speed_test", {}),
    ("generate a password", "password", {}),
    ("pick between pizza and tacos", "choose", {"options": ["pizza", "tacos"]}),
    ("clean up my downloads", "tidy_downloads", {}),
    # Voices and hearing
    ("learn my voice", "voice_train", {}),
    ("Block Freya", "voice_block", {"person": "freya", "on": True}),
    ("when I say free ya, I mean Freya", "hearing_teach", {"heard": "free ya", "meant": "Freya"}),
    ("no, I said open Discord", "said_instead", {"said": "open Discord"}),
    # Power, video, trivia
    ("turn off the PC when the movie ends", "power_when", {"power": "shutdown", "trigger": "media_end"}),
    ("sleep when my download finishes", "power_when", {"power": "sleep", "trigger": "download_done"}),
    ("skip 30 seconds", "video_seek", {"seconds": 30}),
    ("go back a minute", "video_seek", {"seconds": -60}),
    ("quiz me on cricket", "trivia_start", {"topic": "cricket"}),
    # Ambient sounds
    ("play rain sounds", "ambient_play", {"sound": "rain"}),
    ("play brown noise for 30 minutes", "ambient_play", {"sound": "brown noise", "minutes": 30.0}),
    # Voice notes, images, audio, brightness, recording
    ("record a voice note", "voice_note", {}),
    ("make me a wallpaper of a misty forest", "imagine", {"prompt": "a misty forest", "wallpaper": True}),
    ("switch to my headphones", "audio_output", {"device": "headphones"}),
    ("minimize everything except Chrome", "minimize_others", {"name": "chrome"}),
    ("brightness 40", "brightness", {"level": 40}),
    ("start recording", "record_screen", {"on": True}),
    ("what's the AQI in Delhi", "air_quality", {"city": "delhi"}),
    ("what should I watch tonight", "picks", {"kind": "watch"}),
    # Gem herself
    ("gaming mode", "gaming_mode", {"on": True}),
    ("switch to always listening", "set_mode", {"mode": "always_listening"}),
    ("what can you do", "help", {}),
    ("which AI are you using", "ai_status", {}),
]

# Said to Gem but slightly misheard: these only work through router.repair.
REPAIRS = [
    ("spotlite this window", "spotlight"),
    ("Jim, pause", "media"),
]


def route(said):
    norm, _ = router.normalize(said)
    return router.match(norm, said)


class RoutingTest(unittest.TestCase):
    def test_routes(self):
        for said, action, args in ROUTES:
            with self.subTest(said=said):
                m = route(said)
                self.assertIsNotNone(m, "nothing matched")
                self.assertEqual(m.action, action)
                for k, v in args.items():
                    self.assertEqual(m.args.get(k), v, "argument %r" % k)

    def test_repairs(self):
        for said, action in REPAIRS:
            with self.subTest(said=said):
                self.assertIsNone(route(said))
                norm, _ = router.normalize(said)
                m, _ = router.repair(norm, said)
                self.assertIsNotNone(m, "repair found nothing")
                self.assertEqual(m.action, action)

    def test_normalize(self):
        self.assertEqual(router.normalize("Hey Gem, please open Spotify for me")[0], "open spotify")
        self.assertEqual(router.normalize("pause, Gem.")[0], "pause")
        self.assertTrue(router.normalize("Gem what's the time")[1])
        self.assertFalse(router.normalize("what's the time")[1])
        self.assertEqual(router.normalize("Gem's voice is too loud")[0], "gem's voice is too loud")


if __name__ == "__main__":
    unittest.main()
