# Gem — Voice Assistant

A fast, quiet, genuinely useful voice assistant for Windows. Hold Caps Lock, say what you want, let go.
Gem runs common commands instantly on your PC and uses Groq's free AI models for everything else.

## How it looks

Gem lives in a **Dynamic Island**: a small black pill hugging the very top of your screen, like on an iPhone.

- **Idle**: a tiny pill with Gem's crystal, slightly see-through (Settings → Look & sound → island opacity).
  Move the mouse over it (or over an answer card) and it fades almost away so you can see and click what's
  underneath, like a browser tab. Hold **Ctrl** while hovering to make it clickable (click to type, right-click
  for a menu), or switch Settings back to showing the controls on hover. It tucks itself away during fullscreen
  video and games.
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
  (status, quick switches, up next, recent), Reminders, Classes, To-do, Routines, Notes, Memory, Saved (your
  saved screens as a gallery, and voice notes you can play), People (voice lock, and the people Gem knows, with
  an Ignore switch each), AI & hearing (today's AI use, backup AI keys, words Gem learned), History and
  Settings, so you never have to edit JSON.

In always-listening mode a small violet dot in the pill shows that the mic is live.

### Gem's voice

Gem speaks with Amy, a neural voice that runs **on your PC** (Piper). It starts within a fraction of a second,
sounds the same every time and works offline; phrases she says often are cached and play instantly. The voice
model (about 60 MB) downloads once on first run. Settings → Voice lets you pick another local voice or switch
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

Press **Ctrl + Alt + Space** (or hold Ctrl over the island and click) to open a command bar and type a
request. Handy in calls. Up and Down recall what you typed before. Right-click the island for a quick menu.
Within a minute of Gem mishearing you, the bar opens with what it heard, ready to fix: correct the word and press
Enter. Fix the same word the same way twice and Gem learns it.

When every AI model is at its per-minute limit, the island shows **AI busy** with a countdown to when it's back
(built-in commands keep working), and when a backup service takes over it says so.

## What Gem can do

| Area | Try saying |
|---|---|
| Apps & sites | "open Spotify", "close Discord", "switch to Brave", "open GitHub dot com", "open my downloads", "open bluetooth settings" |
| Files | "open my latest download", "find the file called resume" |
| Volume | "volume 40", "turn it down", "turn the volume down to 20", "mute Spotify", "lower Discord", "Spotify volume 30" |
| Media | "pause", "next song", "play it again", "what's playing", "play lofi beats on YouTube", "play Blinding Lights on Spotify" (opens it in Spotify's search) |
| Windows | "show desktop", "snap this left", "minimize", "close this window", "take a screenshot of this window", "snip" |
| Timers & alarms | "10 minute timer for pasta", "set an alarm for half past 6" (a time without AM/PM, 12 included, is the next one on the clock), "how much time is left", "add 5 minutes to the timer" / "5 more minutes", "pause the timer" / "resume the timer", "cancel the pasta timer", "snooze". Named timers remember their length: next time "set a pasta timer" is enough |
| Reminders | "remind me to call mom in 15 minutes", "remind me tomorrow at 8 am to submit the essay", "remind me to drink water every hour", "remind me to stretch every 30 minutes", "every morning remind me to check my email", "remind me to take out the trash every Monday at 7 pm" (repeating ones keep their time even if the PC was asleep) |
| Classes | "what's my schedule today", "when is my next class", "add a class called chemistry on Mondays and Fridays at 4 pm" (a heads-up comes 5 minutes before) |
| To-do & notes | "add milk, eggs and bread to my list", "what's on my to-do list", "mark math homework as done", "take a note that…", "read my notes" |
| Focus | "start a focus session", "focus for 50 minutes", "stop the focus session" |
| Briefing | "good morning" / "brief me" — date, weather, today's classes, reminders and to-dos |
| Weather | "what's the weather", "is it going to rain tomorrow", "do I need an umbrella in Toronto" ("my city is Toronto" saves your home city) |
| Text tools | Select text anywhere, then: "summarize this", "explain this", "fix the grammar", "make this more professional", "translate this to Spanish", "how many words is this" (counted on the PC, with characters and reading time). Also "how do you spell necessary" |
| Dictation | "start dictation" … "new line" … "delete that" … "stop dictation" |
| PC | "system stats", "what's using my memory", "battery", "uptime", "ping", "dark mode", "lock my PC", "restart the computer" (say "confirm" to go ahead) |
| Memory | "remember that my locker code is 42", "what do you remember about me", "forget my locker code" |
| Maths & conversions | "what's 15% of 80", "20% off 50", "15% tip on 80", "12 times 7", "3.5 times 2", "square root of 144", "cube root of 27", "convert 5 miles to km", "70 fahrenheit in celsius", "100 dollars to rupees" (instant, live exchange rates) |
| Stopwatch | "start a stopwatch", "what's the stopwatch at", "stop the stopwatch" (counts up in the island) |
| Clipboard | "what did I copy", "paste what I copied before", "paste clip 3", "paste the link about the essay" (remembered in memory only; passwords and keys are skipped) |
| Reading | Select text and say "read this to me" (with nothing selected, Gem reads the window you're in); "read this page", "read this email", "read my screen"; "keep reading" for the rest of a long page; "copy that" copies Gem's last answer |
| Habits | "I drank a glass of water", "log 20 pushups", "I had a coffee", "how much water today" (with a weekly chart and streaks) |
| Time zones | "what time is it in Tokyo", "3 pm EST in IST", "when it's 9 am in London what time is it here", "add Tokyo to my world clock", "world clock" |
| Countdowns | "how many days until Christmas", "how long until Friday", "my birthday is March 3" → "days until my birthday" |
| Later | "in 20 minutes pause the music", "open Spotify at 7 pm", "at 6 pm start study mode", "sleep timer 30 minutes" |
| Screen time | "screen time today", "screen time this week", "how long have I been on Discord today" (tracked on this PC only) |
| Timeline | "what was I doing at 3", "what was I doing an hour ago", "when did I start Valorant", "how long have I been playing", "when was I last on Discord", "how long have I been on the computer" / "when did I last take a break", "show my timeline", "what did I do this afternoon" / "yesterday". Days run 5 AM to 5 AM, so a late night counts with its evening |
| Pick up where you left off | "what was I working on", "open what I was working on", "open my last Excel file", "reopen the last PDF" (Windows' recent items, or the files you saved most recently if that's turned off) |
| Day recap | "what did I do today": a short summary of your requests, finished to-dos, habits and screen time |
| Extras | "generate a password" (copied to the clipboard, never spoken), "pick between pizza and tacos", "what did I note about the wifi" |
| Your screen | "what's this error", "explain my screen", "summarize this page", "look at my screen and tell me what to click" (a screenshot goes to the vision model; answering never clicks anything). "Explain this" with nothing selected also looks at the screen |
| Highlights | When Gem answers about your screen it outlines what it means (the error, the button) and dims the rest for a few seconds. "Where's the save button?", "show me where the error is", "where do I click to change my password". Caps Lock or "hide the outlines" clears them; Look & sound settings can turn them off |
| Spotlight | "spotlight this window" / "help me focus" dims everything except the window you're in and follows you between windows; "spotlight off" |
| Autofill | "autofill", "what formula goes here", "solve this", "fill in the blanks": Gem finds what needs filling (empty spreadsheet cells, maths questions, form blanks), outlines each spot and writes the answer right inside the blank as an overlay (with a few words of working under it); when there's no blank, it shows a card beside the question instead. The first one is copied, so click and paste; "copy the second one", "copy the next one". Gem never types into your apps |
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
| Ambient sounds | "play rain sounds", "play brown noise for 30 minutes", "ocean waves", "fan", "white noise"; "make it quieter", "stop the sounds" / "stop the rain". Made on the PC, dips while Gem talks |
| Voice notes | "record a voice note" (hands-free, stops when you do, transcribed), "play my last voice note", "read my voice notes", "what did I say in my voice note about the trip" |
| Call notes | "take notes" during a call, class or video (Meet, Discord, Zoom, YouTube...): Gem records your mic and what the PC plays until the call ends or you say "stop taking notes", then saves to Documents\Gem Notes a notes file (title, summary, action items and dates at the top, then the transcript with who said what: You or Others) and an MP3 of the whole call, and opens the notes in Notepad. Let the others know you're recording |
| Images | "make me a wallpaper of a misty forest", "draw a cat in a space suit", then "set it as my wallpaper". Free and quick (Pollinations), so not 4K; one image every ~45 seconds |
| Sound output | "switch to my headphones", "switch the audio to speakers", "what's my audio output" (a numbered list), "switch to the second one" |
| Windows by name | "minimize Discord", "hide Spotify", "restore Discord" / "bring back Spotify", "minimize everything except Chrome" |
| Brightness | "brightness 40", "make the screen brighter", "dim the screen a bit", "what's the brightness". External monitors over DDC/CI (on in the monitor's menu), laptop screens through Windows |
| Recording | "start recording" / "stop recording" (Xbox Game Bar, saved to Videos › Captures) |
| Air | "how's the air quality", "what's the AQI in Delhi", "UV index"; heads-up when it's unhealthy |
| More heads-ups | "Aarav's birthday is March 5" → reminded the evening before and on the day; "while you were away" summary when you come back to the PC; softer voice at night (11 PM to 7 AM) |
| Picks | "what should I watch tonight", "what should I play", "recommend a funny movie": three picks based on your mood, what you've told Gem and the games you have installed |
| Live answers | "who won the game last night", "bitcoin price", "latest news about OpenAI", "what's on floor 6 of the zombie tower in Roblox Rivals" (searches the web and answers aloud) |
| Routines & macros | "study mode" (example), "create a routine called wind down that pauses the music and turns on dark mode", "what routines do I have". Macros can also type, press keys and click: see [Macros](#macros) |
| Messages & email | "message Aarav on Discord saying I'm running late", "tell Priya on Google Chat that the meeting moved to 3", "email Aarav saying the notes are up". Gem gets it ready and waits for you to say "send it": see [Big steps wait for you](#big-steps-wait-for-you) |
| Contacts | "Aarav's email is aarav dot shah at gmail dot com", "Sam's Discord is sam_the_man", "Priya's Google Chat is priya at school dot org". Gamertags with symbols are easiest typed in the command bar ("Sam's Discord is xX_Sniper_Xx"); then "message Sam" or "message Sniper" both find him. If Discord shows a different display name, say "Sam is Bean on Discord" |
| Anything else | Questions, maths, explanations, multi-step requests ("open GitHub and set a 5 minute timer") |
| Gem herself | "gaming mode", "switch to always listening", "turn off your voice", "repeat that", "what did you hear", "what can you do", "which AI are you using". "Undo that" / "put it back" reverses her last change to the volume, brightness or dark mode, or brings back a timer or reminder you just cancelled |
| Mishearings | Gem quietly fixes near-misses when you're clearly talking to her ("spotlite this window", "set a timmer", "Jim, pause"). Teach it words it keeps getting wrong: "when I say free ya, I mean Freya". Right after a mistake: "no, I said open Discord", or "I said Spotify, not spot if I" (learns it and redoes the request). "What words have I taught you", "forget the word fix for free ya" |

To lock the PC say "lock my PC"; to close Gem say "close Gem" or use the tray.

### Reply mode

Gem types into the message box you're in. You press Enter, or, in chat and email apps whose window title shows who
you're talking to (Discord, Google Chat, Gmail...), say "send it" and Gem sends it after checking it's still the same
chat.

- **Away note**: say "I'm stepping away for 30 minutes" (or "away mode until 6"). In any chat or email, "tell them
  I'm away" types *"Parshv isn't here right now, this is his voice assistant speaking. He'll be back in about 25
  minutes."* The island shows *Away · back 4:30*; "I'm back" ends it. Edit the wording in Settings → You.
- **Reply drafts**: copy or select the conversation (Discord, Google Chat, Gmail…), click in the reply box and say
  "reply to this". Gem writes a reply that matches how you write in that chat and shows it in the island.
  "Make it shorter", "more casual" or "try again" rewrite it in place. The draft also stays on your clipboard.

## Macros

A macro (the same thing as a routine) is one phrase that runs a list of steps. Besides Gem's own commands, steps
can work inside other apps:

| Step | What it does |
|---|---|
| `open discord`, `volume 30`, any command | the same as saying it |
| `switch to discord` / `wait for discord` | bring that app to the front (waiting for it if it's starting) |
| `wait 2 seconds` | pause |
| `type hello everyone` | type into the app in front (never presses Enter) |
| `press ctrl+k`, `press tab 3 times` | press keys |
| `click the compose button` | find it on screen with the vision model and click it |
| `click at 45% 60% in discord` | click a spot in that app's window (what recordings use) |
| `ask me first` | stop and wait for your "confirm" |

Three ways to make one:

- **Say it**: "create a macro called hello that switches to Discord, types hi everyone and presses enter". The first
  time it runs, Gem shows the steps it understood and waits for "confirm".
- **Record it**: "record a macro" (or "watch what I do"), do the task, then "stop recording" and "call it ...".
  Keys, typing, clicks and app switches are recorded; anything you ask Gem for while recording becomes a step.
  A red dot in the island shows it's recording. Nothing typed in sign-in or password windows is recorded, and
  recordings stop on their own after 10 minutes.
- **Let Gem work it out**: "figure out how to ...". Gem shows its plan and runs it after you say "confirm";
  "save that as a macro called ..." keeps it.

Run one with its name, "run the hello macro" or from the dashboard (Routines & macros, where you can also edit the
steps). "Stop", a tap on Caps Lock or starting to type yourself stops a macro. Before every key press, bit of typing
or click, Gem checks the app it's working in is still in front, and stops rather than typing somewhere else. It never
types into its own windows.

### Big steps wait for you

Some steps can't be taken back, so Gem shows exactly what will happen and waits for **"send it"** (for anything
that sends) or **"confirm"** (for everything else). "Yes" or "okay" isn't enough, and the card always says which one:

- sending a Discord or Google Chat message or an email (the card shows who it goes to and the exact text),
- Enter in a chat or email app, a terminal, or a checkout, payment or account page,
- deleting in File Explorer or on the desktop (Delete, Ctrl+D, or a recorded click there),
- clicking anything that looks like Send, Delete, Buy, Pay, Submit and the like, or any click in a chat app,
- restarting, shutting down, signing out or sleeping the PC,
- running a plan Gem worked out itself, or a macro Gem wrote for you the first time it runs.

One big step at a time: if you ask for two messages at once, Gem gets the first ready and asks you again for the
second after you've answered. Inside a macro, say **"confirm all"** to OK that step and the same step again for the
rest of that run (say, every click in Discord); sending, deleting, power and your own "ask me first" steps still ask
every time. The island shows how far a macro has got ("Demo · 3 of 7"). With push-to-talk, near misses like
"conform" count as "confirm". Typing and dictation never press Enter where Enter would send or run something; say
"press enter" in dictation if you mean it.

If Gem has learned your voice ("learn my voice"), it has to be your voice saying it. In always-listening mode
before it knows your voice, say "Gem, send it", so a video saying "send it" can't. Typing the phrase in the command bar
works too. Say "cancel" or "stop", or just wait 45 seconds, and nothing happens. Before pressing Send, Gem checks the
same window is still in front showing the same chat, and double-checks the recipient from the window title or a look at
the screen; if it's the wrong chat it stops. Gmail lets you undo for a few seconds after sending.

Nothing scheduled can approve a big step. When a macro or command runs while nobody is there to answer ("at 7 pm run
my morning macro"), big steps are skipped and you get a note about what was skipped. Messages and emails can't be
scheduled at all (sending needs your OK when it happens), and "shut down the PC in an hour" asks for "confirm" now and
warns you a minute before, so you can still say "cancel".

To message someone new on Google Chat, Gem opens the "new chat" search and checks on screen that it really opened
before typing their name; if it can't tell, it asks you to open the chat yourself. Only one question is ever open:
a new one replaces the last, and "stop" or "cancel" also stops a macro that's running.

Phrases, the waiting time and the "Gem, send it" rule are under `"safety"` in `settings.json`.

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
| `settings.json` | All options, including a few not in the window (call-detection ignore list) |
| `reminders.json` | Timers, alarms, reminders and the weekly class schedule (your old `gem_alarms.json` is imported on first run) |
| `todo.json`, `routines.json`, `notes.md`, `memory.json`, `history.jsonl` | To-do list, routines and macros, notes, remembered facts, conversation history |
| `contacts.json` | Email addresses and Discord / Google Chat names for sending messages |
| `screens/`, `voice_notes/`, `voiceprint.json`, `hearing.json`, `timeline.json` | Saved screens, voice notes, voiceprints, words you taught Gem, activity timeline |
| `voices/`, `voice_cache/` | The local voice model and cached phrases |
| `gem.log` | Log, useful if something doesn't work |

Apps are found automatically from the Start Menu, so app updates (like Discord's) no longer break "open".

### AI models

Gem uses Groq's free tier: `openai/gpt-oss-120b` first, then `qwen/qwen3.8-27b` and `openai/gpt-oss-20b`
when one is rate-limited, and `whisper-large-v3-turbo` for speech. Change the order under `"ai"` and `"stt"`.

**Web answers** use Groq's built-in web search on `openai/gpt-oss-20b` (set `"ai"` → `"search_models"` to
change it), so they don't eat into the main model's allowance. Search pages that don't need a key now block
scripts. When the search is unavailable, Gem answers from what the AI knows and says if it may be out of date.
Each model on the free tier takes about 8,000 tokens a minute, and every question sends Gem's list of actions
along, so a busy minute can run out: a backup AI key (below) is the best fix.

**Backup AI.** When every Groq model is at its limit, Gem can switch to Cerebras, Gemini or OpenRouter (all
have free keys: [Cerebras](https://cloud.cerebras.ai), [Gemini](https://aistudio.google.com/apikey),
[OpenRouter](https://openrouter.ai/keys)). Cerebras is the roomiest: the same `gpt-oss-120b` with a million
tokens a day (5 requests a minute per model). Paste a key in the Gem window under **AI & hearing**, or set
`CEREBRAS_API_KEY` / `GEMINI_API_KEY` / `OPENROUTER_API_KEY` like the Groq key. Cerebras and Gemini also cover
screen questions. Any OpenAI-compatible service can be added under `"ai"` → `"backups"`. The same
page shows how much of today's allowance each model has used.

### Panic hotkey

`Ctrl + Alt + Shift + Tab + P` mutes the PC, closes the games listed in settings, shows the desktop, opens
Gmail and hides Gem. Hold Caps Lock and say "I'm back", or use the tray, to bring her back. Voice phrases for
panic can be added under `"panic"` → `"voice_phrases"`.

## Tests

```bash
python -m unittest tests
```

Checks that the README's example phrases still route to the right command, that everyday conversation doesn't
set commands off in always-listening mode, and the time, number, maths and reminder parsing. They run on Linux
and macOS too (the Windows parts are stubbed) and use a temporary data folder, never your real `.gem`.

## Building the EXE

```bash
pip install pyinstaller
build.bat
install.bat
```

`build.bat` makes `dist/Gem/` (`Gem.exe` and its `_internal` folder; `hooks/` fixes PyInstaller's packaging of
the voice detector). It's a folder rather than one big exe because a single-file exe unpacks itself on every
start. `install.bat` copies it to `%LOCALAPPDATA%\Programs\Gem` and starts it; the installed copy adds itself
to Start search. Turn on **Start with Windows** in the tray menu or Settings to launch it at sign-in.

## Privacy

- In push-to-talk mode nothing you say leaves the PC unless you're holding Caps Lock. (The mic stays open so
  the first word isn't cut off, which is why Windows shows the mic icon.)
- In always-listening mode, speech is sent to Groq for transcription; short fragments and filler are dropped
  before any AI call.
- Notes, to-dos, reminders and memory are stored only in `.gem` on your PC.
- Screen time and the timeline (which app was in front, with its window title) are recorded only while you're
  active, stay in `.gem` (`usage.json`, `timeline.json`) and the timeline is cleared after two weeks. Questions
  about it ("what was I working on", "when did I start Valorant") are only answered when they're for Gem, so
  someone else's conversation can't get your activity read out loud.
- Call notes only record after you say "take notes" (the island shows a red dot and the time). The recording stays
  in Documents\Gem Notes; the speech in it (silence cut out) goes to Groq to be transcribed, and the transcript
  to the AI for the summary.
- Your screen only leaves the PC when you ask about it (explain, read, highlight, autofill, remember this). In
  always-listening mode, overheard speech like "remember that" never sends it on its own: it needs Gem's name,
  push-to-talk, an ongoing conversation, or the AI agreeing the request was for Gem.
- Recording a macro reads your keys and clicks only between "record a macro" and "stop recording" (the island
  shows a red dot), skips sign-in and password windows, and keeps the steps in `routines.json` on your PC.
