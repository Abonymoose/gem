"""Tidy the Downloads folder into type folders. Only moves files (never deletes) and can undo the last tidy."""
import json
import logging
import os
import shutil
import time

from ..actions import ActionError, action
from ..cards import card
from ..config import DATA_DIR
from ..runtime import svc
from ..winapi import known_folder

log = logging.getLogger("gem.tidy")

UNDO_FILE = os.path.join(DATA_DIR, "tidy_undo.json")

FOLDERS = {
    "PDFs": {".pdf"},
    "Documents": {".doc", ".docx", ".txt", ".rtf", ".odt", ".md", ".epub", ".pages",
                  ".ppt", ".pptx", ".key", ".xls", ".xlsx", ".csv", ".ods", ".odp"},
    "Images": {".png", ".jpg", ".jpeg", ".jfif", ".gif", ".webp", ".bmp", ".svg", ".heic", ".ico", ".tif", ".tiff",
               ".avif"},
    "Videos": {".mp4", ".mov", ".mkv", ".avi", ".webm", ".wmv", ".m4v"},
    "Music": {".mp3", ".m4a", ".wav", ".flac", ".ogg", ".aac", ".wma"},
    "Installers": {".exe", ".msi", ".msix", ".msixbundle", ".appx", ".appinstaller", ".iso", ".img"},
    "Archives": {".zip", ".rar", ".7z", ".tar", ".gz", ".tgz", ".bz2", ".xz"},
    "Code": {".py", ".js", ".jsx", ".ts", ".tsx", ".json", ".cfg", ".ini", ".yaml", ".yml", ".c", ".cpp", ".h",
             ".java", ".cs", ".sh", ".bat", ".ps1", ".css", ".ipynb"},
    "Web pages": {".html", ".htm", ".mhtml"},
    "3D models": {".stl", ".obj", ".3mf", ".fbx", ".blend", ".gltf", ".glb"},
    "Fonts": {".ttf", ".otf", ".woff", ".woff2"},
}
BY_EXT = {ext: folder for folder, exts in FOLDERS.items() for ext in exts}
# Unfinished downloads and things that must stay put.
SKIP_EXT = {".crdownload", ".part", ".partial", ".tmp", ".download", ".opdownload", ".!ut", ".aria2"}
SKIP_NAMES = {"desktop.ini", "thumbs.db"}
RECENT_SECONDS = 120


def _free_name(folder, name):
    base, ext = os.path.splitext(name)
    target, n = os.path.join(folder, name), 2
    while os.path.exists(target):
        target = os.path.join(folder, "%s (%d)%s" % (base, n, ext))
        n += 1
    return target


def _plan(root):
    """[(source, folder name)] for every loose file worth moving, plus saved-page folders that go with .html files."""
    moves, now = [], time.time()
    names = set(os.listdir(root))
    for name in sorted(names):
        path = os.path.join(root, name)
        if not os.path.isfile(path) or name.lower() in SKIP_NAMES or name.startswith("~$"):
            continue
        ext = os.path.splitext(name)[1].lower()
        if ext in SKIP_EXT or now - os.path.getmtime(path) < RECENT_SECONDS:
            continue
        folder = BY_EXT.get(ext)
        if not folder:
            continue
        moves.append((path, folder))
        if folder == "Web pages":
            assets = os.path.splitext(name)[0] + "_files"
            if assets in names and os.path.isdir(os.path.join(root, assets)):
                moves.append((os.path.join(root, assets), folder))
    return moves


def _summary(counts):
    top = sorted(counts.items(), key=lambda kv: -kv[1])
    return ", ".join("%d into %s" % (n, f) for f, n in top[:4]) + (" and the rest into %d more folders" % (len(top) - 4)
                                                                  if len(top) > 4 else "")


def _run(root, moves):
    done, counts = [], {}
    for src, folder in moves:
        dest_dir = os.path.join(root, folder)
        try:
            os.makedirs(dest_dir, exist_ok=True)
            dest = _free_name(dest_dir, os.path.basename(src))
            shutil.move(src, dest)
            done.append([src, dest])
            if not os.path.isdir(dest):
                counts[folder] = counts.get(folder, 0) + 1
        except Exception as e:
            log.warning("Couldn't move %s: %s", src, e)
    with open(UNDO_FILE, "w", encoding="utf-8") as f:
        json.dump({"t": time.time(), "root": root, "moves": done}, f)
    n = sum(counts.values())
    log.info("Tidied %d files in %s", n, root)
    rows = [{"name": k, "secs": v} for k, v in sorted(counts.items(), key=lambda kv: -kv[1])[:6]]
    return card("tidy", "Done. I moved %d files: %s. Say undo the tidy to put them back." % (n, _summary(counts)),
                total=n, rows=rows)


@action("tidy_downloads", "Sort the Downloads folder into folders by type (PDFs, Images, Installers...). Asks first; "
        "only moves files, never deletes.")
def tidy_downloads():
    root = known_folder("downloads")
    moves = _plan(root)
    files = [m for m in moves if os.path.isfile(m[0])]
    if not files:
        return "Your Downloads folder is already tidy."
    counts = {}
    for _, folder in files:
        counts[folder] = counts.get(folder, 0) + 1
    svc.assistant.confirm("I'll sort %d files in Downloads: %s. Nothing gets deleted. Go ahead?"
                          % (len(files), _summary(counts)), lambda: _run(root, moves), timeout=30)
    return None


@action("tidy_undo", "Undo the last Downloads tidy, moving files back where they were.")
def tidy_undo():
    try:
        with open(UNDO_FILE, encoding="utf-8") as f:
            last = json.load(f)
    except (OSError, ValueError):
        raise ActionError("There's no tidy to undo.")
    back, missing = 0, 0
    for src, dest in reversed(last.get("moves") or []):
        if os.path.exists(dest) and not os.path.exists(src):
            try:
                shutil.move(dest, src)
                back += 1
            except Exception as e:
                log.warning("Couldn't move back %s: %s", dest, e)
                missing += 1
        else:
            missing += 1
    root = last.get("root") or ""
    for folder in FOLDERS:                  # drop the folders the tidy made, if they're empty again
        path = os.path.join(root, folder)
        try:
            if os.path.isdir(path) and not os.listdir(path):
                os.rmdir(path)
        except OSError:
            pass
    os.remove(UNDO_FILE)
    extra = " %d couldn't go back because they were moved or renamed since." % missing if missing else ""
    return "Put %d items back where they were.%s" % (back, extra)
