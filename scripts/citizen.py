"""Prepared-citizen layer: trends filter, local notices, triggers, history, and impact math.

Free public sources only. Missing feeds become an explicit n/a row. This module
never calls X; the fetcher does that and only on public trends or recent search.
"""
from __future__ import annotations

import json
import math
import re
import urllib.parse
from datetime import datetime, timedelta

import desklib as d

THEMES = (
    ("war", re.compile(r"\b(war|invasion|missile|airstrike|troops|ceasefire|gaza|ukraine|nato|hezbollah)\b", re.I)),
    ("outbreak", re.compile(r"\b(outbreak|virus|pandemic|measles|bird flu|h5n1|covid|ebola|mpox|influenza)\b", re.I)),
    ("disaster", re.compile(r"\b(disaster|wildfire|eruption|tsunami|landslide|famine)\b", re.I)),
    ("hurricane", re.compile(r"\b(hurricane|tropical storm|typhoon|cyclone)\b", re.I)),
    ("flood", re.compile(r"\b(flood|flooding)\b", re.I)),
    ("tornado", re.compile(r"\b(tornado|twister)\b", re.I)),
    ("earthquake", re.compile(r"\b(earthquake|quake|seismic|aftershock)\b", re.I)),
    ("existential", re.compile(r"\b(nuclear|doomsday|asteroid|extinction|existential)\b", re.I)),
    ("economic", re.compile(r"\b(inflation|recession|default|bank run|dollar|gold|silver|bitcoin|supply chain|shortage|blackout|grid|preparedness|stockpile|tariff)\b", re.I)),
)

SEARCH_QUERIES = (
    ("war", "war OR invasion OR missile OR ceasefire"),
    ("outbreak", "outbreak OR pandemic OR \"bird flu\" OR measles"),
    ("hurricane", "hurricane OR \"tropical storm\" OR typhoon"),
    ("flood", "flood OR flooding"),
    ("tornado", "tornado"),
    ("earthquake", "earthquake OR seismic"),
    ("existential", "nuclear OR asteroid OR doomsday"),
    ("economic", "inflation OR preparedness OR blackout OR stockpile OR tariff"),
)

RANKS = {"STANDBY": 0, "ALERT": 1, "ACTION": 2, "CRITICAL": 3}
OFFICIAL_KINDS = {"quake", "storm", "nws", "gdacs", "who", "cdc", "neo", "sentry", "relief"}
CHECKLIST = ["fuel", "water", "cash", "meds"]
HISTORY_DAYS = 21

# Thompson's Station, Williamson County, zip 37179.
LOCAL_POINT = (35.802, -86.907)
POWER_QUERY = (
    "https://services1.arcgis.com/utFj6xjAHT9GdIit/arcgis/rest/services/Power_TN/FeatureServer/0/query"
    "?where=County%3D%27Williamson%27&outFields=County,CustomersAffected,CustomersServed,Utility,Timestamp&returnGeometry=false&f=json"
)
ROAD_QUERY = (
    "https://spatial.tdot.tn.gov/arcgis/rest/services/Smartway/Smartway_Events/FeatureServer/0/query"
    "?where=UPPER(DESCRIPTION)%20LIKE%20%27%25WILLIAMSON%25%27&outFields=DESCRIPTION,EVENT_SUBTYPE,CD_ROAD_NAMES,REVISED_DATE&returnGeometry=false&resultRecordCount=40&orderByFields=REVISED_DATE%20DESC&f=json"
)
# news.html is a nav shell and returns 403 to the Actions curl client.
# The news-releases index lists dated /tema/news/YYYY/M/D/ articles and answers 200.
TEMA_PAGE = "https://www.tn.gov/tema/news-info/news-releases.html"
NWS_POINT = "https://api.weather.gov/alerts/active?point=35.802,-86.907"


_BLOCK_TOPIC = re.compile(
    r"\b(secretary of war|department of war|art of war|rules of war|state of war|war room)\b",
    re.I,
)


def topic_of(text: str) -> str:
    """A real topic, not a substring inside a title or a job name."""
    blob = text or ""
    if _BLOCK_TOPIC.search(blob):
        return ""
    if re.search(r"\biran\b", blob, re.I) and re.search(r"\b(war|strike|missile|irgc|ceasefire|attack)\b", blob, re.I):
        return "iran-war"
    if re.search(r"\b(ukraine|kyiv)\b", blob, re.I):
        return "ukraine-war"
    if re.search(r"\b(white house|congress|pentagon|supreme court|senate)\b", blob, re.I):
        return "us-gov"
    if re.search(r"\b(eisenkot|knesset)\b", blob, re.I) or (
        re.search(r"\bisrael\b", blob, re.I) and re.search(r"\b(government|coalition|minister)\b", blob, re.I)
    ):
        return "israel"
    if re.search(r"\b(cop31|antalya)\b", blob, re.I) or re.search(r"climate summit", blob, re.I):
        return "climate"
    if re.search(r"\bg7\b", blob, re.I) or (re.search(r"\brubio\b", blob, re.I) and re.search(r"\bparis\b", blob, re.I)):
        return "g7"
    if re.search(r"\b(midterms?|election integrity)\b", blob, re.I):
        return "election"
    if re.search(r"\b(krakow|kraków)\b", blob, re.I):
        return "attack"
    if re.search(r"\b(hurricane|tropical storm|typhoon)\b", blob, re.I):
        return "hurricane"
    if re.search(r"\b(flood|flooding)\b", blob, re.I):
        return "flood"
    if re.search(r"\btornado(es)?\b", blob, re.I):
        return "tornado"
    if re.search(r"\b(earthquake|seismic)\b", blob, re.I):
        return "earthquake"
    if re.search(r"\b(outbreak|bird flu|h5n1|measles|ebola|mpox)\b", blob, re.I):
        return "outbreak"
    if re.search(r"\b(inflation|recession|stockpile|blackout|preparedness)\b", blob, re.I):
        return "economic"
    if re.search(r"\b(gold|silver)\b", blob, re.I) and re.search(r"\b(inflation|price|surge|selloff|rally)\b", blob, re.I):
        return "economic"
    return ""


def match_theme(text: str) -> str:
    found = topic_of(text)
    if found in {"iran-war", "ukraine-war"}:
        return "war"
    if found == "us-gov":
        return "economic"
    return found


def _all_clear(title: str, note: str = "") -> bool:
    blob = f"{title} {note}".lower()
    return bool(re.search(r"there are no tropical cyclones|no tropical cyclones at this time|tropical weather outlook", blob) and not re.search(r"\b(hurricane|tropical storm)\s+[a-z]", blob))


def confidence_for(item: dict, extra_domains: int = 0) -> dict:
    """confirmed needs two independent non-X sources. X alone stays a rumor."""
    lane = (item.get("lane") or "").lower()
    kind = (item.get("kind") or "").lower()
    x_only = lane == "x" or kind in {"x", "trend"}
    domains = 1 + max(0, int(extra_domains))
    if x_only and extra_domains <= 0:
        level = "rumor"
        domains = 1
    elif x_only and extra_domains >= 2:
        level = "reported"
    elif not x_only and domains >= 2:
        level = "confirmed"
    elif kind in OFFICIAL_KINDS or lane in {"official", "local"}:
        level = "reported"
        domains = max(domains, 1)
    else:
        level = "reported" if domains >= 1 else "rumor"
    if x_only and level == "confirmed":
        level = "reported"
    return {"confidence": level, "sourceCount": domains}


def _conflict_named(kind: str, title: str, note: str) -> bool:
    """Travel advice only when the title or snippet names that conflict."""
    blob = f"{title or ''} {note or ''}"
    if kind == "war-iran":
        return re.search(r"\biran\b", blob, re.I) is not None
    if kind == "war-ukraine":
        return re.search(r"\b(ukraine|kyiv|kharkiv|odesa|oleshky|donbas)\b", blob, re.I) is not None
    if kind == "conflict":
        return re.search(r"\b(iran|ukraine|kyiv|gaza)\b", blob, re.I) is not None
    return False


def tema_notices(html: str, now: datetime) -> list[dict]:
    """Dated TEMA releases from the news-releases index. Relative links are made absolute."""
    rows = []
    seen = set()
    cutoff = (now - timedelta(days=21)).date().isoformat()
    for href, text in re.findall(r'href="([^"]+)"[^>]*>\s*([^<]{8,180})', html or ""):
        title = re.sub(r"\s+", " ", text).strip()
        if title.lower() in {"read full story", "news", "news releases"}:
            continue
        stamp = re.search(r"/tema/news/(\d{4})/(\d{1,2})/(\d{1,2})/", href)
        if not stamp:
            continue
        date = f"{int(stamp.group(1)):04d}-{int(stamp.group(2)):02d}-{int(stamp.group(3)):02d}"
        if date < cutoff or title.lower() in seen:
            continue
        seen.add(title.lower())
        url = href if href.startswith("http") else "https://www.tn.gov" + href
        hot = re.search(r"\b(flood\w*|warning|evacuation|emergency|wildfire|tornado)\b", title, re.I)
        rows.append({
            "id": d.make_id("local-tema", url),
            "title": title,
            "note": "TEMA news release.",
            "url": url,
            "source": "TEMA",
            "kind": "tema",
            "lane": "local",
            "severity": "ALERT" if hot else "STANDBY",
            "date": date,
            "label": date,
            "published": f"{date}T12:00:00-06:00",
            "tags": ["tennessee", "williamson"],
        })
        if len(rows) >= 4:
            break
    return rows


def so_what(item: dict) -> str:
    """A line only when this item calls for something specific. Otherwise nothing to do."""
    sev = (item.get("severity") or "STANDBY").upper()
    kind = (item.get("kind") or item.get("category") or item.get("lane") or "").lower()
    title = item.get("title") or ""
    note = item.get("note") or ""
    if kind in {"episode", "podcast", "x", "substack", "page", "headline"} or (item.get("lane") or "") in {"podcast", "x", "substack"}:
        return ""
    if kind in {"neo", "sentry"} or "close approach" in title.lower():
        return "no action needed"
    if _all_clear(title, note):
        return "no action needed"
    if kind in {"quake", "earthquake"} and not item.get("usImpact"):
        return "no action needed"
    if kind == "nws" and sev in {"ACTION", "CRITICAL"}:
        where = note.split(".")[0][:80] if note else "the warned area"
        return f"{title} covers {where}. What to do: stay off those roads."
    if kind in {"storm", "hurricane"} and sev in {"ACTION", "CRITICAL"}:
        return f"{title}. What to do: follow that warning if you are in the named area."
    if kind in {"war-iran", "war-ukraine", "conflict"} and _conflict_named(kind, title, note):
        return "What to do: no action at home. Skip travel into the named fighting if a trip was planned."
    if kind in {"war-iran", "war-ukraine", "conflict"}:
        return ""
    if kind == "usgov":
        return ""
    if kind in {"market", "price"} or item.get("tape"):
        return "The stock tape moved hard. What to do: no action unless you need cash this week. Not a trade instruction."
    if kind == "trigger" and sev in {"ACTION", "CRITICAL"}:
        return "What to do: fuel, water, cash, and meds, because this threshold is a local hazard."
    if sev in {"STANDBY", "ALERT"}:
        return "no action needed" if sev == "ALERT" else ""
    return "no action needed"


def _action(kind: str, sev: str) -> str:
    if sev == "CRITICAL" and kind in {"storm", "hurricane", "nws", "tornado"}:
        return "Fuel, water, cash, and meds tonight. Stay off the warned roads."
    if sev == "CRITICAL":
        return "Treat this as urgent. Confirm it on the linked official source, then handle water, cash, and a way out."
    if sev == "ACTION":
        return "Top off fuel and water. Recheck this item on the next refresh."
    if sev == "ALERT":
        return "Read the source. No kit change unless you are in the named area."
    return "no action needed"


def _rank(severity: str) -> int:
    return RANKS.get((severity or "STANDBY").upper(), 0)


def _arrow(now_rank: int, then_rank: int | None) -> str:
    if then_rank is None:
        return "→"
    if now_rank > then_rank:
        return "↑"
    if now_rank < then_rank:
        return "↓"
    return "→"


def _snapshot_on_or_before(days: list[dict], day: str) -> dict | None:
    chosen = None
    for snap in days or []:
        stamp = snap.get("date") or ""
        if stamp and stamp <= day and (chosen is None or stamp > chosen.get("date", "")):
            chosen = snap
    return chosen


def apply_outlook(items: list[dict], history: dict, today: str) -> None:
    days = (history or {}).get("days") or []
    yday = (datetime.fromisoformat(today) - timedelta(days=1)).date().isoformat()
    week = (datetime.fromisoformat(today) - timedelta(days=7)).date().isoformat()
    prev_day = _snapshot_on_or_before(days, yday)
    prev_week = _snapshot_on_or_before(days, week)

    def lookup(snap, item_id):
        if not snap:
            return None
        for row in snap.get("threats") or []:
            if row.get("id") == item_id:
                return _rank(row.get("severity") or "")
        return None

    for item in items:
        day_rank = lookup(prev_day, item.get("id"))
        week_rank = lookup(prev_week, item.get("id"))
        now_rank = _rank(item.get("severity") or "")
        item["arrowDay"] = _arrow(now_rank, day_rank)
        item["arrowWeek"] = _arrow(now_rank, week_rank)
        if day_rank is None and week_rank is None:
            item["outlook"] = "First reading. Watch the next 72 hours."
        elif day_rank is not None and now_rank > day_rank:
            item["outlook"] = "Higher than yesterday. Treat the next 72 hours as rising."
        elif week_rank is not None and now_rank > week_rank:
            item["outlook"] = "Higher than last week. The 72-hour path is still up."
        elif day_rank is not None and now_rank < day_rank:
            item["outlook"] = "Lower than yesterday. The 72-hour path is easing if it holds."
        else:
            item["outlook"] = "Steady versus yesterday. No 72-hour escalation in the stored record."
        item["soWhat"] = so_what(item)
        item["action"] = "no action needed" if item["soWhat"] in {"", "no action needed"} else item["soWhat"]
        conf = confidence_for(item, extra_domains=int(item.get("extraDomains") or 0))
        item.update(conf)


def _gulf_bound(blob: str) -> bool:
    """A tropical cyclone aimed at the Gulf, not the standing NHC basin header."""
    if not re.search(r"hurricane|tropical storm|tropical depression", blob or "", re.I):
        return False
    cleaned = re.sub(r"For the North Atlantic.*?Gulf of America:", " ", blob or "", flags=re.I | re.S)
    return bool(re.search(r"gulf", cleaned, re.I))


def raise_to(item: dict, level: str, trigger_id: str) -> None:
    if _rank(item.get("severity") or "") < _rank(level):
        item["severity"] = level
        item["raisedBy"] = trigger_id


def evaluate_triggers(threats: list[dict], assets: dict, trends: dict) -> dict:
    fired = []

    def add(trigger_id, title, level, why, url):
        fired.append({
            "id": trigger_id,
            "title": title,
            "severity": level,
            "why": why,
            "url": url or "",
            "checklist": CHECKLIST,
            "kind": "trigger",
            "lane": "desk",
            "source": "Desk threshold",
            "confidence": "reported",
            "sourceCount": 1,
        })

    for item in threats or []:
        blob = f"{item.get('title') or ''} {item.get('note') or ''}"
        url = item.get("url") or ""
        kind = item.get("kind") or ""
        if kind == "storm" and _gulf_bound(blob):
            raise_to(item, "ACTION", "gulf-storm")
            add("gulf-storm", "Named or tropical system toward the Gulf", "ACTION", blob[:180], url)
        if kind in {"who", "cdc"} and re.search(r"\b(united states|u\.s\.|usa)\b", blob, re.I):
            raise_to(item, "ALERT", "outbreak-us")
            add("outbreak-us", "Outbreak notice names the United States", "ALERT", blob[:180], url)
        if kind == "quake":
            mag = item.get("magnitude")
            if mag is None:
                found = re.search(r"M\s*([0-9]+(?:\.[0-9]+)?)", blob)
                mag = float(found.group(1)) if found else None
            if mag is not None and float(mag) >= 7:
                raise_to(item, "CRITICAL", "quake-m7")
                add("quake-m7", f"Earthquake M{mag} meets the M7 threshold", "CRITICAL", blob[:180], url)
        if kind == "nws" and "tennessee" in (item.get("tags") or []) and re.search(r"tornado|hurricane", blob, re.I) and re.search(r"warning", blob, re.I):
            raise_to(item, "CRITICAL", "tn-warning")
            add("tn-warning", "Tornado or hurricane warning for Tennessee", "CRITICAL", blob[:180], url)

    for series in (assets or {}).get("series") or []:
        pct = series.get("changePct")
        if pct is None:
            continue
        name = (series.get("name") or "").lower()
        if "gold" in name and float(pct) >= 3:
            add("gold-3", f"Gold {pct}% on the day (threshold +3%)", "ALERT", "Daily move from the stored gold series.", series.get("source") or "")
        if "silver" in name and float(pct) >= 5:
            add("silver-5", f"Silver {pct}% on the day (threshold +5%)", "ALERT", "Daily move from the stored silver series.", series.get("source") or "")
        if series.get("id") in {"btc", "eth"} and float(pct) <= -10:
            add(f"{series.get('id')}-drop", f"{series.get('name')} {pct}% on the day (threshold -10%)", "ALERT", "Daily move from the stored crypto series.", series.get("source") or "")

    for trend in (trends or {}).get("items") or []:
        if trend.get("category") == "hurricane" and re.search(r"gulf", trend.get("name") or "", re.I):
            add("gulf-trend", f"X trend names a Gulf storm: {trend.get('name')}", "ALERT", "Trend text matched the Gulf-storm rule. X alone is not confirmed.", "")

    # One row per trigger id.
    unique = {}
    for row in fired:
        unique[row["id"]] = row
    rows = list(unique.values())
    for row in rows:
        row["action"] = "Run the short checklist: fuel, water, cash, meds."
        row["soWhat"] = so_what(row)
    return {
        "items": rows,
        "checklist": CHECKLIST if rows else [],
        "note": "Thresholds: Gulf tropical system, outbreak naming the US, quake M7+, Tennessee tornado or hurricane warning, gold +3% day, silver +5% day, BTC or ETH -10% day.",
    }


def _pearson(xs: list[float], ys: list[float]) -> float | None:
    n = min(len(xs), len(ys))
    if n < 5:
        return None
    xs, ys = xs[:n], ys[:n]
    mx = sum(xs) / n
    my = sum(ys) / n
    num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    dx = math.sqrt(sum((x - mx) ** 2 for x in xs))
    dy = math.sqrt(sum((y - my) ** 2 for y in ys))
    if dx == 0 or dy == 0:
        return None
    return round(num / (dx * dy), 3)


def _returns(points: list[dict]) -> dict[str, float]:
    ordered = [p for p in points or [] if p.get("date") and p.get("price") is not None]
    ordered.sort(key=lambda p: p["date"])
    out = {}
    prev = None
    for point in ordered:
        price = float(point["price"])
        if prev:
            out[point["date"]] = round((price / prev - 1) * 100, 3)
        prev = price
    return out


def _price_on(points: list[dict], day: str, direction: int) -> float | None:
    """Nearest stored close on or before (direction -1) or on or after (direction +1) a day."""
    ordered = sorted((p for p in points or [] if p.get("date") and p.get("price") is not None), key=lambda p: p["date"])
    if direction < 0:
        chosen = [p for p in ordered if p["date"] <= day]
        return None if not chosen else float(chosen[-1]["price"])
    chosen = [p for p in ordered if p["date"] >= day]
    return None if not chosen else float(chosen[0]["price"])


def _shift(day: str, delta: int) -> str:
    return (datetime.fromisoformat(day) + timedelta(days=delta)).date().isoformat()


def _pct(after: float | None, before: float | None) -> float | None:
    if after is None or before is None or before == 0:
        return None
    return round((after / before - 1) * 100, 2)


def event_window(points: list[dict], day: str) -> dict:
    """Percent moves versus the stored close on or before the day before the event."""
    if not day:
        return {"m1": None, "p1": None, "p3": None}
    before = _price_on(points, _shift(day, -1), -1)
    prior = _price_on(points, _shift(day, -2), -1)
    return {
        "m1": _pct(before, prior),
        "p1": _pct(_price_on(points, _shift(day, 1), 1), before),
        "p3": _pct(_price_on(points, _shift(day, 3), 1), before),
    }


def _category(item: dict) -> str:
    kind = item.get("kind") or ""
    if kind in {"quake"}:
        return "earthquake"
    if kind in {"storm"}:
        return "hurricane"
    if kind in {"who", "cdc"}:
        return "outbreak"
    if kind in {"conflict"}:
        return "war"
    if kind in {"neo", "sentry", "clock"}:
        return "existential"
    if kind in {"nws", "gdacs"}:
        blob = f"{item.get('title') or ''} {item.get('note') or ''}"
        theme = match_theme(blob)
        return theme or "disaster"
    return match_theme(item.get("title") or "") or "other"


def impact_report(threats: list[dict], assets: dict) -> dict:
    series = (assets or {}).get("series") or []
    major = []
    for item in threats or []:
        if (item.get("severity") or "") not in {"ACTION", "CRITICAL"}:
            continue
        if not item.get("date"):
            continue
        moves = []
        for asset in series:
            window = event_window(asset.get("points") or [], item["date"])
            moves.append({"id": asset.get("id"), "name": asset.get("name"), "source": asset.get("source") or "", **window})
        major.append({
            "id": item.get("id"),
            "title": item.get("title"),
            "url": item.get("url"),
            "date": item.get("date"),
            "severity": item.get("severity"),
            "category": _category(item),
            "moves": moves,
        })
        if len(major) >= 8:
            break

    by_cat: dict[str, set[str]] = {}
    for item in threats or []:
        if not item.get("date"):
            continue
        by_cat.setdefault(_category(item), set()).add(item["date"])

    correlations = []
    for asset in series:
        rets = _returns(asset.get("points") or [])
        dates = sorted(rets)
        for window in (30, 90):
            used = dates[-window:]
            for category, event_days in sorted(by_cat.items()):
                if category == "other":
                    continue
                xs = [1.0 if day in event_days else 0.0 for day in used]
                ys = [rets[day] for day in used]
                if sum(xs) < 3:
                    coeff = None
                else:
                    coeff = _pearson(xs, ys)
                correlations.append({
                    "asset": asset.get("name"),
                    "assetId": asset.get("id"),
                    "category": category,
                    "window": window,
                    "r": coeff,
                    "eventDays": int(sum(xs)),
                    "days": len(used),
                    "read": _read_corr(coeff, int(sum(xs)), len(used), asset.get("name") or "", category),
                })
    return {
        "events": major,
        "correlations": correlations,
        "note": "-1d is the move into the day before the event. +1d and +3d are moves from that same close to the stored close on or after those days. Correlation is Pearson between a category event-day (1/0) and that asset's daily percent change. Fewer than 5 paired days, or fewer than 3 event days, is n/a.",
    }


def _read_corr(coeff: float | None, event_days: int, days: int, asset: str, category: str) -> dict:
    if coeff is None or days < 5 or event_days < 3:
        return {
            "call": "n/a",
            "confidence": "n/a",
            "text": f"Not enough stored {asset} days beside {category} events in this {days}-day window to separate a link from coincidence.",
        }
    strength = abs(coeff)
    if strength >= 0.45 and event_days >= 5:
        call, confidence = "likely linked", "high"
    elif strength >= 0.3:
        call, confidence = "leans together", "medium"
    else:
        call, confidence = "coincidence more likely", "low"
    direction = "same direction" if coeff > 0 else "opposite direction"
    return {
        "call": call,
        "confidence": confidence,
        "text": f"{asset} and {category} event-days moved in the {direction} (r={coeff} over {days} stored days, {event_days} event days). {call.capitalize()} on this sample. This is not a cause and not advice.",
    }


def filter_trends(raw: list[dict], place: str) -> list[dict]:
    kept = []
    seen = set()
    for row in raw or []:
        name = (row.get("trend_name") or row.get("name") or "").strip()
        theme = match_theme(name)
        if not name or not theme:
            continue
        key = name.lower()
        if key in seen:
            continue
        seen.add(key)
        volume = row.get("tweet_count")
        if volume is None:
            volume = row.get("volume")
        samples = []
        for sample in row.get("samples") or []:
            url = d.http_url(sample.get("url") or "")
            if url:
                samples.append({"text": (sample.get("text") or "")[:180], "url": url})
        query = urllib.parse.quote(name)
        kept.append({
            "id": d.make_id("trend", place + "|" + key),
            "name": name,
            "title": name,
            "category": theme,
            "place": place,
            "volume": volume,
            "url": f"https://x.com/search?q={query}&src=typed_query&f=live",
            "samples": samples[:3],
            "kind": "trend",
            "lane": "x",
            "source": "X trends",
            "severity": "ALERT" if theme in {"hurricane", "tornado", "earthquake", "outbreak", "war"} else "STANDBY",
            "note": f"{place} trend · {theme}",
        })
    return kept


def trends_from_search(buckets: list[dict]) -> dict:
    """buckets: [{category, query, tweets: [{id, text}], resultCount}]"""
    items = []
    for bucket in buckets:
        tweets = bucket.get("tweets") or []
        count = bucket.get("resultCount")
        if count is None:
            count = len(tweets)
        if not count:
            continue
        samples = []
        for tweet in tweets[:3]:
            tid = str(tweet.get("id") or "")
            if tid.isdigit():
                samples.append({"text": (tweet.get("text") or "")[:180], "url": f"https://x.com/i/web/status/{tid}"})
        query = urllib.parse.quote(bucket.get("query") or bucket.get("category") or "")
        items.append({
            "id": d.make_id("trend", bucket.get("category") or ""),
            "name": bucket.get("category"),
            "title": bucket.get("category"),
            "category": bucket.get("category"),
            "place": "recent search",
            "volume": count,
            "url": f"https://x.com/search?q={query}&src=typed_query&f=live",
            "samples": samples,
            "kind": "trend",
            "lane": "x",
            "source": "X recent search",
            "severity": "ALERT" if bucket.get("category") in {"hurricane", "tornado", "earthquake", "outbreak", "war"} else "STANDBY",
            "note": "Count of public recent-search posts, not the trends endpoint.",
        })
    return {
        "mode": "recent-search",
        "note": "The X trends endpoint was not available on this token. Showing recent-search counts for threat and preparedness keywords.",
        "items": items,
    }


def annotate_trends(doc: dict, threats: list[dict]) -> dict:
    titles = " ".join((item.get("title") or "") for item in threats or []).lower()
    for item in doc.get("items") or []:
        extra = 1 if (item.get("name") or "").lower() in titles else 0
        # A matching official title is a second source, still not two non-X sources by itself
        # unless the official item exists: then X + official = reported, not confirmed.
        item.update(confidence_for(item, extra_domains=extra))
        if extra and item["confidence"] == "rumor":
            item["confidence"] = "reported"
            item["sourceCount"] = 2
        item["soWhat"] = so_what(item)
        item["action"] = _action(item.get("category") or "", item.get("severity") or "STANDBY")
    return doc


def fetch_google_trends(now: datetime) -> dict:
    import xml.etree.ElementTree as ET
    import boards

    url = "https://trends.google.com/trending/rss?geo=US"
    try:
        raw = boards._get(url, timeout=25, headers={"Accept": "application/rss+xml"})
        root = ET.fromstring(raw)
    except Exception as err:
        return {"ok": False, "note": f"Google Trends did not answer: {err}", "items": []}
    ht = "{https://trends.google.com/trending/rss}"
    items = []
    seen = 0
    for node in root.findall(".//item"):
        seen += 1
        title = (node.findtext("title") or "").strip()
        topic = topic_of(title)
        if not title or not topic:
            continue
        traffic = (node.findtext(f"{ht}approx_traffic") or "").strip()
        samples = []
        for news in node.findall(f"{ht}news_item"):
            ntitle = (news.findtext(f"{ht}news_item_title") or "").strip()
            nurl = d.http_url(news.findtext(f"{ht}news_item_url") or "")
            nsrc = (news.findtext(f"{ht}news_item_source") or "").strip()
            if nurl and ntitle:
                samples.append({"text": ntitle[:180], "url": nurl, "source": nsrc})
        published = d.parse_pubdate(node.findtext("pubDate") or "")
        stamp = published.isoformat(timespec="seconds") if published else now.isoformat(timespec="seconds")
        items.append({
            "id": d.make_id("gtrend", title.lower()),
            "name": title,
            "title": title,
            "category": topic,
            "place": "US",
            "volume": traffic or None,
            "rise": f"US daily list {traffic}".strip(),
            "look": "news" if len(samples) >= 2 else "chatter",
            "url": samples[0]["url"] if samples else "https://trends.google.com/trending?geo=US",
            "samples": samples[:3],
            "kind": "trend",
            "lane": "news",
            "source": "Google Trends",
            "severity": "ALERT" if topic in {"iran-war", "ukraine-war", "hurricane", "outbreak"} else "STANDBY",
            "note": f"US search trend. Traffic {traffic or 'not given'}.",
            "confidence": "reported" if samples else "rumor",
            "sourceCount": max(1, len({sample.get("source") for sample in samples})),
            "soWhat": "no action needed",
            "published": stamp,
            "date": stamp[:10],
        })
        if len(items) >= 6:
            break
    note = f"Google Trends US daily list answered ({seen} topics). Kept the ones that match a war, government, or threat topic."
    if not items:
        note += " None of today's search trends matched."
    return {"ok": True, "note": note, "items": items}


def news_velocity(threats: list[dict], when: datetime | None = None) -> list[dict]:
    buckets: dict[str, list] = {}
    for item in threats or []:
        topic = {"war-iran": "iran-war", "war-ukraine": "ukraine-war", "usgov": "us-gov"}.get(item.get("kind") or "")
        topic = topic or topic_of(item.get("title") or "")
        if topic not in {"iran-war", "ukraine-war", "us-gov"}:
            continue
        buckets.setdefault(topic, []).append(item)
    out = []
    for topic, rows in buckets.items():
        sources = []
        for row in rows:
            src = row.get("source") or ""
            if src and src not in sources:
                sources.append(src)
        if len(sources) < 3:
            continue
        times = [row.get("published") or "" for row in rows if row.get("published")]
        newest = when.isoformat(timespec="seconds") if when is not None else (max(times) if times else "")
        out.append({
            "id": d.make_id("velocity", topic),
            "name": topic.replace("-", " "),
            "title": topic.replace("-", " "),
            "category": topic,
            "rise": f"{len(sources)} outlets this window",
            "look": "news",
            "url": rows[0].get("url") or "",
            "samples": [{
                "text": row.get("title") or "",
                "url": row.get("url") or "",
                "source": row.get("source") or "",
                "published": row.get("published") or "",
                "date": row.get("date") or "",
            } for row in rows[:3]],
            "kind": "trend",
            "lane": "news",
            "source": "News velocity",
            "severity": "ALERT",
            "note": "The same topic showed up across several outlets.",
            "confidence": "reported",
            "sourceCount": len(sources),
            "soWhat": "no action needed",
            "published": newest,
            "date": newest[:10] if newest else "",
        })
    return out


def _stamp_trend(item: dict, when: datetime | None) -> dict:
    """Give a buzz row a real clock. Prefer the newest sample, otherwise the refresh time."""
    row = dict(item)
    newest = row.get("published") or ""
    for sample in row.get("samples") or []:
        raw = sample.get("published") or ""
        if raw and raw > newest:
            newest = raw
    if not newest and when is not None:
        newest = when.isoformat(timespec="seconds")
    if newest:
        row["published"] = newest
        row["date"] = newest[:10]
    return row


def keep_rising(trends: dict, history: dict, today: str, google_items: list, velocity_items: list, when: datetime | None = None) -> dict:
    yday = (datetime.fromisoformat(today) - timedelta(days=1)).date().isoformat()
    snap = _snapshot_on_or_before((history or {}).get("days") or [], yday)
    old = {(row.get("name") or "").lower(): row.get("volume") for row in (snap or {}).get("trends") or []}
    backed = {(item.get("name") or "").lower() for item in (google_items or []) + (velocity_items or [])}
    backed |= {item.get("category") for item in (velocity_items or [])}
    kept = []
    dropped = 0
    for item in (trends or {}).get("items") or []:
        name = item.get("name") or ""
        if not topic_of(name):
            dropped += 1
            continue
        volume = item.get("volume")
        prev = old.get(name.lower())
        rise = ""
        if isinstance(volume, (int, float)) and isinstance(prev, (int, float)) and volume > prev:
            rise = f"up vs yesterday ({prev} → {volume})"
        elif name.lower() in backed or topic_of(name) in backed:
            rise = "also showing up off X"
        if not rise:
            dropped += 1
            continue
        row = _stamp_trend(item, when)
        row["rise"] = rise
        row["look"] = "chatter" if row.get("lane") == "x" else "news"
        row["soWhat"] = "no action needed"
        kept.append(row)
    for item in (google_items or []) + (velocity_items or []):
        kept.append(_stamp_trend(item, when))
    seen = set()
    unique = []
    for item in kept:
        key = (item.get("name") or "").lower()
        if not key or key in seen:
            continue
        seen.add(key)
        unique.append(item)
    note = (trends or {}).get("note") or ""
    if dropped:
        note = (note + " " if note else "") + f"Dropped {dropped} X topics that were a name match or had no rise versus yesterday."
    return {"mode": (trends or {}).get("mode") or "trends", "note": note.strip(), "items": unique[:12]}


def _millis_day(value) -> str:
    try:
        stamp = int(value) / 1000
    except (TypeError, ValueError):
        return ""
    return datetime.fromtimestamp(stamp, d.CT).strftime("%Y-%m-%d")


def fetch_local(now: datetime) -> dict:
    import boards

    items = []
    gaps = []
    nws_rows = 0
    try:
        raw = boards._get(NWS_POINT, timeout=25, headers={"Accept": "application/geo+json", "User-Agent": "news-desk/1.0 (local)"})
        payload = json.loads(raw)
        for feat in (payload.get("features") or [])[:8]:
            props = feat.get("properties") or {}
            title = props.get("headline") or props.get("event") or "NWS alert"
            link = d.http_url(props.get("uri") or props.get("@id") or "https://api.weather.gov/")
            event = props.get("event") or ""
            sev = "ACTION" if re.search(r"warning", event, re.I) else "ALERT"
            if re.search(r"tornado|hurricane", event, re.I) and re.search(r"warning", event, re.I):
                sev = "CRITICAL"
            items.append({
                "id": d.make_id("local-nws", link or title),
                "title": title,
                "note": (props.get("description") or "")[:400],
                "url": link,
                "source": "NWS",
                "kind": "nws",
                "lane": "local",
                "severity": sev,
                "date": now.strftime("%Y-%m-%d"),
                "label": d.ct_label(now, True),
                "published": now.isoformat(timespec="seconds"),
                "tags": ["tennessee", "williamson"],
            })
            nws_rows += 1
        if nws_rows == 0:
            items.append({
                "id": "local-nws-none",
                "title": "No active NWS alert for Thompson's Station (37179)",
                "note": "api.weather.gov answered for 35.802,-86.907 and returned no alerts.",
                "url": "https://api.weather.gov/alerts/active?point=35.802,-86.907",
                "source": "NWS",
                "kind": "nws",
                "lane": "local",
                "severity": "STANDBY",
                "date": now.strftime("%Y-%m-%d"),
                "label": d.ct_label(now, True),
                "published": now.isoformat(timespec="seconds"),
                "tags": ["tennessee", "williamson"],
            })
    except Exception as err:
        gaps.append(f"NWS point 37179: {err}")
        items.append(_na("NWS alerts", "https://api.weather.gov/", f"n/a — {err}"))

    try:
        payload = json.loads(boards._get(POWER_QUERY, timeout=25))
        feats = payload.get("features") or []
        if not feats:
            items.append(_na("Williamson County power", "https://services1.arcgis.com/utFj6xjAHT9GdIit/arcgis/rest/services/Power_TN/FeatureServer", "n/a — no Williamson row in the public outage summary."))
        else:
            attrs = (feats[0].get("attributes") or {})
            affected = attrs.get("CustomersAffected")
            served = attrs.get("CustomersServed")
            when = _millis_day(attrs.get("Timestamp"))
            stale_power = bool(when and when < (now.date() - timedelta(days=7)).isoformat())
            empty_power = affected in (0, None) and served in (0, None)
            if stale_power or empty_power:
                gaps.append(f"Power_TN row hidden ({when or 'no date'}, affected {affected}, served {served}).")
            else:
                items.append({
                "id": "local-power-williamson",
                "title": f"Williamson County power: {affected if affected is not None else 'n/a'} customers affected",
                "note": f"Customers served: {served if served is not None else 'n/a'}. Public Power_TN summary.",
                "url": "https://services1.arcgis.com/utFj6xjAHT9GdIit/arcgis/rest/services/Power_TN/FeatureServer",
                "source": "Power_TN",
                "kind": "power",
                "lane": "local",
                "severity": "ALERT" if affected not in (None, 0) else "STANDBY",
                "date": when or now.strftime("%Y-%m-%d"),
                "label": when or d.ct_label(now, True),
                "published": now.isoformat(timespec="seconds"),
                "tags": ["tennessee", "williamson"],
            })
    except Exception as err:
        gaps.append(f"Power_TN: {err}")
        items.append(_na("Williamson County power", "https://www.tn.gov/tema.html", f"n/a — {err}"))

    try:
        payload = json.loads(boards._get(ROAD_QUERY, timeout=25))
        feats = payload.get("features") or []
        if not feats:
            items.append(_na("TDOT Williamson roads", "https://smartway.tn.gov/", "n/a — SmartWay returned no Williamson County events."))
        hidden_roads = 0
        kept_roads = 0
        for feat in feats[:40]:
            attrs = feat.get("attributes") or {}
            desc = (attrs.get("DESCRIPTION") or "Road notice").strip()
            when = _millis_day(attrs.get("REVISED_DATE")) or now.strftime("%Y-%m-%d")
            ended = when < now.strftime("%Y-%m-%d") and re.search(r"scheduled|widening|project", desc, re.I)
            live = re.search(r"debris|closure|blocked|crash|flood|disabled", desc, re.I)
            if ended and not live:
                hidden_roads += 1
                continue
            kept_roads += 1
            items.append({
                "id": d.make_id("local-road", desc[:80]),
                "title": desc[:180],
                "note": attrs.get("EVENT_SUBTYPE") or "TDOT SmartWay",
                "url": "https://smartway.tn.gov/",
                "source": "TDOT SmartWay",
                "kind": "road",
                "lane": "local",
                "severity": "ALERT" if re.search(r"closure|blocked|flood", desc, re.I) else "STANDBY",
                "date": when,
                "label": when,
                "published": now.isoformat(timespec="seconds"),
                "tags": ["tennessee", "williamson"],
            })
            if kept_roads >= 6:
                break
        if hidden_roads:
            gaps.append(f"{hidden_roads} ended road projects hidden.")
    except Exception as err:
        gaps.append(f"TDOT: {err}")
        items.append(_na("TDOT Williamson roads", "https://smartway.tn.gov/", f"n/a — {err}"))

    try:
        html = boards._get(
            TEMA_PAGE,
            timeout=25,
            headers={"User-Agent": boards.BROWSER, "Accept": "text/html,application/xhtml+xml"},
        ).decode("utf-8", "replace")
        notices = tema_notices(html, now)
        if notices:
            items.extend(notices)
        else:
            gaps.append("TEMA news page answered with no dated notices.")
    except Exception as err:
        gaps.append(f"TEMA: {err}")

    for item in items:
        if item.get("confidence"):
            continue
        item.update(confidence_for(item))
        item["soWhat"] = so_what(item)
        item["action"] = _action(item.get("kind") or "", item.get("severity") or "STANDBY")
    return {
        "place": "Thompson's Station / Williamson County / Middle Tennessee (37179)",
        "items": items,
        "gaps": gaps,
    }


def _na(title: str, url: str, note: str) -> dict:
    return {
        "id": d.make_id("local-na", title),
        "title": title,
        "note": note,
        "url": url,
        "source": "n/a",
        "kind": "na",
        "lane": "local",
        "severity": "STANDBY",
        "confidence": "rumor",
        "sourceCount": 0,
        "date": "",
        "label": "n/a",
        "published": "",
        "tags": ["tennessee"],
    }


RADAR_QUERIES = (
    ("US and Europe preparedness surge", 'preparedness OR prepping (United States OR Europe OR "civil defense") when:14d'),
    ("Pentagon off-grid and 90-day stories", '(Pentagon OR "Department of Defense") ("off-grid" OR "90-day" OR "90 day" OR stockpile) when:30d'),
    ("Official follow-through", '(FEMA OR "strategic national stockpile" OR "defense production") (budget OR procurement OR legislation OR shortage) when:30d'),
)


def _driver(source: str, url: str) -> str:
    blob = f"{source} {url}".lower()
    if ".gov" in blob or "white house" in blob or "pentagon" in blob or "defense.gov" in blob:
        return "officials"
    if any(name in blob for name in ("reuters", "ap news", "associated press", "bbc", "nyt", "washington post", "wsj", "bloomberg")):
        return "press"
    return "social"


def _follow(text: str) -> list[str]:
    hits = []
    for label, pattern in (
        ("budgets", r"budget"),
        ("orders", r"\border\b"),
        ("procurement", r"procurement|contract"),
        ("shortages", r"shortage"),
        ("legislation", r"bill|legislation|congress"),
    ):
        if re.search(pattern, text, re.I):
            hits.append(label)
    return hits


def fetch_radar(now: datetime) -> dict:
    import boards

    stories = []
    for name, query in RADAR_QUERIES:
        try:
            rows = boards._headlines(query, now, retain_days=30, limit=8)
        except Exception as err:
            stories.append({
                "id": d.make_id("radar", name),
                "title": name,
                "note": f"n/a — {err}",
                "url": "https://news.google.com/",
                "source": "n/a",
                "kind": "radar",
                "lane": "news",
                "severity": "STANDBY",
                "confidence": "rumor",
                "sourceCount": 0,
                "score": None,
                "drivers": [],
                "followThrough": [],
                "velocity": "n/a",
                "read": "The news search did not answer, so this track is n/a.",
            })
            continue
        drivers = sorted({_driver(row.get("source") or "", row.get("url") or "") for row in rows})
        follow = []
        for row in rows:
            follow.extend(_follow(f"{row.get('title') or ''} {row.get('note') or ''}"))
        follow = sorted(set(follow))
        domains = len({(row.get("source") or "").lower() for row in rows})
        recent = 0
        for row in rows:
            try:
                age = (now.date() - datetime.fromisoformat(row["date"]).date()).days
            except (KeyError, ValueError):
                age = 99
            if age <= 3:
                recent += 1
        if recent >= 4:
            velocity = "fast"
        elif recent >= 2:
            velocity = "building"
        elif rows:
            velocity = "slow"
        else:
            velocity = "quiet"
        score = min(100, domains * 8 + (20 if "officials" in drivers else 0) + len(follow) * 15 + recent * 4)
        official_act = bool(rows) and (
            "officials" in drivers or bool(follow) or any(
                re.search(r"\b(department of energy|european commission|white house|pentagon|congress|fema|appropriat|procurement|budget)\b", f"{row.get('title') or ''} {row.get('source') or ''}", re.I)
                for row in rows
            )
        )
        if not rows:
            read = "No recent public headlines."
            call = "noise"
        elif official_act:
            for row in rows:
                blob = f"{row.get('title') or ''} {row.get('source') or ''} {row.get('url') or ''}"
                if re.search(r"\.gov|department of energy|european commission|white house|pentagon|fema", blob, re.I):
                    drivers = sorted(set(drivers) | {"officials"})
            read = "An official body acted or is named in the sources: an agency, a budget, a law, or a procurement step. That is follow-through."
            call = "real"
            if not follow:
                follow = ["official step"]
        elif domains >= 3:
            read = "Several outlets are repeating it. No official step is in the sources."
            call = "mixed"
        else:
            read = "Thin sourcing. More chatter than follow-through on this pass."
            call = "noise"
        if call == "noise":
            score = min(score, 35)
        elif call == "mixed":
            score = min(score, 70)
        elif call == "real":
            score = max(min(score, 100), 55)
        top = rows[0] if rows else {}
        stories.append({
            "id": d.make_id("radar", name),
            "title": name,
            "note": top.get("title") or "No headline in the window.",
            "url": top.get("url") or "https://news.google.com/",
            "source": top.get("source") or "Google News",
            "kind": "radar",
            "lane": "news",
            "severity": "ALERT" if call == "real" else "STANDBY",
            "confidence": "confirmed" if call == "real" and domains >= 2 else ("reported" if rows else "rumor"),
            "sourceCount": domains,
            "score": score if rows else 0,
            "call": call,
            "drivers": drivers,
            "followThrough": follow,
            "velocity": velocity,
            "samples": [{"title": row.get("title"), "url": row.get("url"), "source": row.get("source")} for row in rows[:4]],
            "read": read,
            "date": top.get("date") or now.strftime("%Y-%m-%d"),
            "label": top.get("label") or d.ct_label(now, True),
            "published": top.get("published") or now.isoformat(timespec="seconds"),
        })
        stories[-1]["soWhat"] = so_what(stories[-1])
    return {"items": stories, "note": "Public news search only. Spread velocity is how many of those headlines are from the last 3 days. Score is a desk count, not a prediction."}


def _sp500(markets) -> float | None:
    for region in (markets or {}).get("regions") or []:
        if (region.get("name") or "").lower() not in {"usa", "united states"}:
            continue
        for venue in region.get("venues") or []:
            name = f"{venue.get('indexName') or ''} {venue.get('name') or ''}".lower()
            if "s&p" in name or "spx" in name or "gspc" in name:
                if venue.get("changePct") is None:
                    return None
                return float(venue["changePct"])
    return None


def morning_brief(threats, trends, triggers, assets, local, markets=None) -> str:
    lines = []
    sp = _sp500(markets)
    if sp is not None and abs(sp) >= 3:
        sign = "+" if sp > 0 else ""
        lines.append(f"The stock tape is the story: the S&P 500 is {sign}{sp}% today. What to do: no action unless you need cash this week.")
    real = [
        item for item in threats or []
        if item.get("severity") in {"ACTION", "CRITICAL"}
        and item.get("kind") not in {"neo", "sentry", "clock"}
        and not _all_clear(item.get("title") or "", item.get("note") or "")
    ]
    real.sort(key=lambda item: (-_rank(item.get("severity") or ""), item.get("title") or ""))
    if real:
        top = real[0]
        lines.append(f"Open risk: {top.get('severity')} {top.get('title')}.")
    elif sp is None or abs(sp) < 3:
        lines.append("No rare risk is on the board. A routine flyby or an empty storm outlook is not an emergency.")
    wars = [item.get("title") for item in threats or [] if item.get("kind") in {"war-iran", "war-ukraine"}][:2]
    if wars:
        lines.append("Current war coverage is on the board: " + "; ".join(wars) + ".")
    trend_items = [item for item in (trends or {}).get("items") or [] if item.get("rise") not in (None, "", "flat")]
    if trend_items:
        lead = trend_items[0]
        lines.append(f"Rising topic: {lead.get('name')} ({lead.get('rise')}).")
    local_hot = [item for item in (local or {}).get("items") or [] if item.get("severity") in {"ACTION", "CRITICAL"} and not item.get("stale")]
    if local_hot:
        lines.append(f"Local: {local_hot[0].get('title')}.")
    if not lines:
        lines.append("Nothing on the board needs an action today.")
    return " ".join(lines[:5])


def record_history(history: dict, today: str, threats, trends, triggers, label: str) -> dict:
    days = [snap for snap in (history or {}).get("days") or [] if snap.get("date") != today]
    outlooks = [{"id": item.get("id"), "outlook": item.get("outlook"), "severity": item.get("severity")} for item in threats or []]
    days.append({
        "date": today,
        "label": label,
        "threats": [{"id": item.get("id"), "title": item.get("title"), "severity": item.get("severity"), "kind": item.get("kind")} for item in threats or []],
        "trends": [{"name": item.get("name"), "category": item.get("category"), "volume": item.get("volume")} for item in (trends or {}).get("items") or []],
        "triggers": [item.get("id") for item in (triggers or {}).get("items") or []],
        "outlooks": outlooks,
    })
    days.sort(key=lambda snap: snap.get("date") or "")
    return {"days": days[-HISTORY_DAYS:]}


def weekly_lookback(history: dict, today: str) -> dict:
    days = (history or {}).get("days") or []
    if not days:
        return {"note": "No stored history yet. This fills in after refreshes.", "escalated": [], "fizzled": [], "calls": []}
    week_day = (datetime.fromisoformat(today) - timedelta(days=7)).date().isoformat()
    past = _snapshot_on_or_before(days, week_day) or days[0]
    current = _snapshot_on_or_before(days, today) or days[-1]
    old = {row.get("id"): row for row in past.get("threats") or []}
    now = {row.get("id"): row for row in current.get("threats") or []}
    escalated, fizzled = [], []
    for item_id, row in now.items():
        before = old.get(item_id)
        if before is None and _rank(row.get("severity") or "") >= _rank("ALERT"):
            escalated.append({"title": row.get("title"), "note": f"New since {past.get('date')} · now {row.get('severity')}"})
        elif before and _rank(row.get("severity") or "") > _rank(before.get("severity") or ""):
            escalated.append({"title": row.get("title"), "note": f"{before.get('severity')} → {row.get('severity')} since {past.get('date')}"})
    for item_id, row in old.items():
        after = now.get(item_id)
        if after is None and _rank(row.get("severity") or "") >= _rank("ALERT"):
            fizzled.append({"title": row.get("title"), "note": f"On the board {past.get('date')} at {row.get('severity')}, absent now."})
        elif after and _rank(after.get("severity") or "") < _rank(row.get("severity") or ""):
            fizzled.append({"title": row.get("title"), "note": f"{row.get('severity')} → {after.get('severity')} since {past.get('date')}"})
    calls = []
    old_outlook = {row.get("id"): row for row in past.get("outlooks") or []}
    for item_id, row in old_outlook.items():
        text = (row.get("outlook") or "").lower()
        after = now.get(item_id)
        if "rising" in text or "higher" in text:
            if after and _rank(after.get("severity") or "") > _rank(row.get("severity") or ""):
                calls.append({"title": after.get("title"), "verdict": "right", "note": "The stored outlook said higher, and the status rose."})
            elif after and _rank(after.get("severity") or "") < _rank(row.get("severity") or ""):
                calls.append({"title": after.get("title"), "verdict": "wrong", "note": "The stored outlook said higher, and the status fell."})
            elif after is None:
                calls.append({"title": row.get("id"), "verdict": "wrong", "note": "The stored outlook said higher, and the item left the board."})
    return {
        "since": past.get("date") or "",
        "note": f"Compared with the stored board on {past.get('date') or 'the oldest day'}.",
        "escalated": escalated[:12],
        "fizzled": fizzled[:12],
        "calls": calls[:12],
    }


def change_slice(label: str, previous_ids: dict, current_items: list[dict], section: str) -> dict:
    fresh, escalated, eased, resolved = [], [], [], []
    current = {item.get("id"): item for item in current_items}
    for item_id, item in current.items():
        before = previous_ids.get(item_id)
        if before is None:
            fresh.append(item)
        elif _rank(item.get("severity") or "") > _rank(before):
            escalated.append(item)
        elif _rank(item.get("severity") or "") < _rank(before):
            eased.append(item)
    for item_id, before in previous_ids.items():
        if item_id not in current and _rank(before) >= _rank("ALERT"):
            resolved.append({"id": item_id, "title": item_id, "severity": before, "section": section})
    return {"new": fresh, "escalated": escalated, "eased": eased, "resolved": resolved, "label": label, "section": section}
