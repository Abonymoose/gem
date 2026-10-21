# Gem â€” Voice Assistant

A fast, quiet, genuinely useful voice assistant for Windows. Hold Caps Lock, say what you want, let go.
Gem runs common commands instantly on your PC and uses Groq's free AI models for everything else.

## How it looks

Gem lives in a **Dynamic Island**: a small black pill hugging the very top of your screen, like on an iPhone.

- **Idle**: a tiny pill with Gem's crystal. Clicks pass straight through it to whatever is underneath; rest the
  mouse on it for a moment to make it clickable (click to type, right-click for a menu). It tucks itself away
  during fullscreen video and games.
- **Live activities**: a running timer counts down in the pill; it also shows your next class when it's 15
  minutes away, a running stopwatch, focus time left, the song playing in Spotify, when you're away, and when
  you're on a call or Gem is in quiet time.
- **Listening**: while you hold Caps Lock the island widens with a live waveform of your voice and a violet glow.
- **Answers**: the island opens into a card: weather with icons, timers with a countdown ring, to-do
  checklists, your schedule, PC gauges, now playing, volume, reminders, the morning briefing, web answers with
  sources, routines and screenshots. The card appears the moment Gem starts speaking.
- **Sound cues**: soft tones when listening starts and stops, gentle bells for reminders and alarms.
  All silent during calls, quiet time and gaming.
- **Audio ducking**: music and videos dip while you hold Caps Lock and while Gem answers, then come back to
  exactly where they were.
- **The Gem window**: left-click the tray icon, or say "open your settings" / "open dashboard". It has Home
  (status, quick switches, up next, recent), Reminders, Classes, To-do, Routines, Notes, Memory, History and
  Settings, so you never have to edit JSON.

In always-listening mode a small violet dot in the pill shows that the mic is live.

### Gem's voice

Gem speaks with Amy, a neural voice that runs **on your PC** (Piper). It starts within a fraction of a second,
sounds the same every time and works offline; phrases she says often are cached and play instantly. The voice
model (about 60 MB) downloads once on first run. Settings â†’ Voice lets you pick another local voice or switch
to the online Microsoft voices, which sound a little richer but can take a few seconds to start.

## Talking to Gem

Caps Lock is Gem's key. It never turns your typing into capitals (Shift + Caps Lock still toggles real caps).

| Gesture | Push-to-talk mode (default) | Always-listening mode |
|---|---|---|
| **Hold** Caps Lock | Gem listens while held | Gem is muted while held |
| **Tap** Caps Lock | Stop Gem talking | Stop Gem talking |
| **Triple-tap** Caps Lock | Switch to always-listening | Switch to push-to-talk |

While you hold Caps Lock to talk, the Num, Caps and Scroll Lock lights sweep on and stay lit; they go back to
normal when you let go. A different light pattern confirms each mode switch.

In **always-listening** mode there's no wake word. Gem hears everything but only reacts when the speech is
clearly meant for her (an AI check filters out conversation, calls and video audio). Saying "Gem" anywhere
in a sentence makes it certain. After she replies you have ~25 seconds for follow-ups.

### Quiet time

| Say | What happens |
|---|---|
| "shut up for a bit" / "be quiet" | Quiet for 10 minutes, then she comes back on her own |
| "quiet for an hour" / "shut up for 30 minutes" | Custom length |
| "be quiet until I say" | Quiet until you say "I'm back" |
| "I'm back" / "speak up" / "wake up" | End quiet time early |

Push-to-talk always works, even during quiet time (replies show as text instead of voice).

### Calls

When another app is using your microphone (Discord, Teams, Zoom, Meet in the browser, in-game voice chat),
Gem automatically:

- stops listening (always-listening falls back to push-to-talk),
- answers with on-screen captions instead of speaking,
- turns alarm sounds into silent popups and a light flash.

Everything returns to normal when the call ends.

### Typing instead of talking

Press **Ctrl + Alt + Space** (or rest the mouse on the island and click) to open a command bar and type a
request. Handy in calls. Up and Down recall what you typed before. Right-click the island for a quick menu.

## What Gem can do

| Area | Try saying |
|---|---|
| Apps & sites | "open Spotify", "close Discord", "switch to Brave", "open GitHub dot com", "open my downloads", "open bluetooth settings" |
| Files | "open my latest download", "find the file called resume" |
| Volume | "volume 40", "turn it down", "mute Spotify", "lower Discord", "Spotify volume 30" |
| Media | "pause", "next song", "what's playing", "play lofi beats on YouTube", "play Blinding Lights on Spotify" (opens it in Spotify's search) |
| Windows | "show desktop", "snap this left", "minimize", "close this window", "take a screenshot of this window", "snip" |
| Timers & alarms | "10 minute timer for pasta", "set an alarm for 6:30 am", "how much time is left", "cancel the timer", "snooze" |
| Reminders | "remind me to call mom in 15 minutes", "remind me tomorrow at 8 am to submit the essay", "remind me to drink water every hour" |
| Classes | "what's my schedule today", "when is my next class", "add a class called chemistry on Mondays and Fridays at 4 pm" (a heads-up comes 5 minutes before) |
| To-do & notes | "add milk, eggs and bread to my list", "what's on my to-do list", "mark math homework as done", "take a note thatâ€¦", "read my notes" |
| Focus | "start a focus session", "focus for 50 minutes", "stop the focus session" |
| Briefing | "good morning" / "brief me" â€” date, weather, today's classes, reminders and to-dos |
| Weather | "what's the weather", "is it going to rain tomorrow", "do I need an umbrella in Toronto" ("my city is Toronto" saves your home city) |
| Text tools | Select text anywhere, then: "summarize this", "explain this", "fix the grammar", "make this more professional", "translate this to Spanish" |
| Dictation | "start dictation" â€¦ "new line" â€¦ "delete that" â€¦ "stop dictation" |
| PC | "system stats", "what's using my memory", "battery", "uptime", "ping", "dark mode", "lock my PC", "restart the computer" (asks to confirm) |
| Memory | "remember that my locker code is 42", "what do you remember about me", "forget my locker code" |
| Maths & conversions | "what's 15% of 80", "12 times 7", "square root of 144", "convert 5 miles to km", "70 fahrenheit in celsius", "100 dollars to rupees" (instant, live exchange rates) |
| Stopwatch | "start a stopwatch", "what's the stopwatch at", "stop the stopwatch" (counts up in the island) |
| Clipboard | "what did I copy", "paste what I copied before", "paste clip 3", "paste the link about the essay" (remembered in memory only; passwords and keys are skipped) |
| Reading | Select text and say "read this to me"; "copy that" copies Gem's last answer |
| Habits | "I drank a glass of water", "log 20 pushups", "I had a coffee", "how much water today" (with a weekly chart and streaks) |
| Time zones | "what time is it in Tokyo", "3 pm EST in IST", "when it's 9 am in London what time is it here", "add Tokyo to my world clock", "world clock" |
| Countdowns | "how many days until Christmas", "how long until Friday", "my birthday is March 3" → "days until my birthday" |
| Later | "in 20 minutes pause the music", "open Spotify at 7 pm", "at 6 pm start study mode", "sleep timer 30 minutes" |
| Screen time | "screen time today", "screen time this week", "how long have I been on Discord today" (tracked on this PC only) |
| Day recap | "what did I do today": a short summary of your requests, finished to-dos, habits and screen time |
| Extras | "generate a password" (copied to the clipboard, never spoken), "pick between pizza and tacos", "what did I note about the wifi" |
| Your screen | "what's this error", "explain my screen", "summarize this page", "look at my screen and tell me what to click" (a screenshot goes to the vision model; Gem never clicks anything). "Explain this" with nothing selected also looks at the screen |
| Highlights | When Gem answers about your screen it outlines what it means (the error, the button) and dims the rest for a few seconds. "Where's the save button?", "show me where the error is", "where do I click to change my password". Caps Lock or "hide the outlines" clears them; Look & sound settings can turn them off |
| Spotlight | "spotlight this window" / "help me focus" dims everything except the window you're in and follows you between windows; "spotlight off" |
| Autofill | "autofill", "what formula goes here", "solve this", "fill in the blanks": Gem finds what needs filling (empty spreadsheet cells, maths questions, form blanks) and shows what goes there in a callout next to each spot, with a few words of working. The first one is copied, so click and paste; "copy the second one", "copy the next one". Gem never types into your apps |
| Tidy downloads | "clean up my downloads" sorts loose files into PDFs, Images, Installers and so on after you say yes. Only moves, never deletes. "Undo the tidy" puts everything back |
| Gaming | "clip that" saves the last 30 seconds with Xbox Game Bar. "Mute me" and "deafen me" toggle Discord (keys under `discord` in settings). "Speed test" checks download, upload and ping |
| Voice lock | "learn my voice" (read five short lines), then in always-listening mode Gem ignores speech that isn't you, before it's even transcribed. "Only listen to me" / "listen to everyone", "voice check", "forget my voice". Runs on this PC with a 26 MB WeSpeaker model; push-to-talk keeps improving your voiceprint. Strictness is under Listening in settings |
| Family voices | "learn Freya's voice", or when someone talks: "that was my sister Freya". "Block Freya" and Gem ignores her (with the odd "oh wait, is that Freya? ... anyway"); "unblock Freya", "who do you know". Allowed people get answered by name |
| Screen memory | "remember this" (optionally "as ..."): saves the screen with an AI description. Later: "what was that headphones site I saved?", "what did I save about X", "show me my saved screens", "open it full size". Only when you ask |
| Auto memory | Lasting things you mention in conversation ("I main Jett") are remembered on their own, with a small "Noted" toast. "What do you know about me", "forget that I ..." |
| Auto-clip | In a game, shout "let's go", "no way", "oh my god"... or just say "clip that" (no key needed) and Gem saves the last 30 seconds. Checked offline on this PC, only for your voice, with a cooldown |
| Heads-ups | Rain in the next couple of hours (needs "my city is ..."), a big download finished, something hogging the CPU or memory, C drive almost full, low battery. Held back during calls and games |
| Offline | If the internet or Groq is down, speech falls back to an offline model (Vosk, 40 MB download) so timers, volume, music and apps keep working |
| Little extras | "what's the Wi-Fi password" (shown and copied, not spoken), "make a Wi-Fi QR code" for guests, "QR code for this link", "shorten this link", "copy the text from my screen", "what colour is this" (under the mouse), "remind me to reply to Aarav when I open Discord" |
| Files | "find the PDF I downloaded yesterday", "show me photos from this week", "what's taking up space", "where are my screenshots" → top matches; "open the first one", "show it in the folder" |
| Power when done | "turn off the PC when the movie ends", "sleep when my download finishes", "shut down the computer in 2 hours". A one-minute warning first; "cancel" stops it |
| Video | "skip 30 seconds", "rewind 10 seconds", "go back a minute", "fullscreen", "subtitles" for YouTube, Netflix, Prime, Hotstar, VLC and more (only when a player is in front) |
| Trivia | "let's play trivia", "trivia about movies", "quiz me on cricket": five questions, answer "B", "the second one" or the answer itself; "skip", "stop" |
| Ambient sounds | "play rain sounds", "play brown noise for 30 minutes", "ocean waves", "fan", "white noise"; "make it quieter", "stop the sounds". Made on the PC, dips while Gem talks |
| Voice notes | "record a voice note" (hands-free, stops when you do, transcribed), "play my last voice note", "read my voice notes", "what did I say in my voice note about the trip" |
| Images | "make me a wallpaper of a misty forest", "draw a cat in a space suit", then "set it as my wallpaper". Free and quick (Pollinations), so not 4K; one image every ~45 seconds |
| Sound output | "switch to my headphones", "switch the audio to speakers", "what's my audio output" |
| Windows by name | "minimize Discord", "hide Spotify", "restore Discord" / "bring back Spotify", "minimize everything except Chrome" |
| Brightness | "brightness 40", "make the screen brighter", "dim the screen a bit", "what's the brightness". External monitors over DDC/CI (on in the monitor's menu), laptop screens through Windows |
| Recording | "start recording" / "stop recording" (Xbox Game Bar, saved to Videos › Captures) |
| Air | "how's the air quality", "what's the AQI in Delhi", "UV index"; heads-up when it's unhealthy |
| More heads-ups | "Aarav's birthday is March 5" → reminded the evening before and on the day; "while you were away" summary when you come back to the PC; softer voice at night (11 PM to 7 AM) |
| Picks | "what should I watch tonight", "what should I play", "recommend a funny movie": three picks based on your mood, what you've told Gem and the games you have installed |
| Live answers | "who won the game last night", "bitcoin price", "latest news about OpenAI" (searches the web and answers aloud) |
| Routines | "study mode" (example), "create a routine called wind down that pauses the music and turns on dark mode", "what routines do I have" |
| Anything else | Questions, maths, explanations, multi-step requests ("open GitHub and set a 5 minute timer") |
| Gem herself | "gaming mode", "switch to always listening", "turn off your voice", "repeat that", "what did you hear", "what can you do" |

To lock the PC say "lock my PC"; to close Gem say "close Gem" or use the tray.

### Reply mode

Gem never sends messages by itself: it types into the message box you're in, and you press Enter.

- **Away note**: say "I'm stepping away for 30 minutes" (or "away mode until 6"). In any chat or email, "tell them
  I'm away" types *"Parshv isn't here right now, this is his voice assistant speaking. He'll be back in about 25
  minutes."* The island shows *Away Â· back 4:30*; "I'm back" ends it. Edit the wording in Settings â†’ You.
- **Reply drafts**: copy or select the conversation (Discord, Google Chat, Gmailâ€¦), click in the reply box and say
  "reply to this". Gem writes a reply that matches how you write in that chat and shows it in the island.
  "Make it shorter", "more casual" or "try again" rewrite it in place. The draft also stays on your clipboard.

## Setup

1. Install Python 3.10+.
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Set your Groq key (free at [console.groq.com](https://console.groq.com)). It powers speech recognition
   (Whisper) and the AI. Without it Gem falls back to Google's free recognizer and only local commands work.
   ```cmd
   setx GROQ_API_KEY your_key_here
   ```
4. Run:
   ```bash
   pythonw gem2.py
   ```

No weather key is needed any more (Gem uses Open-Meteo).

## Settings and data

Change settings in the Gem window's **Settings** page: voice (with a Test button), look and sound, microphone,
keys, productivity, AI models, panic, app names, websites and Start with Windows. Items marked â†» apply after
**Restart Gem** (same page).

Everything lives in `C:\Users\<you>\.gem\` (tray icon â†’ More â†’ Data folder):

| File | What |
|---|---|
| `settings.json` | All options, including a few not in the window (call-detection ignore list) |
| `reminders.json` | Timers, alarms, reminders and the weekly class schedule (your old `gem_alarms.json` is imported on first run) |
| `todo.json`, `routines.json`, `notes.md`, `memory.json`, `history.jsonl` | To-do list, routines, notes, remembered facts, conversation history |
| `voices/`, `voice_cache/` | The local voice model and cached phrases |
| `gem.log` | Log, useful if something doesn't work |

Apps are found automatically from the Start Menu, so app updates (like Discord's) no longer break "open".

### AI models

Gem uses Groq's free tier: `openai/gpt-oss-120b` first, then `qwen/qwen3.8-27b` and `openai/gpt-oss-20b`
when one is rate-limited, and `whisper-large-v3-turbo` for speech. Change the order under `"ai"` and `"stt"`.

### Panic hotkey

`Ctrl + Alt + Shift + Tab + P` mutes the PC, closes the games listed in settings, shows the desktop, opens
Gmail and hides Gem. Hold Caps Lock and say "I'm back", or use the tray, to bring her back. Voice phrases for
panic can be added under `"panic"` â†’ `"voice_phrases"`.

## Building the EXE

```bash
pip install pyinstaller
build.bat
```

The executable is `dist/Gem.exe` (`hooks/` fixes PyInstaller's packaging of the voice detector). Turn on
**Start with Windows** in the tray menu or Settings to launch it at sign-in.

## Privacy

- In push-to-talk mode nothing you say leaves the PC unless you're holding Caps Lock. (The mic stays open so
  the first word isn't cut off, which is why Windows shows the mic icon.)
- In always-listening mode, speech is sent to Groq for transcription; short fragments and filler are dropped
  before any AI call.
- Notes, to-dos, reminders and memory are stored only in `.gem` on your PC.
