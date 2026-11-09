"""Nov 17, 2026 blackout-rumor watch.

The only scheduled event is the FEMA/FCC Emergency Alert System test.
Rumor volume never raises the status. A verified US or Tennessee outage does.
"""
from __future__ import annotations

from datetime import date, datetime

import desklib as d

EVENT = date(2026, 11, 17)
BACKUP = date(2026, 12, 3)
EXPIRE = date(2026, 11, 18)
LIVE_FROM = date(2026, 11, 14)
LIVE_TO = date(2026, 11, 18)

FACT_CHECKS = (
    ("Prepared States", "https://www.preparedstates.com/guides/november-17-blackout"),
    ("LB.ua disinformation centre", "https://en.lb.ua/news/2026/11/09/48708_disinformation_centre_debunks.html"),
    ("Blackout map", "https://blackoutmap.net/blog/global-blackout-november-rumour"),
    ("Krakobit", "https://krakobit.com/news/internet-shutdown-rumor-november-17/"),
)


def watch_state(day: date, postponed: bool = False) -> dict:
    """Whether the card is on the desk, and how many days remain until Nov 17."""
    expire = BACKUP if postponed else EXPIRE
    live_end = BACKUP if postponed else LIVE_TO
    return {
        "visible": day <= expire,
        "expires": expire.isoformat(),
        "daysUntil": (EVENT - day).days,
        "eventDate": EVENT.isoformat(),
        "backupDate": BACKUP.isoformat(),
        "postponed": bool(postponed),
        "liveWindow": LIVE_FROM <= day <= live_end,
    }


def severity_for(signals: list[dict]) -> str:
    """Rumor posts stay STANDBY. A verified US or Tennessee outage is ACTION."""
    for signal in signals or []:
        if signal.get("verifiedOutage"):
            return "ACTION"
    return "STANDBY"


def _postponed(headlines: list[dict]) -> bool:
    for row in headlines or []:
        blob = f"{row.get('title') or ''} {row.get('note') or ''}"
        if re_postponed(blob):
            return True
    return False


def re_postponed(blob: str) -> bool:
    import re
    return bool(re.search(r"postpon|reschedul|delayed|moved to", blob or "", re.I) and re.search(
        r"alert|EAS|emergency alert|test", blob or "", re.I
    ))


def _ioda_us(now: datetime) -> dict:
    import boards
    until = int(now.timestamp())
    start = until - 6 * 3600
    url = (
        "https://api.ioda.inetintel.cc.gatech.edu/v2/outages/alerts"
        f"?from={start}&until={until}&entityType=country&entityCode=US"
    )
    try:
        import json
        payload = json.loads(boards._get(url, timeout=25, headers={"Accept": "application/json"}))
    except Exception as err:
        return {"source": "IODA", "ok": False, "note": f"IODA did not answer: {err}", "verifiedOutage": False}
    hits = []
    for row in payload.get("data") or []:
        entity = row.get("entity") or {}
        if str(entity.get("type") or "") != "country":
            continue
        if str(entity.get("code") or "").upper() not in {"US", "USA"}:
            continue
        if str(row.get("level") or "").lower() in {"critical", "warning"}:
            hits.append(row)
    if hits:
        return {
            "source": "IODA",
            "ok": True,
            "note": f"IODA reports {len(hits)} warning-level alert(s) for the United States.",
            "verifiedOutage": True,
            "url": "https://ioda.inetintel.cc.gatech.edu/",
        }
    return {
        "source": "IODA",
        "ok": True,
        "note": "IODA shows no country-level US outage alert in the last 6 hours.",
        "verifiedOutage": False,
        "url": "https://ioda.inetintel.cc.gatech.edu/",
    }


def _cloudflare() -> dict:
    import boards
    url = "https://api.cloudflare.com/client/v4/radar/annotations/outages?dateRange=1d"
    try:
        boards._get(url, timeout=15, headers={"Accept": "application/json"})
    except Exception as err:
        return {
            "source": "Cloudflare Radar",
            "ok": False,
            "note": f"Cloudflare Radar is not available without a key ({err}).",
            "verifiedOutage": False,
        }
    return {
        "source": "Cloudflare Radar",
        "ok": True,
        "note": "Cloudflare Radar answered. This desk does not treat a company status page as a national outage.",
        "verifiedOutage": False,
        "url": "https://radar.cloudflare.com/",
    }


def _local_outage(local: dict | None) -> dict:
    import re
    for item in (local or {}).get("items") or []:
        blob = f"{item.get('title') or ''} {item.get('note') or ''}"
        if item.get("kind") == "na":
            continue
        if re.search(r"no active nws|0 customers affected|row hidden", blob, re.I):
            continue
        if item.get("severity") in {"ACTION", "CRITICAL"} and re.search(r"outage|blackout|power", blob, re.I):
            return {
                "source": item.get("source") or "Local",
                "ok": True,
                "note": item.get("title") or "Local outage alert",
                "verifiedOutage": True,
                "url": item.get("url") or "",
            }
    return {
        "source": "Local power and NWS",
        "ok": True,
        "note": "No TVA, Middle Tennessee Electric, or NWS outage alert for 37179 on this pull.",
        "verifiedOutage": False,
    }


def fetch_blackout(now: datetime, local: dict | None = None, rumor_samples: list | None = None, rumor_note: str = "") -> dict:
    """Build the card. Live feeds run only inside the watch window."""
    state = watch_state(now.date(), postponed=False)
    signals = []
    gaps = []
    headlines = []
    if state["liveWindow"]:
        import boards
        try:
            rumor = boards._headlines('"November 17" (blackout OR "internet shutdown") when:3d', now, retain_days=5, limit=6)
        except Exception as err:
            rumor = []
            gaps.append(f"Blackout rumor search: {err}")
            signals.append({"source": "Google News", "ok": False, "note": f"Rumor search did not answer: {err}", "verifiedOutage": False})
        else:
            signals.append({
                "source": "Google News",
                "ok": True,
                "note": f"{len(rumor)} recent headlines mention a November 17 blackout. Volume alone is not an outage.",
                "verifiedOutage": False,
                "samples": [{"title": row.get("title"), "url": row.get("url"), "source": row.get("source")} for row in rumor[:3]],
            })
        try:
            eas = boards._headlines('(FEMA OR FCC) ("Emergency Alert System" OR EAS) test when:14d', now, retain_days=21, limit=6)
        except Exception as err:
            eas = []
            gaps.append(f"EAS test search: {err}")
            signals.append({"source": "EAS test", "ok": False, "note": f"EAS status search did not answer: {err}", "verifiedOutage": False})
        else:
            headlines = eas
            signals.append({
                "source": "EAS test",
                "ok": True,
                "note": "FEMA/FCC test headlines checked for a postponement.",
                "verifiedOutage": False,
                "samples": [{"title": row.get("title"), "url": row.get("url"), "source": row.get("source")} for row in eas[:2]],
            })
        ioda = _ioda_us(now)
        signals.append(ioda)
        if not ioda.get("ok"):
            gaps.append(ioda.get("note") or "IODA did not answer")
        cloud = _cloudflare()
        signals.append(cloud)
        if not cloud.get("ok"):
            gaps.append(cloud.get("note") or "Cloudflare Radar did not answer")
        signals.append(_local_outage(local))
        if rumor_note:
            signals.append({"source": "X", "ok": True, "note": rumor_note, "verifiedOutage": False, "samples": rumor_samples or []})
    else:
        signals.append({
            "source": "Live checks",
            "ok": True,
            "note": "Rumor, outage, and EAS checks run on refreshes from Nov 14 through Nov 18.",
            "verifiedOutage": False,
        })
    postponed = _postponed(headlines)
    state = watch_state(now.date(), postponed=postponed)
    severity = severity_for(signals) if state["visible"] else "STANDBY"
    samples = []
    for signal in signals:
        for sample in signal.get("samples") or []:
            if sample.get("url"):
                samples.append(sample)
    card = {
        "id": "blackout-nov-17",
        "kind": "blackout",
        "lane": "desk",
        "title": "Nov 17 blackout watch",
        "severity": severity,
        "url": FACT_CHECKS[0][1],
        "published": now.isoformat(timespec="seconds"),
        "date": now.strftime("%Y-%m-%d"),
        "label": d.ct_label(now, True),
        "source": "Desk",
        "soWhat": "Nothing special. Keep a normal 72-hour kit. No extra shopping.",
        "confidence": "reported",
        "sourceCount": 4,
    }
    if severity == "ACTION":
        card["soWhat"] = "A verified outage is reported for the US or Middle Tennessee. Read that source. The global-blackout rumor is still not a scheduled shutdown."
    return {
        "visible": state["visible"],
        "expires": state["expires"],
        "daysUntil": state["daysUntil"],
        "eventDate": state["eventDate"],
        "backupDate": state["backupDate"],
        "postponed": state["postponed"],
        "liveWindow": state["liveWindow"],
        "verdict": "Rumor: no blackout scheduled",
        "real": "FEMA/FCC nationwide Emergency Alert System test at about 2:20 PM ET (1:20 PM CT), radio and TV only, about one minute. The message is “This is only a test. No action is required.” Phones are not included. Backup date is Dec 3, 2026.",
        "action": card["soWhat"],
        "factChecks": [{"name": name, "url": url} for name, url in FACT_CHECKS],
        "signals": signals,
        "samples": samples[:4],
        "severity": severity,
        "gaps": gaps,
        "card": card,
    }
