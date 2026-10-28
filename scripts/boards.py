#!/usr/bin/env python3
"""Economic watch, threat board, asset strip, and frontier lab.

Every fetch fails soft: the caller keeps the previous JSON. Numbers are written
only when a response actually contains them. No prices are invented.
"""
from __future__ import annotations

import json
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
        "query": "United States economy Federal Reserve when:2d",
        "venues": [{
            "name": "NYSE / Nasdaq", "indexName": "S&P 500", "symbol": "^GSPC",
            "timezone": "America/New_York", "sessions": [{"open": "09:30", "close": "16:00"}],
            "holidays": NYSE_HOLIDAYS_2026,
        }],
    },
    {
        "id": "north-america",
        "name": "North America",
        "query": "Canada OR Mexico economy central bank when:2d",
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
        "query": "Brazil economy B3 markets when:2d",
        "venues": [{
            "name": "B3", "indexName": "Ibovespa", "symbol": "^BVSP", "timezone": "America/Sao_Paulo",
            "sessions": [{"open": "10:00", "close": "17:00"}], "holidays": [],
        }],
    },
    {
        "id": "russia",
        "name": "Russia",
        "query": "Russia economy MOEX when:2d",
        "venues": [{
            "name": "MOEX", "indexName": "IMOEX", "symbol": "IMOEX.ME", "timezone": "Europe/Moscow",
            "sessions": [{"open": "10:00", "close": "18:50"}], "holidays": [],
        }],
    },
    {
        "id": "china",
        "name": "China",
        "query": "China economy Shanghai markets when:2d",
        "venues": [{
            "name": "Shanghai", "indexName": "SSE Composite", "symbol": "000001.SS", "timezone": "Asia/Shanghai",
            "sessions": [{"open": "09:30", "close": "11:30"}, {"open": "13:00", "close": "15:00"}], "holidays": [],
        }],
    },
    {
        "id": "europe",
        "name": "Europe",
        "query": "Europe ECB economy markets when:2d",
        "venues": [{
            "name": "Xetra", "indexName": "EURO STOXX 50", "symbol": "^STOXX50E", "timezone": "Europe/Berlin",
            "sessions": [{"open": "09:00", "close": "17:30"}], "holidays": [],
        }],
    },
    {
        "id": "asia",
        "name": "Asia",
        "query": "Japan OR Hong Kong OR India economy markets when:2d",
        "venues": [
            {"name": "Tokyo", "indexName": "Nikkei 225", "symbol": "^N225", "timezone": "Asia/Tokyo",
             "sessions": [{"open": "09:00", "close": "11:30"}, {"open": "12:30", "close": "15:00"}], "holidays": []},
            {"name": "Hong Kong", "indexName": "Hang Seng", "symbol": "^HSI", "timezone": "Asia/Hong_Kong",
             "sessions": [{"open": "09:30", "close": "12:00"}, {"open": "13:00", "close": "16:00"}], "holidays": []},
            {"name": "India", "indexName": "BSE Sensex", "symbol": "^BSESN", "timezone": "Asia/Kolkata",
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


def quake_severity(mag) -> str:
    try:
        mag = float(mag)
    except (TypeError, ValueError):
        return "WATCH"
    if mag >= 7:
        return "CRITICAL"
    if mag >= 6:
        return "WARNING"
    return "WATCH"


def alert_severity(event: str, severity: str) -> str:
    name = (event or "").lower()
    if "tornado warning" in name or "hurricane warning" in name or "extreme" in (severity or "").lower():
        return "CRITICAL"
    if "warning" in name or (severity or "").lower() in {"severe", "extreme"}:
        return "WARNING"
    return "WATCH"


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


def _yahoo(symbol: str, range_: str = "1mo") -> dict | None:
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
    closes = (((result.get("indicators") or {}).get("quote") or [{}])[0]).get("close") or []
    stamps = result.get("timestamp") or []
    points = []
    for stamp, close in zip(stamps, closes):
        if close is None:
            continue
        day = datetime.fromtimestamp(int(stamp), timezone.utc).astimezone(d.CT).strftime("%Y-%m-%d")
        points.append({"date": day, "price": round(float(close), 4)})
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
        as_of = datetime.fromtimestamp(int(meta["regularMarketTime"]), timezone.utc).astimezone(d.CT).strftime("%Y-%m-%d")
    if price is None and not points:
        return None
    return {
        "level": None if price is None else round(float(price), 2),
        "change": change,
        "changePct": pct,
        "asOf": as_of,
        "points": points[-30:],
        "source": f"https://finance.yahoo.com/quote/{quoted}",
    }


def _headlines(query: str, now: datetime, limit: int = 4) -> list[dict]:
    url = "https://news.google.com/rss/search?q=" + urllib.parse.quote(query) + "&hl=en-US&gl=US&ceid=US:en"
    raw = _get(url, timeout=25)
    root = ET.fromstring(raw)
    channel = root.find("channel")
    if channel is None:
        return []
    rows = []
    cutoff = (now.date() - timedelta(days=7)).isoformat()
    for node in channel.findall("item")[:12]:
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
        rows.append(_item("headline", "news", source, title, "", link, published, ["headline"]))
        if len(rows) >= limit:
            break
    return rows


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


def fetch_markets(now: datetime) -> dict:
    regions = []
    for spec in REGIONS:
        venues = []
        for venue in spec["venues"]:
            quote = _yahoo(venue["symbol"], "5d") or {}
            venues.append({
                "name": venue["name"],
                "indexName": venue["indexName"],
                "symbol": venue["symbol"],
                "timezone": venue["timezone"],
                "sessions": venue["sessions"],
                "holidays": venue["holidays"],
                "level": quote.get("level"),
                "change": quote.get("change"),
                "changePct": quote.get("changePct"),
                "asOf": quote.get("asOf") or "",
                "source": quote.get("source") or f"https://finance.yahoo.com/quote/{urllib.parse.quote(venue['symbol'], safe='')}",
            })
        headlines = []
        try:
            headlines = _headlines(spec["query"], now, 4)
        except Exception as err:
            print(f"  headlines {spec['id']}: {err}")
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
            sev = quake_severity(mag)
            quakes.append(_item(
                "quake", "threat", "USGS",
                f"M{float(mag):.1f} {props.get('place') or 'earthquake'}",
                "USGS earthquake, magnitude 4.5 or greater, past 7 days.",
                url, when, ["quake", sev.lower()],
                {"severity": sev, "lat": coords[1], "lon": coords[0], "mag": float(mag)},
            ))
        quakes.sort(key=lambda row: row.get("mag") or 0, reverse=True)
        items.extend(quakes[:30])
        print(f"  quakes {len(quakes[:30])}")
    except Exception as err:
        print(f"  usgs FAILED: {err}")
    extras = []
    extras.extend(_try_nhc(now))
    extras.extend(_try_nws(now))
    extras.extend(_try_gdacs(now))
    extras.extend(_try_relief(now))
    extras.extend(_try_who(now))
    extras.extend(_try_cdc(now))
    extras.extend(_try_conflict(now))
    extras.extend(_try_neos(now))
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
        "tags": ["clock", "watch"],
        "severity": "WATCH",
    })
    return {"items": items + extras}


def _try_nhc(now):
    rows = []
    for url in ("https://www.nhc.noaa.gov/index-at.xml", "https://www.nhc.noaa.gov/index-ep.xml", "https://www.nhc.noaa.gov/gtwo.xml"):
        try:
            for node in _rss_items(url, 6):
                title = re.sub(r"\s+", " ", (node.findtext("title") or "")).strip()
                link = d.http_url(node.findtext("link") or url)
                if not title or not link:
                    continue
                published = d.parse_pubdate(node.findtext("pubDate") or "") or now
                note = d.clean_note(node.findtext("description") or "")
                extra = {"severity": "WARNING"}
                point = _point_from(node)
                if point:
                    extra["lat"], extra["lon"] = point
                else:
                    match = re.search(r"(\d+(?:\.\d+)?)\s*N[\s,]+(\d+(?:\.\d+)?)\s*W", note, re.I)
                    if match:
                        extra["lat"] = float(match.group(1))
                        extra["lon"] = -float(match.group(2))
                if "hurricane warning" in title.lower():
                    extra["severity"] = "CRITICAL"
                rows.append(_item("storm", "threat", "NHC", title, note, link, published, ["storm", extra["severity"].lower()], extra))
        except Exception as err:
            print(f"  nhc {url}: {err}")
    return rows[:10]


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
            rows.append(_item("nws", "threat", "NWS", event, area, link, when, ["nws", sev.lower(), "tennessee"], {"severity": sev}))
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
    return rows


def _try_gdacs(now):
    rows = []
    try:
        for node in _rss_items("https://www.gdacs.org/xml/rss.xml", 12):
            title = re.sub(r"\s+", " ", (node.findtext("title") or "")).strip()
            link = d.http_url(node.findtext("link") or "https://www.gdacs.org/")
            if not title or not link:
                continue
            published = d.parse_pubdate(node.findtext("pubDate") or "") or now
            alert = (node.findtext("{http://www.gdacs.org}alertlevel") or node.findtext("gdacs:alertlevel") or "").lower()
            sev = "CRITICAL" if "red" in alert else "WARNING" if "orange" in alert else "WATCH"
            extra = {"severity": sev}
            point = _point_from(node)
            if point:
                extra["lat"], extra["lon"] = point
            rows.append(_item("gdacs", "threat", "GDACS", title, d.clean_note(node.findtext("description") or ""), link, published, ["gdacs", sev.lower()], extra))
    except Exception as err:
        print(f"  gdacs: {err}")
    return rows


def _try_relief(now):
    rows = []
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
            rows.append(_item("relief", "threat", "ReliefWeb", title, f"{kind}. {country}".strip(), link, published, ["relief", "watch"], {"severity": "WATCH"}))
    except Exception as err:
        print(f"  reliefweb: {err}")
    if not rows:
        rows.append(_item(
            "relief", "threat", "ReliefWeb", "ReliefWeb disasters",
            "The disasters feed did not answer this run. The link opens the public list.",
            "https://reliefweb.int/disasters", now, ["relief", "watch"], {"severity": "WATCH"},
        ))
    return rows


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
            rows.append(_item("who", "threat", "WHO", title, d.clean_note(node.findtext("description") or ""), link, published, ["who", "watch"], {"severity": "WATCH"}))
        if rows:
            break
    return rows[:6]


def _try_cdc(now):
    rows = []
    try:
        for row in _headlines("CDC Health Alert Network", now, 3):
            row = dict(row)
            row["kind"] = "cdc"
            row["source"] = "CDC HAN"
            row["severity"] = "WARNING" if re.search(r"alert|advisory|warning", row.get("title") or "", re.I) else "WATCH"
            row["tags"] = list(dict.fromkeys((row.get("tags") or []) + ["cdc", row["severity"].lower()]))
            rows.append(row)
    except Exception as err:
        print(f"  cdc headlines: {err}")
    rows.append(_item(
        "cdc", "threat", "CDC HAN", "CDC Health Alert Network notices",
        "Official HAN index. A dedicated CDC RSS feed did not answer this run.",
        "https://www.cdc.gov/han/php/notices/index.html", now, ["cdc", "watch"], {"severity": "WATCH"},
    ))
    return rows[:5]


def _try_conflict(now):
    try:
        rows = []
        for row in _headlines("armed conflict war", now, 6):
            row = dict(row)
            row["kind"] = "conflict"
            row["lane"] = "threat"
            row["severity"] = "WATCH"
            row["tags"] = list(dict.fromkeys((row.get("tags") or []) + ["conflict", "watch"]))
            rows.append(row)
        return rows
    except Exception as err:
        print(f"  conflict: {err}")
        return []


def _try_neos(now):
    rows = []
    start = now.strftime("%Y-%m-%d")
    end = (now + timedelta(days=60)).strftime("%Y-%m-%d")
    url = f"https://ssd-api.jpl.nasa.gov/cad.api?dist-max=0.05&date-min={start}&date-max={end}&sort=dist&limit=6"
    try:
        payload = json.loads(_get(url, timeout=30))
        fields = payload.get("fields") or []
        for rec in payload.get("data") or []:
            row = dict(zip(fields, rec))
            name = row.get("des") or row.get("fullname") or "close approach"
            dist = row.get("dist") or ""
            when = d.parse_pubdate(row.get("cd") or "") or now
            link = "https://cneos.jpl.nasa.gov/ca/"
            note = f"NASA/JPL close-approach distance {dist} AU." if dist else "NASA/JPL close approach."
            try:
                sev = "CRITICAL" if float(dist) < 0.01 else "WARNING" if float(dist) < 0.02 else "WATCH"
            except ValueError:
                sev = "WATCH"
            rows.append(_item("neo", "threat", "NASA/JPL CNEOS", f"Close approach {name}", note, link, when, ["neo", sev.lower()], {"severity": sev}))
    except Exception as err:
        print(f"  cneos: {err}")
    try:
        sentry = json.loads(_get("https://ssd-api.jpl.nasa.gov/sentry.api", timeout=30))
        data = sentry.get("data") or []
        for rec in data[:3]:
            name = rec.get("des") or rec.get("fullname") or "sentry object"
            link = "https://cneos.jpl.nasa.gov/sentry/"
            rows.append(_item("sentry", "threat", "NASA/JPL Sentry", f"Sentry object {name}", "Impact-monitoring list. See the JPL page for the risk table.", link, now, ["sentry", "watch"], {"severity": "WATCH"}))
    except Exception as err:
        print(f"  sentry: {err}")
    return rows


def fetch_assets(now: datetime) -> dict:
    series = []
    for spec in ASSETS:
        quote = None
        if spec["kind"] == "yahoo":
            quote = _yahoo(spec["symbol"], "1mo")
            if quote is None and spec.get("fallback"):
                quote = _yahoo(spec["fallback"], "1mo")
        else:
            quote = _coin(spec["coin"])
        series.append({
            "id": spec["id"],
            "name": spec["name"],
            "level": None if not quote else quote.get("level"),
            "changePct": None if not quote else quote.get("changePct"),
            "asOf": "" if not quote else quote.get("asOf") or "",
            "points": [] if not quote else (quote.get("points") or [])[-30:],
            "source": (quote or {}).get("source") or "",
        })
    return {"series": series}


def _coin(coin: str) -> dict | None:
    url = f"https://api.coingecko.com/api/v3/coins/{coin}/market_chart?vs_currency=usd&days=30"
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
        "points": points[-30:],
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
