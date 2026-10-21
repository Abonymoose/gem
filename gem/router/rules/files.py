"""Commands: Finding files."""
import re
import time

from ..core import Match


def register(rule):
    # What you were working on (Windows' recent items)
    @rule(r"^(?:open|reopen|continue|bring up|pull up|go back to) (?:what i was (?:just |last )?working on|"
          r"where i left off|my last (?:file|document|doc)|the last (?:file|document|doc) i (?:had )?open(?:ed)?)$",
          safe=False)
    def _(m, t):
        return Match("recent_files", {"open": True}, False)

    @rule(r"^(?:open|reopen|continue|bring up|pull up) (?:my |the )?(?:last|latest|most recent|recent) "
          r"(word|excel|powerpoint|pdf|doc|document|spreadsheet|presentation|slides|essay|photo|image|video|code|"
          r"python)(?: file| document| doc| one)?$", safe=False)
    def _(m, t):
        return Match("recent_files", {"kind": m.group(1), "open": True}, False)

    @rule(r"^(?:what (?:was i|have i been|am i) (?:just )?working on|(?:show|list|what are)(?: me)? (?:my )?"
          r"recent (?:files|documents|docs)|what (?:files|documents) (?:did i|have i) (?:open|opened|use|used|"
          r"work on|worked on)(?: recently| today| lately)?)$")
    def _(m, t):
        return Match("recent_files", {})

    # Files
    @rule(r"^(?:find|show(?: me)?|where(?:'s| is| are)|look for|search for|get|pull up|list) (?:me )?"
          r"(.*\b(?:pdfs?|photos?|pictures?|images?|screenshots?|videos?|songs?|documents?|docs?|presentations?|"
          r"slides|spreadsheets?|zips?|installers?|files)\b.*)$")
    def _(m, t):
        q = m.group(1)
        if re.search(r"\b(?:saved screens?|voice notes?)\b", q) or re.match(r"^(?:my |the )?file (?:called|named) ", q):
            return None
        return Match("find_files", {"query": q})

    @rule(r"^what did i download(?: today| yesterday| this week| last week| recently)?$|"
          r"^(?:what(?:'s| is| are)|which files are) (?:taking up|using) (?:all )?(?:my |the )?(?:space|storage)$|"
          r"^(?:what are )?my (?:biggest|largest) files$")
    def _(m, t):
        q = t if "download" not in t else "downloads " + t
        return Match("find_files", {"query": q, "biggest": "space" in t or "storage" in t or "biggest" in t
                                    or "largest" in t})

    @rule(r"^(?:open|show) (?:the )?(first|second|third|fourth|fifth|1st|2nd|3rd|4th|5th|last|top)(?: one| file| result)?"
          r"(?: in (?:the |its )?folder)?$|^open (?:number|no) (\d)$|^show (?:it|that) in (?:the |its )?folder$")
    def _(m, t):
        from ...skills import files_find
        if not files_find.last_results["items"] or time.time() - files_find.last_results["t"] > 600:
            return None
        word = m.group(1) or m.group(2) or "first"
        n = {"first": 1, "1st": 1, "top": 1, "second": 2, "2nd": 2, "third": 3, "3rd": 3, "fourth": 4, "4th": 4,
             "fifth": 5, "5th": 5}.get(word, len(files_find.last_results["items"]) if word == "last" else
                                      int(word) if word.isdigit() else 1)
        return Match("open_result", {"number": n, "folder": "folder" in t})
