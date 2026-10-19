# Gem — Voice Assistant

A fast, quiet, genuinely useful voice assistant for Windows. Hold Caps Lock, say what you want, let go.
Gem runs common commands instantly on your PC and uses Groq's free AI models for everything else.

## How it looks

Gem lives at the **top centre of your screen** and only appears when she's needed:

- **The crystal**: Gem's faceted eye. It assembles when Gem starts, opens up and follows your voice while you
  talk, swirls while thinking, sends out rings while speaking, sleeps during quiet time and glitches in Ruhig.
- **Answer cards**: frosted cards under the crystal: weather with icons, timers with a live countdown ring,
  to-do checklists, your schedule, PC gauges, now playing, volume, reminders, the morning briefing, screenshots.
- **Screen-edge glow**: the edges of the screen glow while you hold Caps Lock to talk.
- **Sound cues**: soft tones when listening starts and stops, gentle bells for reminders and alarms.
  All silent during calls, quiet time and gaming.
- **The Gem window**: left-click the tray icon, or say "open your settings" / "open dashboard". It has Home
  (status, quick switches, up next, recent), Reminders, Classes, To-do, Notes, Memory, History and Settings,
  so you never have to edit JSON.

In always-listening mode a small crystal stays at the top as a reminder that the mic is live.

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
| "I'm back" / "speak up" | End quiet time early |
| **Ruhig** / **Weiter** | Quiet until you say Weiter |

Push-to-talk always works, even during quiet time (replies show as text instead of voice).

### Calls

When another app is using your microphone (Discord, Teams, Zoom, Meet in the browser, in-game voice chat),
Gem automatically:

- stops listening (always-listening falls back to push-to-talk),
- answers with on-screen captions instead of speaking,
- turns alarm sounds into silent popups and a light flash.

Everything returns to normal when the call ends.

### Typing instead of talking

Press **Ctrl + Alt + Space** (or click the crystal) to open a command bar and type a request. Handy in calls.
Up and Down recall what you typed before. Right-click the crystal for a quick menu.

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
| Classes | "what's my schedule today", "when is my next class", "add a class called chemistry on Mondays and Fridays at 4 pm" |
| To-do & notes | "add milk, eggs and bread to my list", "what's on my to-do list", "mark math homework as done", "take a note that…", "read my notes" |
| Focus | "start a focus session", "focus for 50 minutes", "stop the focus session" |
| Briefing | "good morning" / "brief me" — date, weather, today's classes, reminders and to-dos |
| Weather | "what's the weather", "is it going to rain tomorrow", "do I need an umbrella in Toronto" ("my city is Toronto" saves your home city) |
| Text tools | Select text anywhere, then: "summarize this", "explain this", "fix the grammar", "make this more professional", "translate this to German", "write a reply" |
| Dictation | "start dictation" … "new line" … "delete that" … "stop dictation" |
| PC | "system stats", "what's using my memory", "battery", "uptime", "ping", "dark mode", "lock my PC", "restart the computer" (asks to confirm) |
| Memory | "remember that my locker code is 42", "what do you remember about me", "forget my locker code" |
| Anything else | Questions, maths, explanations, multi-step requests ("open GitHub and set a 5 minute timer") |
| Gem herself | "gaming mode", "switch to always listening", "turn off your voice", "repeat that", "what did you hear", "what can you do" |

Control words still work as before: **Sperren** locks the PC, **Schluss** closes Gem.

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
keys, productivity, AI models, panic, app names, websites and Start with Windows. Items marked ↻ apply after
**Restart Gem** (same page).

Everything lives in `C:\Users\<you>\.gem\` (tray icon → More → Data folder):

| File | What |
|---|---|
| `settings.json` | All options, including a few not in the window (control words, call-detection ignore list) |
| `reminders.json` | Timers, alarms, reminders and the weekly class schedule (your old `gem_alarms.json` is imported on first run) |
| `todo.json`, `notes.md`, `memory.json`, `history.jsonl` | To-do list, notes, remembered facts, conversation history |
| `gem.log` | Log, useful if something doesn't work |

Apps are found automatically from the Start Menu, so app updates (like Discord's) no longer break "open".

### AI models

Gem uses Groq's free tier: `openai/gpt-oss-120b` first, then `qwen/qwen3.8-27b` and `openai/gpt-oss-20b`
when one is rate-limited, and `whisper-large-v3-turbo` for speech. Change the order under `"ai"` and `"stt"`.

### Panic hotkey

`Ctrl + Alt + Shift + Tab + P` mutes the PC, closes the games listed in settings, shows the desktop, opens
Gmail and hides Gem. Say **Weiter** (holding Caps Lock) or use the tray to bring her back. Voice phrases for
panic can be added under `"panic"` → `"voice_phrases"`.

## Building the EXE

```bash
pip install pyinstaller
build.bat
```

The executable is `dist/Gem.exe` (`hooks/` fixes PyInstaller's packaging of the voice detector). If you used to start Gem by copying the old exe into your Startup folder,
delete that copy and use **Start with Windows** in the tray menu instead, so the old version doesn't start too.

## Privacy

- In push-to-talk mode nothing you say leaves the PC unless you're holding Caps Lock. (The mic stays open so
  the first word isn't cut off, which is why Windows shows the mic icon.)
- In always-listening mode, speech is sent to Groq for transcription; short fragments and filler are dropped
  before any AI call.
- Notes, to-dos, reminders and memory are stored only in `.gem` on your PC.
