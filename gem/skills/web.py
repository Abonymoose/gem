"""Web search, YouTube, Wikipedia and weather (Open-Meteo, no API key needed)."""
import datetime
import logging
import re
import urllib.parse
import webbrowser

import requests

from ..actions import ActionError, action
from ..cards import card
from ..runtime import svc

log = logging.getLogger("gem.web")

_UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
                     "Chrome/126.0 Safari/537.36"}


@action("web_search", "Google search in the browser, for live facts you can't know.", "query: str")
def web_search(query=""):
    if not query:
        raise ActionError("What should I search for?")
    webbrowser.open("https://www.google.com/search?q=" + urllib.parse.quote(query))
    return "Here are the results for %s." % query


@action("youtube", "Play the top YouTube result.", "query: str")
def youtube(query=""):
    if not query:
        webbrowser.open("https://youtube.com")
        return "Opening YouTube."
    search = "https://www.youtube.com/results?search_query=" + urllib.parse.quote(query)
    try:
        html = requests.get(search, headers=_UA, timeout=6).text
        ids = re.findall(r'"videoId":"([a-zA-Z0-9_-]{11})"', html)
        if ids:
            webbrowser.open("https://www.youtube.com/watch?v=" + ids[0])
            return "Playing %s." % query
    except Exception as e:
        log.warning("YouTube search failed: %s", e)
    webbrowser.open(search)
    return "Here's YouTube for %s." % query


@action("spotify_search", "Search in the Spotify app.", "query: str")
def spotify_search(query=""):
    import os
    os.startfile("spotify:search:" + urllib.parse.quote(query))
    return "Searching Spotify for %s." % query


@action("wikipedia", "Wikipedia summary.", "topic: str")
def wikipedia_summary(topic=""):
    import wikipedia
    wikipedia.set_lang("en")
    try:
        results = wikipedia.search(topic, results=3)
        if not results:
            return "I couldn't find %s on Wikipedia." % topic
        try:
            return wikipedia.summary(results[0], sentences=2, auto_suggest=False)
        except wikipedia.exceptions.DisambiguationError as e:
            return wikipedia.summary(e.options[0], sentences=2, auto_suggest=False)
    except Exception as e:
        log.warning("Wikipedia failed: %s", e)
        return "I couldn't reach Wikipedia."


# ── Weather ──────────────────────────────────────────────────────────────────

WEATHER_CODES = {
    0: "clear skies", 1: "mostly clear", 2: "partly cloudy", 3: "overcast", 45: "foggy", 48: "foggy",
    51: "light drizzle", 53: "drizzle", 55: "heavy drizzle", 56: "freezing drizzle", 57: "freezing drizzle",
    61: "light rain", 63: "rain", 65: "heavy rain", 66: "freezing rain", 67: "freezing rain",
    71: "light snow", 73: "snow", 75: "heavy snow", 77: "snow grains", 80: "rain showers",
    81: "rain showers", 82: "heavy rain showers", 85: "snow showers", 86: "heavy snow showers",
    95: "thunderstorms", 96: "thunderstorms with hail", 99: "thunderstorms with hail",
}

_geo_cache = {}


def _geocode(city):
    key = city.lower().strip()
    if key in _geo_cache:
        return _geo_cache[key]
    r = requests.get("https://geocoding-api.open-meteo.com/v1/search",
                     params={"name": city, "count": 1, "language": "en"}, timeout=6).json()
    if not r.get("results"):
        return None
    hit = r["results"][0]
    _geo_cache[key] = (hit["latitude"], hit["longitude"], hit["name"])
    return _geo_cache[key]


@action("weather", "Weather and chance of rain.", "city?: str, when?: now|today|tomorrow")
def weather(city=None, when="now"):
    city = (city or svc.config.get("home_city") or "").strip()
    if not city:
        raise ActionError("Which city? You can also say: my city is, and the name, so I remember it.")
    try:
        geo = _geocode(city)
        if not geo:
            return "I couldn't find a place called %s." % city
        lat, lon, name = geo
        data = requests.get("https://api.open-meteo.com/v1/forecast", params={
            "latitude": lat, "longitude": lon, "timezone": "auto", "forecast_days": 2,
            "current": "temperature_2m,apparent_temperature,relative_humidity_2m,weather_code,wind_speed_10m,is_day",
            "daily": "weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max",
        }, timeout=6).json()
    except requests.RequestException:
        return "I can't reach the weather service."
    d = data["daily"]
    if when in ("today", "tomorrow"):
        i = 0 if when == "today" else 1
        code = d["weather_code"][i]
        desc = WEATHER_CODES.get(code, "mixed weather")
        rain = d["precipitation_probability_max"][i] or 0
        high, low = round(d["temperature_2m_max"][i]), round(d["temperature_2m_min"][i])
        return card("weather", "%s in %s: %s, high of %d and low of %d degrees, %d percent chance of rain." % (
            when.capitalize(), name, desc, high, low, rain), city=name, when=when, code=code, desc=desc,
            high=high, low=low, rain=rain, is_day=True)
    c = data["current"]
    desc = WEATHER_CODES.get(c["weather_code"], "mixed weather")
    feels = round(c["apparent_temperature"])
    temp = round(c["temperature_2m"])
    feel = "" if abs(feels - temp) < 2 else ", feels like %d" % feels
    return card("weather", "It's %d degrees and %s in %s%s." % (temp, desc, name, feel), city=name, when="now",
                code=c["weather_code"], desc=desc, temp=temp, feels=feels, high=round(d["temperature_2m_max"][0]),
                low=round(d["temperature_2m_min"][0]), rain=d["precipitation_probability_max"][0] or 0,
                is_day=bool(c.get("is_day", 1)))


@action("set_home_city", "Save the user's home city.", "city: str")
def set_home_city(city=""):
    if not city:
        raise ActionError("Which city?")
    if not _geocode(city):
        return "I couldn't find a place called %s." % city
    from ..config import SETTINGS_FILE, _read_json, _write_json
    data = _read_json(SETTINGS_FILE, {})
    data["home_city"] = city
    _write_json(SETTINGS_FILE, data)
    svc.config["home_city"] = city
    return "Got it, %s is home." % city


@action("sun_times", "Sunrise and sunset.", "city?: str")
def sun_times(city=None):
    city = (city or svc.config.get("home_city") or "").strip()
    if not city:
        raise ActionError("Which city?")
    lat, lon, name = _geocode(city) or (None, None, None)
    if lat is None:
        return "I couldn't find %s." % city
    d = requests.get("https://api.open-meteo.com/v1/forecast", params={
        "latitude": lat, "longitude": lon, "timezone": "auto", "forecast_days": 1, "daily": "sunrise,sunset"},
        timeout=6).json()["daily"]
    fmt = lambda s: datetime.datetime.fromisoformat(s).strftime("%I:%M %p").lstrip("0")
    return "In %s, sunrise is at %s and sunset at %s." % (name, fmt(d["sunrise"][0]), fmt(d["sunset"][0]))
