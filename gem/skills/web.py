"""Web answers and search, YouTube, Wikipedia and weather (Open-Meteo, no API key needed)."""
import datetime
import html as htmllib
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
                     "Chrome/126.0 Safari/537.36", "Accept-Language": "en-US,en;q=0.9"}


@action("web_search", "Open search results in the browser (only when the user wants to see them).", "query: str")
def web_search(query=""):
    if not query:
        raise ActionError("What should I search for?")
    webbrowser.open("https://www.google.com/search?q=" + urllib.parse.quote(query))
    return "Here are the results for %s." % query


# ── Web answers ──────────────────────────────────────────────────────────────

def _clean(fragment):
    return re.sub(r"\s+", " ", htmllib.unescape(re.sub(r"<[^>]+>", " ", fragment))).strip()


_STOP = {"the", "and", "for", "what", "who", "when", "where", "which", "how", "does", "did", "was", "were", "are",
         "is", "last", "latest", "today", "now", "current", "right", "tell", "about", "with", "this", "that", "from"}


def _keywords(query):
    return [w for w in re.findall(r"[a-z0-9]+", query.lower()) if len(w) > 1 and w not in _STOP]


def _relevant(result, keywords):
    text = (result["title"] + " " + result["snippet"]).lower()
    hits = sum(1 for k in keywords if k in text)
    return hits >= max(1, (len(keywords) + 1) // 2)


def _bing_url(url):
    """Bing wraps result links in a redirect with the real URL base64-encoded in `u`."""
    url = htmllib.unescape(url)
    u = urllib.parse.parse_qs(urllib.parse.urlparse(url).query).get("u", [""])[0]
    if u.startswith("a1"):
        import base64
        s = u[2:]
        try:
            return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4)).decode("utf-8", "ignore")
        except Exception:
            pass
    return url


def _bing(query, limit=6):
    out = []
    try:
        page = requests.get("https://www.bing.com/search", params={"q": query, "form": "QBLH"}, headers=_UA,
                            timeout=6).text
        for m in re.finditer(r'<li class="b_algo".*?<h2[^>]*><a[^>]+href="([^"]+)"[^>]*>(.*?)</a></h2>(.*?)</li>',
                             page, re.S):
            snip = re.search(r"<p[^>]*>(.*?)</p>", m.group(3), re.S)
            out.append({"title": _clean(m.group(2)), "url": _bing_url(m.group(1)),
                        "snippet": _clean(snip.group(1)) if snip else ""})
            if len(out) >= limit:
                break
    except Exception as e:
        log.warning("Bing search failed: %s", e)
    return out


def _news(query, limit=6):
    """Google News RSS: reliable, dated headlines for anything recent."""
    out = []
    try:
        rss = requests.get("https://news.google.com/rss/search", headers=_UA, timeout=6,
                           params={"q": query, "hl": "en-US", "gl": "US", "ceid": "US:en"}).text
        for item in re.findall(r"<item>(.*?)</item>", rss, re.S)[:limit]:
            title = re.search(r"<title>(.*?)</title>", item, re.S)
            date = re.search(r"<pubDate>(.*?)</pubDate>", item, re.S)
            source = re.search(r"<source[^>]*>(.*?)</source>", item, re.S)
            link = re.search(r"<link>(.*?)</link>", item, re.S)
            out.append({"title": _clean(title.group(1)) if title else "", "url": link.group(1) if link else "",
                        "snippet": "", "date": date.group(1)[:16] if date else "",
                        "source": _clean(source.group(1)) if source else ""})
    except Exception as e:
        log.warning("News search failed: %s", e)
    return out


def _search(query):
    """Relevant web results first, then recent news."""
    keywords = _keywords(query)
    web = [r for r in _bing(query) if _relevant(r, keywords)]
    return web, _news(query)


def _page_text(url, limit=3000):
    try:
        r = requests.get(url, headers=_UA, timeout=5)
        if "text/html" not in r.headers.get("content-type", ""):
            return ""
        body = re.sub(r"(?is)<(script|style|nav|footer|header|aside)[^>]*>.*?</\1>", " ", r.text)
        paras = [_clean(p) for p in re.findall(r"(?is)<p[^>]*>(.*?)</p>", body)]
        return " ".join(p for p in paras if len(p) > 40)[:limit]
    except Exception:
        return ""


def _domain(url):
    host = urllib.parse.urlparse(url).netloc.lower()
    return host[4:] if host.startswith("www.") else host


@action("web_answer", "Search the web and answer out loud. Use for news, scores, prices, recent events and other "
        "live facts.", "query: str")
def web_answer(query="", q="", question="", text="", topic=""):
    query = (query or q or question or text or topic or "").strip()
    if not query:
        raise ActionError("What should I look up?")
    web, news = _search(query)
    if not web and not news:
        return web_search(query)
    lines = []
    if web:
        lines.append("Web results:")
        lines += ["- %s (%s): %s" % (r["title"], _domain(r["url"]), r["snippet"]) for r in web]
        top = next((r for r in web if not re.search(r"youtube\.com|\.pdf$", r["url"])), None)
        page = _page_text(top["url"]) if top else ""
        if page:
            lines.append("\nFrom %s:\n%s" % (_domain(top["url"]), page))
    if news:
        lines.append("\nRecent news headlines:")
        lines += ["- %s (%s)" % (r["title"], r["date"]) for r in news]
    instruction = ("Today is %s. Answer the user's question for someone listening, in one or two short plain "
                   "sentences, using only the search results below; prefer the most recent information. Mention "
                   "the source only if it helps. No citation marks or brackets. If the results don't answer it, "
                   "say you couldn't find a clear answer." % datetime.date.today().strftime("%A, %B %d, %Y"))
    answer = svc.brain.complete(instruction, "Question: %s\n\n%s" % (query, "\n".join(lines)), max_tokens=220)
    answer = re.sub(r"\s*(【[^】]*】|\[\d+(?:,\s*\d+)*\])", "", answer).strip()
    sources = []
    for r in web + news:
        d = r.get("source") or _domain(r["url"])
        if d and d not in sources and "news.google" not in d:
            sources.append(d)
    return card("web", answer, query=query, sources=sources[:3])


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


def _air_now(city):
    """(US AQI, PM2.5, UV index) right now for a city, or Nones."""
    geo = _geocode(city)
    if not geo:
        return None, None, None
    lat, lon, _ = geo
    cur = requests.get("https://air-quality-api.open-meteo.com/v1/air-quality", params={
        "latitude": lat, "longitude": lon, "timezone": "auto", "current": "us_aqi,pm2_5,uv_index"},
        timeout=8).json().get("current") or {}
    return cur.get("us_aqi"), cur.get("pm2_5"), cur.get("uv_index")


def _aqi_word(aqi):
    for limit, word in ((50, "good"), (100, "moderate"), (150, "unhealthy for sensitive people"), (200, "unhealthy"),
                        (300, "very unhealthy")):
        if aqi <= limit:
            return word
    return "hazardous"


def _uv_word(uv):
    return "low" if uv < 3 else "moderate" if uv < 6 else "high" if uv < 8 else "very high" if uv < 11 else "extreme"


@action("air_quality", "Air quality (AQI and PM2.5) and the UV index for a city (home by default).", "city?: str")
def air_quality(city=None):
    city = (city or svc.config.get("home_city") or "").strip()
    if not city:
        raise ActionError("Which city? You can also say: my city is, and the name.")
    aqi, pm, uv = _air_now(city)
    if aqi is None:
        return "I couldn't get the air quality for %s." % city
    name = (_geocode(city) or (0, 0, city))[2]
    tip = " Maybe skip the run outside." if aqi > 150 else ""
    uv_txt = " The UV index is %d, %s." % (round(uv), _uv_word(uv)) if uv is not None else ""
    return "Air quality in %s is %s, AQI %d.%s%s" % (name, _aqi_word(aqi), aqi, uv_txt, tip)
