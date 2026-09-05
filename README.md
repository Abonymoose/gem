# Gem — Voice Assistant

A sarcastic, always-on Windows voice assistant with a live animated overlay, system controls, AI fallback via Groq, and persistent alarms.

## Features

- Wake/sleep with a voice trigger ("gem wake up")
- Weather, time, date, Wikipedia lookups
- Open and close apps by voice
- Volume control (set, mute, relative up/down)
- YouTube search and direct playback
- Google search
- Alarms and reminders (one-off and recurring scheduled)
- System stats (CPU, RAM, disk)
- Screenshots (saved to Desktop + clipboard)
- Voice dictation mode
- Jokes, coin flip, dice roll, random facts, roasts, compliments
- Ping test, PC uptime
- AI fallback via Groq (llama-3.3-70b-versatile)
- Silent mode, Ruhig (deaf) mode, Gaming mode
- Animated tkinter overlay (crystal eye, sleeping stars, sniper scope, glitch, void)
- System tray icon
- Panic hotkey (`Ctrl+Alt+Shift+Tab+P`)

## Voice Commands

| Command | What it does |
|---|---|
| `gem wake up` | Wake Gem from sleep |
| `what time is it` | Speaks the current time |
| `what's the date` | Speaks today's date |
| `weather [city]` | Current weather for a city |
| `open [app]` | Launches an app (brave, discord, spotify, steam, vscode, …) |
| `close [app]` | Kills a running app by process name |
| `volume [0-100]` / `volume up/down` | Set or adjust system volume |
| `mute` / `unmute` | Toggle system mute |
| `play [song] on youtube` | Opens the first YouTube result |
| `search for [query]` | Google search |
| `who is / what is [topic]` | Wikipedia summary |
| `set an alarm for [time]` | One-off alarm (7am, in 10 minutes, …) |
| `remind me in [N] minutes to [thing]` | Timed reminder |
| `list alarms` | Lists active alarms |
| `tell me a joke` | Fetches or falls back to a built-in joke |
| `flip a coin` | Heads or tails |
| `roll a dice` / `roll a [N]-sided dice` | Dice roll |
| `roast me` | Gem insults you |
| `compliment me` | Gem reluctantly compliments you |
| `random fact` | A random fact |
| `system stats` | CPU, RAM, disk summary |
| `screenshot` | Saves to Desktop and copies to clipboard |
| `dictate` / `start dictation` | Starts voice-to-text dictation mode |
| `ping` | Tests internet latency |
| `pc uptime` | How long the PC has been on |
| `clear memory` | Wipes Groq chat history |
| `repeat that` | Repeats Gem's last spoken response |
| `what can you do` | Full capabilities list |
| `gaming mode` | Enables sniper scope overlay + silence |
| `shut up` | Silence mode on (no voice output) |
| `speak up` | Silence mode off |
| `Ruhig` | Deaf mode — ignores all commands |
| `Weiter` | Exits Ruhig mode |
| `Sperren` | Locks the screen |
| `Schluss` | Exits Gem |

## Setup

### 1. Install Python 3.10+

Download from [python.org](https://www.python.org/).

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Set environment variables

Gem reads secrets from environment variables. Set these before running:

| Variable | Required | Description |
|---|---|---|
| `OPENWEATHER_API_KEY` | For weather | Free key from [openweathermap.org](https://openweathermap.org/api) |
| `GROQ_API_KEY` | For AI fallback | Free key from [console.groq.com](https://console.groq.com) |

**Windows — set for current session:**
```cmd
set OPENWEATHER_API_KEY=your_key_here
set GROQ_API_KEY=your_key_here
```

**Windows — set permanently (System Properties → Environment Variables)** or add to your shell profile.

### 4. Configure app paths (optional)

The `APPS` dict in `gem2.py` contains hardcoded paths for apps like Discord, Spotify, VS Code, and Lunar Client. Update these paths to match your system if needed.

### 5. Run

```bash
python gem2.py
```

Gem starts in sleep mode. Say **"gem wake up"** to activate it.

## Building the EXE

Uses [PyInstaller](https://pyinstaller.org/):

```bash
pip install pyinstaller
pyinstaller --noconfirm --onefile --windowed --icon=gem.ico gem2.py
```

The executable will be in `dist/gem2.exe`. You can rename it to `gem.exe`.

**Note:** The `dist/` and `build/` folders are excluded from version control.

## Alarms & Schedule

Gem ships with a default class schedule (French and English classes). On first run, this is written to `gem_alarms.json` in the project folder. You can edit alarms by voice:

- `add class` — guided voice setup for a new recurring alarm
- `remove class [name]` — removes a scheduled alarm
- `list alarms` — lists all active alarms

`gem_alarms.json` is excluded from version control (contains personal schedule).
