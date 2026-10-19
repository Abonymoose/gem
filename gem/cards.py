"""Rich answer cards.

An action can return card("weather", "It's 17 degrees...", temp=17, ...)
instead of a plain string. It still behaves as the sentence to speak; the
overlay additionally draws the card (see ui/cardview.py for the kinds).
"""


class Reply(str):
    """A spoken sentence that can carry a card for the overlay."""

    def __new__(cls, text, card_data=None):
        obj = super().__new__(cls, text or "")
        obj.card = card_data
        return obj


def card(kind, text="", **data):
    data["kind"] = kind
    return Reply(text, data)


def card_of(value):
    return getattr(value, "card", None)
