"""Small utilities: coin, dice, jokes, quick maths."""
import random

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
