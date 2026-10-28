#!/usr/bin/env python3
"""Fetch public podcast, Substack, site, and X sources into data/.

Read-only. Public posts only. This script never calls an X direct-message
endpoint and never reads private messages. If X_BEARER_TOKEN is missing, X is
skipped and the desk shows "X feed offline".
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import desklib as d

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
SOURCES_PATH = Path(__file__).resolve().parent / "sources.json"
UA = "news-desk/1.0 (+https://github.com/torelldan/news-desk)"
ITUNES = "{http://www.itunes.com/dtds/podcast-1.0.dtd}"
DC = "{http://purl.org/dc/elements/1.1/}"
CONTENT = "{http://purl.org/rss/1.0/modules/content/}encoded"
X_API = "https://api.x.com"
HUBERMAN_PAUSE = 0.3


def load_json(path: Path, default):
    if not path.exists():
        return default
    return json.loads(path.read_text())


def save_json(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text)
    tmp.replace(path)


def get_bytes(url: str, timeout: int = 45, headers: dict | None = None) -> tuple[bytes, str, int]:
    last = None
    for attempt in range(2):
        req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "*/*", **(headers or {})})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read(), resp.geturl(), getattr(resp, "status", 200)
        except urllib.error.HTTPError as err:
            if err.code < 500 and err.code != 429:
                raise
            last = err
        except (urllib.error.URLError, TimeoutError, ConnectionError) as err:
            last = err
        time.sleep(1.1 * (attempt + 1))
    raise last


def parse_xml(raw: bytes) -> ET.Element:
    if raw.startswith(b"\xef\xbb\xbf"):
        raw = raw[3:]
    try:
        return ET.fromstring(raw)
    except ET.ParseError:
        text = raw.decode("utf-8", "replace")
        text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", text)
        return ET.fromstring(text)


def item_link(item: ET.Element) -> str:
    link = d.http_url(item.findtext("link") or "")
    if link:
        return link
    guid = item.find("guid")
    if guid is not None and (guid.attrib.get("isPermaLink", "true").lower() != "false"):
        link = d.http_url(guid.text or "")
        if link:
            return link
    enc = item.find("enclosure")
    if enc is not None:
        return d.http_url(enc.attrib.get("url") or "")
    return ""


def item_note(item: ET.Element) -> str:
    """Prefer the description. If that is only an ad-choice stub, use the encoded show notes."""
    description = item.findtext("description") or ""
    summary = item.findtext(f"{ITUNES}summary") or ""
    raw = description if len(d.strip_html(description)) >= len(d.strip_html(summary)) else summary
    if len(d.clean_note(raw)) >= 40:
        return raw
    encoded = item.findtext(CONTENT) or ""
    if encoded and len(d.clean_note(encoded)) >= 40:
        return encoded
    return raw or encoded


def stamp_item(source_id, source_name, lane, kind, title, guest, note, url, when, time_known, extra_tags=None) -> dict:
    when = d.to_ct(when)
    item = {
        "id": d.make_id(source_id, url),
        "kind": kind,
        "lane": lane,
        "sourceId": source_id,
        "source": source_name,
        "title": re.sub(r"\s+", " ", title or "").strip() or source_name,
        "guest": guest or "",
        "note": note or "",
        "url": url,
        "published": when.isoformat(timespec="seconds"),
        "date": when.strftime("%Y-%m-%d"),
        "label": d.ct_label(when, time_known),
        "weekday": ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"][when.weekday()],
        "timeKnown": bool(time_known),
    }
    item["tags"] = d.tags_for(item, extra_tags)
    return item


def fetch_feed_items(spec: dict, lane: str, kind: str, now: datetime) -> tuple[list[dict], str, str]:
    raw, _final, _status = get_bytes(spec["feed"], timeout=60)
    root = parse_xml(raw)
    channel = root.find("channel")
    if channel is None:
        raise RuntimeError("RSS channel missing")
    channel_title = re.sub(r"\s+", " ", (channel.findtext("title") or "")).strip()
    if d.channel_rejected(channel_title, spec.get("rejectChannel") or []):
        raise RuntimeError(f"refusing channel {channel_title!r}")
    home = d.http_url(channel.findtext("link") or "") or spec["feed"]
    retain_days = int(spec.get("_retain", 120))
    cutoff_date = (now.date() - timedelta(days=retain_days)).isoformat()
    skips = {"title": 0, "promo": 0, "trailer": 0, "nolink": 0, "nodate": 0, "old": 0}
    items: list[dict] = []
    for node in channel.findall("item"):
        title = re.sub(r"\s+", " ", (node.findtext("title") or "")).strip()
        episode_type = (node.findtext(f"{ITUNES}episodeType") or "").strip().lower()
        if episode_type == "trailer":
            skips["trailer"] += 1
            continue
        if d.title_skipped(title, spec.get("skipTitle") or []):
            skips["title"] += 1
            continue
        raw_note = item_note(node)
        plain = d.strip_html(raw_note)
        if d.is_cross_promo(title, plain):
            skips["promo"] += 1
            continue
        link = item_link(node)
        if not link:
            skips["nolink"] += 1
            continue
        published = d.parse_pubdate(node.findtext("pubDate") or node.findtext(f"{DC}date") or "")
        if published is None:
            skips["nodate"] += 1
            continue
        if published.strftime("%Y-%m-%d") < cutoff_date:
            skips["old"] += 1
            continue
        guest = d.guest_from_title(title)
        note = d.clean_note(plain)
        items.append(stamp_item(
            spec["id"], spec["name"], lane, kind, title, guest, note, link, published, True,
        ))
    print(f"  {spec['id']}: {len(items)} kept, skips {skips}, channel {channel_title!r}")
    return items, home, channel_title


def huberman_note_from_html(html: str) -> str:
    """First official episode-note paragraphs, else the page meta description. Never the transcript."""
    text = ""
    match = re.search(r'class="rich-text-episode-notes[^"]*"[^>]*>([\s\S]*?)</div>', html)
    if match:
        block = re.split(r"<h[1-6]\b", match.group(1), maxsplit=1, flags=re.I)[0]
        paragraphs = re.findall(r"<p[^>]*>([\s\S]*?)</p>", block, flags=re.I)
        text = " ".join(d.strip_html(part) for part in paragraphs if d.strip_html(part))
    if len(text) < 40:
        for tag in re.findall(r"<meta\b[^>]*>", html, re.I):
            if re.search(r'\bname="description"', tag, re.I):
                content = re.search(r'\bcontent="([^"]*)"', tag, re.I)
                if content:
                    text = d.strip_html(content.group(1))
                    break
    return d.clean_note(text)


def fetch_huberman(spec: dict, now: datetime, cache: dict) -> tuple[list[dict], dict]:
    raw, _final, _status = get_bytes(spec["list"], timeout=45)
    html = raw.decode("utf-8", "replace")
    pattern = re.compile(
        r'href="(/episode/[^"]+)"[\s\S]*?chip-category="([^"]*)"[\s\S]*?fs-list-field="date"[^>]*>([^<]+)</div>[\s\S]*?card-title[^>]*>(.*?)</h2>',
        re.I,
    )
    cards = pattern.findall(html)
    if not cards:
        raise RuntimeError("Huberman listing returned no episode cards")
    retain_days = int(spec.get("_retain", 120))
    cutoff_date = (now.date() - timedelta(days=retain_days)).isoformat()
    items = []
    seen_paths = set()
    fetched = 0
    for path, category, date_text, title_html in cards:
        if path in seen_paths:
            continue
        seen_paths.add(path)
        try:
            naive = datetime.strptime(re.sub(r"\s+", " ", date_text).strip(), "%B %d, %Y")
        except ValueError:
            continue
        when = datetime(naive.year, naive.month, naive.day, 12, 0, tzinfo=d.CT)
        if when.strftime("%Y-%m-%d") < cutoff_date:
            continue
        url = "https://www.hubermanlab.com" + path
        title = d.strip_html(title_html)
        note = cache.get(url) or ""
        if len(note) < 40:
            time.sleep(HUBERMAN_PAUSE)
            try:
                page, _u, _s = get_bytes(url, timeout=30)
                note = huberman_note_from_html(page.decode("utf-8", "replace"))
                fetched += 1
            except Exception as err:
                print(f"  huberman page failed {url}: {err}")
                note = ""
            if note:
                cache[url] = note
        extra = []
        cat = (category or "").lower()
        if "essential" in cat:
            extra.append("essentials")
        elif "solo" in cat:
            extra.append("solo")
        elif "guest" in cat:
            extra.append("guest")
        items.append(stamp_item(
            spec["id"], spec["name"], "podcast", "episode", title,
            d.guest_from_title(title), note, url, when, False, extra,
        ))
    print(f"  huberman: {len(items)} kept, {fetched} episode pages fetched")
    return items, cache


def x_get(path: str, token: str, params: dict) -> dict:
    safe = d.assert_public_x_path(path)
    query = urllib.parse.urlencode(params)
    url = X_API + safe + ("?" + query if query else "")
    raw, _final, _status = get_bytes(url, timeout=30, headers={"Authorization": f"Bearer {token}"})
    return json.loads(raw.decode("utf-8"))


def fetch_x(accounts: list[dict], token: str, now: datetime, retain_days: int) -> tuple[list[dict], dict]:
    if not token:
        print("  X_BEARER_TOKEN is not set. Skipping X.")
        return [], {"online": False, "note": "X feed offline", "reason": "missing X_BEARER_TOKEN"}
    cutoff_date = (now.date() - timedelta(days=retain_days)).isoformat()
    handles = [a["handle"] for a in accounts]
    by_handle = {a["handle"].lower(): a for a in accounts}
    try:
        found = x_get("/2/users/by", token, {"usernames": ",".join(handles)})
    except Exception as err:
        print(f"  X lookup failed: {err}")
        return [], {"online": False, "note": "X feed offline", "reason": "lookup failed"}
    posts: list[dict] = []
    errors = []
    for user in found.get("data") or []:
        handle = user.get("username") or ""
        spec = by_handle.get(handle.lower())
        uid = str(user.get("id") or "")
        if not spec or not uid.isdigit():
            continue
        try:
            payload = x_get(
                f"/2/users/{uid}/tweets",
                token,
                {
                    "max_results": "10",
                    "exclude": "retweets,replies",
                    "tweet.fields": "created_at,referenced_tweets,note_tweet",
                },
            )
        except Exception as err:
            errors.append(f"@{handle}: {err}")
            print(f"  X @{handle} failed: {err}")
            continue
        for tweet in payload.get("data") or []:
            refs = tweet.get("referenced_tweets") or []
            kinds = {str(ref.get("type") or "") for ref in refs if isinstance(ref, dict)}
            if "retweeted" in kinds or "replied_to" in kinds:
                continue
            text = ((tweet.get("note_tweet") or {}).get("text")) or tweet.get("text") or ""
            text = re.sub(r"\s+", " ", text).strip()
            if text.lower().startswith("rt @"):
                continue
            created = d.parse_pubdate(tweet.get("created_at") or "")
            if created is None or created.strftime("%Y-%m-%d") < cutoff_date:
                continue
            url = f"https://x.com/{handle}/status/{tweet.get('id')}"
            if not d.http_url(url) or not str(tweet.get("id") or "").isdigit():
                continue
            title = text[:90] + ("…" if len(text) > 90 else "")
            posts.append(stamp_item(
                spec["id"], spec["name"], "x", "x", title or f"@{handle}", "",
                d.clean_note(text, limit=2000), url, created, True, [f"@{handle}"],
            ))
    status = {"online": True, "note": "", "reason": "", "errors": errors}
    if errors and not posts and not (found.get("data") or []):
        status = {"online": False, "note": "X feed offline", "reason": "; ".join(errors)}
    print(f"  X: {len(posts)} public posts, accounts {len(found.get('data') or [])}")
    return posts, status


def fetch_pages(spec: dict, now: datetime, previous: dict) -> tuple[dict, list[dict]]:
    label = d.ct_label(now, True)
    prev_rows = {row.get("id"): row for row in (previous.get("pages") or [])}
    rows = []
    changes = []
    for page in spec["pages"]:
        prior = prev_rows.get(page["id"]) or {}
        row = {
            "id": page["id"],
            "name": page["name"],
            "url": page["url"],
            "finalUrl": prior.get("finalUrl") or page["url"],
            "hash": prior.get("hash") or "",
            "status": "error",
            "changed": False,
            "checkedAt": now.isoformat(timespec="seconds"),
            "checkedLabel": label,
            "error": None,
        }
        try:
            raw, final, _status = get_bytes(page["url"], timeout=30)
            digest = d.page_hash(raw.decode("utf-8", "replace"))
            row["finalUrl"] = final or page["url"]
            row["hash"] = digest
            row["error"] = None
            old = prior.get("hash") or ""
            if not old:
                row["status"] = "baseline"
                row["changed"] = False
            elif old == digest:
                row["status"] = "unchanged"
                row["changed"] = False
            else:
                row["status"] = "changed"
                row["changed"] = True
                change = stamp_item(
                    "carota-site", "Carota Wealth", "site", "page",
                    f"{page['name']} page changed", "",
                    "Official page copy changed since the previous check.",
                    page["url"], now, True, ["page-change", page["id"]],
                )
                change["id"] = d.make_id("carota-site", page["url"] + "#" + digest[:12])
                changes.append(change)
        except Exception as err:
            row["error"] = str(err)
            row["status"] = "error"
            print(f"  page {page['id']} failed: {err}")
        rows.append(row)
    print("  pages: " + ", ".join(f"{r['id']}={r['status']}" for r in rows))
    return {"checkedAt": now.isoformat(timespec="seconds"), "pages": rows}, changes


def keep_source(previous: list[dict], source_id: str) -> list[dict]:
    return [row for row in previous if row.get("sourceId") == source_id]


def source_row(spec_id, name, short, lane, url, subtitle, items, offline=False) -> dict:
    latest = None
    for item in items:
        if latest is None or (item.get("published") or "") > (latest.get("published") or ""):
            latest = item
    return {
        "id": spec_id,
        "name": name,
        "short": short,
        "lane": lane,
        "url": url,
        "subtitle": subtitle or "",
        "lastLabel": (latest or {}).get("label") or "",
        "lastDate": (latest or {}).get("date") or "",
        "count": len(items),
        "offline": bool(offline),
    }


def main() -> int:
    now = datetime.now(d.CT)
    catalog = json.loads(SOURCES_PATH.read_text())
    retain = int(catalog.get("retainDays") or 120)
    prev_eps = load_json(DATA / "episodes.json", [])
    prev_sigs = load_json(DATA / "signals.json", [])
    prev_pages = load_json(DATA / "pages.json", {})
    prev_seen_doc = load_json(DATA / "seen.json", {})
    seen_existed = (DATA / "seen.json").exists()
    prev_seen = set(prev_seen_doc.get("ids") or [])
    notes = load_json(DATA / "huberman_notes.json", {})
    errors = []
    content_ok = 0
    episodes: list[dict] = []
    homes = {}

    for pod in catalog["podcasts"]:
        pod = dict(pod)
        pod["_retain"] = retain
        try:
            items, home, channel_title = fetch_feed_items(pod, "podcast", "episode", now)
            episodes.extend(items)
            homes[pod["id"]] = (home, channel_title)
            content_ok += 1
        except Exception as err:
            errors.append(f"{pod['name']}: {err}")
            print(f"  {pod['id']} FAILED: {err}")
            episodes.extend(keep_source(prev_eps, pod["id"]))
            homes[pod["id"]] = (pod["feed"], "")

    hub = dict(catalog["huberman"])
    hub["_retain"] = retain
    try:
        hub_items, notes = fetch_huberman(hub, now, notes)
        episodes.extend(hub_items)
        homes[hub["id"]] = (hub["home"], "Huberman Lab")
        content_ok += 1
    except Exception as err:
        errors.append(f"Huberman Lab: {err}")
        print(f"  huberman FAILED: {err}")
        episodes.extend(keep_source(prev_eps, hub["id"]))
        homes[hub["id"]] = (hub["home"], "")

    signals: list[dict] = []
    carota = dict(catalog["carota"])
    carota["_retain"] = retain
    carota["skipTitle"] = []
    carota["rejectChannel"] = []
    try:
        posts, home, channel_title = fetch_feed_items(carota, "substack", "substack", now)
        signals.extend(posts)
        homes[carota["id"]] = (home or carota["home"], channel_title)
        content_ok += 1
    except Exception as err:
        errors.append(f"Carota Wealth: {err}")
        print(f"  carota FAILED: {err}")
        signals.extend([row for row in prev_sigs if row.get("kind") == "substack"])
        homes[carota["id"]] = (carota["home"], "")

    try:
        pages_doc, page_changes = fetch_pages(carota, now, prev_pages)
        content_ok += 1
    except Exception as err:
        errors.append(f"Carota pages: {err}")
        pages_doc, page_changes = prev_pages or {"pages": []}, []
        print(f"  pages FAILED: {err}")

    prior_page_signals = [row for row in prev_sigs if row.get("kind") == "page"]
    known_page = {row.get("id") for row in prior_page_signals}
    for change in page_changes:
        if change["id"] not in known_page:
            prior_page_signals.append(change)
    signals.extend(prior_page_signals)

    token = os.environ.get("X_BEARER_TOKEN", "").strip()
    x_posts, x_status = fetch_x(catalog["x"], token, now, retain)
    if x_status.get("online"):
        signals.extend(x_posts)
        for err in x_status.get("errors") or []:
            errors.append(f"X {err}")
    else:
        signals.extend([row for row in prev_sigs if row.get("kind") == "x"])
        if x_status.get("reason") and x_status.get("reason") != "missing X_BEARER_TOKEN":
            errors.append("X feed offline: " + x_status.get("reason"))

    if content_ok == 0:
        print("All content fetches failed. Leaving data/ untouched.")
        return 1

    cutoff_date = (now.date() - timedelta(days=retain)).isoformat()
    episodes = [row for row in episodes if (row.get("date") or "") >= cutoff_date and d.http_url(row.get("url") or "")]
    signals = [row for row in signals if (row.get("date") or "") >= cutoff_date and d.http_url(row.get("url") or "")]
    episodes = d.dedupe_items(d.unique_by_id(episodes), prev_seen)
    signals = d.dedupe_items(d.unique_by_id(signals), prev_seen)
    episodes.sort(key=lambda row: row.get("published") or "", reverse=True)
    signals.sort(key=lambda row: row.get("published") or "", reverse=True)

    catalog_rows = []
    for pod in catalog["podcasts"]:
        home, subtitle = homes.get(pod["id"], (pod["feed"], ""))
        mine = [row for row in episodes if row.get("sourceId") == pod["id"]]
        catalog_rows.append(source_row(pod["id"], pod["name"], pod["short"], "podcast", home, subtitle, mine))
    home, subtitle = homes.get(hub["id"], (hub["home"], ""))
    catalog_rows.append(source_row(
        hub["id"], hub["name"], hub["short"], "podcast", home, subtitle,
        [row for row in episodes if row.get("sourceId") == hub["id"]],
    ))
    home, subtitle = homes.get(carota["id"], (carota["home"], ""))
    catalog_rows.append(source_row(
        carota["id"], carota["name"], carota["short"], "substack", home, subtitle,
        [row for row in signals if row.get("sourceId") == carota["id"]],
    ))
    site_row = source_row(
        "carota-site", "Carota Wealth site", "SITE", "site", "https://carotawealth.com/",
        "about, services, research, contact",
        [row for row in signals if row.get("sourceId") == "carota-site"],
    )
    # The pages are checked every run even when the copy has not changed.
    watched = (pages_doc or {}).get("pages") or []
    if watched:
        site_row["lastDate"] = now.strftime("%Y-%m-%d")
        site_row["lastLabel"] = d.ct_label(now, True)
        site_row["count"] = len(watched)
    catalog_rows.append(site_row)
    x_offline = not x_status.get("online")
    for account in catalog["x"]:
        mine = [row for row in signals if row.get("sourceId") == account["id"]]
        catalog_rows.append(source_row(
            account["id"], account["name"], account["short"], "x",
            f"https://x.com/{account['handle']}",
            "X feed offline" if x_offline else f"@{account['handle']}",
            mine, offline=x_offline,
        ))

    all_items = episodes + signals
    current_ids = [row["id"] for row in all_items]
    if not seen_existed:
        baseline = True
        change_items = []
    else:
        baseline = False
        change_items = [row for row in all_items if row["id"] not in prev_seen]
    change_items.sort(key=lambda row: row.get("published") or "", reverse=True)

    meta = {
        "baseline": baseline,
        "checkedAt": now.isoformat(timespec="seconds"),
        "checkedLabel": d.ct_label(now, True),
        "errors": errors,
        "retainDays": retain,
        "today": now.strftime("%Y-%m-%d"),
        "x": {"online": bool(x_status.get("online")), "note": x_status.get("note") or "", "reason": x_status.get("reason") or ""},
    }
    save_json(DATA / "episodes.json", episodes)
    save_json(DATA / "signals.json", signals)
    save_json(DATA / "pages.json", pages_doc)
    save_json(DATA / "changes.json", {
        "baseline": baseline,
        "since": prev_seen_doc.get("checkedAt"),
        "items": change_items[:80],
    })
    save_json(DATA / "meta.json", meta)
    save_json(DATA / "sources.json", catalog_rows)
    save_json(DATA / "seen.json", {"checkedAt": meta["checkedAt"], "ids": current_ids})
    save_json(DATA / "huberman_notes.json", notes)
    print(
        f"saved {len(episodes)} episodes, {len(signals)} signals, "
        f"{len(change_items)} changes, baseline={baseline}, x={meta['x']['note'] or 'online'}, "
        f"{meta['checkedLabel']}"
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        raise SystemExit(130)
