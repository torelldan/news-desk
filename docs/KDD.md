# News Desk: Knowledge Design Document (KDD)

| | |
|---|---|
| **System** | News Desk, a prepared-citizen situation desk |
| **Repository** | https://github.com/torelldan/news-desk |
| **Live site** | https://torelldan.github.io/news-desk/ |
| **Place** | Thompson's Station / Williamson County / Middle Tennessee, ZIP 37179 (35.802, -86.907) |
| **Owner** | Daniel (torelldan) |
| **Written against** | `main` at commit `c175c1d`, after PR #17 (merged Nov 11, 2026, 1:20 PM CT) |
| **Companion docs** | [PFL.md](PFL.md) (process flow and architecture), [ONE-PAGER.md](ONE-PAGER.md) |

This document says what the desk knows, where each fact comes from, how a fact becomes a severity, and why the design looks the way it does. It describes the code as it is. Where the README and the code disagree, the code wins, and the gap is listed under [Known limitations](#8-known-limitations).

---

## 1. Purpose and audience

**Purpose.** The desk is one static web page that answers a single question each morning: *is there anything today that I, in Thompson's Station, should act on, and what should I watch?* It brings together:

- official hazard feeds (weather, storms, quakes, outbreaks, near-Earth objects);
- current-events headlines on a fixed set of stories (Iran war, Ukraine war, U.S. government, Israel, climate summit, G7, the Krakow attack, European storms);
- local Williamson County notices (NWS, TEMA, power, roads);
- markets and assets (indexes, DXY, gold, silver, BTC, ETH);
- science headlines (the "Frontier lab");
- the original "public ledger": main-feed episodes of eight podcasts, Carota Wealth site posts and page changes, and public posts from nine X accounts.

Each item gets a severity and, only when warranted, a "so what" line that says what to do. Most of the time the right answer is "no action needed", and the page is built to say that plainly.

**Audience.** One reader: Daniel, a prepared citizen in 37179 and not a developer. The page uses plain sentences, is Matrix-styled (black background, green text), and opens with every section folded to one line (status chip, count, top headline).

**Non-goals** (stated in the code or README):

- It is not a trading terminal. Market lines say "Not a trade instruction" and the impact map says "This is not advice."
- It does not post, like, or message anywhere. It never requests X direct messages. `desklib.assert_public_x_path` allows only four public X API paths.
- It does not write recaps or store transcripts. Notes come from official descriptions.
- It does not invent numbers. A missing quote is `n/a`; a dead feed is "Source down", never a false all-clear.

---

## 2. Information model

### 2.1 The page (sections in on-screen order)

All sections are `<section data-sec=...>` blocks in `template.html`. Each one starts collapsed. Whether it is open is remembered in the browser (`localStorage` key `desk-ui`).

| # | Section (on-screen title) | What it shows | Data it reads (`DESK.*`) |
|---|---|---|---|
| — | Header + **Refresh** link | Last refresh time (CT), X status, the Refresh link (opens the GitHub Actions page) | `meta.json` |
| 02 | **Today** | X trending topics (US WOEID 23424977, world WOEID 1) kept only when they match a threat or preparedness theme. Falls back to X recent-search counts, and Google Trends adds context. | `trends.json` |
| — | **Morning brief** | 3–5 sentences built from the board by `citizen.morning_brief` | `meta.json` → `brief` |
| — | **Standing orders** | Only threat and local items whose so-what line asks for an action (`needsAction`) | `threats.json`, `local.json` |
| 01 | **Economic watch** | 7 regions, 10 index venues: index level, % change, OPEN/CLOSED in CT, region headlines (Google News) | `markets.json` |
| — | **Preparedness triggers** | The **Storm watch** card, the static **Nov 17 blackout-rumor / EAS test** card, the fired thresholds, and the fuel/water/cash/meds checklist | `storms.json`, `local.json`, `triggers.json`, plus browser-side code |
| — | **Local · 37179** | NWS alerts at 35.802,-86.907, TEMA releases (or the Williamson County fallback), Power_TN, TDOT SmartWay | `local.json` |
| 03 | **Watchlist** | Threat items that are ALERT (shown severity) and need no action: things to monitor. One line per story, with "+N related · sources" | `threats.json` |
| 04 | **What changed** | New, updated (material change to a known story), escalated, de-escalated, and resolved items since the last refresh and since yesterday, plus Carota page changes and the market tape | `changes.json`, `history.json` |
| 05 | **World threat board** | All threat items, clustered one row per story ("+N related"), grouped into 12 categories (Iran war … Local Tennessee alerts) | `threats.json` |
| 06 | **Impact map** | Plain market read, event-window moves, 30/90-day correlations; numbers behind "Show the numbers" | `impact.json`, `assets.json` |
| 07 | **Frontier lab** | Science items tagged PREPRINT / PEER-REVIEWED / NEWS by field | `science.json` |
| 08 | **World desk** | The source map: every source with count, last date, and "source down" | `sources.json` |
| — | **Narrative radar** | Preparedness talk: velocity, drivers, follow-through, real-versus-noise call | `radar.json` |
| — | **Weekly look-back** | Escalated / fizzled vs ~7 days ago; whether stored "higher" outlooks were right. Clustered by story with "+N related" | `lookback.json` |
| 09 | **Intel briefs** | Up to 16 lines: live ALERT+ threats plus the top of the log, ranked by `deskRank` | derived in browser |
| — | **Situation log** | Podcasts, signals, X posts, filterable by date window (24h / 48h / 72h / 4+) | `episodes.json`, `signals.json` |

Global filters in the browser: a **date window** (All, 24h, 48h, 72h, 4+ days, computed from each item's age), a **focus** (new, escalating, resolved, watch), and a text search. The section counts follow the active filter.

### 2.2 The item record

Every row on the board is a JSON object with a common core, built by `boards._item()` or an equivalent:

| Field | Meaning |
|---|---|
| `id` | Stable hash of kind + URL + title (`desklib.make_id`) |
| `kind` | Source or category: `quake`, `storm`, `tropical`, `spc-watch`, `spc-outlook`, `nws`, `gdacs`, `relief`, `who`, `cdc`, `neo`, `sentry`, `clock`, `war-iran`, `war-ukraine`, `usgov`, `israel`, `climate`, `diplomacy`, `attack`, `windstorm`, `tema`, `power`, `road`, `na`, `trigger`, `headline`, `paper`, `episode`, `x`, `substack`, `page` |
| `lane` | `threat`, `news`, `local`, `science`, `podcast`, `x`, `substack`, `site`, `desk` |
| `severity` | `STANDBY`, `ALERT`, `ACTION`, `CRITICAL` (empty for science and ledger rows) |
| `title`, `note`, `url`, `source` | What it is, a short official note, the link (required; rows without an http(s) link are dropped), who said it |
| `published`, `date`, `label` | ISO time in America/Chicago, the CT date, a display label |
| `soWhat`, `action` | The "so what" line and the action line (§3.4) |
| `confidence`, `sourceCount` | `confirmed` / `reported` / `rumor` and the count of independent sources |
| `arrowDay`, `arrowWeek`, `outlook` | ↑ → ↓ versus yesterday and last week, plus a 72-hour outlook sentence |
| `raisedBy`, `demoted` | Set when a trigger raised the severity or the 72-hour rule lowered it |

### 2.3 Severity scale

There are four levels. They are ranked identically in Python (`citizen.RANKS`) and in the page (`rankOf`):

| Rank | Level | Meaning on the desk | Typical so-what |
|---|---|---|---|
| 0 | **STANDBY** | On file; nothing to do. Also the floor for anything unknown. | none, or "no action needed" |
| 1 | **ALERT** | Worth watching; read the source. No kit change unless you are in the named area. | "Read the source…" |
| 2 | **ACTION** | Something specific to do or prepare (top off fuel and water, stay weather-aware, stay off named roads). | "Top off fuel and water…" |
| 3 | **CRITICAL** | Urgent and local, or a rare global event that meets a hard threshold. | "Take shelter now…" (tornado warning) |

Two rules adjust severity after classification:

- **72-hour ALERT decay.** An ALERT older than 72 hours is shown as STANDBY. This is done on the server (`boards.demote_stale_alerts`, which marks `demoted: "older than 72h"`) and again in the browser (`shownSeverity`). Only ALERT decays; ACTION and CRITICAL do not.
- **Triggers raise, never lower.** `citizen.raise_to` lifts an item to a trigger's level if it is lower (§3.5).

### 2.4 Source-to-severity mapping

| Source (kind) | Rule in code | STANDBY | ALERT | ACTION | CRITICAL |
|---|---|---|---|---|---|
| **USGS quakes** (`quake`), `boards.quake_severity` | U.S. place or tsunami flag = "home" | home < M5.5; abroad < M7 | home M5.5–5.9; abroad M7–7.9; abroad M6+ with a USGS alert colour or ≥ 5 felt reports | home M6–6.9; abroad M8+ | home M7+ |
| **NWS alerts** (`nws`), `boards.alert_severity` | Event name first, then the CAP severity | anything else | Tornado / Hurricane / Tropical Storm / Flash Flood **Watch**; any other watch or advisory | Tropical Storm Warning, Flash Flood Warning, any other **Warning**; CAP `Severe` | **Tornado Warning**, **Hurricane Warning**; CAP `Extreme` |
| **NHC RSS on the threat board** (`storm`), `_storm_severity` | Outlook / "no tropical cyclones" rows are dropped | other | — | "Hurricane <Name>", Tropical Storm Warning | Hurricane Warning |
| **NHC Storm watch** (`tropical`), `tropical_severity` | Track and advisory vs Tennessee (box 34.98–36.72 N, 90.35–81.62 W, or ≤ 450 km of home) | no U.S. watch, track misses TN | U.S. hurricane / TS / storm-surge watch or warning in effect | forecast point reaches TN | forecast point reaches TN at ≥ 64 kt (hurricane strength) |
| **SPC watches** (`spc-watch`), `spc_watch_severity` | Must name Williamson, Davidson, Rutherford, Maury, Sumner, Wilson, Hickman, Cheatham, Dickson, Bedford, Marshall, or "Middle Tennessee" | no watches, or watches elsewhere | Severe Thunderstorm Watch covering Middle TN | **Tornado Watch** covering Middle TN | — |
| **SPC Day 1–3 outlook** (`spc-outlook`), `outlook_at_point` | Highest categorical polygon containing 35.802, -86.907 | none, General thunder, Marginal | Slight | Enhanced, Moderate | High |
| **GDACS** (`gdacs`) | GDACS alert level | — | Green / other | Orange | Red |
| **ReliefWeb** (`relief`) | fixed | — | every disaster row | — | — |
| **WHO** (`who`) | title words; ≤ 14 days old; COVID data packages skipped | other | "outbreak", "cases", "deaths", "epidemic" | — | — |
| **CDC HAN** (`cdc`), via Google News | title names HAN | — | other CDC HAN headline | title says "Health Alert Network" / "HAN" | — |
| **NASA/JPL CNEOS** (`neo`) | close approach ≤ 5 lunar distances in the next 60 days; takes the Sentry level when the object is on the Sentry list | routine flyby (not on Sentry) | Sentry level | Sentry level | Sentry level |
| **NASA/JPL Sentry** (`sentry`) | first possible impact ≤ 15 years out | not listed | Torino ≥ 1 | Torino ≥ 2 or Palermo > -2 | Torino ≥ 5 or impact probability ≥ 1% |
| **Doomsday Clock** (`clock`) | link only | always | | | |
| **Headline desks** (`war-iran`, `war-ukraine`, `usgov`, `israel`, `climate`, `diplomacy`, `attack`) | `boards._try_desks` | — | every kept headline | — | — |
| **European storm** (`windstorm`) | Storm Charles / Bruna wording | always (fact-check row) | | | |
| **TEMA** (`tema`), `citizen.tema_notices` | ALERT needs all three: the report names Williamson County / 37179 / Thompson's Station; a hazard word (flood…, warning, evacuation, emergency, wildfire, tornado); and no "all clear / closed / final report" | everything else, including reports for other counties | local + hazard + still open | — | — |
| **Williamson County RSS fallback** (`tema`) | title words | other | flood…, warning, evacuation, emergency, tornado | — | — |
| **Power_TN** (`power`) | Williamson row | 0 affected | any customers affected | — | — |
| **TDOT SmartWay** (`road`) | description words | other | "closure", "blocked", "flood" | — | — |
| **Triggers** (`trigger`) | §3.5 | | gold / silver / crypto / outbreak-US / Gulf X trend | Gulf-bound tropical system | quake M7+, Tennessee tornado or hurricane warning |
| **Frontier lab, podcasts, X, Carota** | no severity (ledger) | — | — | — | — |

### 2.5 Confidence

`citizen.confidence_for` labels each threat and local item:

- **confirmed** needs two or more independent, non-X sources;
- **reported** is one official or local source (official kinds: quake, storm, nws, gdacs, who, cdc, neo, sentry, relief), or one press source;
- **rumor** is X-only (an X post or trend with no outside source). An X-only item can never be confirmed. The browser also downgrades a "confirmed" X item to "rumor".

---

## 3. Sources and fallbacks

Every fetch "fails soft": on error, the previous JSON for that board is kept and the error is written to `meta.json → errors`, which the page shows as "Source down". Requests use Python's standard library, with a `curl` retry (`boards._get`) using a browser User-Agent when urllib fails.

### 3.1 Hazard and weather sources

| Source | Endpoint(s) | Fallback | Feeds section(s) |
|---|---|---|---|
| **NWS, threat board** | `api.weather.gov/alerts/active?point=35.925,-86.869` (Franklin), `?area=TN`, then national `severity=Extreme,Severe` filtered to tornado / flood / hurricane (≤ 12) | Each URL is independent; a failure is logged. A national failure adds a gap. | World threat board ("Local Tennessee alerts" or "Natural disasters") |
| **NWS, local** | `api.weather.gov/alerts/active?point=35.802,-86.907` (Thompson's Station), ≤ 8 alerts | No alerts gives an explicit "No active NWS alert for Thompson's Station (37179)" STANDBY row. Failure gives an `n/a` row plus a gap. | Local; tornado watch / warning also mirrored onto Storm watch |
| **NHC, Storm watch** | `nhc.noaa.gov/CurrentStorms.json`; for storms with watches or within 2,500 km, the forecast-advisory text is read for track points | Atlantic, East Pacific, and Central Pacific RSS (`index-at/ep/cp.xml`, public advisories only). Nothing active gives "No active tropical systems" (STANDBY). Both down gives the gap "NHC: …" and Source down. | Preparedness → Storm watch |
| **NHC, threat board** | `index-at.xml`, `index-ep.xml`, `gtwo.xml` (≤ 10 rows) | Outlook-only rows are skipped. No feed answering gives a gap. | World threat board |
| **SPC watches** | `spc.noaa.gov/products/spcwwrss.xml` (≤ 8) | Empty feed gives "No SPC tornado or severe thunderstorm watches" (STANDBY). Failure gives the gap "SPC watches: …". | Storm watch |
| **SPC outlooks** | `day{1,2,3}otlk_cat.nolyr.geojson`, point-in-polygon at 37179 | A failed day adds a gap for that day only | Storm watch |
| **USGS** | `earthquake.usgs.gov/.../4.5_week.geojson` (top 30 by magnitude) | gap "USGS: …" | World threat board |
| **GDACS** | `gdacs.org/xml/rss.xml`, `rss_7d.xml`, `gdacs.org/xml/rss.xml` | tries all three; then gap. **Currently broken** (XML parse error). | World threat board |
| **ReliefWeb** | API `api.reliefweb.int/v1/disasters` | `reliefweb.int/disasters/rss.xml`, then `updates/rss.xml`. **Currently broken** (API HTTP 410, RSS empty). | World threat board |
| **WHO** | DON RSS `who.int/feeds/entity/csr/don/en/rss.xml` | `who.int/rss-feeds/news-english.xml`. Items older than 14 days are dropped. **Currently returns nothing in 14 days.** | World threat board (Pandemics & outbreaks) |
| **CDC HAN** | Google News search "CDC Health Alert Network" (3-day window) | none; gap when nothing is ≤ 14 days old. **Currently empty.** | World threat board |
| **NASA/JPL** | `ssd-api.jpl.nasa.gov/sentry.api`, `cad.api` (≤ 0.05 au, next 60 days) | each independent; gap per API | World threat board (Space & existential) |
| **Bulletin of the Atomic Scientists** | static link row to the Doomsday Clock | n/a (no fetch) | World threat board |

### 3.2 Local Williamson County sources

| Source | Endpoint | Fallback / rules |
|---|---|---|
| **TEMA** | `tn.gov/tema/news-info/news-releases.html`, then `tn.gov/tema/news.html`, with browser-like headers; three attempts (waits of 1.5 s and 3 s). Reads dated links `/tema/news/YYYY/M/D/`. Since PR #17: only reports dated within about **72 hours** (date-based cutoff); the **county is taken from the report title** ("Polk County …") and tagged; the note says the date and either "Names Williamson County." or "<County> County. Not a Williamson County / 37179 notice."; the label is a readable date ("Nov 6, 2026"); a later report on the same event **supersedes** earlier ones ("Flash Report #2" replaces "#1"); ≤ 4 rows. The page also hides any TEMA row older than 72 hours. | If neither page gives dated notices: **Williamson County public-safety RSS** (`williamsoncounty-tn.gov/RSSFeed.aspx?ModID=1&CID=PublicSafety-40`), ≤ 21 days, ≤ 4 rows, filed as kind `tema`, source "Williamson County". A TEMA error is still recorded as a gap even when the fallback supplies rows. **TEMA is flaky** (resets / 403 from the Actions runner). |
| **Power_TN** | ArcGIS `Power_TN/FeatureServer/0` where County = Williamson | Row hidden (and a gap noted) when stale (> 7 days) or all zeros; `n/a` row on error. |
| **TDOT SmartWay** | ArcGIS `Smartway_Events` where description mentions Williamson (≤ 6 kept) | Ended "scheduled / widening / project" items are hidden unless they say debris / closure / blocked / crash / flood / disabled. |

### 3.3 News, markets, trends, science, ledger

| Source | Use | Fallback |
|---|---|---|
| **Google News RSS** (`news.google.com/rss/search`) | (a) the headline desks in §3.6; (b) region headlines for Economic watch (kept `retainDays` = 120, merged with saved rows, ≤ 40 per region); (c) CDC HAN; (d) Narrative radar queries | Region headlines keep the cached rows on failure. A desk with 0 headlines adds a gap. |
| **Yahoo Finance chart API** | 10 index venues (5-day) and DXY (fallback UUP), gold (GC=F), silver (SI=F) at 6 months | Missing level shows `n/a`. The whole board keeps its cache if the producer throws. |
| **CoinGecko** | BTC, ETH 90-day daily | `None` gives a blank series |
| **X API v2** (secret `X_BEARER_TOKEN`) | Public posts of 9 accounts; trends by WOEID; recent-search counts if trends are refused | Missing or rejected token: X is skipped, cached X posts are kept, and the page shows **X feed offline** |
| **Google Trends** (US daily) | Context for Today; matched against threat topics | note in `meta.trends.google` |
| **Science feeds** | arXiv (gr-qc/hep-th, space-ph, quant-ph, cs.AI), Phys.org, NASA, Nature, ScienceDaily, bioRxiv / medRxiv API, MIT Tech Review, IEEE Spectrum, Google AI blog; ≤ 4 per feed, ≤ 16 per field, 21-day window | Board keeps its cache only if *all* feeds fail |
| **Podcasts** | 7 RSS feeds plus Huberman episode pages (120-day window) | Per-feed: keep that source's previous episodes |
| **Carota Wealth** | carotawealth.com sitemap / research / insights; page hashes for about, services, research, contact | keep cached posts / previous hashes |

### 3.4 So-what and action lines

`citizen.so_what` (server) and `soWhat` (browser) give a line **only when the item calls for something specific**. Examples from the code:

- NWS Tornado Warning: "Take shelter now. Interior room, lowest floor, away from windows."
- NWS Flash Flood at ACTION or above: "… What to do: stay off flooded roads."
- European windstorm: "No action for 37179. This is a European named storm, not an Atlantic hurricane."
- Close approaches, Sentry, distant quakes, and "no tropical cyclones" rows: "no action needed".
- Iran or Ukraine war headline that *names* the conflict: "What to do: no action at home. Skip travel into the named fighting if a trip was planned." (See §4.2.)
- U.S. government headlines: no line.
- Storm watch rows use `boards._storm_advice` (for example, a tornado watch covering Middle TN: "know the shelter spot and stay with the warning").

**Standing orders** shows an item only if its so-what line exists, does not say "no action", and the kind is not `market`, `war-iran`, `war-ukraine`, or `usgov` (`needsAction`).

### 3.5 Preparedness triggers (`citizen.evaluate_triggers`)

| Trigger id | Fires when | Level | Effect |
|---|---|---|---|
| `gulf-storm` | An NHC `storm` row mentions hurricane / tropical storm / depression **and** "Gulf" outside the standing basin header | ACTION | raises the item to ACTION |
| `outbreak-us` | A WHO or CDC row names the United States | ALERT | raises to ALERT |
| `quake-m7` | Any quake M7+ | CRITICAL | raises to CRITICAL |
| `tn-warning` | A Tennessee-tagged NWS row with tornado or hurricane **and** "warning" | CRITICAL | raises to CRITICAL |
| `gold-3` / `silver-5` | Gold ≥ +3% or silver ≥ +5% on the day | ALERT | trigger row only |
| `btc-drop` / `eth-drop` | BTC or ETH ≤ −10% on the day | ALERT | trigger row only |
| `gulf-trend` | An X hurricane trend names the Gulf | ALERT | trigger row only ("X alone is not confirmed") |

When any trigger fires, the checklist **fuel, water, cash, meds** is shown.

### 3.6 Headline desks (`boards._try_desks`)

| Hinted kind | Google News query (abridged) | Window |
|---|---|---|
| `war-iran` | Iran (war OR strike OR missile OR IRGC OR ceasefire) | 14 d |
| `war-ukraine` | Ukraine (Russia OR missile OR ceasefire OR Kyiv OR front) | 14 d |
| `usgov` | "White House" OR Congress OR Pentagon OR "Supreme Court" OR Rubio OR "election integrity" OR midterms | 7 d |
| `israel` | Israel (government OR coalition OR Eisenkot OR Knesset) | 7 d |
| `climate` | (COP31 OR Antalya) (climate OR summit OR COP) | 14 d |
| `diplomacy` | (G7 OR Rubio) (Paris OR ministers) | 7 d |
| `attack` | Krakow (attack OR stabbing OR explosion) | 7 d |
| `windstorm` | "Storm Charles" OR "Storm Bruna" OR "Hurricane Charles" OR "European windstorm", with Madeira / Portugal / Spain / Canary | 7 d |

Each query returns ≤ 8 rows. Rows are kept only if dated in the current year, are not "essay / analysis" pieces, and survive `classify_desk` (§4.2). Kept rows are ALERT (windstorm: STANDBY), `confidence: reported`, then clustered by story (`cluster_rows`: the lead is the highest-severity, then newest copy; the others become a `related` count and `relatedSources` list) and capped at **4 stories per kind** (`fold_desk_rows`, `DESK_CAP = 4`).

---

## 4. Rules

### 4.1 Dedupe

There are four dedupe layers, each with a different job.

1. **Ledger dedupe** (`desklib.dedupe_items`): podcasts and signals are deduped by the **official description** (first 400 normalized characters plus source), not the title, so a retitled upload collapses to one row. Numbered parts with different episode numbers, and copies more than 3 days apart, stay separate. Short notes (< 80 characters) fall back to the URL.
2. **Threat title dedupe** (`boards._dedupe_titles`): identical normalized titles on the threat board are kept once.
3. **Story dedupe** (`boards.same_story`, mirrored in the browser as `sameStoryTitle`). Two headlines are the same story when any of these hold:
   - after stripping the outlet suffix (" - NPR") and stop words, they share ≥ 3 tokens covering ≥ 35% of the shorter title;
   - they share ≥ 3 Israel-government words;
   - both name the same tracked place: Krakow, Oleshky, Antalya, COP31 ("COP 31" is normalized to "cop31"), or Abu Dhabi;
   - both describe a killing or shooting, Poland is mentioned, and Krakow is named;
   - both name the same tracked person (Hegseth, Massie, Eisenkot, Netanyahu) plus one more shared word;
   - both are the European storm Charles, or both Bruna;
   - both are the Israel government-formation story (`_israel_government`);
   - both are Russia–Ukraine peace talks (`_ukraine_talks`, which catches "peace push" without "Abu Dhabi");
   - both are a shooting / killing in Poland or Krakow (`_poland_shooting`, PR #17).
4. **Story clustering with "+N related"** (PR #17). `boards.cluster_rows` (server) and `clusterStories` (browser) keep **one lead row per story**: the copy with the highest shown severity, with the newest breaking ties. Every other copy adds 1 to the lead's `related` count, and its outlet is added to `relatedSources`. The page prints "+N related · Outlet A, Outlet B". Clustering applies to the headline desks (before the cap of 4), the **World threat board** (and its header count), the **Watchlist**, and the **Weekly look-back** (escalated, fizzled, calls; the server appends "+N related (sources)" to the note).
5. **Browser dedupe**: `uniqueTitles` (by story key) in Today, Standing orders, and Watchlist; URL dedupe in the watch pool; `foldSameStory` in What changed (§4.3).

> **Design note.** The named places and people are hard-coded for the stories on the board in Nov 2026. As those stories age out, these rules stop matching anything (harmless). New recurring stories may need new names added to `boards.py` **and** `template.html` together.

### 4.2 Conflict-kind rule (`boards.classify_desk`, `citizen._conflict_named`)

A Google News query can return a headline that never mentions its war. PR #14 fixed a case where the Massie / Hegseth impeachment story arrived on the Iran query and led the Watchlist with "skip travel into the named fighting".

- A headline gets a conflict kind **only if its own title or snippet names that conflict**: Iran for `war-iran`; Ukraine / Kyiv / Kharkiv / Odesa / Oleshky / Donbas for `war-ukraine`.
- Otherwise it is re-classified from its text (for example to `usgov` when it says Congress / Pentagon / Hegseth / Massie / Senate / Rubio…). If nothing matches and the query was a war or windstorm query, the row is **dropped** (kind `news`).
- European-storm wording always wins: `windstorm`.
- The travel line "Skip travel into the named fighting" is given only when `_conflict_named` is true.

### 4.3 What changed

The server (`fetch.py`) writes `changes.json` with:

- **`sinceRefresh`**: the threat board vs the previous `threats.json`, and Today trends vs the previous `trends.json`;
- **`sinceYesterday`**: the threat board vs the newest `history.json` snapshot dated yesterday or earlier ("no stored yesterday" if none);
- each with `new`, `escalated` (rank up), `deescalated` (rank down), and `resolved` (gone, was ALERT or above, and no current item is the same story), each capped at 20. A current item is matched to its previous row by id **or by same story** (`boards.prior_item`), so a new outlet on an old story is not "new";
- **material updates and 7-day memory** (PR #17). For an item with no match in the comparison set, the server looks back through `history.json` snapshots from the last **7 days** (`boards.recent_story`):
  - same story found and **no material change**: suppressed (a returning item is not "new");
  - same story found and **material change**: listed with the note "Update to that story. Was: <old title>";
  - no match, but the item is STANDBY and dated 2+ days ago (`old_standby_return`): suppressed;
  - otherwise: new.
  
  A matched item whose headline claim changed while its severity did not rise is also listed as an update. A **material change** (`story_update`) is a higher severity, or a **change of lead claim**: the set of claim words in the title (won, victory, effectively over, ceasefire, strike(s), impeach, killed, dies, hospital, peace push, peace deal, voted, no to war) shares nothing with the old title's set (`headline_shift`). Another outlet repeating the same claim is not an update;
- `groups` (new ledger / board items, severity changes, Carota page changes, price moves).

The browser (`changeRows`) then:

1. flattens the refresh rows, adds yesterday rows not already present (`changeKey`), adds up to 6 Carota page changes, and adds the market tape if it fired;
2. runs `foldSameStory`: in one section, two rows of the same story keep the newer; a "new" + "resolved" pair of the same story cancels out; a "resolved" row whose story is still live is dropped. A "new" row is checked against the last 7 days of snapshots plus yesterday's titles: if any match has the same lead claim and the row is not higher in severity, it is dropped; otherwise it is relabelled **updated** with "Update to that story. Was: …". An unmatched STANDBY row dated 2+ days ago is dropped;
3. applies the date and focus filters;
4. adds, at the top, any current threat-board item that is a material update to a story seen in the last 7 days but is not already listed (`leadUpdates`).

**Header chip** (`changeStatus`) is **ALERT** only if some open row (not resolved, not de-escalated, not a market row) has shown severity ALERT or higher; otherwise STANDBY. The chip never shows ACTION or CRITICAL. **Header headline** (`changeLead`) names the open row with the highest shown severity, with the newest breaking ties (PR #16).

### 4.4 Sorting: severity, then newest

The shared comparator is "shown severity, high to low, then `published` (or `date`), newest first". It is used by:

- **Story clustering** (`clusterStories`): picks the lead of each story by the same comparator;
- **World threat board**: rows inside each of the 12 groups, and the groups themselves (by top severity, then newest item; empty groups last);
- **Section header leads** (`leadItem`) for What changed and the threat board;
- **Standing orders** (severity, then newest);
- **Watchlist**: first by topic weight (Iran / Ukraine war 3, U.S. government 2, others 1), *then* shown severity, then newest;
- Intel briefs and the situation log instead use `deskRank` (topic relevance score), then newest.

Section header chips use `topSeverity` (the highest shown severity in the section), except What changed (above) and a few fixed-STANDBY sections (Frontier lab, World desk, Intel briefs, Situation log).

### 4.5 Storm watch

The Storm watch card sits at the top of **Preparedness triggers**. Its rows come from two places:

1. **Local NWS tornado watch or warning, mirrored in the browser** (`localTornadoItems`): any `local.json` NWS row whose title or note says "tornado watch" or "tornado warning". Severity follows the NWS rule: Watch ALERT, Warning CRITICAL with "Take shelter now".
2. **`storms.json`** (`boards.fetch_storm_watch`), in this order:
   - **Tropical**: one row per active NHC storm (name, class and category, max winds kt/mph, movement, basin, position, and whether a U.S. watch is in effect), severity per §2.4; or "No active tropical systems";
   - **SPC watches**: each current watch, or "No SPC tornado or severe thunderstorm watches";
   - **SPC outlooks**: "Day N convective outlook: <category> at Thompson's Station (37179)" for days 1–3.

The card header shows the highest shown severity among its rows. The note line is "Atlantic hurricane season runs through Nov 30." and adds "A quiet tropical line means NHC reported no active systems." **only** when the tropical status really is the quiet line (PR #16). Each gap is shown as "Source down: …". NHC and SPC also appear on the World desk source map with a count and last-check time (`apply_storm_sources`).

### 4.6 Static cards

- **Nov 17 "global blackout" rumor / EAS test card** (PR #13). It is defined entirely in `template.html` (`blackoutCard`, `blackoutHtml`) and **fetches nothing**. It is STANDBY, computes a countdown to Tue Nov 17, 2026 in the browser, and gives the verdict: rumor, no blackout, internet shutdown, or bank wipe is scheduled. What is real is the FEMA/FCC nationwide Emergency Alert System test at about 1:20 PM CT (2:20 PM ET), about one minute, radio and TV only, not phones, with backup date Dec 3, 2026. What to do: nothing special. It links to three fact-checks. It **hides automatically after Nov 18, 2026** (CT date), with a test in `test_blackout_rumor_hides_after_nov_18`.
- **Doomsday Clock**: a link-only STANDBY row; the desk never states the clock setting.
- **Storm Charles fact-check**: not static, but a recurring headline desk (`windstorm`) that files European Storm Charles / Bruna coverage as STANDBY with the no-action line (PR #15). It was added after "Hurricane Charles" turned out to be a European storm that hit Madeira, Portugal, and Spain on Nov 10–11, 2026.

### 4.7 Time

All stored times are America/Chicago (`desklib.CT`). Feed dates (UTC) are converted on fetch. The workflow names its commit with the Chicago date. The page shows market session hours converted to CT in the browser, including daylight time.

---

## 5. Data stores (`data/*.json`)

| File | Written by | Content |
|---|---|---|
| `meta.json` | fetch.py | check time (CT), `errors[]`, X status, trends notes, morning `brief`, `baseline` |
| `episodes.json`, `signals.json` | fetch.py | ledger rows (120-day window) |
| `seen.json` | fetch.py | ids from the last run (for ledger "new") |
| `pages.json` | fetch.py | Carota page hashes |
| `huberman_notes.json` | fetch.py | cache of fetched Huberman descriptions |
| `changes.json` | fetch.py | What changed (§4.3) |
| `sources.json` | fetch.py | the World desk source map rows |
| `markets.json`, `assets.json`, `science.json` | boards.py via `refresh_file` | boards (cache kept on failure) |
| `threats.json` | boards.py, then citizen.py | threat board after triggers and outlooks |
| `storms.json` | boards.py | Storm watch |
| `local.json`, `triggers.json`, `trends.json`, `radar.json`, `impact.json` | citizen.py | prepared-citizen layer |
| `history.json` | citizen.py | 21 daily snapshots (threat ids, titles, severities, outlooks) |
| `lookback.json` | citizen.py | weekly look-back |
| `world.json` | static | world map SVG path for the World desk |

---

## 6. Key design decisions and rationale

| Decision | Rationale (from code, README, and PR history) |
|---|---|
| **One static, self-contained `index.html`** with data embedded at build time (`build.py` replaces `/*__DATA__*/` with `const DESK = {...}`) | Browsers block `fetch()` of local JSON over `file://`, so the page works opened from disk or from Pages with no server, no API calls at view time, and nothing to keep running. |
| **GitHub Actions + GitHub Pages; no server, no database** | Free, versioned, and every refresh is a commit you can inspect or roll back. Git history doubles as the archive. |
| **No paid monitoring, no extra routines or services** | Daniel asked not to spend credits on monitoring. The refresh is the only scheduled work. Sources are free public feeds; the only key is `X_BEARER_TOKEN` (X API access is billed by X; without it the X parts go offline and everything else still works). |
| **Hourly backup cron with a skip-if-already-refreshed guard** (PR #11, PR #14) | GitHub delivers scheduled runs hours late on this repo. Several attempts raise the chance of a morning refresh; the guard keeps it to one refresh commit per Chicago day. |
| **Manual refresh always runs** (`workflow_dispatch` bypasses the guard) | Daniel can force a fresh desk any time from the Refresh link. |
| **Fail soft, keep the cache, show "Source down"** | A flaky feed should not blank a section or fake an all-clear. Errors are visible. |
| **Never invent a figure** | Missing prices are `n/a`; the Doomsday Clock is a link; no recaps. |
| **CRITICAL is rare** (PR #9) | Distant quakes and routine flybys are STANDBY. CRITICAL is reserved for local warnings, U.S. M7+ quakes, hurricane-strength tracks into TN, and real Sentry risk, so the label keeps its meaning. |
| **72-hour ALERT decay** (PR #11) | Old wires should not keep the Watchlist on ALERT. |
| **Conflict kind only when named** (PR #14) | Prevents wrong travel advice on unrelated stories. |
| **Story-level dedupe and a cap of 4 per desk** (PR #14, PR #16) | Many outlets carry one story; the board should list the story once, newest copy. |
| **Cluster by story, keep material updates** (PR #17) | Repeated headlines from many outlets crowded the board and re-appeared as "new". One lead per story with "+N related" keeps it short. A 7-day memory stops returning items from looking new, while a real change of claim or a higher severity still shows as an update. The case that prompted it: NPR's "Trump says US won Iran war" was hidden as the same story as AP's earlier "effectively over" line; it is now listed as an update to that story. |
| **TEMA: county-aware, 72-hour, superseding** (PR #17) | Statewide TEMA flash reports (e.g. Polk County flooding) were tagged Williamson and shown as ALERT for days. Now only reports that name Williamson / 37179 can be ALERT, old reports age off after ~72 hours, and the newest report on an event replaces earlier ones. |
| **Severity-then-newest sorting** (PR #14, PR #16) | The section header and first row should be the most serious thing, not whichever row the feed listed first. |
| **Collapsed sections with a one-line summary** (PR #8, PR #10) | The default view fits one screen; header counts match the rows inside. |
| **Static content where a feed isn't needed** (PR #13) | The Nov 17 card is a fixed fact-check with a built-in expiry, so it costs nothing to run and can't break. |
| **Local layer pinned to 37179 coordinates** | NWS, SPC outlooks, and the NHC distance check all use 35.802, -86.907 (the threat board's NWS point uses Franklin, 35.925, -86.869). |
| **Read-only and public-only X** | The allow-list of X paths guarantees DMs are never requested. |

---

## 7. Tests

`tests/test_rules.py` has 24 plain-Python test functions (run with `python3 tests/test_rules.py`, which prints `ok`). They cover: time conversion; feed skip rules; cross-promo and note cleaning; dedupe by description; the X path allow-list and error handling; Carota parsing; board helpers (quake and alert severities); trend filtering and confidence; triggers, outlooks, and impact; the blackout card expiry; the conflict-kind rule; same-story folding (Israel PM, Ukraine peace push, COP 31); TEMA parsing; storm-watch severities including SPC geometry and Storm Charles vs a Florida "Hurricane Charles"; and (PR #17) material updates, clustering, and returning items (`test_material_updates_clusters_and_returning_items`) plus TEMA county, age, and local relevance (`test_tema_county_age_and_local_relevance`).

**Tests are run by the developer before a change is proposed, not by the refresh workflow.** The workflow does not run tests.

## 9. Nov 12 additions

- **Japan and India** are their own economic-watch regions. Asia keeps the Hang Seng. Tokyo's afternoon session ends at 15:30 (JPX, "12:30 pm to 3:30 pm"). The Russia venue is labeled IMOEX and its level is the MOEX ISS current value. Yahoo's `IMOEX.ME` symbol is not used; it returns 404.
- **Macro strip** in `data/macro.json`: BIS policy rates for US, Japan, India, euro area, China, Brazil, Russia, Canada, and Mexico; Japan 10-year from the Ministry of Finance CSV (2.84% on Nov 11, 2026); India 10-year from FRED `INDIRLTLT01STM` without a browser user-agent; India CPI from OECD SDMX; Japan CPI year-over-year from the DBnomics STATJP CPI index. The file is reused for 7 days.
- **Impact.** A market-read count needs at least 10 event days and ignores STANDBY quakes. Gold and silver driver lines say "association, not proof".
- **Strikes** (`data/strikes.json`) come from Google News and are cross-checked against Wikipedia's Current events page. A match is tagged confirmed. A house explosion or other domestic accident is dropped. News alone is never CRITICAL. A named chokepoint (Hormuz, Red Sea, Ust-Luga, Novorossiysk, Primorsk) is ALERT. GDELT stays off.
- **Drivers** on the impact map: 1-week, 1-month, 3-month, and 1-year changes for gold, silver, DXY, the 10-year, the real 10-year (FRED DFII10), the S&P, VIX, copper, and the gold/silver ratio; 30- and 90-day return correlations; ZQF27 and ZQH27 implied fed-funds rates beside FRED DFF; T10Y2Y and T10Y3M with an inversion flag; copper/gold beside the 10-year; GLD, SLV, and GOLDBEES.NS volume; Brent and WTI with the energy-strike count. The gold/silver line is the price ratio (gold divided by silver, about 77), not the one-month percent change. Copper/gold is shown per 1,000 so a ratio near 0.0016 does not render as 0. The driver block and the gold card use the same print.
- **Rising situations** persist in `data/trendlog.json` (90 days of topic rows, 14 days of cluster rows, about a 300 KB cap, topics with no activity for 30 days dropped). The existing refresh writes it, bootstrapping from `history.json`. A state change is a What changed row.
- **Rising situations** (`data/rising.json`) score topics already on the board. EMERGING, RISING, PEAKING, and FADING are shown; a steady topic stays hidden. No new schedule.

---

## 8. Known limitations

1. **GitHub cron runs land late.** GitHub's `schedule` events on this repo arrive hours late, often in the afternoon. The eight tries (09:07, 10:17, 11:23, 12:37, 13:15, 14:41, 15:47, 16:53 UTC, which is 3:07–10:53 AM CT in winter and an hour later in summer) improve the odds but guarantee nothing. A morning-fresh desk still depends on a manual refresh. A reliable fix needs an outside trigger, which has not been chosen.
2. **One refresh per day from the schedule.** Once a commit named `Refresh desk YYYY-MM-DD` (Chicago date) is among the last 30 commits, every later scheduled try that day skips. A manual run is never skipped. A run that changed nothing makes no commit, so it does not count as "refreshed".
3. **Broken sources** (as of the Nov 11, 2026 8:59 AM CT refresh, `meta.json → errors`):
   - **GDACS**: RSS XML does not parse ("not well-formed").
   - **ReliefWeb**: API returns HTTP 410; RSS fallbacks are empty.
   - **WHO**: no outbreak notice in the last 14 days (DON feed has been 404).
   - **CDC HAN**: no notice newer than 14 days.
   
   These four are shown as "Source down", never as an all-clear.
4. **TEMA is flaky.** tn.gov often resets or 403s the GitHub runner. The fetch tries two URLs three times, then falls back to the Williamson County public-safety RSS (which is often empty). TEMA is a real, working source when it answers. Since PR #17, a statewide report that doesn't name Williamson stays STANDBY and drops off after ~72 hours, so Local is often just the NWS line. The county comes from the title's "<Name> County" text only; a report naming several counties is tagged with the first.
5. **Tests are not part of the refresh.** A broken rule would only be caught when someone runs the tests.
6. **Hard-coded story names and claim words** (§4.1, §4.3) need hand upkeep as the news moves on, and must be changed in both `boards.py` and `template.html`. When neither headline has a claim word, token overlap under 0.35 is treated as an update (the Kushner/Putin lead shares about a third of its words with the Abu Dhabi talks line, so a 0.2 cutoff would still hide it).
7. **Year-bound content.** NYSE holidays are hard-coded for 2026. Threat rows and the browser's `onBoard` filter keep only items dated in the current year (the browser literally checks `"2026"`). The blackout card expires after Nov 18, 2026. Some of this will need a touch in January 2027.
8. **Statewide NWS alerts.** An alert for `area=TN` is ALERT only when its SAME/UGC codes include Williamson (`047187` / `TNC187`) or an adjacent county. The rest of Tennessee is STANDBY, "elsewhere in TN". The point alert for 35.802,-86.907 is unchanged.
9. **X depends on paid API credits.** HTTP 402 means credits ran out; the page then shows X feed offline.
10. **Market OPEN/CLOSED** knows NYSE holidays only; other venues can show OPEN on a local holiday.
11. **Headlines are Google News titles.** Truncation such as a title ending "from pos" is in the source title; the desk does not cut titles.

---

## 10. Glossary

| Term | Meaning |
|---|---|
| **37179** | ZIP code of Thompson's Station, TN; the desk's home point is 35.802, -86.907 |
| **ACTION** | Severity 2: something specific to do or prepare |
| **ALERT** | Severity 1: watch it; read the source |
| **Baseline** | The first run, when nothing is "new" yet |
| **build.py** | Script that injects `data/*.json` into `template.html` to make `index.html` |
| **CAP severity** | The NWS alert's own `Extreme / Severe / …` field |
| **CRITICAL** | Severity 3: urgent, local, or a rare global threshold |
| **Cron** | GitHub's built-in timer that starts the refresh on a schedule |
| **DESK** | The JavaScript object holding all data inside `index.html` |
| **Desk (headline desk)** | One of the fixed Google News topic queries (Iran war, Ukraine war, …) |
| **EAS** | Emergency Alert System; the real nationwide test on Nov 17, 2026 |
| **Fail soft** | On error, keep the previous data and note "Source down" |
| **GitHub Actions** | GitHub's job runner; runs the "Refresh desk" workflow |
| **GitHub Pages** | GitHub's free web hosting; serves `index.html` from `main` |
| **Kind** | The category tag on each item (`nws`, `quake`, `war-iran`, …) |
| **Lane** | The broad stream an item belongs to (threat, news, local, …) |
| **NHC** | National Hurricane Center |
| **NWS** | National Weather Service (api.weather.gov) |
| **Related (+N related)** | Count of other outlets' copies folded under one story's lead row |
| **Material update** | A known story whose severity rose or whose lead claim changed; shown in What changed as "Update to that story" |
| **Pull request (PR)** | A proposed change waiting for approval; merging it applies the change |
| **Refresh** | One run of the workflow: fetch, rebuild, publish |
| **Shown severity** | Severity after the 72-hour ALERT decay |
| **Skip guard** | Workflow step that cancels a scheduled run if today already has a refresh |
| **So what** | The one-line "what this means / what to do" under an item |
| **Source down** | Display text for a feed that failed this run |
| **SPC** | Storm Prediction Center (tornado and severe-thunderstorm watches and outlooks) |
| **STANDBY** | Severity 0: on file, nothing to do |
| **Standing orders** | The section listing only items that need an action |
| **Storm watch** | The Preparedness card combining NHC, SPC, and local tornado alerts |
| **TEMA** | Tennessee Emergency Management Agency |
| **Trigger** | A hard threshold that raises severity and shows the checklist |
| **WOEID** | Yahoo "Where On Earth ID" used by X trends (US 23424977, world 1) |
