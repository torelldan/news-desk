#!/usr/bin/env python3
"""Build index.html from template.html + data/*.json. Data is embedded; no fetch at view time."""
from __future__ import annotations

import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent
DATA = ROOT / "data"


def load(name, default):
    path = DATA / name
    if not path.exists():
        return default
    return json.loads(path.read_text())


def js(obj) -> str:
    text = json.dumps(obj, ensure_ascii=False)
    return text.replace("</", "<\\/").replace("<!--", "<\\!--")


def main() -> None:
    meta = load("meta.json", {})
    pages = load("pages.json", {})
    changes = load("changes.json", {})
    desk = {
        "updated": meta.get("checkedLabel") or "",
        "updatedIso": meta.get("checkedAt") or "",
        "today": meta.get("today") or "",
        "baseline": bool(meta.get("baseline", True)),
        "retainDays": meta.get("retainDays") or 120,
        "x": meta.get("x") or {"online": False, "note": "X feed offline", "reason": "missing X_BEARER_TOKEN"},
        "errors": meta.get("errors") or [],
        "episodes": load("episodes.json", []),
        "signals": load("signals.json", []),
        "pages": pages.get("pages") if isinstance(pages, dict) else [],
        "changes": changes.get("items") if isinstance(changes, dict) else [],
        "sources": load("sources.json", []),
        "markets": load("markets.json", {"regions": [], "holidayNote": ""}),
        "threats": load("threats.json", {"items": []}),
        "assets": load("assets.json", {"series": []}),
        "science": load("science.json", {"items": []}),
        "world": load("world.json", {"viewBox": "0 0 800 400", "path": ""}),
    }
    template = (ROOT / "template.html").read_text()
    if "/*__DATA__*/" not in template:
        raise SystemExit("template placeholder missing")
    blob = f"const DESK = {js(desk)};"
    html = template.replace("/*__DATA__*/", blob)
    (ROOT / "index.html").write_text(html)
    n_eps = len(desk["episodes"])
    n_sig = len(desk["signals"])
    n_m = len((desk["markets"] or {}).get("regions") or [])
    n_t = len((desk["threats"] or {}).get("items") or [])
    n_s = len((desk["science"] or {}).get("items") or [])
    print(f"wrote index.html: {n_eps} episodes, {n_sig} signals, {n_m} markets, {n_t} threats, {n_s} papers, updated {desk['updated'] or 'unfetched'}")


if __name__ == "__main__":
    main()
