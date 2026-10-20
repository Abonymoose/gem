"""Instant maths, unit and currency conversion: answered locally, no AI round trip."""
import ast
import logging
import math
import operator
import re
import time

import requests

from ..actions import ActionError, action
from ..cards import card
from ..parse import words_to_numbers

log = logging.getLogger("gem.calc")

# ── Maths ────────────────────────────────────────────────────────────────────

_OPS = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv,
        ast.Pow: operator.pow, ast.Mod: operator.mod, ast.USub: operator.neg, ast.UAdd: operator.pos}


def _eval(node):
    if isinstance(node, ast.Expression):
        return _eval(node.body)
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return node.value
    if isinstance(node, ast.BinOp) and type(node.op) in _OPS:
        left, right = _eval(node.left), _eval(node.right)
        if isinstance(node.op, ast.Pow) and abs(right) > 100:
            raise ValueError("exponent too large")
        return _OPS[type(node.op)](left, right)
    if isinstance(node, ast.UnaryOp) and type(node.op) in _OPS:
        return _OPS[type(node.op)](_eval(node.operand))
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "sqrt" and len(node.args) == 1:
        return math.sqrt(_eval(node.args[0]))
    raise ValueError("unsupported expression")


def fmt(x):
    if isinstance(x, float):
        if math.isinf(x) or math.isnan(x):
            raise ValueError("not a number")
        if x.is_integer() and abs(x) < 1e15:
            return "{:,}".format(int(x))
        if abs(x) >= 1000:
            return "{:,.2f}".format(x).rstrip("0").rstrip(".")
        return ("%.6g" % x)
    return "{:,}".format(x)


def to_expression(text):
    """Spoken maths -> a Python expression string, or None."""
    t = words_to_numbers(text.lower())
    t = re.sub(r"^(?:what(?:'s| is)|how much is|calculate|compute|work out|whats)\s+", "", t).strip(" ?.")
    t = t.replace(",", "")
    t = re.sub(r"(\d+(?:\.\d+)?)\s*(?:%|percent)\s+of\s+", r"(\1/100)*", t)
    t = re.sub(r"(\d+(?:\.\d+)?)\s*(?:%|percent)", r"(\1/100)", t)
    t = re.sub(r"\bsquare root of\s+(\d+(?:\.\d+)?)", r"sqrt(\1)", t)
    t = re.sub(r"(\d+(?:\.\d+)?)\s+squared\b", r"(\1**2)", t)
    t = re.sub(r"(\d+(?:\.\d+)?)\s+cubed\b", r"(\1**3)", t)
    for words, op in ((r"to the power of|raised to(?: the power of)?|\^", "**"), (r"multiplied by|times|\bx\b|×", "*"),
                      (r"divided by|over|÷", "/"), (r"plus|and", "+"), (r"minus|less", "-"), (r"mod|modulo", "%")):
        t = re.sub(r"\s*(?:%s)\s*" % words, " %s " % op, t)
    t = re.sub(r"\s+", " ", t).strip()
    if not re.fullmatch(r"[\d.\s+\-*/%()sqrt]+", t) or not re.search(r"\d", t) or not re.search(r"[+\-*/%]|sqrt", t):
        return None
    return t


def calculate(text):
    expr = to_expression(text)
    if not expr:
        return None
    try:
        value = _eval(ast.parse(expr, mode="eval"))
    except Exception:
        return None
    shown = re.sub(r"\(([\d.]+)/100\)\*", r"\1% of ", expr).replace("**", "^").replace("*", "×").replace("/", "÷").replace("sqrt", "√")
    return card("calc", "That's %s." % fmt(value), expression=shown, result=fmt(value))


@action("calculate", "Exact arithmetic (percentages, powers, square roots).", "expression: str")
def calculate_action(expression=""):
    res = calculate(expression)
    if res is None:
        raise ActionError("I couldn't work that out.")
    return res


# ── Units ────────────────────────────────────────────────────────────────────

UNITS = {
    # length (metres)
    "mm": ("length", 0.001), "millimeter": ("length", 0.001), "cm": ("length", 0.01), "centimeter": ("length", 0.01),
    "m": ("length", 1.0), "meter": ("length", 1.0), "km": ("length", 1000.0), "kilometer": ("length", 1000.0),
    "inch": ("length", 0.0254), "in": ("length", 0.0254), "foot": ("length", 0.3048), "feet": ("length", 0.3048),
    "ft": ("length", 0.3048), "yard": ("length", 0.9144), "mile": ("length", 1609.344), "mi": ("length", 1609.344),
    # mass (kilograms)
    "mg": ("mass", 1e-6), "g": ("mass", 0.001), "gram": ("mass", 0.001), "kg": ("mass", 1.0), "kilogram": ("mass", 1.0),
    "kilo": ("mass", 1.0), "lb": ("mass", 0.45359237), "pound": ("mass", 0.45359237), "oz": ("mass", 0.028349523),
    "ounce": ("mass", 0.028349523), "stone": ("mass", 6.35029318), "ton": ("mass", 1000.0), "tonne": ("mass", 1000.0),
    # volume (litres)
    "ml": ("volume", 0.001), "milliliter": ("volume", 0.001), "l": ("volume", 1.0), "liter": ("volume", 1.0),
    "cup": ("volume", 0.2365882), "pint": ("volume", 0.4731765), "quart": ("volume", 0.9463529),
    "gallon": ("volume", 3.785411784), "tablespoon": ("volume", 0.0147868), "teaspoon": ("volume", 0.00492892),
    # time (seconds)
    "second": ("time", 1.0), "sec": ("time", 1.0), "minute": ("time", 60.0), "min": ("time", 60.0),
    "hour": ("time", 3600.0), "hr": ("time", 3600.0), "day": ("time", 86400.0), "week": ("time", 604800.0),
    "month": ("time", 2629746.0), "year": ("time", 31556952.0),
    # speed (m/s)
    "kph": ("speed", 1 / 3.6), "km/h": ("speed", 1 / 3.6), "kmh": ("speed", 1 / 3.6),
    "kilometers per hour": ("speed", 1 / 3.6), "mph": ("speed", 0.44704), "miles per hour": ("speed", 0.44704),
    # data (bytes)
    "byte": ("data", 1.0), "kb": ("data", 1e3), "kilobyte": ("data", 1e3), "mb": ("data", 1e6),
    "megabyte": ("data", 1e6), "gb": ("data", 1e9), "gigabyte": ("data", 1e9), "tb": ("data", 1e12),
    "terabyte": ("data", 1e12),
}
TEMPS = {"c": "c", "celsius": "c", "centigrade": "c", "f": "f", "fahrenheit": "f", "k": "k", "kelvin": "k"}

CURRENCIES = {
    "usd": "USD", "dollar": "USD", "us dollar": "USD", "buck": "USD", "inr": "INR", "rupee": "INR", "indian rupee": "INR",
    "eur": "EUR", "euro": "EUR", "gbp": "GBP", "british pound": "GBP", "pound sterling": "GBP", "sterling": "GBP",
    "cad": "CAD", "canadian dollar": "CAD", "aud": "AUD", "australian dollar": "AUD", "jpy": "JPY", "yen": "JPY",
    "cny": "CNY", "yuan": "CNY", "chf": "CHF", "franc": "CHF", "aed": "AED", "dirham": "AED", "sgd": "SGD",
    "mxn": "MXN", "peso": "MXN", "krw": "KRW", "won": "KRW", "btc": None,
}


def _unit_key(word):
    w = word.lower().strip().rstrip(".")
    w = {"metres": "meter", "metre": "meter", "litres": "liter", "litre": "liter", "kilometres": "kilometer",
         "centimetres": "centimeter", "millimetres": "millimeter", "inches": "inch", "lbs": "lb", "kgs": "kg",
         "pounds": "pound", "feet": "feet"}.get(w, w)
    if w.endswith("s") and w[:-1] in UNITS and w not in UNITS:
        w = w[:-1]
    if w.startswith("degrees "):
        w = w[len("degrees "):]
    return w


def _currency(word):
    w = word.lower().strip().rstrip(".")
    if w.endswith("s") and w[:-1] in CURRENCIES:
        w = w[:-1]
    return CURRENCIES.get(w, w.upper() if re.fullmatch(r"[a-z]{3}", w) and w.upper() in _rates_cache.get("rates", {})
                          else None)


_rates_cache = {}


def _rates():
    if _rates_cache.get("at", 0) > time.time() - 3 * 3600:
        return _rates_cache["rates"]
    data = requests.get("https://open.er-api.com/v6/latest/USD", timeout=6).json()
    _rates_cache.update(rates=data["rates"], at=time.time())
    return data["rates"]


_CONVERT = re.compile(r"^(?:convert\s+|what(?:'s| is)\s+|how much is\s+)?([\d.,]+)\s*([a-z/ ]+?)\s+(?:to|in|into)\s+"
                      r"([a-z/ ]+?)\??$")
_HOW_MANY = re.compile(r"^how many\s+([a-z/ ]+?)\s+(?:are\s+)?(?:in|per)\s+(?:a|an|one|([\d.]+))\s+([a-z/ ]+?)\??$")


def convert(text):
    t = words_to_numbers(text.lower()).strip(" ?.")
    t = re.sub(r"\b(?:a|an)\s+(?=[a-z])", "1 ", t) if t.startswith(("convert a ", "convert an ")) else t
    m = _CONVERT.match(t)
    if m:
        amount, src, dst = float(m.group(1).replace(",", "")), m.group(2).strip(), m.group(3).strip()
    else:
        m = _HOW_MANY.match(t)
        if not m:
            return None
        dst, amount, src = m.group(1).strip(), float(m.group(2) or 1), m.group(3).strip()

    s_cur, d_cur = _currency(src), _currency(dst)
    if s_cur or d_cur:
        try:
            rates = _rates()
        except Exception:
            raise ActionError("I can't get exchange rates right now.")
        s_cur = s_cur or ("GBP" if _unit_key(src) == "pound" else None)
        d_cur = d_cur or ("GBP" if _unit_key(dst) == "pound" else None)
        if not (s_cur in rates and d_cur in rates):
            return None
        value = amount / rates[s_cur] * rates[d_cur]
        return card("calc", "%s %s is about %s %s." % (fmt(amount), s_cur, fmt(round(value, 2)), d_cur),
                    expression="%s %s → %s" % (fmt(amount), s_cur, d_cur), result="%s %s" % (fmt(round(value, 2)), d_cur))

    s_t, d_t = TEMPS.get(_unit_key(src)), TEMPS.get(_unit_key(dst))
    if s_t and d_t:
        c = {"c": amount, "f": (amount - 32) * 5 / 9, "k": amount - 273.15}[s_t]
        value = {"c": c, "f": c * 9 / 5 + 32, "k": c + 273.15}[d_t]
        names = {"c": "°C", "f": "°F", "k": "K"}
        return card("calc", "%s%s is %s%s." % (fmt(amount), names[s_t], fmt(round(value, 1)), names[d_t]),
                    expression="%s%s → %s" % (fmt(amount), names[s_t], names[d_t]),
                    result="%s%s" % (fmt(round(value, 1)), names[d_t]))

    s_u, d_u = UNITS.get(_unit_key(src)), UNITS.get(_unit_key(dst))
    if not s_u or not d_u or s_u[0] != d_u[0]:
        return None
    value = amount * s_u[1] / d_u[1]
    value = round(value, 2) if abs(value) >= 1 else round(value, 4)
    return card("calc", "%s %s is %s %s." % (fmt(amount), src, fmt(value), dst),
                expression="%s %s → %s" % (fmt(amount), src, dst), result="%s %s" % (fmt(value), dst))


@action("convert", "Convert units or currencies, e.g. '5 miles to km', '100 usd to inr', '70 f to c'.", "query: str")
def convert_action(query=""):
    res = convert(query)
    if res is None:
        raise ActionError("I couldn't convert that.")
    return res
