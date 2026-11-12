#!/usr/bin/env python3
"""Economic watch, threat board, asset strip, and frontier lab.

Every fetch fails soft: the caller keeps the previous JSON. Numbers are written
only when a response actually contains them. No prices are invented.
"""
from __future__ import annotations

import json
import math
import re
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone

import desklib as d

BROWSER = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/131.0.0.0 Safari/537.36"
)
NWS_UA = "news-desk/1.0 (https://github.com/torelldan/news-desk)"
ATOM = "{http://www.w3.org/2005/Atom}"
GEORSS = "{http://www.georss.org/georss}"

# NYSE holidays for 2026. Other venues list weekday hours only.
NYSE_HOLIDAYS_2026 = [
    "2026-01-01", "2026-01-19", "2026-02-16", "2026-04-03", "2026-05-25",
    "2026-06-19", "2026-07-03", "2026-09-07", "2026-11-26", "2026-12-25",
]

REGIONS = [
    {
        "id": "usa",
        "name": "USA",
        "query": "United States economy Federal Reserve when:14d",
        "venues": [{
            "name": "NYSE / Nasdaq", "indexName": "S&P 500", "symbol": "^GSPC",
            "timezone": "America/New_York", "sessions": [{"open": "09:30", "close": "16:00"}],
            "holidays": NYSE_HOLIDAYS_2026,
        }],
    },
    {
        "id": "north-america",
        "name": "North America",
        "query": "Canada OR Mexico economy central bank when:14d",
        "venues": [
            {"name": "TSX", "indexName": "S&P/TSX", "symbol": "^GSPTSE", "timezone": "America/Toronto",
             "sessions": [{"open": "09:30", "close": "16:00"}], "holidays": []},
            {"name": "BMV", "indexName": "IPC Mexico", "symbol": "^MXX", "timezone": "America/Mexico_City",
             "sessions": [{"open": "08:30", "close": "15:00"}], "holidays": []},
        ],
    },
    {
        "id": "latin-america",
        "name": "Latin America",
        "query": "Brazil economy B3 markets when:14d",
        "venues": [{
            "name": "B3", "indexName": "Ibovespa", "symbol": "^BVSP", "timezone": "America/Sao_Paulo",
            "sessions": [{"open": "10:00", "close": "17:00"}], "holidays": [],
        }],
    },
    {
        "id": "russia",
        "name": "Russia",
        "query": "Russia economy MOEX when:14d",
        "venues": [{
            "name": "MOEX", "indexName": "IMOEX", "symbol": "IMOEX", "timezone": "Europe/Moscow",
            "sessions": [{"open": "10:00", "close": "18:50"}], "holidays": [],
        }],
    },
    {
        "id": "china",
        "name": "China",
        "query": "China economy Shanghai markets when:14d",
        "venues": [{
            "name": "Shanghai", "indexName": "SSE Composite", "symbol": "000001.SS", "timezone": "Asia/Shanghai",
            "sessions": [{"open": "09:30", "close": "11:30"}, {"open": "13:00", "close": "15:00"}], "holidays": [],
        }],
    },
    {
        "id": "europe",
        "name": "Europe",
        "query": "Europe ECB economy markets when:14d",
        "venues": [{
            "name": "Xetra", "indexName": "EURO STOXX 50", "symbol": "^STOXX50E", "timezone": "Europe/Berlin",
            "sessions": [{"open": "09:00", "close": "17:30"}], "holidays": [],
        }],
    },
    {
        "id": "asia",
        "name": "Asia",
        "query": "Hong Kong economy Hang Seng when:14d",
        "venues": [
            {"name": "Hong Kong", "indexName": "Hang Seng", "symbol": "^HSI", "timezone": "Asia/Hong_Kong",
             "sessions": [{"open": "09:30", "close": "12:00"}, {"open": "13:00", "close": "16:00"}], "holidays": []},
        ],
    },
    {
        "id": "japan",
        "name": "Japan",
        "query": "Japan economy BoJ Nikkei when:14d",
        "venues": [
            {"name": "Tokyo", "indexName": "Nikkei 225", "symbol": "^N225", "timezone": "Asia/Tokyo",
             "sessions": [{"open": "09:00", "close": "11:30"}, {"open": "12:30", "close": "15:30"}], "holidays": []},
        ],
    },
    {
        "id": "india",
        "name": "India",
        "query": "India economy RBI Sensex Nifty when:14d",
        "venues": [
            {"name": "India", "indexName": "BSE Sensex", "symbol": "^BSESN", "timezone": "Asia/Kolkata",
             "sessions": [{"open": "09:15", "close": "15:30"}], "holidays": []},
            {"name": "NSE", "indexName": "Nifty 50", "symbol": "^NSEI", "timezone": "Asia/Kolkata",
             "sessions": [{"open": "09:15", "close": "15:30"}], "holidays": []},
        ],
    },
]

ASSETS = [
    {"id": "dxy", "name": "DXY", "symbol": "DX-Y.NYB", "fallback": "UUP", "kind": "yahoo"},
    {"id": "gold", "name": "Gold", "symbol": "GC=F", "kind": "yahoo"},
    {"id": "silver", "name": "Silver", "symbol": "SI=F", "kind": "yahoo"},
    {"id": "btc", "name": "BTC", "coin": "bitcoin", "kind": "coingecko"},
    {"id": "eth", "name": "ETH", "coin": "ethereum", "kind": "coingecko"},
]

SCIENCE = [
    {"field": "physics", "review": "PREPRINT", "name": "arXiv gr-qc / hep-th", "url": "https://export.arxiv.org/api/query?search_query=cat:gr-qc+OR+cat:hep-th&start=0&max_results=4&sortBy=submittedDate&sortOrder=descending"},
    {"field": "physics", "review": "NEWS", "name": "Phys.org physics", "url": "https://phys.org/rss-feed/physics-news/"},
    {"field": "propulsion", "review": "PREPRINT", "name": "arXiv physics.space-ph", "url": "https://export.arxiv.org/api/query?search_query=cat:physics.space-ph&start=0&max_results=4&sortBy=submittedDate&sortOrder=descending"},
    {"field": "propulsion", "review": "NEWS", "name": "NASA", "url": "https://www.nasa.gov/feed/"},
    {"field": "biomedical", "review": "NEWS", "name": "Nature", "url": "https://www.nature.com/nature.rss"},
    {"field": "biomedical", "review": "NEWS", "name": "ScienceDaily health", "url": "https://www.sciencedaily.com/rss/top/health.xml"},
    {"field": "biomedical", "review": "PREPRINT", "name": "bioRxiv", "url": "biorxiv-api"},
    {"field": "biomedical", "review": "PREPRINT", "name": "medRxiv", "url": "medrxiv-api"},
    {"field": "quantum", "review": "PREPRINT", "name": "arXiv quant-ph", "url": "https://export.arxiv.org/api/query?search_query=cat:quant-ph&start=0&max_results=4&sortBy=submittedDate&sortOrder=descending"},
    {"field": "technology", "review": "NEWS", "name": "MIT Technology Review", "url": "https://www.technologyreview.com/feed/"},
    {"field": "technology", "review": "NEWS", "name": "IEEE Spectrum", "url": "https://spectrum.ieee.org/feeds/feed.rss"},
    {"field": "ai", "review": "PREPRINT", "name": "arXiv cs.AI", "url": "https://export.arxiv.org/api/query?search_query=cat:cs.AI&start=0&max_results=4&sortBy=submittedDate&sortOrder=descending"},
    {"field": "ai", "review": "NEWS", "name": "Google AI blog", "url": "https://blog.google/technology/ai/rss/"},
]


def index_change(price, previous):
    """Return (change, percent) or (None, None). Never invent a figure."""
    try:
        price = float(price)
        previous = float(previous)
    except (TypeError, ValueError):
        return None, None
    if previous == 0:
        return None, None
    change = round(price - previous, 2)
    return change, round(100.0 * change / previous, 2)


_US_PLACE = re.compile(
    r",\s*(Alabama|Alaska|Arizona|Arkansas|California|Colorado|Connecticut|Delaware|Florida|Georgia|"
    r"Hawaii|Idaho|Illinois|Indiana|Iowa|Kansas|Kentucky|Louisiana|Maine|Maryland|Massachusetts|"
    r"Michigan|Minnesota|Mississippi|Missouri|Montana|Nebraska|Nevada|New Hampshire|New Jersey|"
    r"New Mexico|New York|North Carolina|North Dakota|Ohio|Oklahoma|Oregon|Pennsylvania|"
    r"Rhode Island|South Carolina|South Dakota|Tennessee|Texas|Utah|Vermont|Virginia|Washington|"
    r"West Virginia|Wisconsin|Wyoming|Puerto Rico|Guam)\b",
    re.I,
)


def is_us_place(place: str) -> bool:
    return bool(_US_PLACE.search(place or ""))


def quake_severity(mag, place: str = "", tsunami: bool = False) -> str:
    """Distant quakes stay quiet. CRITICAL is a U.S. or tsunami-linked shock, not every M6."""
    try:
        mag = float(mag)
    except (TypeError, ValueError):
        return "STANDBY"
    home = is_us_place(place) or bool(tsunami)
    if home:
        if mag >= 7:
            return "CRITICAL"
        if mag >= 6:
            return "ACTION"
        if mag >= 5.5:
            return "ALERT"
        return "STANDBY"
    if mag >= 8:
        return "ACTION"
    if mag >= 7:
        return "ALERT"
    if mag >= 6:
        return "STANDBY"
    return "STANDBY"


def keep_quake(mag, place: str = "", tsunami: bool = False, alert: str = "", felt: int = 0) -> bool:
    """Distant quakes stay off the board unless they are M6+ with a reported impact."""
    try:
        mag = float(mag)
    except (TypeError, ValueError):
        return False
    if is_us_place(place) or tsunami:
        return quake_severity(mag, place, tsunami) != "STANDBY" or True
    impact = str(alert or "").lower() in {"yellow", "orange", "red"} or int(felt or 0) >= 5
    if mag >= 6 and impact:
        return True
    return quake_severity(mag, place, tsunami) != "STANDBY"


def alert_severity(event: str, severity: str) -> str:
    name = (event or "").lower()
    level = (severity or "").lower()
    if "tornado warning" in name or "hurricane warning" in name:
        return "CRITICAL"
    if "tornado watch" in name or "hurricane watch" in name or "tropical storm watch" in name or "flash flood watch" in name:
        return "ALERT"
    if "tropical storm warning" in name or "flash flood warning" in name or "warning" in name:
        return "ACTION"
    if level == "extreme":
        return "CRITICAL"
    if level == "severe":
        return "ACTION"
    if "watch" in name or "advisory" in name:
        return "ALERT"
    return "STANDBY"


def _get(url: str, timeout: int = 30, headers: dict | None = None) -> bytes:
    base = {"User-Agent": BROWSER, "Accept": "*/*"}
    if headers:
        base.update(headers)
    req = urllib.request.Request(url, headers=base)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read()
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, ConnectionError):
        cmd = ["curl", "-fsSL", "--compressed", "--http1.1", "-L", "--max-time", str(timeout), "-A", base["User-Agent"]]
        for key, value in base.items():
            if key.lower() == "user-agent":
                continue
            cmd.extend(["-H", f"{key}: {value}"])
        cmd.append(url)
        proc = subprocess.run(cmd, capture_output=True, timeout=timeout + 8)
        if proc.returncode != 0 or not proc.stdout:
            err = proc.stderr.decode("utf-8", "replace")[:180]
            raise RuntimeError(err or f"fetch failed {url}")
        return proc.stdout


def _yahoo(symbol: str, range_: str = "1mo", tz_name: str = "America/New_York") -> dict | None:
    quoted = urllib.parse.quote(symbol, safe="")
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{quoted}?interval=1d&range={range_}"
    try:
        payload = json.loads(_get(url, timeout=25).decode("utf-8", "replace"))
    except Exception:
        return None
    result = ((payload.get("chart") or {}).get("result") or [None])[0]
    if not isinstance(result, dict):
        return None
    meta = result.get("meta") or {}
    quote = ((result.get("indicators") or {}).get("quote") or [{}])[0]
    closes = quote.get("close") or []
    volumes = quote.get("volume") or []
    stamps = result.get("timestamp") or []
    from deskextra import exchange_day
    points = []
    for index, (stamp, close) in enumerate(zip(stamps, closes)):
        if close is None:
            continue
        day = exchange_day(stamp, tz_name)
        point = {"date": day, "price": round(float(close), 4)}
        if index < len(volumes) and volumes[index] is not None:
            point["volume"] = volumes[index]
        points.append(point)
    price = meta.get("regularMarketPrice")
    previous = meta.get("chartPreviousClose")
    usable = [point["price"] for point in points if point.get("price") is not None]
    if len(usable) >= 2:
        change, pct = index_change(usable[-1], usable[-2])
        price = usable[-1]
    else:
        change, pct = index_change(price, previous)
    as_of = ""
    if meta.get("regularMarketTime"):
        as_of = exchange_day(meta["regularMarketTime"], tz_name)
    if price is None and not points:
        return None
    return {
        "level": None if price is None else round(float(price), 2),
        "change": change,
        "changePct": pct,
        "asOf": as_of,
        "points": points[-400:],
        "source": f"https://finance.yahoo.com/quote/{quoted}",
    }


def _headlines(query: str, now: datetime, retain_days: int = 120, limit: int = 40) -> list[dict]:
    """Read every item the RSS still publishes. Callers merge this with older saved rows."""
    url = "https://news.google.com/rss/search?q=" + urllib.parse.quote(query) + "&hl=en-US&gl=US&ceid=US:en"
    raw = _get(url, timeout=25)
    root = ET.fromstring(raw)
    channel = root.find("channel")
    if channel is None:
        return []
    rows = []
    cutoff = (now.date() - timedelta(days=retain_days)).isoformat()
    for node in channel.findall("item"):
        title = re.sub(r"\s+", " ", (node.findtext("title") or "")).strip()
        link = d.http_url(node.findtext("link") or "")
        if not title or not link:
            continue
        published = d.parse_pubdate(node.findtext("pubDate") or "")
        if published is None:
            continue
        if published.strftime("%Y-%m-%d") < cutoff:
            continue
        source = (node.findtext("source") or "Google News").strip()
        rows.append(_item("headline", "news", source, title, "", link, published, ["headline", "standby"], {"severity": "STANDBY"}))
        if len(rows) >= limit:
            break
    return rows


def merge_rows(fresh, previous, cutoff: str, cap: int = 40) -> list[dict]:
    """Keep prior rows whose dates are still inside the window, then add new ones. Dedupe by URL."""
    chosen = {}
    for row in list(previous or []) + list(fresh or []):
        url = row.get("url") or ""
        if not url or (row.get("date") or "") < cutoff:
            continue
        chosen[url] = row
    rows = sorted(chosen.values(), key=lambda row: row.get("published") or "", reverse=True)
    return rows[:cap]


def _item(kind, lane, source, title, note, url, when, tags, extra=None) -> dict:
    when = d.to_ct(when)
    row = {
        "id": d.make_id(kind, url + "|" + title[:80]),
        "kind": kind,
        "lane": lane,
        "source": source,
        "sourceId": kind,
        "title": title,
        "guest": "",
        "note": (note or "")[:500],
        "url": url,
        "published": when.isoformat(timespec="seconds"),
        "date": when.strftime("%Y-%m-%d"),
        "label": d.ct_label(when, True),
        "weekday": ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"][when.weekday()],
        "timeKnown": True,
        "tags": tags,
    }
    if extra:
        row.update(extra)
    return row


def _usa_headline(title: str) -> bool:
    """A China-only currency story is not the USA region's lead."""
    if re.search(r"\b(china|yuan|renminbi)\b", title or "", re.I) and not re.search(
        r"\b(federal reserve|fed\b|united states|u\.s\.|white house|treasury)\b", title or "", re.I
    ):
        return False
    return True


def _moex_quote() -> dict | None:
    from zoneinfo import ZoneInfo
    from deskextra import moex_level
    try:
        payload = json.loads(_get(
            "https://iss.moex.com/iss/engines/stock/markets/index/securities/IMOEX.json?iss.meta=off",
            timeout=25,
            headers={"User-Agent": NWS_UA, "Accept": "application/json"},
        ))
    except Exception as err:
        print(f"  moex: {err}")
        return None
    quote = moex_level(payload)
    if quote:
        quote["asOf"] = datetime.now(timezone.utc).astimezone(ZoneInfo("Europe/Moscow")).strftime("%Y-%m-%d")
    return quote


def fetch_markets(now: datetime, previous: dict | None = None, retain_days: int = 120) -> dict:
    regions = []
    for spec in REGIONS:
        venues = []
        for venue in spec["venues"]:
            imoex = venue["symbol"] in {"IMOEX", "IMOEX.ME"}
            if imoex:
                quote = _moex_quote() or {}
                fallback = "https://iss.moex.com/iss/engines/stock/markets/index/securities/IMOEX.json"
            else:
                quote = _yahoo(venue["symbol"], "5d", venue.get("timezone") or "America/New_York") or {}
                fallback = f"https://finance.yahoo.com/quote/{urllib.parse.quote(venue['symbol'], safe='')}"
            venues.append({
                "name": venue["name"],
                "indexName": venue["indexName"],
                "symbol": "IMOEX" if imoex else venue["symbol"],
                "timezone": venue["timezone"],
                "sessions": venue["sessions"],
                "holidays": venue["holidays"],
                "level": quote.get("level"),
                "change": quote.get("change"),
                "changePct": quote.get("changePct"),
                "asOf": quote.get("asOf") or "",
                "source": quote.get("source") or fallback,
            })
        prior_regions = {row.get("id"): row for row in ((previous or {}).get("regions") or [])}
        old_heads = (prior_regions.get(spec["id"]) or {}).get("headlines") or []
        cutoff = (now.date() - timedelta(days=retain_days)).isoformat()
        try:
            fresh = _headlines(spec["query"], now, retain_days, 40)
            if spec["id"] == "usa":
                fresh = [row for row in fresh if _usa_headline(row.get("title") or "")]
            headlines = merge_rows(fresh, old_heads, cutoff, 40)
        except Exception as err:
            print(f"  headlines {spec['id']}: {err}; keeping {len(old_heads)} cached")
            headlines = merge_rows([], old_heads, cutoff, 40)
        print(f"  headlines {spec['id']}: {len(headlines)}")
        regions.append({"id": spec["id"], "name": spec["name"], "venues": venues, "headlines": headlines})
    return {
        "holidayNote": "OPEN/CLOSED uses weekday sessions in each exchange's zone, converted to America/Chicago. Only the NYSE holiday list is included; other venues may be open on a local holiday.",
        "regions": regions,
    }


def _rss_items(url: str, limit: int = 8) -> list[ET.Element]:
    root = ET.fromstring(_get(url, timeout=30))
    channel = root.find("channel")
    if channel is None:
        channel = root.find(f"{ATOM}feed")
    if channel is None:
        return []
    nodes = channel.findall("item") or channel.findall(f"{ATOM}entry")
    return nodes[:limit]


def _point_from(node: ET.Element):
    point = node.findtext(f"{GEORSS}point") or ""
    if point:
        bits = point.split()
        if len(bits) >= 2:
            try:
                return float(bits[0]), float(bits[1])
            except ValueError:
                return None
    lat = node.findtext(f"{GEORSS}lat") or node.findtext("lat")
    lon = node.findtext(f"{GEORSS}long") or node.findtext("long") or node.findtext("lon")
    try:
        if lat and lon:
            return float(lat), float(lon)
    except ValueError:
        return None
    return None


def fetch_threats(now: datetime) -> dict:
    items = []
    gaps: list[str] = []
    network_ok = False
    try:
        payload = json.loads(_get("https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/4.5_week.geojson", timeout=40))
        network_ok = True
        quakes = []
        for feat in payload.get("features") or []:
            props = feat.get("properties") or {}
            coords = (feat.get("geometry") or {}).get("coordinates") or []
            mag = props.get("mag")
            url = d.http_url(props.get("url") or "")
            if mag is None or not url or len(coords) < 2:
                continue
            when = datetime.fromtimestamp(int(props.get("time") or 0) / 1000, timezone.utc)
            place = props.get("place") or "earthquake"
            tsunami = str(props.get("tsunami") or "") == "1"
            alert = str(props.get("alert") or "")
            try:
                felt = int(props.get("felt") or 0)
            except (TypeError, ValueError):
                felt = 0
            sev = quake_severity(mag, place, tsunami)
            impact = alert.lower() in {"yellow", "orange", "red"} or felt >= 5
            if not is_us_place(place) and not tsunami and float(mag) >= 6 and impact and sev == "STANDBY":
                sev = "ALERT"
            if not keep_quake(mag, place, tsunami, alert, felt):
                continue
            note = "USGS earthquake, magnitude 4.5 or greater, past 7 days."
            if impact and not is_us_place(place):
                note += " Reported shaking or an alert color is on the USGS record."
            if tsunami:
                note += " A tsunami flag is set."
            elif not is_us_place(place):
                note += " Outside the United States, with no tsunami flag."
            quakes.append(_item(
                "quake", "threat", "USGS",
                f"M{float(mag):.1f} {place}",
                note,
                url, when, ["quake", sev.lower()],
                {"severity": sev, "lat": coords[1], "lon": coords[0], "mag": float(mag), "usImpact": is_us_place(place) or tsunami},
            ))
        quakes.sort(key=lambda row: row.get("mag") or 0, reverse=True)
        items.extend(quakes[:30])
        print(f"  quakes {len(quakes[:30])}")
    except Exception as err:
        gaps.append(f"USGS: {err}")
        print(f"  usgs FAILED: {err}")
    extras = []
    for producer in (_try_nhc, _try_nws, _try_gdacs, _try_relief, _try_who, _try_cdc, _try_desks, _try_neos):
        batch, batch_gaps = producer(now)
        extras.extend(batch)
        gaps.extend(batch_gaps)
    if not items and not extras:
        raise RuntimeError("threat feeds returned nothing")
    if not network_ok and not any(row.get("kind") != "clock" for row in extras):
        raise RuntimeError("threat feeds failed")
    extras.append({
        "id": "clock:bulletin",
        "kind": "clock",
        "lane": "threat",
        "source": "Bulletin of the Atomic Scientists",
        "sourceId": "clock",
        "title": "Doomsday Clock",
        "guest": "",
        "note": "The official setting is published by the Bulletin. This row is only the link.",
        "url": "https://thebulletin.org/doomsday-clock/",
        "published": now.isoformat(timespec="seconds"),
        "date": now.strftime("%Y-%m-%d"),
        "label": d.ct_label(now, True),
        "weekday": ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"][now.weekday()],
        "timeKnown": True,
        "tags": ["clock", "standby"],
        "severity": "STANDBY",
    })
    kept = [row for row in items + extras if _in_year(row, now.year) or row.get("kind") == "clock"]
    kept = _drop_old_health(kept, now)
    return {"items": demote_stale_alerts(_dedupe_titles(kept), now), "gaps": gaps}


def demote_stale_alerts(rows: list[dict], now: datetime) -> list[dict]:
    """An ALERT older than about 72 hours is no longer the live status."""
    cutoff = now - timedelta(hours=72)
    for row in rows:
        if (row.get("severity") or "") != "ALERT":
            continue
        published = d.parse_pubdate(row.get("published") or "")
        if published is not None and published < cutoff:
            row["severity"] = "STANDBY"
            row["demoted"] = "older than 72h"
    return rows


def _drop_old_health(rows: list[dict], now: datetime) -> list[dict]:
    """WHO and CDC notes older than two weeks are not a current outbreak."""
    cutoff = (now - timedelta(days=14)).date().isoformat()
    out = []
    for row in rows:
        if row.get("kind") in {"who", "cdc"} and (row.get("date") or "9999") < cutoff:
            continue
        if row.get("kind") in {"who", "cdc"} and re.search(r"did not answer|data package|technical package", f"{row.get('title') or ''} {row.get('note') or ''}", re.I):
            if (row.get("date") or "9999") < cutoff:
                continue
        out.append(row)
    return out


def _in_year(row: dict, year: int) -> bool:
    date = str(row.get("date") or "")
    if len(date) >= 4 and date[:4].isdigit():
        return int(date[:4]) == year
    return False


def _dedupe_titles(rows: list[dict]) -> list[dict]:
    seen = set()
    out = []
    for row in rows:
        key = re.sub(r"\W+", " ", (row.get("title") or "").lower()).strip()
        if key and key in seen:
            continue
        if key:
            seen.add(key)
        out.append(row)
    return out


def _storm_severity(title: str, note: str) -> str:
    title_l = (title or "").lower()
    blob = f"{title} {note}".lower()
    if "tropical weather outlook" in title_l or re.search(r"there are no tropical cyclones|no tropical cyclones at this time", title_l):
        return "STANDBY"
    if "hurricane warning" in blob or "tropical storm warning" in blob:
        return "CRITICAL" if "hurricane warning" in blob else "ACTION"
    if re.search(r"\bhurricane\s+[a-z]", blob):
        return "ACTION"
    return "STANDBY"


def _try_nhc(now):
    rows = []
    answered = False
    failures = []
    for url in ("https://www.nhc.noaa.gov/index-at.xml", "https://www.nhc.noaa.gov/index-ep.xml", "https://www.nhc.noaa.gov/gtwo.xml"):
        try:
            nodes = _rss_items(url, 6)
            answered = True
            for node in nodes:
                title = re.sub(r"\s+", " ", (node.findtext("title") or "")).strip()
                link = d.http_url(node.findtext("link") or url)
                if not title or not link:
                    continue
                published = d.parse_pubdate(node.findtext("pubDate") or "") or now
                note = d.clean_note(node.findtext("description") or "")
                extra = {"severity": _storm_severity(title, note)}
                if extra["severity"] == "STANDBY" and ("outlook" in title.lower() or "no tropical cyclones" in title.lower()):
                    continue
                point = _point_from(node)
                if point:
                    extra["lat"], extra["lon"] = point
                else:
                    match = re.search(r"(\d+(?:\.\d+)?)\s*N[\s,]+(\d+(?:\.\d+)?)\s*W", note, re.I)
                    if match:
                        extra["lat"] = float(match.group(1))
                        extra["lon"] = -float(match.group(2))
                rows.append(_item("storm", "threat", "NHC", title, note, link, published, ["storm", extra["severity"].lower()], extra))
        except Exception as err:
            failures.append(str(err))
            print(f"  nhc {url}: {err}")
    gaps = []
    if not answered:
        gaps.append("NHC: outlook feeds did not answer. " + "; ".join(failures[:2]))
    return rows[:10], gaps


HOME = (35.802, -86.907)
# Tennessee, generous enough for a track point over the state.
TN_BOX = (34.98, 36.72, -90.35, -81.62)
TN_REACH_KM = 450
_COMPASS = ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE", "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"]
_NHC_CLASS = {
    "TD": "Tropical Depression",
    "TS": "Tropical Storm",
    "HU": "Hurricane",
    "STS": "Subtropical Storm",
    "STD": "Subtropical Depression",
    "PTC": "Potential Tropical Cyclone",
    "EX": "Post-tropical Cyclone",
    "LO": "Low",
    "DB": "Disturbance",
    "SD": "Subtropical Depression",
    "SS": "Subtropical Storm",
    "TY": "Typhoon",
    "ST": "Tropical Storm",
    "PC": "Post-tropical Cyclone",
}
_OUTLOOK_DN = {
    2: ("General thunderstorms", "STANDBY"),
    3: ("Marginal", "STANDBY"),
    4: ("Slight", "ALERT"),
    5: ("Enhanced", "ACTION"),
    6: ("Moderate", "ACTION"),
    7: ("High", "CRITICAL"),
}
_MIDDLE_TN = re.compile(
    r"\b(williamson|davidson|rutherford|maury|sumner|wilson|hickman|cheatham|dickson|bedford|marshall|middle tennessee)\b",
    re.I,
)
_WATCH_PHRASE = re.compile(
    r"hurricane watch|tropical storm watch|storm surge watch|hurricane warning|tropical storm warning|storm surge warning",
    re.I,
)


def compass_point(degrees) -> str:
    try:
        deg = float(degrees) % 360
    except (TypeError, ValueError):
        return ""
    return _COMPASS[int((deg + 11.25) // 22.5) % 16]


def hurricane_category(knots) -> str:
    try:
        knots = float(knots)
    except (TypeError, ValueError):
        return ""
    if knots >= 137:
        return "Category 5"
    if knots >= 113:
        return "Category 4"
    if knots >= 96:
        return "Category 3"
    if knots >= 83:
        return "Category 2"
    if knots >= 64:
        return "Category 1"
    return ""


def _km(lat1, lon1, lat2, lon2) -> float:
    radius = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return 2 * radius * math.asin(min(1.0, math.sqrt(a)))


def _in_tennessee(lat, lon) -> bool:
    south, north, west, east = TN_BOX
    return south <= lat <= north and west <= lon <= east


def forecast_positions(text: str) -> list[tuple[float, float, int]]:
    """Lat, lon, and knots from an NHC forecast advisory."""
    found = []
    for match in re.finditer(
        r"(\d+(?:\.\d+)?)\s*([NS])\s+(\d+(?:\.\d+)?)\s*([EW])\s+(\d+)\s*KT",
        text or "",
        re.I,
    ):
        lat = float(match.group(1)) * (-1 if match.group(2).upper() == "S" else 1)
        lon = float(match.group(3)) * (-1 if match.group(4).upper() == "W" else 1)
        found.append((lat, lon, int(match.group(5))))
    return found


def threatens_tennessee(positions, text: str = "") -> tuple[bool, int]:
    """A forecast point over Tennessee, or within reach of Middle Tennessee."""
    peak = 0
    hit = bool(re.search(r"\btennessee\b", text or "", re.I))
    for lat, lon, knots in positions or []:
        if _in_tennessee(lat, lon) or _km(lat, lon, HOME[0], HOME[1]) <= TN_REACH_KM:
            hit = True
            peak = max(peak, knots)
    return hit, peak


def us_coastal_watch(text: str, watches_present: bool = False) -> bool:
    """True when an NHC product has a US hurricane or tropical storm watch or warning."""
    blob = text or ""
    if re.search(r"no coastal watches or warnings in effect", blob, re.I):
        return False
    if _WATCH_PHRASE.search(blob):
        return True
    return bool(watches_present)


def tropical_severity(positions, advisory: str, watches_present: bool, knots_now=0) -> str:
    """STANDBY unless a US watch/warning is up, or the track reaches Tennessee."""
    hit, peak = threatens_tennessee(positions, advisory)
    try:
        knots_now = int(knots_now or 0)
    except (TypeError, ValueError):
        knots_now = 0
    strongest = peak or (knots_now if hit else 0)
    if hit and strongest >= 64:
        return "CRITICAL"
    if hit:
        return "ACTION"
    if us_coastal_watch(advisory, watches_present):
        return "ALERT"
    return "STANDBY"


def _point_in_ring(lon: float, lat: float, ring) -> bool:
    inside = False
    if len(ring) < 3:
        return False
    j = len(ring) - 1
    for i, point in enumerate(ring):
        xi, yi = point[0], point[1]
        xj, yj = ring[j][0], ring[j][1]
        if ((yi > lat) != (yj > lat)) and (lon < (xj - xi) * (lat - yi) / ((yj - yi) or 1e-15) + xi):
            inside = not inside
        j = i
    return inside


def _point_in_geom(lon: float, lat: float, geom: dict) -> bool:
    kind = (geom or {}).get("type")
    coords = (geom or {}).get("coordinates") or []
    if kind == "Polygon":
        if not coords or not _point_in_ring(lon, lat, coords[0]):
            return False
        return not any(_point_in_ring(lon, lat, hole) for hole in coords[1:])
    if kind == "MultiPolygon":
        return any(_point_in_geom(lon, lat, {"type": "Polygon", "coordinates": poly}) for poly in coords)
    return False


def outlook_at_point(features, lon=HOME[1], lat=HOME[0]) -> tuple[str, str]:
    """Highest SPC categorical risk whose polygon contains the point."""
    best_dn = 0
    label = ""
    for feature in features or []:
        props = feature.get("properties") or {}
        try:
            dn = int(props.get("DN") or 0)
        except (TypeError, ValueError):
            dn = 0
        if dn <= best_dn:
            continue
        if _point_in_geom(lon, lat, feature.get("geometry") or {}):
            best_dn = dn
            label = props.get("LABEL2") or props.get("LABEL") or ""
    if best_dn <= 1:
        return "No thunderstorm risk", "STANDBY"
    name, sev = _OUTLOOK_DN.get(best_dn, (label or "Thunderstorms", "STANDBY"))
    return name, sev


def spc_watch_severity(title: str, note: str = "") -> str:
    blob = f"{title or ''} {note or ''}"
    if re.search(r"no watches are valid|no watches", blob, re.I):
        return "STANDBY"
    covers = _MIDDLE_TN.search(blob) is not None
    if re.search(r"tornado watch", blob, re.I) and covers:
        return "ACTION"
    if re.search(r"severe thunderstorm watch|severe tstm watch", blob, re.I) and covers:
        return "ALERT"
    return "STANDBY"


def _storm_row(now, title, note, url, severity, kind, source) -> dict:
    row = _item(kind, "local", source, title, note, url, now, [kind, severity.lower(), "tennessee"], {"severity": severity})
    row["soWhat"] = _storm_advice(kind, severity, title)
    row["action"] = "no action needed" if row["soWhat"] in {"", "no action needed"} else row["soWhat"]
    return row


def _storm_advice(kind: str, severity: str, title: str) -> str:
    if kind == "nws" and re.search(r"tornado warning", title or "", re.I):
        return "Take shelter now. Interior room, lowest floor, away from windows."
    if severity == "CRITICAL":
        return "The forecast reaches Tennessee at hurricane strength. What to do: treat this as a local hurricane threat."
    if severity == "ACTION" and kind == "tropical":
        return "The track comes close to Tennessee. What to do: plan for heavy rain, flooding, or a tornado risk in Middle Tennessee."
    if severity == "ACTION" and kind == "spc-outlook":
        return "SPC has an enhanced or moderate risk at 37179. What to do: stay weather-aware through the outlook period."
    if severity == "ACTION":
        return "A tornado watch covers Middle Tennessee. What to do: know the shelter spot and stay with the warning."
    if severity == "ALERT" and kind == "tropical":
        return "A US hurricane or tropical storm watch or warning is in effect. No action for 37179 unless this note names Tennessee."
    if severity == "ALERT":
        return "A severe thunderstorm watch covers Middle Tennessee. What to do: stay weather-aware. No shelter action yet."
    return "No action for 37179."


def _basin_name(storm_id: str) -> str:
    prefix = (storm_id or "")[:2].lower()
    return {"al": "Atlantic", "ep": "East Pacific", "cp": "Central Pacific"}.get(prefix, "NHC basin")


def describe_storm(storm: dict, advisory: str = "", positions=None) -> dict:
    """One active-storm line: name, type, winds, movement, advisory link, severity."""
    name = storm.get("name") or "Unnamed"
    code = (storm.get("classification") or "").upper()
    kind_name = _NHC_CLASS.get(code, code or "Tropical cyclone")
    try:
        knots = int(float(storm.get("intensity") or 0))
    except (TypeError, ValueError):
        knots = 0
    category = hurricane_category(knots) if code == "HU" else ""
    label = f"{kind_name} {name}" + (f", {category}" if category else "")
    direction = compass_point(storm.get("movementDir"))
    try:
        speed = int(float(storm.get("movementSpeed") or 0))
    except (TypeError, ValueError):
        speed = 0
    move = f"Moving {direction} at {speed} kt" if direction else "Movement not in the feed"
    mph = round(knots * 1.15078) if knots else 0
    winds = f"Max winds {knots} kt ({mph} mph)" if knots else "Max winds not in the feed"
    positions = list(positions or [])
    if storm.get("latitudeNumeric") is not None and storm.get("longitudeNumeric") is not None:
        positions = [(float(storm["latitudeNumeric"]), float(storm["longitudeNumeric"]), knots)] + positions
    watches = storm.get("windWatchesWarnings") or storm.get("stormSurgeWatchWarningGIS")
    severity = tropical_severity(positions, advisory, bool(watches), knots)
    where = f"{storm.get('latitude') or ''} {storm.get('longitude') or ''}".strip()
    basin = _basin_name(storm.get("id") or "")
    watch_line = "US hurricane or tropical storm watch/warning is in effect" if severity == "ALERT" else "No US hurricane or tropical storm watch or warning"
    if severity in {"ACTION", "CRITICAL"}:
        watch_line = "Forecast track reaches Tennessee"
    elif us_coastal_watch(advisory, bool(watches)) and severity == "STANDBY":
        watch_line = "No US hurricane or tropical storm watch or warning"
    note = f"{winds}. {move}. {basin}" + (f" at {where}." if where else ".") + f" {watch_line}."
    adv = storm.get("publicAdvisory") or {}
    url = d.http_url((adv.get("url") if isinstance(adv, dict) else "") or "https://www.nhc.noaa.gov/")
    return {
        "title": label,
        "note": note,
        "url": url,
        "severity": severity,
        "kind": "tropical",
        "source": "NHC",
    }


def _quiet_tropical(now) -> dict:
    return _storm_row(
        now,
        "No active tropical systems",
        "NHC reported no active tropical cyclones. The Atlantic hurricane season runs through Nov 30.",
        "https://www.nhc.noaa.gov/",
        "STANDBY",
        "tropical",
        "NHC",
    )


def _storms_from_rss(now) -> tuple[list[dict], bool]:
    """Atlantic, East Pacific, and Central Pacific RSS when CurrentStorms.json is down."""
    rows = []
    answered = False
    seen = set()
    for url in (
        "https://www.nhc.noaa.gov/index-at.xml",
        "https://www.nhc.noaa.gov/index-ep.xml",
        "https://www.nhc.noaa.gov/index-cp.xml",
    ):
        try:
            nodes = _rss_items(url, 8)
        except Exception:
            continue
        answered = True
        for node in nodes:
            title = re.sub(r"\s+", " ", (node.findtext("title") or "")).strip()
            if not title or re.search(r"tropical weather outlook|no tropical cyclones", title, re.I):
                continue
            if not re.search(r"public advisory|summary for", title, re.I):
                continue
            key = re.sub(r"\W+", " ", title.lower())
            if key in seen:
                continue
            seen.add(key)
            link = d.http_url(node.findtext("link") or url)
            note = d.clean_note(node.findtext("description") or "")
            severity = tropical_severity(forecast_positions(note), f"{title} {note}", False, 0)
            rows.append(_storm_row(now, title, note or "NHC RSS advisory.", link, severity, "tropical", "NHC"))
    return rows, answered


def _nhc_storm_items(now) -> tuple[list[dict], str]:
    try:
        payload = json.loads(_get("https://www.nhc.noaa.gov/CurrentStorms.json", timeout=25, headers={"Accept": "application/json", "User-Agent": NWS_UA}))
    except Exception as err:
        rows, answered = _storms_from_rss(now)
        if not answered:
            return [], f"NHC: {err}"
        if not rows:
            return [_quiet_tropical(now)], ""
        return rows, ""
    storms = payload.get("activeStorms") or []
    if not storms:
        return [_quiet_tropical(now)], ""
    rows = []
    for storm in storms:
        advisory = ""
        positions = []
        adv = storm.get("forecastAdvisory") if isinstance(storm.get("forecastAdvisory"), dict) else {}
        public = storm.get("publicAdvisory") if isinstance(storm.get("publicAdvisory"), dict) else {}
        text_url = (adv or {}).get("url") or (public or {}).get("url") or ""
        watches = storm.get("windWatchesWarnings") or storm.get("stormSurgeWatchWarningGIS")
        near = False
        if storm.get("latitudeNumeric") is not None and storm.get("longitudeNumeric") is not None:
            near = _km(float(storm["latitudeNumeric"]), float(storm["longitudeNumeric"]), HOME[0], HOME[1]) < 2500 or bool(watches)
        if text_url and (watches or near):
            try:
                advisory = _get(text_url, timeout=20, headers={"User-Agent": NWS_UA}).decode("utf-8", "replace")
                positions = forecast_positions(advisory)
            except Exception:
                advisory = ""
        described = describe_storm(storm, advisory, positions)
        rows.append(_storm_row(now, described["title"], described["note"], described["url"], described["severity"], "tropical", "NHC"))
    return rows, ""


def _spc_watch_items(now) -> tuple[list[dict], str]:
    try:
        nodes = _rss_items("https://www.spc.noaa.gov/products/spcwwrss.xml", 12)
    except Exception as err:
        return [], f"SPC watches: {err}"
    rows = []
    for node in nodes:
        title = re.sub(r"\s+", " ", (node.findtext("title") or "")).strip()
        if not title or title.lower() in {"spc tornado/severe thunderstorm watches", "spc forecast products"}:
            continue
        note = d.clean_note(node.findtext("description") or "")
        link = d.http_url(node.findtext("link") or "https://www.spc.noaa.gov/products/watch/")
        severity = spc_watch_severity(title, note)
        if re.search(r"no watches are valid", title, re.I):
            title = "No SPC tornado or severe thunderstorm watches"
            note = "SPC watch feed answered. Nothing is in effect."
        rows.append(_storm_row(now, title, note, link, severity, "spc-watch", "SPC"))
    if not rows:
        rows.append(_storm_row(
            now,
            "No SPC tornado or severe thunderstorm watches",
            "SPC watch feed answered with no watch products.",
            "https://www.spc.noaa.gov/products/watch/",
            "STANDBY",
            "spc-watch",
            "SPC",
        ))
    return rows[:8], ""


def _spc_outlook_items(now) -> tuple[list[dict], list[str]]:
    rows = []
    gaps = []
    for day in (1, 2, 3):
        url = f"https://www.spc.noaa.gov/products/outlook/day{day}otlk_cat.nolyr.geojson"
        page = f"https://www.spc.noaa.gov/products/outlook/day{day}otlk.html"
        try:
            payload = json.loads(_get(url, timeout=25, headers={"Accept": "application/geo+json", "User-Agent": NWS_UA}))
        except Exception as err:
            gaps.append(f"SPC day {day} outlook: {err}")
            continue
        label, severity = outlook_at_point(payload.get("features") or [])
        title = f"Day {day} convective outlook: {label} at Thompson's Station (37179)"
        note = "SPC categorical outlook for 35.802, -86.907."
        rows.append(_storm_row(now, title, note, page, severity, "spc-outlook", "SPC"))
    return rows, gaps


def fetch_storm_watch(now: datetime) -> dict:
    """Hurricane, SPC watch, and Day 1–3 outlook lines for the preparedness card."""
    items = []
    gaps = []
    storms, gap = _nhc_storm_items(now)
    if gap:
        gaps.append(gap)
    items.extend(storms)
    watches, gap = _spc_watch_items(now)
    if gap:
        gaps.append(gap)
    items.extend(watches)
    outlooks, outlook_gaps = _spc_outlook_items(now)
    gaps.extend(outlook_gaps)
    items.extend(outlooks)
    return {
        "place": "Thompson's Station / Williamson County / Middle Tennessee (37179)",
        "note": storm_watch_note(items),
        "items": items,
        "gaps": gaps,
    }


def storm_watch_note(items) -> str:
    """The 'quiet list' sentence only when NHC actually reported no active systems."""
    note = "Atlantic hurricane season runs through Nov 30."
    tropical = [item for item in items or [] if item.get("kind") == "tropical"]
    active = [item for item in tropical if not re.search(r"no active tropical", item.get("title") or "", re.I)]
    if tropical and not active:
        note += " A quiet tropical line means NHC reported no active systems."
    return note


def storm_source_rows(storms: dict) -> list[dict]:
    """Source-map rows for the storm watch, with a count and the last check time."""
    items = (storms or {}).get("items") or []
    gaps = " ".join((storms or {}).get("gaps") or []).lower()

    def pack(source_id, name, short, url, kinds, down_key):
        mine = [item for item in items if item.get("kind") in kinds]
        latest = max(mine, key=lambda item: item.get("published") or "", default=None)
        offline = down_key in gaps and not mine
        return {
            "id": source_id,
            "name": name,
            "short": short,
            "lane": "threat",
            "url": url,
            "subtitle": "source down" if offline else "threat",
            "lastLabel": (latest or {}).get("label") or "",
            "lastDate": (latest or {}).get("date") or "",
            "count": len(mine),
            "offline": offline,
        }

    return [
        pack("threat-storm", "NHC storms", "NHC", "https://www.nhc.noaa.gov/", {"tropical"}, "nhc"),
        pack("threat-spc", "SPC storm watch", "SPC", "https://www.spc.noaa.gov/", {"spc-watch", "spc-outlook"}, "spc"),
    ]


def apply_storm_sources(rows: list[dict], storms: dict) -> list[dict]:
    by_id = {row.get("id"): row for row in rows}
    for row in storm_source_rows(storms):
        current = by_id.get(row["id"])
        if current:
            current.update(row)
        else:
            rows.append(row)
            by_id[row["id"]] = row
    return rows


def _try_nws(now):
    rows = []
    headers = {"User-Agent": NWS_UA, "Accept": "application/geo+json"}
    urls = [
        "https://api.weather.gov/alerts/active?point=35.925,-86.869",
        "https://api.weather.gov/alerts/active?area=TN",
    ]
    seen = set()
    for url in urls:
        try:
            payload = json.loads(_get(url, timeout=30, headers=headers))
        except Exception as err:
            print(f"  nws {url}: {err}")
            continue
        for feat in (payload.get("features") or [])[:20]:
            props = feat.get("properties") or {}
            event = props.get("event") or "Weather alert"
            link = d.http_url(props.get("uri") or props.get("@id") or "https://www.weather.gov")
            if not link or link in seen:
                continue
            seen.add(link)
            when = d.parse_pubdate(props.get("sent") or props.get("effective") or "") or now
            sev = alert_severity(event, props.get("severity") or "")
            area = props.get("areaDesc") or "Tennessee"
            from deskextra import nws_geo, tn_alert_scope
            extra = {"severity": sev}
            extra.update(nws_geo(props))
            if "area=TN" in url:
                scope = tn_alert_scope(props)
                if scope == "elsewhere":
                    sev = "STANDBY"
                    extra["severity"] = sev
                    area = f"{area}. Elsewhere in Tennessee, not Williamson County or an adjacent county."
            rows.append(_item("nws", "threat", "NWS", event, area, link, when, ["nws", sev.lower(), "tennessee"], extra))
    try:
        national = "https://api.weather.gov/alerts/active?status=actual&message_type=alert&severity=Extreme,Severe"
        payload = json.loads(_get(national, timeout=40, headers=headers))
        kept = 0
        for feat in payload.get("features") or []:
            props = feat.get("properties") or {}
            event = props.get("event") or ""
            if not re.search(r"tornado|flood|hurricane", event, re.I):
                continue
            link = d.http_url(props.get("uri") or "")
            if not link or link in seen:
                continue
            seen.add(link)
            when = d.parse_pubdate(props.get("sent") or "") or now
            sev = alert_severity(event, props.get("severity") or "")
            rows.append(_item("nws", "threat", "NWS", event, props.get("areaDesc") or "United States", link, when, ["nws", sev.lower()], {"severity": sev}))
            kept += 1
            if kept >= 12:
                break
    except Exception as err:
        print(f"  nws national: {err}")
        return rows, [f"NWS national alerts: {err}"]
    return rows, []


def _try_gdacs(now):
    rows = []
    errors = []
    for url in (
        "https://www.gdacs.org/xml/rss.xml",
        "https://www.gdacs.org/xml/rss_7d.xml",
        "https://gdacs.org/xml/rss.xml",
    ):
        try:
            nodes = _rss_items(url, 12)
        except Exception as err:
            errors.append(str(err))
            print(f"  gdacs {url}: {err}")
            continue
        for node in nodes:
            title = re.sub(r"\s+", " ", (node.findtext("title") or "")).strip()
            link = d.http_url(node.findtext("link") or "https://www.gdacs.org/")
            if not title or not link:
                continue
            published = d.parse_pubdate(node.findtext("pubDate") or "") or now
            alert = (node.findtext("{http://www.gdacs.org}alertlevel") or node.findtext("gdacs:alertlevel") or "").lower()
            sev = "CRITICAL" if "red" in alert else "ACTION" if "orange" in alert else "ALERT"
            extra = {"severity": sev}
            point = _point_from(node)
            if point:
                extra["lat"], extra["lon"] = point
            rows.append(_item("gdacs", "threat", "GDACS", title, d.clean_note(node.findtext("description") or ""), link, published, ["gdacs", sev.lower()], extra))
        if rows:
            return rows, []
    if not rows:
        return [], ["GDACS: " + (errors[0] if errors else "RSS returned no events.")]
    return rows, []


def _try_relief(now):
    rows = []
    errors = []
    url = "https://api.reliefweb.int/v1/disasters?appname=news-desk&profile=list&preset=latest&limit=8"
    try:
        payload = json.loads(_get(url, timeout=30))
        for entry in payload.get("data") or []:
            fields = entry.get("fields") or {}
            title = fields.get("name") or ""
            link = d.http_url(fields.get("url") or "")
            if not title or not link:
                continue
            created = ((fields.get("date") or {}).get("created")) or ""
            published = d.parse_pubdate(created) or now
            country = ((fields.get("primary_country") or {}).get("name")) or ""
            kind = ((fields.get("primary_type") or {}).get("name")) or "disaster"
            rows.append(_item("relief", "threat", "ReliefWeb", title, f"{kind}. {country}".strip(), link, published, ["relief", "alert"], {"severity": "ALERT"}))
    except Exception as err:
        errors.append(str(err))
        print(f"  reliefweb: {err}")
    if rows:
        return rows, []
    for rss in ("https://reliefweb.int/disasters/rss.xml", "https://reliefweb.int/updates/rss.xml"):
        try:
            for node in _rss_items(rss, 8):
                title = re.sub(r"\s+", " ", (node.findtext("title") or "")).strip()
                link = d.http_url(node.findtext("link") or rss)
                if not title or not link:
                    continue
                published = d.parse_pubdate(node.findtext("pubDate") or "") or now
                rows.append(_item("relief", "threat", "ReliefWeb", title, "", link, published, ["relief", "alert"], {"severity": "ALERT"}))
            if rows:
                return rows, []
        except Exception as err:
            errors.append(str(err))
            print(f"  reliefweb {rss}: {err}")
    return [], ["ReliefWeb: disasters feed did not answer. " + (errors[0] if errors else "")]


def _try_who(now):
    rows = []
    for url in ("https://www.who.int/feeds/entity/csr/don/en/rss.xml", "https://www.who.int/rss-feeds/news-english.xml"):
        try:
            nodes = _rss_items(url, 6)
        except Exception as err:
            print(f"  who {url}: {err}")
            continue
        for node in nodes:
            title = re.sub(r"\s+", " ", (node.findtext("title") or "")).strip()
            link = d.http_url(node.findtext("link") or "")
            if not title or not link:
                continue
            published = d.parse_pubdate(node.findtext("pubDate") or "") or now
            if published.year < now.year or (now - published).days > 14:
                continue
            if re.search(r"covid|technical package|data for covid", title, re.I):
                continue
            sev = "ALERT" if re.search(r"outbreak|cases|deaths|epidemic", title, re.I) else "STANDBY"
            rows.append(_item("who", "threat", "WHO", title, d.clean_note(node.findtext("description") or ""), link, published, ["who", sev.lower()], {"severity": sev}))
        if rows:
            break
    gaps = [] if rows else ["WHO: outbreak notices did not answer in the last 14 days."]
    return rows[:6], gaps


def _try_cdc(now):
    rows = []
    try:
        for row in _headlines("CDC Health Alert Network", now, 3):
            row = dict(row)
            row["kind"] = "cdc"
            row["source"] = "CDC HAN"
            official = bool(re.search(r"health alert network|\bHAN\b", row.get("title") or "", re.I))
            row["severity"] = "ACTION" if official else "ALERT"
            row["tags"] = list(dict.fromkeys((row.get("tags") or []) + ["cdc", row["severity"].lower()]))
            rows.append(row)
    except Exception as err:
        print(f"  cdc headlines: {err}")
        return [], [f"CDC HAN: {err}"]
    fresh = [row for row in rows if (row.get("date") or "") >= (now - timedelta(days=14)).date().isoformat()]
    if not fresh:
        return [], ["CDC HAN: RSS did not answer and no notice is newer than 14 days."]
    return fresh[:5], []


_STORY_STOP = {
    "the", "and", "for", "with", "from", "that", "this", "after", "over", "into",
    "about", "says", "say", "new", "news", "has", "have", "was", "are", "but",
    "not", "its", "his", "her", "who", "what", "when", "where", "will", "their",
    "they", "been", "than", "also", "just", "more", "most", "out", "off", "per",
    "via", "his", "her", "you", "your",
}
_PLACE_NAMES = {"krakow", "oleshky", "antalya", "cop31", "abu dhabi"}
_PERSON_NAMES = {"hegseth", "massie", "eisenkot", "netanyahu"}
_NAME_RE = re.compile(
    r"\b(krakow|kraków|oleshky|eisenkot|netanyahu|cop31|antalya|hegseth|massie)\b",
    re.I,
)
DESK_CAP = 4


def _strip_outlet(title: str) -> str:
    cleaned = title or ""
    for _ in range(2):
        nxt = re.sub(r"\s+[-–—|]\s+[^-–—|]{2,60}$", "", cleaned)
        if nxt == cleaned:
            break
        cleaned = nxt
    return cleaned


def _normalize_story_text(title: str) -> str:
    cleaned = _strip_outlet(title or "")
    cleaned = re.sub(r"israeli", "israel", cleaned, flags=re.I)
    cleaned = re.sub(r"kraków", "krakow", cleaned, flags=re.I)
    cleaned = re.sub(r"\bcop\s*31\b", "cop31", cleaned, flags=re.I)
    return cleaned


def story_tokens(title: str) -> set[str]:
    words = re.findall(r"[a-z0-9]{3,}", _normalize_story_text(title).lower())
    return {word for word in words if word not in _STORY_STOP}


def _story_names(title: str) -> set[str]:
    text = _normalize_story_text(title)
    found = set()
    for match in _NAME_RE.finditer(text or ""):
        found.add(match.group(0).lower().replace("ó", "o"))
    if re.search(r"abu dhabi", text or "", re.I):
        found.add("abu dhabi")
    return found


def _israel_government(title: str) -> bool:
    """The Eisenkot / next-prime-minister story, not every headline that says Israel."""
    blob = (title or "").lower()
    if "israel" not in blob:
        return False
    if re.search(r"\b(eisenkot|netanyahu|knesset)\b", blob):
        return True
    if re.search(r"prime minister", blob) and re.search(r"\b(choose|next|form|government|coalition)\b", blob):
        return True
    if re.search(r"\bgovernment\b", blob) and re.search(r"\b(form|forge|coalition|president)\b", blob):
        return True
    return False


def _ukraine_talks(title: str) -> bool:
    """Russia-Ukraine peace talks, including a peace-push headline that never says Abu Dhabi."""
    blob = (title or "").lower()
    if not re.search(r"\bukraine\b", blob) or not re.search(r"\brussia", blob):
        return False
    if re.search(r"\b(abu dhabi|peace push|peace talks|peace deal)\b", blob):
        return True
    return bool(re.search(r"\btalks\b", blob) and re.search(r"\b(peace|negotiat)\b", blob))


def same_story(a: str, b: str) -> bool:
    """True when two headlines are the same story under different outlets or follow-ups."""
    if not a or not b:
        return False
    left, right = story_tokens(a), story_tokens(b)
    if len(left) >= 2 and len(right) >= 2:
        shared = left & right
        small = min(len(left), len(right))
        if len(shared) >= 3 and len(shared) / small >= 0.35:
            return True
        if len(shared & {"israel", "president", "government", "netanyahu", "eisenkot", "knesset", "coalition"}) >= 3:
            return True
    names_a, names_b = _story_names(a), _story_names(b)
    if names_a & names_b & _PLACE_NAMES:
        return True
    violent = all(re.search(r"\b(kill\w*|shoot\w*|gunman)\b", text or "", re.I) for text in (a, b))
    mentions_poland = re.search(r"\b(polish|poland)\b", a or "", re.I) or re.search(r"\b(polish|poland)\b", b or "", re.I)
    mentions_krakow = "krakow" in names_a or "krakow" in names_b
    if violent and mentions_poland and mentions_krakow:
        return True
    people = names_a & names_b & _PERSON_NAMES
    if people and len((left & right) - people) >= 1:
        return True
    if european_named_storm(a) and european_named_storm(b):
        if re.search(r"\bcharles\b", a, re.I) and re.search(r"\bcharles\b", b, re.I):
            return True
        if re.search(r"\bbruna\b", a, re.I) and re.search(r"\bbruna\b", b, re.I):
            return True
    if _israel_government(a) and _israel_government(b):
        return True
    if _ukraine_talks(a) and _ukraine_talks(b):
        return True
    if _poland_shooting(a) and _poland_shooting(b):
        return True
    return False


def _poland_shooting(title: str) -> bool:
    blob = title or ""
    if not re.search(r"\b(poland|polish|krak[oó]w)\b", blob, re.I):
        return False
    return re.search(r"\b(shoot\w*|kill\w*|gunman|massacre)\b", blob, re.I) is not None


_CLAIM_RE = re.compile(
    r"\b(won|victory|effectively over|ceasefire|strikes?|impeach|killed|dies|hospital|peace push|peace deal|voted|no to war)\b",
    re.I,
)
_SEV_RANK = {"STANDBY": 0, "ALERT": 1, "ACTION": 2, "CRITICAL": 3}


def _claim_tokens(title: str) -> set[str]:
    return {match.group(0).lower() for match in _CLAIM_RE.finditer(title or "")}


def headline_shift(new_title: str, old_title: str) -> bool:
    """True when the lead claim changed, not when another outlet repeated it."""
    if not new_title or not old_title:
        return False
    fresh, prior = _claim_tokens(new_title), _claim_tokens(old_title)
    if not fresh and not prior:
        left, right = story_tokens(new_title), story_tokens(old_title)
        if len(left) < 2 or len(right) < 2:
            return False
        # The Kushner/Putin lead shares about a third of its tokens with the
        # Abu Dhabi talks headline, so 0.2 would still hide that update.
        return len(left & right) / min(len(left), len(right)) < 0.35
    if fresh & prior:
        return False
    return True


def story_update(new_title: str, old_title: str, new_sev: str = "", old_sev: str = "") -> bool:
    if _SEV_RANK.get((new_sev or "").upper(), 0) > _SEV_RANK.get((old_sev or "").upper(), 0):
        return True
    return headline_shift(new_title, old_title)


def cluster_rows(rows: list[dict]) -> list[dict]:
    """One lead per story. Extras become a related count and source list on that lead."""
    ordered = sorted(
        rows or [],
        key=lambda row: (
            _SEV_RANK.get((row.get("severity") or "").upper(), 0),
            row.get("published") or row.get("date") or "",
        ),
        reverse=True,
    )
    kept: list[dict] = []
    for row in ordered:
        title = row.get("title") or ""
        from deskextra import rows_same_cluster, story_family
        family = story_family(title)
        lead = next((
            other for other in kept
            if (family and family == story_family(other.get("title") or "") and family in {"g7", "wh-letter"})
            or rows_same_cluster(row, other, same_story)
        ), None)
        if lead is None:
            copy = dict(row)
            copy["related"] = int(row.get("related") or 0)
            copy["relatedSources"] = list(row.get("relatedSources") or [])
            kept.append(copy)
            continue
        lead["related"] = int(lead.get("related") or 0) + 1 + int(row.get("related") or 0)
        sources = lead.setdefault("relatedSources", [])
        for src in [row.get("source") or ""] + list(row.get("relatedSources") or []):
            if src and src != lead.get("source") and src not in sources:
                sources.append(src)
    return kept


def old_standby_return(item: dict, today: str) -> bool:
    """An old STANDBY headline is not news just because it left the board and came back."""
    if (item.get("severity") or "").upper() != "STANDBY":
        return False
    published = str(item.get("date") or item.get("published") or "")[:10]
    if len(published) < 10:
        return False
    try:
        limit = (datetime.fromisoformat(today) - timedelta(days=2)).date().isoformat()
    except ValueError:
        return False
    return published <= limit


def recent_story(item: dict, days: list, today: str, window: int = 7) -> dict | None:
    """The latest copy of this story on a snapshot from the last `window` days, before today."""
    try:
        start = (datetime.fromisoformat(today) - timedelta(days=window)).date().isoformat()
    except ValueError:
        return None
    best = None
    best_day = ""
    for snap in days or []:
        stamp = snap.get("date") or ""
        if not stamp or stamp >= today or stamp < start:
            continue
        if best_day and stamp < best_day:
            continue
        for row in snap.get("threats") or []:
            same_id = item.get("id") and item.get("id") == row.get("id")
            if same_id or same_story(item.get("title") or "", row.get("title") or ""):
                best = row
                best_day = stamp
                break
    return best


def european_named_storm(title: str, note: str = "") -> bool:
    """Storm Charles / Bruna style European windstorms, not Atlantic hurricanes."""
    blob = f"{title or ''} {note or ''}"
    if re.search(r"\bstorm\s+(charles|bruna)\b", blob, re.I):
        return True
    if re.search(r"\beuropean windstorm\b|\bextratropical storm\b", blob, re.I):
        return True
    named = re.search(r"\b(hurricane|depression|cyclone|storm)\s+(charles|bruna)\b", blob, re.I)
    place = re.search(r"\b(madeira|portugal|spain|canary|azores|europe)\b", blob, re.I)
    return bool(named and place)


def classify_desk(title: str, note: str, hinted: str) -> str:
    """Conflict kinds only when the headline itself names that conflict.

    A Google News query can return a row that never mentions the war. Those
    rows are reclassified from the title (for example a congressional story
    that arrived on the Iran query) or dropped as kind ``news``.
    """
    if european_named_storm(title, note):
        return "windstorm"
    blob = f"{title or ''} {note or ''}"
    rules = (
        ("war-iran", r"\biran\b"),
        ("war-ukraine", r"\b(ukraine|kyiv|kharkiv|odesa|oleshky|donbas)\b"),
        ("israel", r"\b(israel|israeli|eisenkot|netanyahu|knesset|gaza)\b"),
        ("climate", r"\bcop\s*31\b|\bantalya\b"),
        ("attack", r"\bkrak[oó]w\b"),
        ("diplomacy", r"\bg7\b"),
        ("usgov", r"\b(white house|congress|pentagon|hegseth|massie|impeach|supreme court|midterms?|senate|rubio)\b"),
    )
    matched = [kind for kind, pattern in rules if re.search(pattern, blob, re.I)]
    if hinted in matched:
        return hinted
    if matched:
        return matched[0]
    if hinted in {"war-iran", "war-ukraine", "conflict", "windstorm"}:
        return "news"
    if hinted in {"usgov", "israel", "climate", "diplomacy", "attack", "news"}:
        return hinted
    return "news"


def fold_desk_rows(rows: list[dict], cap: int = DESK_CAP) -> list[dict]:
    """One lead per story, then at most ``cap`` headlines per kind."""
    kept: list[dict] = []
    for row in cluster_rows(rows):
        kind = row.get("kind") or ""
        if sum(1 for other in kept if other.get("kind") == kind) >= cap:
            continue
        kept.append(row)
    return kept


def prior_item(item: dict, prev_items: list) -> dict | None:
    """The previous board row for this item, including the same story on another outlet."""
    for prev in prev_items:
        if not isinstance(prev, dict):
            continue
        if item.get("id") and item.get("id") == prev.get("id"):
            return prev
    title = item.get("title") or ""
    for prev in prev_items:
        if isinstance(prev, dict) and same_story(title, prev.get("title") or ""):
            return prev
    return None


def _try_desks(now):
    """Current Iran war, Ukraine war, and U.S. government headlines. Not a generic 'war' keyword."""
    specs = (
        ("war-iran", "Iran war", 'Iran (war OR strike OR missile OR IRGC OR ceasefire) when:14d'),
        ("war-ukraine", "Ukraine war", 'Ukraine (Russia OR missile OR ceasefire OR Kyiv OR front) when:14d'),
        ("usgov", "US government", '("White House" OR Congress OR Pentagon OR "Supreme Court" OR Rubio OR "election integrity" OR midterms) when:7d'),
        ("israel", "Israel", 'Israel (government OR coalition OR Eisenkot OR Knesset) when:7d'),
        ("climate", "Climate summit", '(COP31 OR Antalya) (climate OR summit OR COP) when:14d'),
        ("diplomacy", "G7", '(G7 OR Rubio) (Paris OR ministers) when:7d'),
        ("attack", "Attack", '(Krakow OR Kraków OR Krakow) (attack OR stabbing OR explosion) when:7d'),
        ("windstorm", "European storm", '("Storm Charles" OR "Storm Bruna" OR "Hurricane Charles" OR "European windstorm") (Madeira OR Portugal OR Spain OR Canary) when:7d'),
    )
    rows = []
    gaps = []
    for kind, source, query in specs:
        try:
            found = _headlines(query, now, retain_days=21, limit=8)
        except Exception as err:
            gaps.append(f"{source}: {err}")
            print(f"  {kind}: {err}")
            continue
        kept = 0
        for row in found:
            if str(row.get("date") or "")[:4] != str(now.year):
                continue
            if re.search(r"\b(essay|analysis|implications under)\b", row.get("title") or "", re.I):
                continue
            row = dict(row)
            assigned = classify_desk(row.get("title") or "", row.get("note") or "", kind)
            if assigned == "news":
                continue
            row["kind"] = assigned
            row["lane"] = "news"
            row["severity"] = "STANDBY" if assigned == "windstorm" else "ALERT"
            row["confidence"] = "reported"
            row["sourceCount"] = 1
            row["tags"] = list(dict.fromkeys((row.get("tags") or []) + [assigned, "standby" if assigned == "windstorm" else "alert"]))
            rows.append(row)
            kept += 1
        print(f"  {kind} {kept}")
        if kept == 0:
            gaps.append(f"{source}: 0 headlines for this check.")
    folded = fold_desk_rows(rows)
    print(f"  desks {len(rows)} headlines, {len(folded)} after story dedupe")
    return folded, gaps


def _sentry_soon(rec: dict, year: int) -> bool:
    years = [int(n) for n in re.findall(r"2\d{3}", str(rec.get("range") or ""))]
    if not years:
        return False
    return min(years) <= year + 15


def _sentry_level(rec: dict) -> str:
    """Torino, Palermo, or impact probability. A name on the list is not a risk by itself."""
    try:
        torino = float(rec.get("ts_max") or 0)
    except (TypeError, ValueError):
        torino = 0
    try:
        palermo = float(rec.get("ps_max") or -10)
    except (TypeError, ValueError):
        palermo = -10
    try:
        prob = float(rec.get("ip") or 0)
    except (TypeError, ValueError):
        prob = 0
    if torino >= 5 or prob >= 0.01:
        return "CRITICAL"
    # Cumulative odds under 1 percent, with Torino 0, are not a citizen alert.
    if torino >= 2 or prob >= 0.01 or palermo > -2:
        return "ACTION"
    if torino >= 1:
        return "ALERT"
    return ""


def _try_neos(now):
    rows = []
    gaps = []
    risky = {}
    try:
        sentry = json.loads(_get("https://ssd-api.jpl.nasa.gov/sentry.api", timeout=30))
        for rec in sentry.get("data") or []:
            if not _sentry_soon(rec, now.year):
                continue
            level = _sentry_level(rec)
            if not level:
                continue
            for key in (rec.get("des"), rec.get("fullname")):
                if key:
                    risky[str(key).upper()] = (level, rec)
    except Exception as err:
        gaps.append(f"Sentry: {err}")
        print(f"  sentry: {err}")
    start = now.strftime("%Y-%m-%d")
    end = (now + timedelta(days=60)).strftime("%Y-%m-%d")
    url = f"https://ssd-api.jpl.nasa.gov/cad.api?dist-max=0.05&date-min={start}&date-max={end}&sort=dist&limit=8"
    au_miles = 92955807.3
    ld_au = 0.002569
    try:
        payload = json.loads(_get(url, timeout=30))
        fields = payload.get("fields") or []
        for rec in payload.get("data") or []:
            row = dict(zip(fields, rec))
            name = row.get("des") or "close approach"
            try:
                dist = float(row.get("dist") or 0)
            except ValueError:
                continue
            if dist <= 0:
                continue
            ld = dist / ld_au
            if ld > 5 and name.upper() not in risky:
                continue
            miles = dist * au_miles
            when = d.parse_pubdate(row.get("cd") or "") or now
            hit = risky.get(name.upper())
            sev = hit[0] if hit else "STANDBY"
            risk = ""
            if hit:
                rec_s = hit[1]
                risk = f" Torino {rec_s.get('ts_max')}, Palermo {rec_s.get('ps_max')}, impact probability {rec_s.get('ip')}."
            note = f"Miss distance about {miles:,.0f} miles ({ld:.1f} lunar distances).{risk or ' No Torino or Palermo impact risk on this flyby.'}"
            link = "https://cneos.jpl.nasa.gov/ca/"
            rows.append(_item("neo", "threat", "NASA/JPL CNEOS", f"Close approach {name}", note, link, when, ["neo", sev.lower()], {"severity": sev, "lunar": round(ld, 2)}))
    except Exception as err:
        gaps.append(f"CNEOS close approaches: {err}")
        print(f"  cneos: {err}")
    for key, (level, rec) in list(risky.items())[:5]:
        if any(key in (row.get("title") or "").upper() for row in rows):
            continue
        if not str(key).startswith("(") and " " in str(key):
            continue
        name = rec.get("des") or key
        if any(name.upper() in (row.get("title") or "").upper() for row in rows):
            continue
        note = f"Torino {rec.get('ts_max')}, Palermo {rec.get('ps_max')}, impact probability {rec.get('ip')}."
        rows.append(_item(
            "sentry", "threat", "NASA/JPL Sentry", f"Sentry risk {name}", note,
            "https://cneos.jpl.nasa.gov/sentry/", now, ["sentry", level.lower()], {"severity": level},
        ))
        if sum(1 for row in rows if row.get("kind") == "sentry") >= 3:
            break
    return rows, gaps


def fetch_assets(now: datetime) -> dict:
    series = []
    for spec in ASSETS:
        quote = None
        if spec["kind"] == "yahoo":
            quote = _yahoo(spec["symbol"], "6mo")
            if quote is None and spec.get("fallback"):
                quote = _yahoo(spec["fallback"], "6mo")
        else:
            quote = _coin(spec["coin"])
        series.append({
            "id": spec["id"],
            "name": spec["name"],
            "level": None if not quote else quote.get("level"),
            "changePct": None if not quote else quote.get("changePct"),
            "asOf": "" if not quote else quote.get("asOf") or "",
            "points": [] if not quote else (quote.get("points") or [])[-100:],
            "source": (quote or {}).get("source") or "",
        })
    return {"series": series}


def _coin(coin: str) -> dict | None:
    url = f"https://api.coingecko.com/api/v3/coins/{coin}/market_chart?vs_currency=usd&days=90"
    try:
        payload = json.loads(_get(url, timeout=30, headers={"Accept": "application/json"}))
    except Exception as err:
        print(f"  coingecko {coin}: {err}")
        return None
    points = []
    for stamp, price in payload.get("prices") or []:
        day = datetime.fromtimestamp(int(stamp) / 1000, timezone.utc).astimezone(d.CT).strftime("%Y-%m-%d")
        points.append({"date": day, "price": round(float(price), 2)})
    # one point per day, last sample
    by_day = {}
    for point in points:
        by_day[point["date"]] = point
    points = [by_day[day] for day in sorted(by_day)]
    if len(points) < 2:
        return None
    change, pct = index_change(points[-1]["price"], points[-2]["price"])
    return {
        "level": points[-1]["price"],
        "change": change,
        "changePct": pct,
        "asOf": points[-1]["date"],
        "points": points[-120:],
        "source": f"https://www.coingecko.com/en/coins/{coin}",
    }


def fetch_science(now: datetime) -> dict:
    items = []
    failures = 0
    cutoff = (now - timedelta(days=21)).date().isoformat()
    for spec in SCIENCE:
        if "export.arxiv.org" in spec["url"]:
            time.sleep(3)
        try:
            if spec["url"] in {"biorxiv-api", "medrxiv-api"}:
                batch = _preprint_api(spec, now, cutoff)
            else:
                batch = _science_feed(spec, now, cutoff)
            items.extend(batch[:4])
            print(f"  science {spec['name']}: {len(batch[:4])}")
        except Exception as err:
            failures += 1
            print(f"  science {spec['name']}: {err}")
    if not items and failures:
        raise RuntimeError(f"all {failures} science feeds failed")
    # cap per field
    kept = []
    counts = {}
    for row in items:
        field = row.get("field") or "science"
        counts[field] = counts.get(field, 0) + 1
        if counts[field] <= 16:
            kept.append(row)
    kept.sort(key=lambda row: row.get("published") or "", reverse=True)
    return {"items": kept}


def _preprint_api(spec: dict, now: datetime, cutoff: str) -> list[dict]:
    server = "medrxiv" if spec["url"].startswith("med") else "biorxiv"
    start = (now - timedelta(days=5)).strftime("%Y-%m-%d")
    end = now.strftime("%Y-%m-%d")
    payload = json.loads(_get(f"https://api.biorxiv.org/details/{server}/{start}/{end}/0", timeout=40))
    rows = []
    for rec in payload.get("collection") or []:
        title = re.sub(r"\s+", " ", rec.get("title") or "").strip()
        doi = rec.get("doi") or ""
        link = d.http_url(f"https://www.{server}.org/content/{doi}") if doi else ""
        if not title or not link:
            continue
        published = d.parse_pubdate(rec.get("date") or "") or now
        if published.strftime("%Y-%m-%d") < cutoff:
            continue
        rows.append(_item(
            "paper", "science", spec["name"], title, rec.get("abstract") or "", link, published,
            ["science", spec["field"], "preprint"],
            {"field": spec["field"], "review": "PREPRINT", "severity": ""},
        ))
        if len(rows) >= 4:
            break
    return rows


def _science_feed(spec: dict, now: datetime, cutoff: str) -> list[dict]:
    raw = _get(spec["url"], timeout=40)
    root = ET.fromstring(raw)
    rss1 = "{http://purl.org/rss/1.0/}"
    nodes = root.findall(f"{ATOM}entry") or root.findall("entry")
    if not nodes:
        channel = root.find("channel")
        if channel is None:
            channel = root.find(f"{rss1}channel")
        if channel is not None:
            nodes = channel.findall("item") or channel.findall(f"{rss1}item")
    if not nodes:
        nodes = root.findall(f"{rss1}item")
    rows = []
    for node in nodes[:6]:
        rss1 = "{http://purl.org/rss/1.0/}"
        title = re.sub(r"\s+", " ", (
            node.findtext(f"{ATOM}title") or node.findtext("title") or node.findtext(f"{rss1}title") or ""
        )).strip()
        link = ""
        rss1 = "{http://purl.org/rss/1.0/}"
        for child in list(node):
            if child.tag in {f"{ATOM}link", "link", f"{rss1}link"}:
                link = d.http_url(child.attrib.get("href") or child.text or "")
                if link:
                    break
        if not title or not link:
            continue
        published = d.parse_pubdate(
            node.findtext(f"{ATOM}published") or node.findtext(f"{ATOM}updated") or node.findtext("pubDate") or ""
        ) or now
        if published.strftime("%Y-%m-%d") < cutoff:
            continue
        summary = node.findtext(f"{ATOM}summary") or node.findtext("description") or ""
        review = spec["review"]
        if "arxiv.org" in link or "biorxiv" in link or "medrxiv" in link:
            review = "PREPRINT"
        elif re.search(r"nature\.com/(?:.+/)?articles/|science\.org/doi/", link):
            review = "PEER-REVIEWED"
        rows.append(_item(
            "paper", "science", spec["name"], title, d.clean_note(summary), link, published,
            ["science", spec["field"], review.lower()],
            {"field": spec["field"], "review": review, "severity": ""},
        ))
        if len(rows) >= 4:
            break
    return rows


def extra_sources(markets: dict, threats: dict, science: dict, gaps: list | None = None) -> list[dict]:
    """World-desk rows for the boards, not only the podcast and X list."""
    rows = []

    def add(source_id, name, short, lane, url, items):
        latest = None
        for item in items:
            if latest is None or (item.get("published") or "") > (latest.get("published") or ""):
                latest = item
        rows.append({
            "id": source_id,
            "name": name,
            "short": short,
            "lane": lane,
            "url": url,
            "subtitle": lane,
            "lastLabel": (latest or {}).get("label") or "",
            "lastDate": (latest or {}).get("date") or "",
            "count": len(items),
            "offline": False,
        })

    for region in (markets or {}).get("regions") or []:
        venue = (region.get("venues") or [{}])[0]
        add(
            "mkt-" + region["id"], region["name"] + " markets", region["name"][:8].upper(),
            "economy", venue.get("source") or "https://finance.yahoo.com/", region.get("headlines") or [],
        )
    kind_home = {
        "quake": ("USGS earthquakes", "USGS", "https://earthquake.usgs.gov/earthquakes/map/"),
        "storm": ("NHC storms", "NHC", "https://www.nhc.noaa.gov/"),
        "nws": ("NWS alerts", "NWS", "https://www.weather.gov/"),
        "gdacs": ("GDACS", "GDACS", "https://www.gdacs.org/"),
        "relief": ("ReliefWeb", "RELIEF", "https://reliefweb.int/disasters"),
        "who": ("WHO outbreaks", "WHO", "https://www.who.int/emergencies/disease-outbreak-news"),
        "cdc": ("CDC HAN", "CDC", "https://www.cdc.gov/han/php/notices/index.html"),
        "conflict": ("Conflict wires", "WAR", "https://news.google.com/"),
        "neo": ("JPL close approaches", "CNEOS", "https://cneos.jpl.nasa.gov/ca/"),
        "sentry": ("JPL Sentry", "SENTRY", "https://cneos.jpl.nasa.gov/sentry/"),
        "clock": ("Doomsday Clock", "CLOCK", "https://thebulletin.org/doomsday-clock/"),
    }
    by_kind = {}
    for item in (threats or {}).get("items") or []:
        by_kind.setdefault(item.get("kind"), []).append(item)
    down = " ".join(gaps or []).lower()
    for kind, (name, short, url) in kind_home.items():
        add("threat-" + kind, name, short, "threat", url, by_kind.get(kind) or [])
        if kind in {"gdacs", "relief", "who", "cdc", "sentry"} and kind in down or name.split()[0].lower() in down:
            rows[-1]["offline"] = True
            rows[-1]["subtitle"] = "source down"
    by_field = {}
    for item in (science or {}).get("items") or []:
        by_field.setdefault(item.get("field") or "science", []).append(item)
    field_url = {
        "physics": "https://phys.org/physics-news/",
        "propulsion": "https://www.nasa.gov/news/",
        "biomedical": "https://www.nature.com/",
        "quantum": "https://arxiv.org/list/quant-ph/recent",
        "technology": "https://www.technologyreview.com/",
        "ai": "https://blog.google/technology/ai/",
    }
    for field, items in by_field.items():
        add("lab-" + field, field + " lab", field[:8].upper(), "science", field_url.get(field, "https://arxiv.org/"), items)
    return rows


def refresh_file(path, producer, errors, label):
    previous = None
    if path.exists():
        try:
            previous = json.loads(path.read_text())
        except json.JSONDecodeError:
            previous = None
    try:
        fresh = producer()
    except Exception as err:
        errors.append(f"{label}: {err}")
        print(f"  {label} FAILED: {err}; keeping cache")
        return previous if previous is not None else producer_empty(label)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(fresh, ensure_ascii=False, indent=2) + "\n")
    return fresh


def producer_empty(label):
    if label == "markets":
        return {"holidayNote": "", "regions": []}
    if label == "assets":
        return {"series": []}
    return {"items": []}
