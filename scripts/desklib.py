#!/usr/bin/env python3
"""Pure helpers for the news desk. No network. Times are America/Chicago."""
from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from html import unescape
from zoneinfo import ZoneInfo

CT = ZoneInfo("America/Chicago")

NOTE_MARKERS = (
    "you might enjoy",
    "you might also enjoy",
    "learn more about your ad choices",
)
PROMO_SENTENCE = re.compile(
    r"(patreon|discord\.gg|newsletter\b|perplexity|#ad\b|ad choices|"
    r"use code |welcome kit|drinkag1|pplx\.ai|perfect jean|"
    r"subscribe to|follow (me|us|julian)|sponsors?\b|clippers discord|"
    r"for a limited time|% off|percent off|free shipping|promo code|with code |save \$|"
    r"see below for timestamps|thank you for listening|check out our sponsors)",
    re.I,
)
BOILERPLATE_CUTS = NOTE_MARKERS + (
    "thank you for listening",
    "see below for timestamps",
    "check out our sponsors",
    "check out my sponsors",
)
MONTHS = (
    "january", "february", "march", "april", "may", "june",
    "july", "august", "september", "october", "november", "december",
)
WEEKDAYS = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")


def to_ct(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(CT)


def parse_pubdate(raw: str) -> datetime | None:
    raw = (raw or "").strip()
    if not raw:
        return None
    try:
        return to_ct(parsedate_to_datetime(raw))
    except (TypeError, ValueError, IndexError, OverflowError):
        pass
    for fmt in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%d"):
        try:
            dt = datetime.strptime(raw.replace("Z", "+0000") if fmt.endswith("Z") else raw, fmt)
            return to_ct(dt)
        except ValueError:
            continue
    return None


def ct_label(dt: datetime, time_known: bool = True) -> str:
    dt = to_ct(dt)
    if time_known:
        return dt.strftime("%b %-d, %Y %-I:%M %p CT")
    return dt.strftime("%b %-d, %Y CT")


def strip_html(value: str) -> str:
    text = value or ""
    text = re.sub(r"(?is)<br\s*/?>", "\n", text)
    text = re.sub(r"(?is)</p>", "\n", text)
    text = re.sub(r"(?is)<[^>]+>", " ", text)
    text = unescape(text)
    text = text.replace("\xa0", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n+", " ", text)
    return text.strip()


def clean_note(value: str, limit: int = 900) -> str:
    """Official description only. Sponsor headers, timestamp lists, and cross-promo tails are cut."""
    text = strip_html(value)
    text = re.sub(r"\(\*+\s*timestamps[^)]*\)\s*~?\s*", " ", text, flags=re.I)
    text = re.sub(r"https?://\S+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    text = re.sub(r"\.([A-Z])", r". \1", text)
    low = text.lower()
    cut = len(text)
    for marker in BOILERPLATE_CUTS:
        idx = low.find(marker)
        if idx != -1:
            cut = min(cut, idx)
    stamp = re.search(r"\*{2,}\s*timestamps", text, flags=re.I)
    if stamp:
        cut = min(cut, stamp.start())
    text = text[:cut].strip(" -|•·:;,-")
    pieces = re.split(
        r"(?i)\b(?:sponsors?:?|join patreon|patreon:|clippers discord|newsletter:|"
        r"follow julian|follow danny|julian yt|subscribe to|episode links|"
        r"outline\b|\*{2,}\s*timestamps|\d+\)\s+)",
        text,
    )
    prose = []
    for piece in pieces:
        sentences = [part.strip(" -|•·:;,") for part in re.split(r"(?<=[.!?])\s+", piece) if part.strip()]
        kept = []
        for sentence in sentences:
            if len(sentence) < 40:
                continue
            if not re.search(r"[.!?]$", sentence):
                continue
            if PROMO_SENTENCE.search(sentence[:180]):
                continue
            kept.append(sentence)
            if len(kept) == 2:
                break
        if kept:
            prose.append(" ".join(kept))
            break
    if not prose:
        sentences = [part.strip() for part in re.split(r"(?<=[.!?])\s+", text) if part.strip()]
        leftovers = [sentence for sentence in sentences if len(sentence) >= 40 and not PROMO_SENTENCE.search(sentence[:140])]
        prose = leftovers[:2]
    chosen = " ".join(prose).strip(" -|•·:;,-")
    if len(chosen) > limit:
        chosen = chosen[:limit].rstrip() + "…"
    return chosen


def is_cross_promo(title: str, note: str) -> bool:
    """Skip items that are themselves cross-promos. A footer on a real episode is not one."""
    title_l = (title or "").lower()
    if "you might enjoy" in title_l or "you might also enjoy" in title_l:
        return True
    low = (note or "").lower()
    for marker in ("you might enjoy", "you might also enjoy"):
        idx = low.find(marker)
        if idx != -1 and idx < 24:
            return True
    return False


def title_skipped(title: str, needles: list[str]) -> bool:
    hay = (title or "").lower()
    return any((n or "").lower() in hay for n in needles if n)


def channel_rejected(channel_title: str, needles: list[str]) -> bool:
    hay = (channel_title or "").lower()
    return any((n or "").lower() in hay for n in needles if n)


def guest_from_title(title: str) -> str:
    text = re.sub(r"\s+", " ", title or "").strip()
    if "|" in text:
        tail = text.split("|")[-1].strip(" -–—")
        if tail and len(tail.split()) <= 6:
            return tail
    match = re.match(r"^#?\d+\s*[–—-]\s*(.+)$", text)
    if match:
        rest = match.group(1).strip()
        if ":" not in rest and len(rest.split()) <= 5:
            return rest
    match = re.match(
        r"^#\d+\s+([A-Z][\w.'’]+(?:\s+[A-Z][\w.'’]+){0,3})\s+[-–—]",
        text,
    )
    if match:
        return match.group(1).strip()
    return ""


def norm_text(value: str) -> str:
    text = (value or "").lower()
    text = re.sub(r"https?://\S+", " ", text)
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def episode_numbers(title: str) -> set[str]:
    return set(re.findall(r"\d+", title or ""))


def same_listing(a: dict, b: dict) -> bool:
    """Collapse a retitle of one episode. Keep numbered parts and later visits with the same bio."""
    left, right = episode_numbers(a.get("title") or ""), episode_numbers(b.get("title") or "")
    if left and right and left.isdisjoint(right):
        return False
    da, db = a.get("date") or "", b.get("date") or ""
    if da and db:
        try:
            gap = abs((datetime.fromisoformat(da).date() - datetime.fromisoformat(db).date()).days)
        except ValueError:
            gap = 0
        if gap > 3:
            return False
    return True


def fingerprint(item: dict) -> str:
    """Dedupe key uses the official note (and source), never the title."""
    note = norm_text(item.get("note") or "")[:400]
    source = item.get("sourceId") or ""
    if len(note) >= 80:
        return source + "|note|" + note
    return source + "|url|" + (item.get("url") or item.get("id") or "")


def dedupe_items(items: list[dict], seen: set[str] | None = None) -> list[dict]:
    seen = seen or set()
    groups: list[dict] = []
    for item in items:
        key = fingerprint(item)
        placed = False
        for group in groups:
            if group["key"] == key and all(same_listing(item, other) for other in group["rows"]):
                group["rows"].append(item)
                placed = True
                break
        if not placed:
            groups.append({"key": key, "rows": [item]})
    kept: list[dict] = []
    for group in groups:
        rows = group["rows"]
        known = [row for row in rows if row.get("id") in seen]
        pool = known or rows
        pool.sort(key=lambda row: row.get("published") or "", reverse=True)
        kept.append(pool[0])
    return kept


def unique_by_id(items: list[dict]) -> list[dict]:
    found: set[str] = set()
    out: list[dict] = []
    for item in items:
        ident = item.get("id") or ""
        if not ident or ident in found:
            continue
        found.add(ident)
        out.append(item)
    return out


def make_id(source_id: str, url: str) -> str:
    digest = hashlib.sha256(url.encode("utf-8")).hexdigest()[:16]
    return f"{source_id}:{digest}"


def slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", (value or "").lower()).strip("-")


def tags_for(item: dict, extra: list[str] | None = None) -> list[str]:
    tags: list[str] = []
    for bit in [item.get("lane"), item.get("sourceId"), *(extra or [])]:
        if bit and bit not in tags:
            tags.append(bit)
    guest = slug(item.get("guest") or "")
    if 2 <= len(guest) <= 40 and guest not in tags:
        tags.append(guest)
    return tags


def stable_page_text(html: str) -> str:
    """Text used for page-change hashes. Digits and calendar words are stripped so clocks don't flap."""
    text = html or ""
    text = re.sub(r"(?is)<script\b[^>]*>.*?</script>", " ", text)
    text = re.sub(r"(?is)<style\b[^>]*>.*?</style>", " ", text)
    text = re.sub(r"(?is)<noscript\b[^>]*>.*?</noscript>", " ", text)
    text = re.sub(r"(?is)<svg\b[^>]*>.*?</svg>", " ", text)
    text = re.sub(r"(?is)<iframe\b[^>]*>.*?</iframe>", " ", text)
    text = re.sub(r"(?is)<[^>]+>", " ", text)
    text = unescape(text).replace("\xa0", " ").lower()
    for word in MONTHS + WEEKDAYS:
        text = re.sub(rf"\b{word}\b", "#", text)
    text = re.sub(r"\d[\d,.:%+\-/]*", "#", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def page_hash(html: str) -> str:
    return hashlib.sha256(stable_page_text(html).encode("utf-8")).hexdigest()


def assert_public_x_path(path: str) -> str:
    """Allow only public user lookup and public tweet reads. Never DMs."""
    path = "/" + path.lstrip("/")
    lowered = path.lower()
    if "/dm" in lowered or "direct_message" in lowered or "dm_event" in lowered:
        raise RuntimeError("refusing X direct-message endpoint")
    if path == "/2/users/by" or re.fullmatch(r"/2/users/\d+/tweets", path):
        return path
    raise RuntimeError(f"refusing unexpected X path: {path}")


def http_url(value: str) -> str:
    value = (value or "").strip()
    if value.startswith("https://") or value.startswith("http://"):
        return value
    return ""
