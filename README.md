# News Desk

A static public ledger for a fixed set of podcasts, Substack posts, site pages, and X accounts. `index.html` is one self-contained file. Browsers block `fetch()` of local JSON over `file://`, so `build.py` embeds `data/` at build time.

Times on the page are **America/Chicago**.

## Files

- `template.html` — the page. A `/*__DATA__*/` placeholder is where the data goes. Edit the UI here, not in `index.html`.
- `build.py` — reads `data/*.json`, injects it into the template, and writes `index.html`.
- `scripts/sources.json` — the main feeds, the X handles, and the Carota Wealth pages.
- `scripts/fetch.py` — polls those sources and writes `data/`. Read-only. It does not post, like, or message.
- `scripts/desklib.py` — date conversion, note cleaning, dedupe, and the X path guard.
- `data/episodes.json` — main-feed episodes in the retention window.
- `data/signals.json` — Substack posts, public X posts, and page-change notices.
- `data/pages.json` — Carota Wealth page hashes for change detection.
- `data/changes.json` — items new since the previous run. The first run is a baseline and this list is empty.
- `data/meta.json` — last check time (CT), X status, and source errors.
- `data/seen.json` — ids from the last run, used to compute What Changed.
- `data/huberman_notes.json` — official Huberman descriptions already fetched, so the next run does not re-download them.
- `.github/workflows/refresh.yml` — daily cron plus **Run workflow**.

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

- Carota Wealth Substack RSS (`carotawealth.substack.com/feed`). Actions' Python TLS handshake is rejected by Substack, so the feed is downloaded with `curl`, then `feed.xml` and the `www` host. If every attempt fails, the previously saved Substack posts stay in `data/signals.json`.
- Carota Wealth pages `about.html`, `services.html`, `research.html`, and `contact.html`. The fetcher stores a hash of the stable copy in `data/pages.json`. Digits and calendar words are ignored so a live price or an “as of” date does not count as a change. The first sighting of a page is a baseline, not a change.
- X accounts, public posts only: `@AlchemyAmerican` `@AmericanALCHMY` `@hubermanlab` `@joerogan` `@lexfridman` `@JonesDanny` `@ShawnRyanShow` `@ShawnRyan762` `@juliandorey`. Retweets and replies are dropped. **Direct messages are never requested.** The only X paths the script will call are `/2/users/by` and `/2/users/{id}/tweets`.

Every row links to its source. If a row has no http(s) link, it is dropped.

## X feed offline

The refresh job reads the Actions secret `X_BEARER_TOKEN`. If that secret is missing, or the API rejects it, X is skipped, the rest of the desk still updates, and the page shows **X feed offline**.

Lookup is one batched `GET /2/users/by?usernames=` call, then `GET /2/users/{id}/tweets` with `Authorization: Bearer`. Public posts are written into `data/signals.json` with `"kind": "x"`. X `created_at` values look like `2026-10-28T19:02:49.000Z`; those are kept. Retweets and replies are not. A secret pasted with `%3D` in place of `=` is URL-decoded. The workflow log and `data/meta.json` (`x.status`, `x.title`, `x.detail`, `x.reason`) record the HTTP status and the API error title and detail. The token is never written to the log or the JSON.

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

That page does not start the job by itself. Click **Run workflow**. The same job also runs every day at **13:15 UTC** (8:15 AM CT while daylight time is in effect, 7:15 AM CT after the fall time change).

The job fetches sources, writes `data/`, runs `build.py`, and commits `data/` plus `index.html` to `main` when something changed. That push is what republishes GitHub Pages.

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
