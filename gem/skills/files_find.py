"""Find files by describing them: "the PDF I downloaded yesterday", "photos from this week", "my biggest files"."""
import datetime
import logging
import os
import re
import threading
import time

from ..actions import ActionError, action
from ..cards import card
from ..winapi import known_folder

log = logging.getLogger("gem.files_find")

KINDS = {
    "pdf": {".pdf"},
    "image": {".png", ".jpg", ".jpeg", ".jfif", ".gif", ".webp", ".bmp", ".heic"},
    "video": {".mp4", ".mov", ".mkv", ".avi", ".webm", ".wmv"},
    "audio": {".mp3", ".m4a", ".wav", ".flac", ".ogg", ".aac"},
    "document": {".doc", ".docx", ".txt", ".rtf", ".odt", ".md", ".epub"},
    "slides": {".ppt", ".pptx", ".key", ".odp"},
    "spreadsheet": {".xls", ".xlsx", ".csv", ".ods"},
    "archive": {".zip", ".rar", ".7z", ".tar", ".gz"},
    "installer": {".exe", ".msi", ".msix", ".iso"},
    "code": {".py", ".js", ".jsx", ".ts", ".html", ".css", ".json", ".java", ".cpp", ".c", ".cs"},
}
KIND_WORDS = {
    "pdf": "pdf", "pdfs": "pdf", "photo": "image", "photos": "image", "picture": "image", "pictures": "image",
    "image": "image", "images": "image", "screenshot": "image", "screenshots": "image", "pic": "image",
    "pics": "image", "video": "video", "videos": "video", "clip": "video", "clips": "video", "recording": "video",
    "song": "audio", "songs": "audio", "music": "audio", "audio": "audio", "doc": "document", "docs": "document",
    "document": "document", "documents": "document", "word": "document", "essay": "document",
    "presentation": "slides", "presentations": "slides", "slides": "slides", "powerpoint": "slides",
    "spreadsheet": "spreadsheet", "spreadsheets": "spreadsheet", "excel": "spreadsheet", "zip": "archive",
    "zips": "archive", "archive": "archive", "installer": "installer", "installers": "installer",
    "setup": "installer", "code": "code", "script": "code", "python": "code",
}
STOP = {"find", "show", "me", "my", "the", "a", "an", "that", "i", "file", "files", "from", "in", "on", "of",
        "downloaded", "download", "downloads", "saved", "made", "got", "with", "about", "called", "named", "where",
        "is", "was", "what", "did", "open", "last", "this", "today", "yesterday", "week", "month", "recent",
        "latest", "newest", "biggest", "largest", "huge", "big", "all", "any", "some", "for", "to", "it", "which",
        "ago", "days", "earlier", "folder", "pc", "computer", "laptop", "one", "ones", "took", "taking", "and"}
SKIP_DIRS = {"node_modules", ".git", "__pycache__", "venv", ".venv", "appdata", "$recycle.bin", "site-packages"}

_index = {"t": 0.0, "files": []}
_lock = threading.Lock()
last_results = {"t": 0.0, "items": []}


def _roots():
    roots = [known_folder(n) for n in ("desktop", "documents", "downloads", "pictures", "videos", "music")]
    od = os.environ.get("OneDrive")
    if od:
        roots.append(od)
    seen, out = set(), []
    for r in roots:
        if r and os.path.isdir(r) and os.path.normcase(r) not in seen:
            seen.add(os.path.normcase(r))
            out.append(r)
    return out


def _scan():
    files = []
    for root in _roots():
        base = root.rstrip("\\").count("\\")
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames if d.lower() not in SKIP_DIRS and not d.startswith(".")
                           and dirpath.count("\\") - base < 5]
            for f in filenames:
                if f.startswith(("~$", ".")) or f.lower() in ("desktop.ini", "thumbs.db"):
                    continue
                p = os.path.join(dirpath, f)
                try:
                    st = os.stat(p)
                except OSError:
                    continue
                files.append((p, f.lower(), os.path.splitext(f)[1].lower(), st.st_mtime, st.st_size))
                if len(files) > 80000:
                    return files
    return files


def _files():
    with _lock:
        if time.time() - _index["t"] > 300:
            _index["files"] = _scan()
            _index["t"] = time.time()
        return _index["files"]


def _since(text):
    now = datetime.datetime.now()
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    if "today" in text:
        return today
    if "yesterday" in text:
        return today - datetime.timedelta(days=1)
    m = re.search(r"(\d+|a|an|one|two|three|four|five|six|seven) (day|week|month)s? ago|"
                  r"(?:last|past) (\d+|two|three|four|five|six|seven) (day|week|month)s", text)
    if m:
        words = {"a": 1, "an": 1, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7}
        num = m.group(1) or m.group(3)
        n = int(num) if num.isdigit() else words.get(num, 1)
        days = n * {"day": 1, "week": 7, "month": 30}[m.group(2) or m.group(4)]
        return now - datetime.timedelta(days=days + (1 if m.group(1) else 0))      # "3 days ago" allows a day's slack
    if "this week" in text:
        return today - datetime.timedelta(days=today.weekday())
    if "last week" in text:
        return today - datetime.timedelta(days=today.weekday() + 7)
    if "this month" in text:
        return today.replace(day=1)
    if "last month" in text:
        return (today.replace(day=1) - datetime.timedelta(days=1)).replace(day=1)
    return None


def _until(text):
    today = datetime.datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    if "yesterday" in text:
        return today
    if "last week" in text:
        return today - datetime.timedelta(days=today.weekday())
    if "last month" in text:
        return today.replace(day=1)
    return None


def _when(t):
    dt = datetime.datetime.fromtimestamp(t)
    days = (datetime.date.today() - dt.date()).days
    if days == 0:
        return "today " + dt.strftime("%I:%M %p").lstrip("0")
    if days == 1:
        return "yesterday"
    return "%d days ago" % days if days < 14 else dt.strftime("%b %d, %Y")


def _size(n):
    for unit in ("bytes", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return ("%d %s" if unit == "bytes" else "%.1f %s") % (n, unit)
        n /= 1024.0


@action("find_files", "Find files on this PC by description: type (pdf, photo, video...), when (today, last week...), "
        "words in the name, or the biggest ones. Shows the top matches; 'open the first one' opens one.",
        "query: str, kind?: str, biggest?: bool")
def find_files(query="", kind="", biggest=False):
    text = (query or "").lower()
    kinds = {KIND_WORDS[w] for w in re.findall(r"[a-z]+", text) if w in KIND_WORDS}
    if kind and kind.lower() in KINDS:
        kinds.add(kind.lower())
    exts = set().union(*(KINDS[k] for k in kinds)) if kinds else None
    biggest = biggest or bool(re.search(r"\b(?:biggest|largest|huge|space)\b", text))
    since, until = _since(text), _until(text)
    words = [w for w in re.findall(r"[a-z0-9]+", text) if w not in STOP and w not in KIND_WORDS and len(w) > 1
             and not w.isdigit()]
    if not (exts or since or biggest or words):
        raise ActionError("What should I look for? You can say a type, a name, or when you got it.")
    only = os.path.normcase(known_folder("downloads")) if re.search(r"\bdownload(?:ed|s)?\b", text) else None
    hits = []
    for path, name, ext, mtime, size in _files():
        if exts and ext not in exts:
            continue
        if only and not os.path.normcase(path).startswith(only):
            continue
        if since and mtime < since.timestamp():
            continue
        if until and mtime >= until.timestamp():
            continue
        score = sum(1 for w in words if w in name)
        if words and not score:
            continue
        hits.append((score, size if biggest else mtime, path, mtime, size))
    if not hits:
        return "I couldn't find a file like that."
    hits.sort(key=lambda h: (-h[0], -h[1]))
    top = hits[:5]
    last_results.update(t=time.time(), items=[h[2] for h in top])
    rows = [{"name": os.path.basename(h[2]), "folder": os.path.basename(os.path.dirname(h[2])), "when": _when(h[3]),
             "size": _size(h[4])} for h in top]
    first = rows[0]
    if len(hits) == 1:
        text_out = "Found %s in %s, from %s." % (first["name"], first["folder"], first["when"])
    else:
        text_out = "Found %d. The %s is %s, from %s. Say open the first one to open it." % (
            len(hits), "biggest" if biggest else "best match", first["name"], first["when"])
    return card("files", text_out, rows=rows, total=len(hits))


RECENT_DIR = os.path.join(os.environ.get("APPDATA", ""), r"Microsoft\Windows\Recent")
NOT_WORK = {".exe", ".msi", ".lnk", ".url", ".ini", ".tmp", ".log", ".dll", ".sys"}


def _recent_items(limit=150):
    """Files Windows lists as recently opened, newest first: [(path, when opened)]."""
    try:
        links = [e for e in os.scandir(RECENT_DIR) if e.name.lower().endswith(".lnk")]
    except OSError:
        return []
    links.sort(key=lambda e: -e.stat().st_mtime)
    try:
        import pythoncom
        import win32com.client
        pythoncom.CoInitialize()
        shell = win32com.client.Dispatch("WScript.Shell")
    except Exception:
        return []
    out, seen = [], set()
    for e in links[:limit]:
        try:
            target = shell.CreateShortcut(e.path).TargetPath
        except Exception:
            continue
        key = os.path.normcase(target or "")
        if not target or key in seen or os.path.splitext(target)[1].lower() in NOT_WORK or not os.path.isfile(target):
            continue
        seen.add(key)
        out.append((target, e.stat().st_mtime))
    return out


WORK_KINDS = ("document", "slides", "spreadsheet", "pdf", "code")


def _recently_saved(exts=None, limit=150):
    """When Windows isn't keeping recent items (it's a privacy setting), the files you saved most recently in your
    own folders, leaving out downloads (and screenshots, unless you asked for pictures)."""
    exts = exts or set().union(*(KINDS[k] for k in WORK_KINDS))
    downloads = os.path.normcase(known_folder("downloads") or "~")
    files = [(p, mtime) for p, name, ext, mtime, size in _files()
             if ext in exts and not os.path.normcase(p).startswith(downloads)]
    files.sort(key=lambda f: -f[1])
    return files[:limit]


@action("recent_files", "Files the user opened recently (what they were working on), optionally of a kind or with "
        "words in the name; open=true opens the newest match.", "query?: str, kind?: str, open?: bool")
def recent_files(query="", kind="", open=False):
    text = (query or "").lower()
    kinds = {KIND_WORDS[w] for w in re.findall(r"[a-z]+", text) if w in KIND_WORDS}
    if kind and kind.lower() in KINDS:
        kinds.add(kind.lower())
    elif kind and kind.lower() in KIND_WORDS:
        kinds.add(KIND_WORDS[kind.lower()])
    exts = set().union(*(KINDS[k] for k in kinds)) if kinds else None
    words = [w for w in re.findall(r"[a-z0-9]+", text) if w not in STOP and w not in KIND_WORDS and len(w) > 1
             and w not in ("working", "worked", "opened", "using", "used", "had")]
    hits = []
    recent = _recent_items()
    for path, opened in recent or _recently_saved(exts):
        name = os.path.basename(path).lower()
        if exts and os.path.splitext(name)[1] not in exts:
            continue
        if words and not all(w in name for w in words):
            continue
        hits.append((path, opened))
    if not hits:
        what = "%s files" % kind if kind else "files like that" if words else "files"
        return "I don't see any recent %s." % what
    top = hits[:5]
    last_results.update(t=time.time(), items=[p for p, _ in top])
    if open:
        os.startfile(top[0][0])
        return "Opening %s." % os.path.splitext(os.path.basename(top[0][0]))[0]
    rows = [{"name": os.path.basename(p), "folder": os.path.basename(os.path.dirname(p)), "when": _when(t),
             "size": _size(os.path.getsize(p))} for p, t in top]
    names = ", then ".join(os.path.splitext(r["name"])[0] for r in rows[:3])
    said = ("Most recently you had %s open." if recent else "The files you saved most recently are %s.") % names
    return card("files", said + " Say open the first one to pick up where you left off.", rows=rows,
                total=len(hits))


@action("open_result", "Open one of the files just found (1 = first).", "number: number, folder?: bool")
def open_result(number=1, folder=False):
    items = last_results["items"] if time.time() - last_results["t"] < 600 else []
    n = int(number or 1)
    if not items or not 1 <= n <= len(items):
        raise ActionError("There's nothing to open from the last search.")
    path = items[n - 1]
    if folder:
        import subprocess
        subprocess.Popen(["explorer", "/select,", path])
        return None
    os.startfile(path)
    return None
