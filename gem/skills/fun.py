"""Small utilities: coin, dice, jokes, quick maths."""
import random
import re

import requests

from ..actions import action


@action("coin_flip", "Flip a coin.")
def coin_flip():
    return random.choice(["Heads.", "Tails."])


@action("roll_dice", "Roll dice.", "sides?: number, count?: number")
def roll_dice(sides=6, count=1):
    sides, count = max(2, int(sides or 6)), max(1, min(10, int(count or 1)))
    rolls = [random.randint(1, sides) for _ in range(count)]
    if count == 1:
        return "You rolled a %d." % rolls[0]
    return "You rolled %s, for a total of %d." % (", ".join(map(str, rolls)), sum(rolls))


@action("random_number", "Pick a random number in a range.", "low: number, high: number", ai=False)
def random_number(low=1, high=10):
    low, high = int(low), int(high)
    if low > high:
        low, high = high, low
    return "%d." % random.randint(low, high)


@action("joke", "Tell a clean joke.", ai=False)
def joke():
    try:
        data = requests.get("https://v2.jokeapi.dev/joke/Programming,Misc,Pun?safe-mode&type=twopart",
                            timeout=5).json()
        if data.get("setup"):
            return "%s ... %s" % (data["setup"], data["delivery"])
    except Exception:
        pass
    return random.choice([
        "Why don't scientists trust atoms? Because they make up everything.",
        "Why did the scarecrow win an award? He was outstanding in his field.",
        "I told my computer I needed a break. It said: no problem, I'll go to sleep.",
    ])


@action("password", "Generate a strong password and copy it to the clipboard (it is never spoken or shown).",
        "length?: number")
def password(length=16):
    import secrets
    import string
    from .. import winapi
    length = max(8, min(64, int(length or 16)))
    pool = string.ascii_letters + string.digits + "!@#$%^&*-_=+?"
    while True:
        pw = "".join(secrets.choice(pool) for _ in range(length))
        if (any(c.islower() for c in pw) and any(c.isupper() for c in pw) and any(c.isdigit() for c in pw)
                and any(not c.isalnum() for c in pw)):
            break
    winapi.set_clipboard(pw)
    return "Done, a %d-character password is on your clipboard." % length


@action("choose", "Pick one option at random.", "options: [str]")
def choose(options=None):
    if isinstance(options, str):
        options = [o for o in re.split(r",\s*|\s+or\s+|\s+and\s+", options) if o.strip()]
    options = [o.strip() for o in (options or []) if o and o.strip()]
    if len(options) < 2:
        return "Give me at least two options."
    return "%s." % random.choice(options).capitalize()
