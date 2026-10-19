"""Opening and closing apps, websites, folders, settings pages and files.

Apps are found automatically from the Start Menu (so updates that move an
exe, like Discord's, don't break anything). settings.json "apps" can add
aliases or exact paths.
"""
import difflib
import logging
import os
import re
import subprocess
import threading
import time
import urllib.parse
import webbrowser

import psutil

from ..actions import ActionError, action
from ..runtime import svc
from ..winapi import close_window, focus_window, foreground_window, known_folder, top_windows, \
    window_process_name, window_title

log = logging.getLogger("gem.apps")

BUILTIN_APPS = {
    "notepad": "notepad.exe", "calculator": "calc.exe", "paint": "mspaint.exe",
    "command prompt": "cmd.exe", "cmd": "cmd.exe", "terminal": "wt.exe", "powershell": "powershell.exe",
    "task manager": "taskmgr.exe", "file explorer": "explorer.exe", "explorer": "explorer.exe",
    "files": "explorer.exe", "control panel": "control.exe", "snipping tool": "snippingtool.exe",
    "settings": "ms-settings:", "microsoft store": "ms-windows-store:", "camera": "microsoft.windows.camera:",
}

SETTINGS_PAGES = {
    "bluetooth": "bluetooth", "wifi": "network-wifi", "wi-fi": "network-wifi", "network": "network",
    "display": "display", "screen": "display", "sound": "sound", "audio": "sound",
    "volume mixer": "apps-volume", "mixer": "apps-volume", "update": "windowsupdate",
    "windows update": "windowsupdate", "updates": "windowsupdate", "apps": "appsfeatures",
    "notifications": "notifications", "focus assist": "quiethours", "do not disturb": "quiethours",
    "power": "powersleep", "battery": "batterysaver", "mouse": "mousetouchpad",
    "keyboard": "typing", "microphone": "privacy-microphone", "storage": "storagesense",
    "night light": "nightlight", "default apps": "defaultapps", "startup apps": "startupapps",
    "startup": "startupapps", "background": "personalization-background", "wallpaper": "personalization-background",
    "colors": "colors", "themes": "themes", "date and time": "dateandtime", "time": "dateandtime",
    "vpn": "network-vpn", "printers": "printers", "privacy": "privacy", "accounts": "yourinfo",
}

FOLDERS = ["downloads", "documents", "desktop", "pictures", "music", "videos"]


# ── Start Menu index ─────────────────────────────────────────────────────────

class AppIndex:
    def __init__(self):
        self.entries = {}       # lower-case name -> launch target (path or shell:AppsFolder id)
        self._lock = threading.Lock()
        self.ready = threading.Event()

    def refresh_async(self):
        threading.Thread(target=self.refresh, name="app-index", daemon=True).start()

    def refresh(self):
        found = {}
        roots = [os.path.join(os.environ.get("PROGRAMDATA", r"C:\ProgramData"), r"Microsoft\Windows\Start Menu\Programs"),
                 os.path.join(os.environ.get("APPDATA", ""), r"Microsoft\Windows\Start Menu\Programs")]
        for root in roots:
            for dirpath, _, files in os.walk(root):
                for f in files:
                    name, ext = os.path.splitext(f)
                    if ext.lower() not in (".lnk", ".url", ".appref-ms"):
                        continue
                    low = name.lower()
                    if any(w in low for w in ("uninstall", "readme", "help", "documentation", "release notes")):
                        continue
                    found.setdefault(low, os.path.join(dirpath, f))
        try:
            out = subprocess.run(["powershell", "-NoProfile", "-Command",
                                  "Get-StartApps | ForEach-Object { $_.Name + '|' + $_.AppID }"],
                                 capture_output=True, text=True, timeout=20,
                                 creationflags=subprocess.CREATE_NO_WINDOW).stdout
            for line in out.splitlines():
                if "|" in line:
                    name, appid = line.rsplit("|", 1)
                    found.setdefault(name.strip().lower(), "shell:AppsFolder\\" + appid.strip())
        except Exception as e:
            log.warning("Get-StartApps failed: %s", e)
        with self._lock:
            self.entries = found
        self.ready.set()
        log.info("Indexed %d Start Menu apps", len(found))

    def find(self, name):
        name = name.lower().strip()
        self.ready.wait(timeout=5)
        with self._lock:
            entries = dict(self.entries)
        if name in entries:
            return name, entries[name]
        starts = [k for k in entries if k.startswith(name + " ") or k.startswith(name)]
        if starts:
            k = min(starts, key=len)
            return k, entries[k]
        words = [k for k in entries if re.search(r"\b%s\b" % re.escape(name), k)]
        if words:
            k = min(words, key=len)
            return k, entries[k]
        close = difflib.get_close_matches(name, list(entries), n=1, cutoff=0.8)
        if close:
            return close[0], entries[close[0]]
        return None, None


index = AppIndex()


def _launch(target):
    if target.startswith("shell:AppsFolder\\"):
        subprocess.Popen(["explorer.exe", target])
    elif re.match(r"^[a-z][a-z0-9.+-]*:", target) and not re.match(r"^[a-z]:\\", target, re.I):
        os.startfile(target)                           # URI like ms-settings: or https:
    elif os.path.exists(target):
        os.startfile(target)
    else:
        subprocess.Popen(target, shell=False)


def resolve_app(name):
    """Return (display name, launch target) for a spoken app name."""
    name = re.sub(r"^(?:the|my)\s+", "", name.lower().strip())
    name = re.sub(r"\s+(?:app|application|program)$", "", name)
    configured = svc.config.get("apps", {}) if svc.config else {}
    if name in configured:
        target = configured[name]
        if os.path.exists(target) or target.startswith(("http", "shell:", "ms-")):
            return name, target
        hit, path = index.find(target)                 # value names a Start Menu entry
        if path:
            return name, path
    if name in BUILTIN_APPS:
        return name, BUILTIN_APPS[name]
    hit, path = index.find(name)
    if path:
        return hit, path
    return None, None


def resolve_site(name):
    name = name.lower().strip()
    sites = svc.config.get("websites", {}) if svc.config else {}
    if name in sites:
        return sites[name]
    # "github dot com", "github.com", or "github com" once the dot was lost in transcription.
    m = re.match(r"^([a-z0-9-]+(?:\.[a-z0-9-]+)*)\s*(?:\bdot\b|\.)\s*(com|org|net|io|ai|dev|co|uk|de|in|gg|tv|app)$", name) \
        or re.match(r"^([a-z0-9-]+)\s+(com|org|net|io)$", name)
    if m:
        return "https://%s.%s" % (m.group(1), m.group(2))
    return None


# ── Actions ──────────────────────────────────────────────────────────────────

@action("open_app", "Open an app, website, folder or Settings page by name.", "name: str")
def open_app(name=""):
    name = (name or "").strip()
    if not name:
        raise ActionError("What should I open?")
    low = name.lower()
    site = resolve_site(low)
    if site:
        webbrowser.open(site)
        return "Opening %s." % name
    m = re.match(r"^(?:my\s+)?(%s)(?:\s+folder)?$" % "|".join(FOLDERS), low)
    if m:
        os.startfile(known_folder(m.group(1)))
        return "Opening %s." % m.group(1).capitalize()
    m = re.match(r"^(.+?)\s+settings$", low)
    if m and m.group(1) in SETTINGS_PAGES:
        os.startfile("ms-settings:" + SETTINGS_PAGES[m.group(1)])
        return "Opening %s settings." % m.group(1)
    display, target = resolve_app(low)
    if target:
        try:
            _launch(target)
        except Exception as e:
            log.error("Launch of %s (%s) failed: %s", display, target, e)
            raise ActionError("I couldn't open %s." % name)
        return "Opening %s." % name
    raise ActionError("I couldn't find an app called %s." % name)


def _process_names(name):
    name = name.lower().strip()
    procs = svc.config.get("processes", {}) if svc.config else {}
    if name in procs:
        return [p.lower() for p in procs[name]]
    _, target = resolve_app(name)
    if target and target.lower().endswith(".exe"):
        return [os.path.basename(target).lower()]
    if target and target.lower().endswith(".lnk"):
        try:
            import win32com.client
            lnk = win32com.client.Dispatch("WScript.Shell").CreateShortcut(target)
            exe = os.path.basename(lnk.TargetPath).lower()
            if exe == "update.exe":                      # Squirrel apps like Discord
                args = re.search(r"--processStart\s+\"?([^\"\s]+)", lnk.Arguments or "")
                if args:
                    exe = args.group(1).lower()
            if exe:
                return [exe]
        except Exception:
            pass
    return [name.replace(" ", "") + ".exe"]


def running(name):
    wanted = set(_process_names(name))
    return [p for p in psutil.process_iter(["name"]) if (p.info["name"] or "").lower() in wanted]


@action("close_app", "Close an app.", "name: str")
def close_app(name=""):
    procs = running(name)
    if not procs:
        return "%s isn't running." % name.capitalize()
    for p in procs:
        try:
            p.terminate()
        except Exception:
            pass
    return "Closed %s." % name


@action("close_window", "Close the focused window.")
def close_current_window():
    hwnd = foreground_window()
    title = window_title(hwnd)
    close_window(hwnd)
    return None if title else "Closed."


@action("switch_to", "Bring an open app to the front.", "name: str")
def switch_to(name=""):
    name = name.lower().strip()
    wanted = set(_process_names(name))
    windows = top_windows()
    hit = next((w for w in windows if w[2] in wanted), None) \
        or next((w for w in windows if name in w[1].lower()), None)
    if not hit:
        if resolve_app(name)[1]:
            return open_app(name)
        return "%s isn't open." % name.capitalize()
    focus_window(hit[0])
    return None


@action("open_folder", "Open Downloads, Documents, Desktop, Pictures, Music or Videos.", "name: str", ai=False)
def open_folder(name="downloads"):
    name = name.lower().strip()
    if name not in FOLDERS:
        raise ActionError("I can open Downloads, Documents, Desktop, Pictures, Music or Videos.")
    os.startfile(known_folder(name))
    return "Opening %s." % name.capitalize()


@action("open_settings", "Open a Windows Settings page (bluetooth, wifi, display, sound, update, ...).", "page: str", ai=False)
def open_settings(page=""):
    page = page.lower().replace(" settings", "").strip()
    uri = SETTINGS_PAGES.get(page)
    os.startfile("ms-settings:" + (uri or ""))
    return "Opening %s settings." % page if uri else "Opening Settings."


@action("open_url", "Open a URL.", "url: str")
def open_url(url=""):
    if not url:
        raise ActionError("Which website?")
    if not re.match(r"^https?://", url):
        url = "https://" + url
    webbrowser.open(url)
    return "Opening %s." % urllib.parse.urlparse(url).netloc.replace("www.", "")


def _search_files(words, limit_s=3.0):
    words = [w for w in re.findall(r"[a-z0-9]+", words.lower()) if w not in ("the", "my", "file", "called", "named")]
    if not words:
        return []
    roots = [known_folder(f) for f in ("desktop", "documents", "downloads")]
    hits, end = [], time.time() + limit_s
    for root in roots:
        for dirpath, dirs, files in os.walk(root):
            dirs[:] = [d for d in dirs if not d.startswith((".", "node_modules", "__pycache__", "AppData"))]
            for f in files:
                low = f.lower()
                if all(w in low for w in words):
                    path = os.path.join(dirpath, f)
                    try:
                        hits.append((os.path.getmtime(path), path))
                    except OSError:
                        pass
            if time.time() > end:
                break
    return [p for _, p in sorted(hits, reverse=True)]


@action("find_file", "Find and open a file by name.", "name: str")
def find_file(name="", open=True):
    hits = _search_files(name)
    if not hits:
        return "I couldn't find a file matching %s." % name
    if open:
        os.startfile(hits[0])
        return "Opening %s." % os.path.basename(hits[0])
    return "I found %d files. The newest is %s." % (len(hits), os.path.basename(hits[0]))


@action("open_latest_download", "Open the newest download.")
def open_latest_download():
    folder = known_folder("downloads")
    files = [os.path.join(folder, f) for f in os.listdir(folder)]
    files = [f for f in files if os.path.isfile(f) and not f.endswith((".crdownload", ".part", ".tmp"))]
    if not files:
        return "Your Downloads folder is empty."
    newest = max(files, key=os.path.getmtime)
    os.startfile(newest)
    return "Opening %s." % os.path.basename(newest)


@action("what_window", "Say which app and window is in front.", ai=False)
def what_window():
    hwnd = foreground_window()
    return "That's %s." % (window_title(hwnd) or window_process_name(hwnd) or "the desktop")
