"""Nov 12 rules: local NWS scope, bar dates, macro, strikes, and rising scores.

Fetches fail soft. Nothing here needs a paid key or a new schedule.
"""
from __future__ import annotations

import csv
import io
import json
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

TN_WILLIAMSON = {"187"}
TN_ADJACENT = {"037", "149", "119", "081", "043", "021"}  # Davidson, Rutherford, Maury, Hickman, Dickson, Cheatham
TN_COUNTY_FIPS = {
    "johnson": "091", "cocke": "029", "greene": "059", "unicoi": "171", "carter": "019",
    "blount": "009", "sevier": "155", "monroe": "123", "williamson": "187", "davidson": "037",
    "rutherford": "149", "maury": "119", "hickman": "081", "dickson": "043", "cheatham": "021",
}
STRIKE_PLACES = (
    ("ust-luga", "Russia"), ("ust luga", "Russia"), ("suez", "Egypt"), ("egypt", "Egypt"),
    ("smolensk", "Russia"), ("leningrad", "Russia"), ("kirishi", "Russia"), ("afipsky", "Russia"),
)

CHOKEPOINTS = ("hormuz", "red sea", "ust-luga", "ust luga", "novorossiysk", "primorsk")
DOMESTIC_ACCIDENT = re.compile(r"\b(house explosion|apartment explosion|gas leak|clarksville|accidental blast)\b", re.I)
STRIKE_MEANS = re.compile(r"\b(drone|missile|airstrike|air strike|shelling|bomb|bombard)\w*\b", re.I)
ENERGY_TARGET = re.compile(r"\b(refinery|pipeline|terminal|oil|gas|lng|power plant|substation|energy)\b", re.I)


def tn_county_codes(props: dict | None) -> set[str]:
    geo = (props or {}).get("geocode") or {}
    found = set()
    for key in ("UGC", "SAME"):
        for code in geo.get(key) or []:
            text = str(code).upper().replace(" ", "")
            match = re.search(r"(?:TNC|047)(\d{3})$", text)
            if match:
                found.add(match.group(1))
            elif re.fullmatch(r"047\d{3}", text):
                found.add(text[-3:])
    return found


def tn_alert_scope(props: dict | None) -> str:
    """williamson, adjacent, or elsewhere. Elsewhere in Tennessee is not a 37179 alert."""
    codes = tn_county_codes(props)
    area = ((props or {}).get("areaDesc") or "")
    if codes & TN_WILLIAMSON or re.search(r"\bWilliamson\b", area):
        return "williamson"
    if codes & TN_ADJACENT or re.search(r"\b(Davidson|Rutherford|Maury|Hickman|Dickson|Cheatham)\b", area):
        return "adjacent"
    return "elsewhere"


def tn_codes_from_area(text: str) -> dict:
    """UGC and SAME codes named in an NWS area line, so the client can re-check the county."""
    found = []
    for name, code in TN_COUNTY_FIPS.items():
        if re.search(rf"\bnot\s+{name}\b", text or "", re.I):
            continue
        if re.search(rf"\b{name}\b", text or "", re.I):
            found.append(code)
    return {"ugc": [f"TNC{code}" for code in found], "same": [f"047{code}" for code in found]}


def nws_geo(props: dict | None) -> dict:
    geo = (props or {}).get("geocode") or {}
    ugc = [str(code) for code in (geo.get("UGC") or [])]
    same = [str(code) for code in (geo.get("SAME") or [])]
    if not ugc and not same:
        named = tn_codes_from_area((props or {}).get("areaDesc") or "")
        ugc, same = named["ugc"], named["same"]
    return {"ugc": ugc, "same": same}


def exchange_day(stamp, tz_name: str) -> str:
    """Date a bar in the exchange zone. Midnight New York must not become the previous Chicago date."""
    moment = datetime.fromtimestamp(int(stamp), timezone.utc).astimezone(ZoneInfo(tz_name))
    return moment.strftime("%Y-%m-%d")


def published_within_hours(item: dict, now: datetime, hours: int = 36) -> bool:
    raw = item.get("published") or item.get("date") or ""
    if not raw:
        return False
    try:
        if len(str(raw)) == 10:
            stamp = datetime.fromisoformat(str(raw)).replace(tzinfo=now.tzinfo)
        else:
            stamp = datetime.fromisoformat(str(raw))
        if stamp.tzinfo is None and now.tzinfo is not None:
            stamp = stamp.replace(tzinfo=now.tzinfo)
        return abs((now - stamp).total_seconds()) <= hours * 3600
    except ValueError:
        return False


def proper_nouns(title: str) -> set[str]:
    cleaned = re.sub(r"\s+[-–—|]\s+[^-–—|]{2,60}$", "", title or "")
    skip = {"the", "and", "for", "with", "from", "this", "after", "over", "into", "about", "says", "new", "news", "read", "letter"}
    found = set()
    for match in re.finditer(r"\b([A-Z][A-Za-z0-9]{2,}|[A-Z]{2,}\d*)\b", cleaned):
        word = match.group(1).lower()
        if word not in skip:
            found.add(word)
    if re.search(r"\bcop\s*31\b", cleaned, re.I):
        found.add("cop31")
    if re.search(r"\bg7\b", cleaned, re.I):
        found.add("g7")
    return found


def within_48h(a: dict, b: dict) -> bool:
    def stamp(row):
        raw = str(row.get("published") or row.get("date") or "")
        try:
            if len(raw) == 10:
                return datetime.fromisoformat(raw)
            return datetime.fromisoformat(raw)
        except ValueError:
            return None
    left, right = stamp(a), stamp(b)
    if left is None or right is None:
        return False
    if left.tzinfo is not None:
        left = left.replace(tzinfo=None)
    if right.tzinfo is not None:
        right = right.replace(tzinfo=None)
    return abs((left - right).total_seconds()) <= 48 * 3600


def same_topic_recent(a: dict, b: dict) -> bool:
    """Same topic inside 48 hours when two proper nouns are shared."""
    if not within_48h(a, b):
        return False
    return len(proper_nouns(a.get("title") or "") & proper_nouns(b.get("title") or "")) >= 2


def rows_same_cluster(a: dict, b: dict, same_story) -> bool:
    if same_story(a.get("title") or "", b.get("title") or ""):
        return True
    return same_topic_recent(a, b)


def correlation_ready(event_days: int, minimum: int = 10) -> bool:
    return int(event_days or 0) >= minimum


def quake_counts_for_market(item: dict) -> bool:
    if (item.get("kind") or "") != "quake":
        return True
    return (item.get("severity") or "").upper() != "STANDBY"


def clean_strike_title(title: str) -> str:
    text = re.sub(r"\s*[-–—|]?\s*https?://\S+", "", title or "")
    return re.sub(r"\s+", " ", text).strip(" -")


def strike_fields(title: str) -> dict:
    blob = clean_strike_title(title)
    means = ""
    match = STRIKE_MEANS.search(blob)
    if match:
        means = match.group(1).lower()
    target_type = "military"
    if ENERGY_TARGET.search(blob):
        target_type = "energy"
    elif re.search(r"\b(airport|rail|bridge|port)\b", blob, re.I):
        target_type = "transport"
    elif re.search(r"\b(assassinat|killed .*official|mayor)\b", blob, re.I):
        target_type = "assassination"
    elif re.search(r"\b(apartment|residential|civilian|hospital|school)\b", blob, re.I):
        target_type = "civilian"
    country = ""
    low = blob.lower()
    for needle, name in STRIKE_PLACES:
        if needle in low:
            country = name
            break
    if not country:
        for name in ("Ukraine", "Russia", "Iran", "Israel", "Syria", "Yemen", "Lebanon", "Egypt"):
            if re.search(rf"\b{name}\b", blob, re.I):
                country = name
                break
    return {"means": means, "target_type": target_type, "country": country}


def normalize_strikes(doc: dict) -> dict:
    for item in (doc or {}).get("items") or []:
        title = clean_strike_title(item.get("title") or "")
        item["title"] = title
        if not str(item.get("country") or "").strip():
            item["country"] = strike_fields(title).get("country") or ""
    return doc


def keep_strike(title: str) -> bool:
    """Drop a domestic accident that is not a strike."""
    if DOMESTIC_ACCIDENT.search(title or "") and not STRIKE_MEANS.search(title or ""):
        return False
    return bool(STRIKE_MEANS.search(title or "") or ENERGY_TARGET.search(title or ""))


def strike_severity(title: str, *, energy_hits_72h: int = 1, brent_move: float | None = None) -> str:
    """News alone never reaches CRITICAL. US homeland or US energy is ACTION."""
    blob = (title or "").lower()
    if re.search(r"\b(united states|u\.s\. homeland|us forces|american base|us energy)\b", blob):
        return "ACTION"
    fields = strike_fields(title)
    energy = fields["target_type"] == "energy"
    chokepoint = any(name in blob for name in CHOKEPOINTS)
    if energy and brent_move is not None and abs(brent_move) >= 3:
        return "ALERT"
    if energy and energy_hits_72h >= 3:
        return "ALERT"
    if chokepoint:
        return "ALERT"
    return "STANDBY"


def rising_volume_points(today: float, week_avg: float) -> int:
    ratio = (today + 1) / (week_avg + 1)
    if ratio >= 3:
        return 3
    if ratio >= 2:
        return 2
    if ratio >= 1.5:
        return 1
    return 0


def rising_state(score: int, *, first_seen_days: int, rising_before: bool, today: float, avg3: float, avg14: float, max90: float, severity_step_days: int) -> str:
    if first_seen_days <= 3 and score >= 4:
        return "EMERGING"
    volume_rising = avg14 > 0 and avg3 > 1.5 * avg14 and today >= avg3
    if score >= 5 or volume_rising:
        if rising_before and max90 > 0 and today >= 0.8 * max90 and today < avg3:
            return "PEAKING"
        return "RISING"
    if rising_before and ((avg14 > 0 and avg3 < 0.5 * avg14) or severity_step_days >= 3):
        return "FADING"
    return ""


def gold_driver_lines(moves: dict) -> list[str]:
    """Rule-based notes. Each line is an association, not proof."""
    lines = []
    gold = moves.get("gold")
    dxy = moves.get("dxy")
    y10 = moves.get("y10_bp")
    real = moves.get("real_bp")
    implied = moves.get("implied_bp")
    vix = moves.get("vix")
    spx = moves.get("spx")
    brent = moves.get("brent")
    deescalation = moves.get("deescalation")
    level = moves.get("gs_level")
    change = moves.get("gs_change")
    copper = moves.get("copper")
    if gold is not None and gold < 0 and dxy is not None and dxy >= 1 and ((y10 or 0) >= 15 or (real or 0) >= 15):
        lines.append(f"Gold {gold}% with DXY {dxy}% and yields up. Association, not proof: stronger dollar / higher rates.")
    if implied is not None and implied >= 15:
        lines.append(f"Fed-funds futures implied rate {implied} bp. Association, not proof: more rate-hike bets.")
    if vix is not None and vix <= -3 and spx is not None and spx > 0:
        lines.append(f"VIX {vix} pts and S&P {spx}%. Association, not proof: fear premium fading.")
    if brent is not None and brent <= -5 and deescalation:
        lines.append(f"Brent {brent}% beside a de-escalation headline. Association, not proof: war premium easing.")
    mentioned = False
    if level is not None and change is not None and change >= 3 and copper is not None and copper < 0:
        lines.append(
            f"Gold/silver ratio {round(float(level), 1)} (1-month change {change}%) and copper {copper}%. "
            "Association, not proof: industrial worry is hitting silver harder."
        )
        mentioned = True
    if level is not None and not mentioned:
        extra = f" 1-month change {change}%." if change is not None else ""
        lines.append(f"Gold/silver ratio {round(float(level), 1)}.{extra}")
    return lines


def format_copper_gold(ratio: float | None) -> str:
    """A copper/gold price near 0.0016 is unreadable at two decimals. Show it per 1,000."""
    if ratio is None:
        return "n/a"
    number = float(ratio)
    if abs(number) < 0.05:
        return f"{number * 1000:.2f} per 1,000"
    return f"{number:.2f}"


def driver_moves(drivers: dict | None) -> dict:
    """One gold print: the ratio is gold divided by silver, and the 1-month change stays a percent."""
    rows = {row.get("name"): row for row in ((drivers or {}).get("rows") or [])}

    def change(name: str, key: str = "1M"):
        return ((rows.get(name) or {}).get("changes") or {}).get(key)

    gold = (rows.get("Gold") or {}).get("level")
    silver = (rows.get("Silver") or {}).get("level")
    level = None
    if gold not in (None, 0) and silver not in (None, 0):
        level = round(float(gold) / float(silver), 2)
    elif (rows.get("Gold/silver") or {}).get("level") not in (None, ""):
        level = (rows.get("Gold/silver") or {}).get("level")
    return {
        "gold": change("Gold"),
        "dxy": change("DXY"),
        "y10_bp": change("10Y"),
        "real_bp": change("Real 10Y"),
        "vix": change("VIX"),
        "spx": change("S&P"),
        "brent": change("Brent"),
        "copper": change("Copper"),
        "gs_level": level,
        "gs_change": change("Gold/silver"),
    }


def use_driver_snapshot(assets: dict | None, drivers: dict | None) -> None:
    """Copy the driver gold, silver, and dollar levels onto the asset cards so the map matches."""
    rows = {row.get("name"): row for row in ((drivers or {}).get("rows") or [])}
    for asset in (assets or {}).get("series") or []:
        row = rows.get(asset.get("name") or "")
        if not row or row.get("level") in (None, ""):
            continue
        level = row["level"]
        asset["level"] = level
        points = asset.get("points") or []
        if points:
            points[-1]["price"] = level
            prior = points[-2]["price"] if len(points) >= 2 else None
            if prior not in (None, 0):
                asset["changePct"] = round(100.0 * (float(level) / float(prior) - 1), 2)


def story_family(title: str) -> str:
    """A topic key for rows that are the same story even when the wording diverges."""
    blob = title or ""
    if re.search(r"\bg7\b", blob, re.I):
        return "g7"
    if re.search(r"white house", blob, re.I) and re.search(r"\b(letter|investigat\w*|garcia)\b", blob, re.I):
        return "wh-letter"
    if re.search(r"\biran\b", blob, re.I) and re.search(r"\b(war|strike|nuclear|tehran)\b", blob, re.I):
        return "iran-war"
    if re.search(r"\bmidterms?\b", blob, re.I):
        return "midterm"
    if re.search(r"\bukraine\b", blob, re.I) and re.search(r"\b(talks|zelensky|kushner|witkoff|abu dhabi)\b", blob, re.I):
        return "ukraine-talks"
    return ""


def topic_still_live(title: str, rows: list | None) -> bool:
    fam = story_family(title)
    if not fam:
        return False
    return any(story_family(row.get("title") or "") == fam for row in rows or [])


def vix_zone(level: float | None) -> str:
    if level is None:
        return ""
    if level < 15:
        return "below 15"
    if level <= 25:
        return "15 to 25"
    return "above 25"


def parse_bis_rates(csv_text: str) -> dict[str, dict]:
    rows = list(csv.DictReader(io.StringIO(csv_text or "")))
    out = {}
    for row in rows:
        area = (row.get("REF_AREA") or "").strip()
        value = row.get("OBS_VALUE")
        period = row.get("TIME_PERIOD") or ""
        if not area or value in (None, ""):
            continue
        try:
            number = float(value)
        except ValueError:
            continue
        out[area] = {"value": number, "asOf": period, "source": "BIS WS_CBPOL"}
    return out


def parse_mof_jgb_10y(csv_text: str) -> dict | None:
    lines = [line for line in (csv_text or "").splitlines() if re.match(r"\d{4}/\d{1,2}/\d{1,2},", line.strip())]
    if not lines:
        return None
    bits = lines[-1].split(",")
    if len(bits) < 11:
        return None
    try:
        value = float(bits[10])
    except ValueError:
        return None
    year, month, day = bits[0].split("/")
    return {"value": value, "asOf": f"{int(year):04d}-{int(month):02d}-{int(day):02d}", "source": "Japan Ministry of Finance JGB"}


def parse_fred_last(csv_text: str) -> dict | None:
    rows = list(csv.reader(io.StringIO(csv_text or "")))
    for row in reversed(rows[1:]):
        if len(row) < 2 or row[1] in {"", "."}:
            continue
        try:
            return {"value": float(row[1]), "asOf": row[0], "source": "FRED"}
        except ValueError:
            continue
    return None


def macro_is_fresh(previous: dict | None, today: str, days: int = 7) -> bool:
    stamp = str((previous or {}).get("checkedAt") or "")[:10]
    if len(stamp) < 10 or len(today) < 10:
        return False
    try:
        age = (datetime.fromisoformat(today) - datetime.fromisoformat(stamp)).days
    except ValueError:
        return False
    return 0 <= age < days


def refresh_macro(previous: dict | None, today: str, fetch) -> dict:
    """Keep last good macro values. Refetch only when the file is 7 days old or missing."""
    if macro_is_fresh(previous, today):
        return previous or {"regions": {}, "gaps": []}
    gaps = list((previous or {}).get("gaps") or [])
    regions = dict((previous or {}).get("regions") or {})
    try:
        rates = parse_bis_rates(fetch("https://stats.bis.org/api/v1/data/WS_CBPOL/M.JP+IN+US+XM+CN+BR+RU+CA+MX/all?format=csv&lastNObservations=1"))
    except Exception as err:
        gaps.append(f"BIS policy rates: {err}")
        rates = {}
    labels = {"US": "usa", "JP": "japan", "IN": "india", "XM": "europe", "CN": "china", "BR": "latin-america", "RU": "russia", "CA": "north-america", "MX": "north-america"}
    for code, region in labels.items():
        rate = rates.get(code)
        if not rate:
            continue
        text = f"{rate['value']}% as of {rate['asOf']}"
        row = regions.setdefault(region, {})
        if region == "north-america" and code == "MX":
            row["policy"] = (row.get("policy") or "") + f"; Mexico {text}"
        elif region == "north-america":
            row["policy"] = f"Canada {text}"
        else:
            row["policy"] = text
    return {"checkedAt": today, "regions": regions, "gaps": gaps[-8:], "note": "Slow figures refresh when older than 7 days. Last good value is kept when a source fails."}


def window_change(points: list[dict], sessions: int) -> float | None:
    usable = [point for point in points or [] if point.get("price") not in (None, "")]
    if len(usable) <= sessions:
        return None
    last = float(usable[-1]["price"])
    prev = float(usable[-1 - sessions]["price"])
    if prev == 0:
        return None
    return round(100.0 * (last - prev) / prev, 2)


def basis_change(points: list[dict], sessions: int) -> float | None:
    """Change in basis points when the series is already a percent yield."""
    usable = [point for point in points or [] if point.get("price") not in (None, "")]
    if len(usable) <= sessions:
        return None
    return round((float(usable[-1]["price"]) - float(usable[-1 - sessions]["price"])) * 100, 1)


def _pearson(xs: list[float], ys: list[float]) -> float | None:
    n = min(len(xs), len(ys))
    if n < 5:
        return None
    xs, ys = xs[:n], ys[:n]
    mx, my = sum(xs) / n, sum(ys) / n
    num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    dx = sum((x - mx) ** 2 for x in xs) ** 0.5
    dy = sum((y - my) ** 2 for y in ys) ** 0.5
    if dx == 0 or dy == 0:
        return None
    return round(num / (dx * dy), 2)


def return_corr(metal: list[dict], driver: list[dict], sessions: int) -> float | None:
    def rets(points):
        out = []
        prev = None
        for point in points or []:
            price = point.get("price")
            if price in (None, ""):
                continue
            if prev not in (None, 0):
                out.append((point.get("date"), (float(price) / float(prev) - 1) * 100))
            prev = price
        return out[-sessions:]
    left, right = rets(metal), dict(rets(driver))
    xs, ys = [], []
    for day, value in left:
        if day in right:
            xs.append(value)
            ys.append(right[day])
    return _pearson(xs, ys)


def implied_funds_rate(futures_price: float | None) -> float | None:
    if futures_price is None:
        return None
    return round(100.0 - float(futures_price), 3)


def curve_flag(value: float | None) -> str:
    if value is None:
        return ""
    return "inverted" if value < 0 else "positive"


def wiki_confirms(title: str, page_text: str) -> bool:
    blob = (page_text or "").lower()
    skip = {"drone", "strike", "strikes", "ukraine", "russia", "russian", "reuters", "police", "military", "oil", "terminal"}
    for match in re.finditer(r"\b[A-Z][A-Za-z-]{4,}\b", title or ""):
        name = match.group(0)
        if name.lower() in skip:
            continue
        if name.lower() in blob:
            return True
    return False


def _topic_key(row: dict) -> str:
    return (row.get("kind") or row.get("topic") or "other").lower()


def update_trendlog(previous: dict | None, history: dict | None, today: str, threats: list | None = None) -> tuple[dict, list]:
    """90-day topic rows, 14-day cluster rows, pruned after 30 quiet days, capped near 300 KB."""
    topics = [dict(row) for row in ((previous or {}).get("topics") or [])]
    states = dict((previous or {}).get("states") or {})
    if not topics:
        for snap in (history or {}).get("days") or []:
            day = snap.get("date") or ""
            if not day:
                continue
            buckets: dict[str, dict] = {}
            for row in snap.get("threats") or []:
                key = _topic_key(row)
                bucket = buckets.setdefault(key, {"count": 0, "severity": "STANDBY"})
                bucket["count"] += 1
                if (row.get("severity") or "") in {"ALERT", "ACTION", "CRITICAL"}:
                    bucket["severity"] = row.get("severity")
            for key, bucket in buckets.items():
                topics.append({"date": day, "topic": key, "count": bucket["count"], "outlets": bucket["count"], "countries": 1, "severity": bucket["severity"], "keywords": [], "score": 0})
    if threats:
        buckets = {}
        for row in threats:
            key = _topic_key(row)
            bucket = buckets.setdefault(key, {"count": 0, "severity": "STANDBY", "keywords": []})
            bucket["count"] += 1
            title = row.get("title") or ""
            for word in ("evacuat", "state of emergency", "mobiliz", "martial law", "nuclear", "curfew", "no-fly", "embassy closure", "blackout", "ceasefire collapses"):
                if word in title.lower() and word not in bucket["keywords"]:
                    bucket["keywords"].append(word)
            if (row.get("severity") or "") in {"ALERT", "ACTION", "CRITICAL"}:
                bucket["severity"] = row.get("severity")
        topics = [row for row in topics if row.get("date") != today]
        for key, bucket in buckets.items():
            topics.append({"date": today, "topic": key, "count": bucket["count"], "outlets": bucket["count"], "countries": 1, "severity": bucket["severity"], "keywords": bucket["keywords"], "score": 0})
    cutoff = ""
    try:
        cutoff = (datetime.fromisoformat(today) - timedelta(days=90)).date().isoformat()
    except ValueError:
        cutoff = ""
    if cutoff:
        topics = [row for row in topics if (row.get("date") or "") >= cutoff]
    last_seen: dict[str, str] = {}
    for row in topics:
        last_seen[row.get("topic") or ""] = max(last_seen.get(row.get("topic") or "", ""), row.get("date") or "")
    quiet_after = ""
    try:
        quiet_after = (datetime.fromisoformat(today) - timedelta(days=30)).date().isoformat()
    except ValueError:
        quiet_after = ""
    if quiet_after:
        topics = [row for row in topics if last_seen.get(row.get("topic") or "", "") >= quiet_after]
    topics.sort(key=lambda row: (row.get("date") or "", row.get("topic") or ""))
    encoded = json.dumps(topics)
    while len(encoded.encode("utf-8")) > 300_000 and topics:
        topics.pop(0)
        encoded = json.dumps(topics)
    cluster_start = ""
    try:
        cluster_start = (datetime.fromisoformat(today) - timedelta(days=14)).date().isoformat()
    except ValueError:
        cluster_start = ""
    clusters = [row for row in topics if not cluster_start or (row.get("date") or "") >= cluster_start]
    items = []
    changes = []
    topics_today = sorted({row.get("topic") for row in topics if row.get("date") == today})
    for topic in topics_today:
        rows = [row for row in topics if row.get("topic") == topic]
        counts = [row.get("count") or 0 for row in rows]
        today_count = counts[-1] if counts else 0
        week = counts[-8:-1] or counts[:-1] or [0]
        week_avg = sum(week) / len(week)
        avg3 = sum(counts[-3:]) / max(1, len(counts[-3:]))
        avg14 = sum(counts[-14:]) / max(1, len(counts[-14:]))
        score = rising_volume_points(today_count, week_avg)
        reasons = []
        ratio = round((today_count + 1) / (week_avg + 1), 1)
        if score:
            reasons.append(f"{ratio}x usual volume")
        keywords = rows[-1].get("keywords") or []
        if keywords:
            score += min(4, 2 * len(keywords))
            reasons.append("'" + keywords[0] + "' appeared")
        if (rows[-1].get("outlets") or 0) >= 5:
            score += 1
            reasons.append("5 or more outlets")
        first = rows[0].get("date") or today
        try:
            age = (datetime.fromisoformat(today) - datetime.fromisoformat(first)).days
        except ValueError:
            age = 99
        state = rising_state(score, first_seen_days=age, rising_before=states.get(topic) in {"RISING", "PEAKING", "EMERGING"}, today=today_count, avg3=avg3, avg14=avg14, max90=max(counts or [0]), severity_step_days=0)
        if not state:
            continue
        items.append({"topic": topic, "state": state, "score": score, "reasons": " · ".join(reasons), "spark": [{"price": row.get("count") or 0} for row in rows[-14:]]})
        if states.get(topic) != state:
            changes.append({"title": f"{topic} is {state}", "section": "Rising situations", "change": "updated", "severity": "ALERT", "note": " · ".join(reasons), "date": today})
        states[topic] = state
    return {"topics": topics, "clusters": clusters, "states": states, "checkedAt": today}, items, changes


def collect_drivers(yahoo, fetch_text, energy_strikes: int = 0) -> dict:
    """1W/1M/3M/1Y changes, correlations, funds futures, the curve, and ETF volume."""
    symbols = {
        "Gold": ("GC=F", False), "Silver": ("SI=F", False), "DXY": ("DX-Y.NYB", False),
        "10Y": ("^TNX", True), "S&P": ("^GSPC", False), "VIX": ("^VIX", False),
        "Copper": ("HG=F", False), "Brent": ("BZ=F", False), "WTI": ("CL=F", False),
        "ZQF27": ("ZQF27.CBT", False), "ZQH27": ("ZQH27.CBT", False),
        "GLD": ("GLD", False), "SLV": ("SLV", False), "GOLDBEES": ("GOLDBEES.NS", False),
    }
    series = {}
    gaps = []
    for name, (symbol, _yield) in symbols.items():
        quote = yahoo(symbol, "2y", "America/New_York") or {}
        points = quote.get("points") or []
        if not points:
            gaps.append(f"{name}: no points")
        series[name] = points
    for name, series_id in (("Real 10Y", "DFII10"), ("DFF", "DFF"), ("T10Y2Y", "T10Y2Y"), ("T10Y3M", "T10Y3M")):
        try:
            points = []
            text = fetch_text(f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series_id}")
            for row in parse_fred_rows(text):
                points.append(row)
            series[name] = points
        except Exception as err:
            gaps.append(f"{name}: {err}")
            series[name] = []
    silver = {point["date"]: point["price"] for point in series.get("Silver") or []}
    series["Gold/silver"] = [
        {"date": point["date"], "price": round(point["price"] / silver[point["date"]], 4)}
        for point in series.get("Gold") or []
        if silver.get(point["date"])
    ]
    copper = {point["date"]: point["price"] for point in series.get("Copper") or []}
    series["Copper/gold"] = [
        {"date": point["date"], "price": round(copper[point["date"]] / point["price"], 6)}
        for point in series.get("Gold") or []
        if copper.get(point["date"]) and point.get("price")
    ]
    order = ["Gold", "Silver", "DXY", "10Y", "Real 10Y", "S&P", "VIX", "Copper", "Gold/silver"]
    rows = [driver_row(name, series[name], yield_series=name in {"10Y", "Real 10Y"}) for name in order if series.get(name)]
    corrs = []
    for metal in ("Gold", "Silver"):
        for row in metal_correlations(series.get(metal) or [], {key: series.get(key) or [] for key in ("DXY", "10Y", "Real 10Y", "S&P", "VIX", "Copper")}):
            row["metal"] = metal
            corrs.append(row)
    def last(name):
        points = series.get(name) or []
        return points[-1]["price"] if points else None
    funds = {"dff": last("DFF"), "zqf": implied_funds_rate(last("ZQF27")), "zqh": implied_funds_rate(last("ZQH27"))}
    curve = []
    for name in ("T10Y2Y", "T10Y3M"):
        points = series.get(name) or []
        if not points:
            continue
        value = points[-1]["price"]
        curve.append({"name": name, "value": value, "flag": curve_flag(value), "inverted": value < 0, "spark": [{"price": point["price"]} for point in points[-30:]]})
    volumes = [{"name": name, "price": last(name), "volume": (series.get(name) or [{}])[-1].get("volume")} for name in ("GLD", "SLV", "GOLDBEES") if series.get(name)]
    return {
        "rows": rows,
        "correlations": corrs,
        "funds": funds,
        "curve": curve,
        "copperGold": {"ratio": last("Copper/gold") if False else ((series.get("Copper/gold") or [{}])[-1].get("price") if series.get("Copper/gold") else None), "yield10": last("10Y")},
        "volumes": volumes,
        "oil": {"brent": last("Brent"), "wti": last("WTI"), "energyStrikes": energy_strikes},
        "gaps": gaps,
    }


def parse_fred_rows(csv_text: str) -> list[dict]:
    points = []
    for row in (csv_text or "").splitlines()[1:]:
        bits = row.split(",")
        if len(bits) < 2 or bits[1] in {"", "."}:
            continue
        try:
            points.append({"date": bits[0], "price": float(bits[1])})
        except ValueError:
            continue
    return points


def driver_row(name: str, points: list[dict], *, yield_series: bool = False) -> dict:
    usable = [point for point in points or [] if point.get("price") not in (None, "")]
    level = None if not usable else round(float(usable[-1]["price"]), 4)
    changes = {
        "1W": window_change(usable, 5),
        "1M": window_change(usable, 21),
        "3M": window_change(usable, 63),
        "1Y": window_change(usable, 252),
    }
    if yield_series:
        changes = {key: basis_change(usable, sessions) for key, sessions in (("1W", 5), ("1M", 21), ("3M", 63), ("1Y", 252))}
    return {"name": name, "level": level, "changes": changes, "spark": [{"price": point["price"]} for point in usable[-30:]], "unit": "bp" if yield_series else "%"}


def metal_correlations(metal_points: list[dict], drivers: dict[str, list[dict]]) -> list[dict]:
    rows = []
    for name, points in drivers.items():
        rows.append({
            "driver": name,
            "d30": return_corr(metal_points, points, 30),
            "d90": return_corr(metal_points, points, 90),
        })
    return rows


def moex_level(payload: dict) -> dict | None:
    """IMOEX from the MOEX ISS payload. Yahoo's IMOEX.ME symbol 404s."""
    for block in (payload or {}).values():
        if not isinstance(block, dict):
            continue
        cols = block.get("columns") or []
        data = block.get("data") or []
        if not cols or not data:
            continue
        row = dict(zip(cols, data[0]))
        for key in ("CURRENTVALUE", "LASTVALUE", "LAST", "CLOSE"):
            if row.get(key) not in (None, ""):
                try:
                    price = float(row[key])
                except (TypeError, ValueError):
                    continue
                prev = None
                for pkey in ("PREVPRICE", "OPENVALUE", "OPEN"):
                    if row.get(pkey) not in (None, ""):
                        try:
                            prev = float(row[pkey])
                        except (TypeError, ValueError):
                            prev = None
                        break
                change = None if prev in (None, 0) else round(price - prev, 2)
                pct = None if change is None else round(100.0 * change / prev, 2)
                return {
                    "level": round(price, 2),
                    "change": change,
                    "changePct": pct,
                    "source": "https://iss.moex.com/iss/engines/stock/markets/index/securities/IMOEX.json",
                }
    return None


GDACS_GEOJSON = "https://www.gdacs.org/gdacsapi/api/events/geteventlist/events4app"
RELIEF_DISASTERS = "https://reliefweb.int/disasters"
WHO_DON = "https://www.who.int/api/news/diseaseoutbreaknews?$orderby=PublicationDate%20desc&$top=12"
CDC_HAN_RSS = "https://tools.cdc.gov/api/v2/resources/media/413690.rss"
CDC_HAN_ARCHIVE = "https://www.cdc.gov/han/php/notices/index.html"
CDC_HAN_EMPTY = (
    "CDC HAN: the official syndication feed answered with no notices, "
    "and the archive page did not answer."
)

_MONTHS = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}
_SEV_RANK = {"STANDBY": 0, "ALERT": 1, "ACTION": 2, "CRITICAL": 3}


def _day_shift(day: str, days: int) -> str:
    return (datetime.fromisoformat(day[:10]) - timedelta(days=days)).strftime("%Y-%m-%d")


def _plain(value: str) -> str:
    text = re.sub(r"<[^>]+>", " ", value or "")
    return re.sub(r"\s+", " ", text).strip()


def gdacs_severity(level: str) -> str:
    name = (level or "").lower()
    if "red" in name:
        return "CRITICAL"
    if "orange" in name:
        return "ACTION"
    return "ALERT"


def parse_gdacs_events(payload: dict | None, today: str, limit: int = 8) -> list[dict]:
    """Current GDACS events. Orange and red stay; a green event is kept only if it started within 14 days."""
    cutoff = _day_shift(today, 14)
    rows = []
    seen = set()
    for feature in (payload or {}).get("features") or []:
        props = feature.get("properties") or {}
        title = _plain(props.get("name") or props.get("description") or "")
        link_field = props.get("url") or {}
        link = link_field.get("report") if isinstance(link_field, dict) else str(link_field or "")
        link = link.strip()
        if not title or not link.startswith("http") or link in seen:
            continue
        level = props.get("episodealertlevel") or props.get("alertlevel") or ""
        severity = gdacs_severity(level)
        started = str(props.get("fromdate") or "")[:10]
        # The desk only shows the current year, so a drought that began earlier stays off this board.
        if started[:4] != today[:4]:
            continue
        if severity == "ALERT" and started < cutoff:
            continue
        seen.add(link)
        point = ((feature.get("geometry") or {}).get("coordinates") or [None, None])
        lat = lon = None
        try:
            if len(point) >= 2 and point[0] is not None and point[1] is not None:
                lon, lat = float(point[0]), float(point[1])
        except (TypeError, ValueError):
            lat = lon = None
        country = props.get("country") or ""
        note = f"{level or 'Green'} alert. {country}".strip()
        rows.append({
            "title": title,
            "url": link,
            "date": started or str(props.get("datemodified") or "")[:10] or today,
            "severity": severity,
            "note": note[:500],
            "lat": lat,
            "lon": lon,
        })
    rows.sort(key=lambda row: (_SEV_RANK.get(row["severity"], 0), row.get("date") or ""), reverse=True)
    return rows[:limit]


def relief_severity(status: str) -> str:
    name = (status or "").lower()
    if name == "alert":
        return "ACTION"
    if name in {"past", "archive", "closed"}:
        return "STANDBY"
    return "ALERT"


def _relief_day(title: str, blurb: str, today: str) -> str:
    named = re.search(r"(\d{1,2})\s+([A-Za-z]{3,9})\s+(20\d{2})", f"{blurb} {title}")
    if named and named.group(2).lower()[:3] in _MONTHS:
        month = _MONTHS[named.group(2).lower()[:3]]
        day = min(int(named.group(1)), 28)
        return f"{int(named.group(3)):04d}-{month:02d}-{day:02d}"
    month_only = re.search(r"-\s+([A-Za-z]{3,9})\s+(20\d{2})\s*$", title or "")
    if month_only and month_only.group(1).lower()[:3] in _MONTHS:
        month = _MONTHS[month_only.group(1).lower()[:3]]
        return f"{int(month_only.group(2)):04d}-{month:02d}-01"
    return today


def parse_relief_disasters(html: str, today: str, limit: int = 8) -> list[dict]:
    """Primary cards on the public disasters page. Related-disaster links inside a card are not separate rows."""
    rows = []
    seen = set()
    for match in re.finditer(r'<article class="rw-disaster-map__article\b[^"]*"(.*?)</article>', html or "", re.S | re.I):
        block = match.group(0)
        opening = match.group(1)
        href = re.search(r'<h3[^>]*>\s*<a href="(https://reliefweb\.int/disaster/[^"]+)"', block, re.S)
        title_match = re.search(r'<h3[^>]*>\s*<a[^>]*>(.*?)</a>', block, re.S)
        if not href or not title_match:
            continue
        url = href.group(1)
        title = _plain(title_match.group(1))
        if not title or url in seen:
            continue
        seen.add(url)
        status = ""
        status_match = re.search(r'data-disaster-status="([^"]+)"', opening)
        if status_match:
            status = status_match.group(1)
        blurb_match = re.search(r"<p>(.*?)</p>", block, re.S)
        blurb = _plain(blurb_match.group(1) if blurb_match else "")
        lat = lon = None
        lat_match = re.search(r'data-disaster-lat="([^"]+)"', opening)
        lon_match = re.search(r'data-disaster-lon="([^"]+)"', opening)
        try:
            if lat_match and lon_match:
                lat, lon = float(lat_match.group(1)), float(lon_match.group(1))
        except ValueError:
            lat = lon = None
        rows.append({
            "title": title,
            "url": url,
            "date": _relief_day(title, blurb, today),
            "severity": relief_severity(status),
            "note": blurb[:500],
            "lat": lat,
            "lon": lon,
        })
        if len(rows) >= limit:
            break
    return rows


def who_severity(title: str) -> str:
    if re.search(r"outbreak|cases|deaths|epidemic|disease|virus|fever", title or "", re.I):
        return "ALERT"
    return "STANDBY"


def parse_who_dons(payload: dict | None, today: str, days: int = 14, limit: int = 6) -> list[dict]:
    cutoff = _day_shift(today, days)
    rows = []
    seen = set()
    for item in (payload or {}).get("value") or []:
        title = item.get("OverrideTitle") if item.get("UseOverrideTitle") and item.get("OverrideTitle") else (item.get("Title") or "")
        title = _plain(title)
        if not title or re.search(r"covid|technical package|data for covid", title, re.I):
            continue
        slug = str(item.get("ItemDefaultUrl") or item.get("UrlName") or "").strip().strip("/")
        if not slug:
            continue
        url = "https://www.who.int/emergencies/disease-outbreak-news/item/" + slug
        day = str(item.get("PublicationDate") or item.get("PublicationDateAndTime") or "")[:10]
        if not day or day < cutoff or url in seen:
            continue
        seen.add(url)
        rows.append({
            "title": title,
            "url": url,
            "date": day,
            "severity": who_severity(title),
            "note": _plain(item.get("Summary") or "")[:500],
        })
        if len(rows) >= limit:
            break
    return rows


def cdc_han_severity(title: str) -> str:
    blob = title or ""
    if re.search(r"\bhealth alert\b", blob, re.I):
        return "ACTION"
    if re.search(r"\bhealth advisory\b", blob, re.I):
        return "ALERT"
    if re.search(r"\b(health update|info service)\b", blob, re.I):
        return "STANDBY"
    if re.search(r"health alert network|\bHAN\b|\bCDCHAN\b", blob, re.I):
        return "ACTION"
    return "ALERT"


def _rfc_day(value: str) -> str:
    match = re.search(r"(\d{1,2})\s+([A-Za-z]{3})\s+(\d{4})", value or "")
    if not match or match.group(2).lower() not in _MONTHS:
        return ""
    return f"{int(match.group(3)):04d}-{_MONTHS[match.group(2).lower()]:02d}-{int(match.group(1)):02d}"


def parse_cdc_han_rss(xml_text: str, today: str, days: int = 14, limit: int = 5) -> list[dict]:
    try:
        root = ET.fromstring(xml_text or "")
    except ET.ParseError:
        return []
    cutoff = _day_shift(today, days)
    rows = []
    seen = set()
    for node in root.iter("item"):
        title = _plain(node.findtext("title") or "")
        link = (node.findtext("link") or "").strip()
        if not title or not link.startswith("http") or link in seen:
            continue
        day = _rfc_day(node.findtext("pubDate") or "")
        if day and day < cutoff:
            continue
        seen.add(link)
        desc = _plain(node.findtext("description") or "")
        rows.append({
            "title": title,
            "url": link,
            "date": day or today,
            "severity": cdc_han_severity(title),
            "note": desc[:500],
        })
        if len(rows) >= limit:
            break
    return rows


def parse_cdc_archive(html: str, limit: int = 8) -> list[dict]:
    """Notice links on the HAN archive page. An access-denied page has none."""
    if re.search(r"access denied", (html or "")[:800], re.I):
        return []
    rows = []
    seen = set()
    for href, raw in re.findall(r'<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>', html or "", re.S | re.I):
        title = _plain(raw)
        if not re.search(r"\b(?:HAN|CDCHAN)[-\s]?\d{3,}|Health Alert\b|Health Advisory\b", title, re.I):
            continue
        if not re.search(r"han", href, re.I):
            continue
        if href.startswith("/"):
            href = "https://www.cdc.gov" + href
        if not href.startswith("http") or href in seen:
            continue
        seen.add(href)
        rows.append({
            "title": title,
            "url": href,
            "date": "",
            "severity": cdc_han_severity(title),
            "note": "",
        })
        if len(rows) >= limit:
            break
    return rows
