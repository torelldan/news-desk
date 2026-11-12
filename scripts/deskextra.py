"""Nov 12 rules: local NWS scope, bar dates, macro, strikes, and rising scores.

Fetches fail soft. Nothing here needs a paid key or a new schedule.
"""
from __future__ import annotations

import csv
import io
import json
import re
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

TN_WILLIAMSON = {"187"}
TN_ADJACENT = {"037", "149", "119", "081", "043", "021"}  # Davidson, Rutherford, Maury, Hickman, Dickson, Cheatham

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


def strike_fields(title: str) -> dict:
    blob = title or ""
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
    for name in ("Ukraine", "Russia", "Iran", "Israel", "Syria", "Yemen", "Lebanon"):
        if re.search(rf"\b{name}\b", blob, re.I):
            country = name
            break
    return {"means": means, "target_type": target_type, "country": country}


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
    ratio = moves.get("gs_ratio")
    copper = moves.get("copper")
    if gold is not None and gold < 0 and dxy is not None and dxy >= 1 and ((y10 or 0) >= 15 or (real or 0) >= 15):
        lines.append(f"Gold {gold}% with DXY {dxy}% and yields up. Association, not proof: stronger dollar / higher rates.")
    if implied is not None and implied >= 15:
        lines.append(f"Fed-funds futures implied rate {implied} bp. Association, not proof: more rate-hike bets.")
    if vix is not None and vix <= -3 and spx is not None and spx > 0:
        lines.append(f"VIX {vix} pts and S&P {spx}%. Association, not proof: fear premium fading.")
    if brent is not None and brent <= -5 and deescalation:
        lines.append(f"Brent {brent}% beside a de-escalation headline. Association, not proof: war premium easing.")
    if ratio is not None and ratio >= 3 and copper is not None and copper < 0:
        lines.append(f"Gold/silver ratio {ratio} and copper {copper}%. Association, not proof: industrial worry is hitting silver harder.")
    return lines


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
                pct = None if not change else round(100.0 * change / prev, 2)
                return {
                    "level": round(price, 2),
                    "change": change,
                    "changePct": pct,
                    "source": "https://iss.moex.com/iss/engines/stock/markets/index/securities/IMOEX.json",
                }
    return None
