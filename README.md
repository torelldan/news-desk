# News Desk

A static public ledger for a fixed set of podcasts, Substack posts, site pages, and X accounts. `index.html` is one self-contained file. Browsers block `fetch()` of local JSON over `file://`, so `build.py` embeds `data/` at build time.

Times on the page are **America/Chicago**.

**Documentation:** [docs/ONE-PAGER.md](docs/ONE-PAGER.md) (start here), [docs/KDD.md](docs/KDD.md) (Knowledge Design Document: sources, severities, rules), [docs/PFL.md](docs/PFL.md) (Process Flow Layout: architecture, refresh flow, operations). Index: [docs/README.md](docs/README.md).

## Files

- `template.html` — the page. A `/*__DATA__*/` placeholder is where the data goes. Edit the UI here, not in `index.html`.
- `build.py` — reads `data/*.json`, injects it into the template, and writes `index.html`.
- `scripts/sources.json` — the main feeds, the X handles, and the Carota Wealth pages.
- `scripts/fetch.py` — polls those sources and writes `data/`. Read-only. It does not post, like, or message.
- `scripts/desklib.py` — date conversion, note cleaning, dedupe, and the X path guard.
- `scripts/boards.py` — Economic watch, World threat board, assets, Frontier lab, Storm watch, and story matching / clustering.
- `scripts/citizen.py` — the prepared-citizen layer: local 37179, triggers, outlooks, so-what lines, trends, radar, impact, morning brief, history, look-back.
- `tests/test_rules.py` — rule tests. Run `python3 tests/test_rules.py` before proposing a change; the refresh workflow does not run them.
- `data/episodes.json` — main-feed episodes in the retention window.
- `data/signals.json` — Substack posts, public X posts, and page-change notices.
- `data/pages.json` — Carota Wealth page hashes for change detection.
- `data/changes.json` — items new since the previous run. The first run is a baseline and this list is empty.
- `data/meta.json` — last check time (CT), X status, and source errors.
- `data/seen.json` — ids from the last run, used to compute What Changed.
- `data/huberman_notes.json` — official Huberman descriptions already fetched, so the next run does not re-download them.
- `.github/workflows/refresh.yml` — hourly morning tries (09:07–16:53 UTC) that skip once today is refreshed, plus **Run workflow**.
- `docs/` — KDD, PFL, and one-pager.

## What gets collected

Podcast RSS, main feeds only:

- AREA52 DEBRIEFED
- Joe Rogan Experience — skips **JRE MMA Show** and **Protect Our Parks**
- American Alchemy
- Danny Jones
- Huberman Lab — no RSS; episode pages on hubermanlab.com
- Lex Fridman
- Shawn Ryan Show — this feed, not Target Intelligence
- Julian Dorey — this feed, not Julian Dorey Daily

Rules the fetcher enforces:

- Every new main-feed episode inside a 120-day window. Older archive rows age off.
- Skip items that are “You Might Enjoy” cross-promos. A promo footer on a real episode is cut from the note.
- Skip podcast trailers.
- Dedupe by the official description, not the title. A retitled upload of the same episode collapses to one row.
- Notes come from the official description (Huberman: the episode-note paragraph, else the page meta description). The desk does not write recaps and does not store transcripts.
- `pubDate` is converted from UTC to America/Chicago. Huberman listing dates have no clock, so those rows show the calendar date only.

Signals:

- Carota Wealth is read from carotawealth.com (the sitemap, the research page, and any insights or blog URL that answers) with the same Python client Actions uses for the about, services, research, and contact pages. The Substack host is not requested. Previously saved Substack posts stay in the log and are deduped by title.
- Carota Wealth pages `about.html`, `services.html`, `research.html`, and `contact.html`. The fetcher stores a hash of the stable copy in `data/pages.json`. Digits and calendar words are ignored so a live price or an “as of” date does not count as a change. The first sighting of a page is a baseline, not a change.
- X accounts, public posts only: `@AlchemyAmerican` `@AmericanALCHMY` `@hubermanlab` `@joerogan` `@lexfridman` `@JonesDanny` `@ShawnRyanShow` `@ShawnRyan762` `@juliandorey`. Retweets and replies are dropped. **Direct messages are never requested.** Allowed X paths are `/2/users/by`, `/2/users/{id}/tweets`, `/2/trends/by/woeid/{woeid}`, and `/2/tweets/search/recent`. Personalized trends are refused.

Every row links to its source. If a row has no http(s) link, it is dropped.

## Prepared citizen desk

The page is a situation log, not a trading terminal. Every section starts collapsed to one line (status, count, top headline) and opens on click. That choice is remembered in the browser. On a wide screen, Today sits beside the morning brief and standing orders. Standing orders lists only items that need an action. The watchlist is what to monitor. CRITICAL is a U.S. or tsunami-linked quake, a real storm warning, or an asteroid with a real impact score due soon. A routine flyby is not an emergency. A large S&P day raises Economic watch. Iran, Ukraine, and U.S. government headlines are their own current-year groups. What changed includes the previous day when that day is on file. The impact section leads with a plain market read; the price table stays behind “Show the numbers.”

- Economic watch: session hours are converted to America/Chicago in the browser, including daylight time. OPEN/CLOSED treats Saturday and Sunday as closed. Only NYSE holidays are listed; other venues can show OPEN on a local holiday. Index levels come from Yahoo Finance, except IMOEX, which comes from the MOEX ISS API because `IMOEX.ME` returns 404. Yahoo daily bars are dated in the exchange's time zone, not Chicago. Japan and India are their own regions; Asia keeps the Hang Seng. Each region's header names the venue that moved the most. Tokyo's afternoon session closes at 15:30. A USA headline that is only about China's currency is not the USA lead. A macro strip (FX, BIS policy rate, 10-year yield, CPI) is stored in `data/macro.json` and refreshed when it is older than 7 days. A blank level is `n/a`. Headlines are Google News RSS, kept and deduped for `retainDays`, so the 48h / 72h / 4+ day windows fill in across refreshes.
- World threat board: USGS M4.5+ for the week, NHC storm RSS, NWS alerts for Franklin TN (35.925, -86.869), Tennessee, then U.S. tornado, flood, and hurricane warnings, GDACS, ReliefWeb, WHO outbreak notices, CDC HAN when the feed answers, conflict headlines, NASA/JPL close approaches and Sentry, and a link to the Bulletin Doomsday Clock. A statewide Tennessee alert stays ALERT only when its SAME/UGC codes include Williamson (047187) or an adjacent county (Davidson, Rutherford, Maury, Hickman, Dickson, Cheatham). Anywhere else in Tennessee is STANDBY, "elsewhere in TN". Severity runs STANDBY, ALERT, ACTION, CRITICAL.
- Today is X trending topics for the US (WOEID 23424977) and worldwide (WOEID 1), kept only when the name matches war, outbreaks, disasters, hurricanes, floods, tornadoes, earthquakes, existential risk, or economic and preparedness themes. Each row shows post volume and sample links. If the trends endpoint is not on the token's plan, the refresh uses public recent-search counts for those keywords and says so. Followed-account posts stay in the situation log, not in Today.
- Standing orders are the few items that need an action. The watchlist is the monitor list. The threat board is the grouped index. A so-what line appears only when that item calls for something specific.
- Morning brief is 3–5 sentences written from the stored board: what leads, why it is on the page, and whether a trigger says to act.
- Every item has a "so what" line for money, supplies, travel, safety, and an action, or "no action needed".
- Preparedness triggers raise status when a threshold hits: a tropical cyclone toward the Gulf (not the standing NHC basin header), an outbreak notice that names the United States, a quake M7+, a Tennessee tornado or hurricane warning, gold +3% on the day, silver +5%, or BTC/ETH −10%. A short checklist then shows: fuel, water, cash, meds.
- Local layer is Thompson's Station / Williamson County / Middle Tennessee, zip 37179. NWS alerts for 35.802,-86.907, the public Power_TN county summary, TDOT SmartWay events that name Williamson County, and TEMA news releases. TEMA is read from `tn.gov/tema/news-info/news-releases.html` (then `news.html`) with browser-like headers and two retries. The county is taken from the report; only a report that names Williamson County, 37179, or Thompson's Station can be ALERT. Each release shows its date, reports older than about 72 hours drop off, and a later report on the same event replaces earlier ones. If tn.gov does not answer, Williamson County's public-safety RSS is the fallback, and the failure is listed as Source down.
- Storm watch (Preparedness): NHC active storms (`CurrentStorms.json`, RSS fallback), SPC tornado and severe-thunderstorm watches, and SPC Day 1–3 outlooks at 37179, plus any local NWS tornado watch or warning. Data file: `data/storms.json`.
- Impact map keeps the land plot and the DXY, gold, silver, BTC, and ETH series (about 90 days). For each ACTION or CRITICAL event it computes the −1d / +1d / +3d move from stored closes, and a 30- and 90-day correlation of asset daily moves with event categories. The read is "likely linked", "leans together", or "coincidence more likely", with a confidence, or n/a when the window is too thin. Tickers link to the event math. This is not advice.
- Source confidence is confirmed, reported, or rumor, with a count of independent sources. An X-only item cannot be confirmed.
- Narrative radar tracks preparedness talk (US/Europe kit surge, Pentagon off-grid / 90-day stories, official budgets and orders) from public news search: spread velocity, who is driving it, real-world follow-through, and a real-versus-noise score.
- Weekly look-back compares the stored board with about seven days earlier by story, not only by id. The first list is "New since" that day. A story still on the board is not also listed as fizzled. `data/history.json` keeps 21 daily snapshots.
- What changed reports escalations, de-escalations, new and resolved threats, material updates to a known story (a new lead claim, a low token overlap when neither title has a claim word, or a higher severity, shown as "Update to that story"), and new trends, once for the last refresh and once for yesterday, each line named with its section. Something is "new" only if it was published within 36 hours, unless the claim changed. A resolved line appears only when the whole story cluster is gone. A story seen in the last 7 days is not listed as new when it returns.
- Headlines about one story are clustered: the World threat board, Watchlist, and Weekly look-back show one lead row with "+N related" and the other outlets named.

- New data files: `data/trends.json`, `data/triggers.json`, `data/local.json`, `data/storms.json`, `data/radar.json`, `data/impact.json`, `data/history.json`, `data/lookback.json`. The morning brief is `brief` on `data/meta.json`.
- Frontier lab: a capped set of arXiv preprints, phys.org, NASA, Nature, ScienceDaily, bioRxiv, medRxiv, IEEE Spectrum, MIT Technology Review, and the Google AI blog. Preprints are tagged PREPRINT. Journal article URLs are tagged PEER-REVIEWED. News is tagged NEWS.

If a feed fails, the previous JSON for that board is kept and the error is listed in `data/meta.json`. No key is required beyond `X_BEARER_TOKEN`.

## X feed offline

The refresh job reads the Actions secret `X_BEARER_TOKEN`. If that secret is missing, or the API rejects it, X is skipped, the rest of the desk still updates, and the page shows **X feed offline**.

Lookup is one batched `GET /2/users/by?usernames=` call, then `GET /2/users/{id}/tweets` with `Authorization: Bearer`. Today also calls `GET /2/trends/by/woeid/{woeid}` and, only if that endpoint is refused, `GET /2/tweets/search/recent`. Public posts are written into `data/signals.json` with `"kind": "x"`. X `created_at` values look like `2026-10-28T19:02:49.000Z`; those are kept. Retweets and replies are not. A secret pasted with `%3D` in place of `=` is URL-decoded. The workflow log and `data/meta.json` (`x.status`, `x.title`, `x.detail`, `x.reason`) record the HTTP status and the API error title and detail. The token is never written to the log or the JSON.

The 18:49 UTC run reached X and got **HTTP 402 Payment Required**. That is a credits or plan rejection, not a missing secret (that case is logged as `missing X_BEARER_TOKEN`, and a bad token is HTTP 401).

The 19:02 UTC run, after credits were added, found all 9 accounts and saved no posts. X sends `created_at` as `2026-10-28T19:02:49.000Z`. The parser rejected the milliseconds, so every post was dropped and `x.online` stayed true. Those timestamps are kept now. The log prints `api=` / `kept=` / `dropped=` per account.

To turn X on:

1. Create an app-only bearer token in the X developer portal (API v2, read access to public posts).
2. On this repo: **Settings → Secrets and variables → Actions → New repository secret**.
3. Name: `X_BEARER_TOKEN`. Value: the bearer token.
4. Run the refresh workflow. Do not commit the token.

## Manual refresh

The **Refresh** button on the page opens:

https://github.com/torelldan/news-desk/actions/workflows/refresh.yml

That page does not start the job by itself. Click **Run workflow**, keep the branch on `main`, and click the green **Run workflow** button. A manual run always goes through.

The job also has eight scheduled tries each morning: **09:07, 10:17, 11:23, 12:37, 13:15, 14:41, 15:47, and 16:53 UTC** (3:07–10:53 AM CT in winter, 4:07–11:53 AM CT in summer). GitHub delivers scheduled runs late on this repo, sometimes by hours, so these are extra attempts, not a guarantee. A scheduled try checks the last 30 commits for `Refresh desk YYYY-MM-DD` with today's Chicago date and skips if it is there. Only one scheduled refresh lands per day; for a fresh morning desk, a manual run is the reliable path.

The job fetches sources, writes `data/`, runs `build.py`, and commits `data/` plus `index.html` to `main` as `Refresh desk YYYY-MM-DD` when something changed. That push is what republishes GitHub Pages, usually live 3–5 minutes later. If nothing changed, no commit is made.

If `main` is protected, allow `github-actions[bot]` to push, or the commit step will fail.

## GitHub Pages

After this lands on `main`:

1. **Settings → Pages**.
2. **Build and deployment → Source: Deploy from a branch**.
3. Branch: **main**. Folder: **/ (root)**. Save.

The site is `index.html` at the repository root. A `.nojekyll` file is included so Pages serves it as-is. The next refresh commit on `main` republishes the desk.

## Local

```bash
python3 tests/test_rules.py
python3 scripts/fetch.py
python3 build.py
```

Open `index.html`. `fetch.py` uses only the Python standard library. With no `X_BEARER_TOKEN` in the environment, the X section stays offline.
