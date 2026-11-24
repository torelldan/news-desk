#!/usr/bin/env python3
"""Rules that do not need the network."""
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import desklib as d


def test_x_created_at_with_milliseconds():
    parsed = d.parse_pubdate("2026-10-28T19:02:49.000Z")
    assert parsed is not None
    assert parsed.strftime("%Y-%m-%d") == "2026-10-28"
    assert parsed.hour == 14  # 19:02 UTC is 2:02 PM CT in October
    assert d.parse_pubdate("Wed, 28 Oct 2026 19:02:49 GMT") is not None


def test_ct_conversion():
    raw = "Fri, 23 Oct 2026 17:00:00 -0000"
    ct = d.parse_pubdate(raw)
    assert ct is not None
    assert ct.tzinfo is not None
    assert ct.utcoffset().total_seconds() == -5 * 3600  # CDT on Oct 23 2026
    assert d.ct_label(ct) == "Oct 23, 2026 12:00 PM CT"
    assert ct.strftime("%Y-%m-%d") == "2026-10-23"


def test_jre_skips_and_keeps_main_feed():
    needles = ["jre mma", "protect our parks"]
    assert d.title_skipped("JRE MMA Show #187 with Robert Whittaker", needles)
    assert d.title_skipped("#2539 - Protect Our Parks 17", needles)
    assert not d.title_skipped("JRE MMA Show #182 - Protect Ya Neck", ["protect our parks"])
    assert d.title_skipped("JRE MMA Show #182 - Protect Ya Neck", needles)
    assert not d.title_skipped("#2570 - Mystery Boys", needles)


def test_other_shows_stay_on_their_feeds():
    assert d.channel_rejected("Target Intelligence", ["target intelligence"])
    assert not d.channel_rejected("The Shawn Ryan Show", ["target intelligence"])
    assert d.channel_rejected("Julian Dorey Daily", ["julian dorey daily"])
    assert not d.channel_rejected("Julian Dorey Podcast", ["julian dorey daily"])


def test_cross_promo_and_notes():
    official = (
        "Kurt Metzger and Duncan Trussell are comedians who host their own shows and this one. "
        "Learn more about your ad choices. Visit podcastchoices.com/adchoices"
    )
    assert d.clean_note(official).startswith("Kurt Metzger and Duncan Trussell are comedians")
    assert "ad choices" not in d.clean_note(official).lower()
    mixed = "A real episode about radar sites and the people who run them. You Might Enjoy: Some Other Show"
    assert d.clean_note(mixed).startswith("A real episode about radar")
    assert "you might enjoy" not in d.clean_note(mixed).lower()
    assert not d.is_cross_promo("A real episode", mixed)
    assert d.is_cross_promo("You Might Enjoy: Other Show", "promo copy")
    promo = (
        "SPONSORS: 1) PERPLEXITY: Start your free trial of Perplexity Computer today at https://pplx.ai/x #ad. "
        "JOIN PATREON FOR EARLY EPISODES. "
        "(***TIMESTAMPS in Description Below) ~ John Van Duyn, Medieval Mindset, is a popular digital creator "
        "who explores the historical past and contrasts it with modern life across long essays. "
        "****TIMESTAMPS**** 0:00 - Intro and opening chat about Rome."
    )
    note = d.clean_note(promo)
    assert note.startswith("John Van Duyn")
    assert "PATREON" not in note
    assert "0:00" not in note


def test_numbered_parts_stay_separate():
    note = (
        "Raymond Leo Cardinal Burke is an American cardinal and canon lawyer who defends "
        "traditional doctrine across long public interviews and published lectures."
    )
    a = {"id": "a", "sourceId": "shawn", "title": "#338 Cardinal Burke - The New Testament", "note": note, "url": "https://ex/a", "published": "2026-10-02T00:00:00-05:00"}
    b = {"id": "b", "sourceId": "shawn", "title": "#337 Cardinal Burke - The Old Testament", "note": note, "url": "https://ex/b", "published": "2026-10-01T00:00:00-05:00"}
    assert len(d.dedupe_items([a, b], set())) == 2


def test_dedupe_by_description_not_title():
    note = (
        "Two comedians walk through a long official description that is easily "
        "long enough to fingerprint without using the episode title at all."
    )
    a = {"id": "jre:1", "sourceId": "jre", "title": "#1 - Old Title", "note": note, "url": "https://ex/a", "published": "2026-10-01T00:00:00-05:00"}
    b = {"id": "jre:2", "sourceId": "jre", "title": "Completely Different Title", "note": note, "url": "https://ex/b", "published": "2026-10-02T00:00:00-05:00"}
    kept = d.dedupe_items([a, b], set())
    assert len(kept) == 1
    assert kept[0]["id"] == "jre:2"
    # Same guest, different official notes: keep both.
    c = dict(a, id="jre:3", note=note + " A second episode with its own official description and different facts.", url="https://ex/c", guest="Same Guest")
    b2 = dict(b, guest="Same Guest")
    assert len(d.dedupe_items([b2, c], set())) == 2
    # Prefer an id we already published so the ledger does not flap.
    again = d.dedupe_items([a, b], {"jre:1"})
    assert again[0]["id"] == "jre:1"


def test_guest_parser():
    assert d.guest_from_title("#2570 - Mystery Boys") == "Mystery Boys"
    assert d.guest_from_title("Unlocking Persistent Motivation | Ross Edgley") == "Ross Edgley"
    assert d.guest_from_title("#443 - Ex-Banker Exposes Who Trump Actually Works For | Simon Dixon") == "Simon Dixon"
    assert d.guest_from_title("#351 Chris Hansen - Hollywood’s Movie") == "Chris Hansen"
    assert d.guest_from_title("#503 – AI Crisis in Math: Navier-Stokes and More") == ""


def test_page_hash_ignores_clocks():
    a = "<html><body><p>Regime note October 28, 2026 price $10.50</p><script>var x=1</script></body></html>"
    b = "<html><body><p>Regime note November 2, 2026 price $99</p><script>var x=2</script></body></html>"
    c = "<html><body><p>Regime note changed October 28, 2026 price $10.50</p></body></html>"
    assert d.page_hash(a) == d.page_hash(b)
    assert d.page_hash(a) != d.page_hash(c)


def test_x_paths_never_include_dms():
    assert d.assert_public_x_path("/2/users/by") == "/2/users/by"
    assert d.assert_public_x_path("/2/users/99/tweets") == "/2/users/99/tweets"
    assert d.assert_public_x_path("/2/trends/by/woeid/23424977") == "/2/trends/by/woeid/23424977"
    assert d.assert_public_x_path("/2/tweets/search/recent") == "/2/tweets/search/recent"
    for blocked in ("/2/dm_events", "/2/dm_conversations", "/1.1/direct_messages/events/list.json", "/2/users/9/dm", "/2/users/personalized_trends"):
        try:
            d.assert_public_x_path(blocked)
        except RuntimeError:
            pass
        else:
            raise AssertionError(blocked)


def test_bearer_and_x_errors():
    assert d.normalize_bearer("abc%3D%3D") == "abc=="
    assert d.normalize_bearer("Bearer abc%3D") == "abc="
    assert d.normalize_bearer("  raw-token==  ") == "raw-token=="
    body = '{"title":"CreditsDepleted","detail":"Your enrolled account does not have any credits.","status":402}'
    info = d.describe_x_error(402, body, token="super-secret-token")
    assert info["status"] == 402
    assert info["title"] == "CreditsDepleted"
    assert "credits" in info["detail"].lower()
    assert "HTTP 402 Payment Required (credits or plan)" in info["reason"]
    assert "CreditsDepleted" in info["reason"]
    assert "super-secret-token" not in info["reason"]
    leaked = '{"title":"Bad","detail":"rejected super-secret-token"}'
    hidden = d.describe_x_error(401, leaked, token="super-secret-token")
    assert "super-secret-token" not in hidden["reason"]
    assert "HTTP 401 Unauthorized" in hidden["reason"]
    assert hidden["detail"] == "rejected [redacted]"
    limited = '{"errors":[{"message":"Rate limit exceeded","code":88}]}'
    rate = d.describe_x_error(429, limited)
    assert "HTTP 429 Too Many Requests (rate limit)" in rate["reason"]
    assert "Rate limit exceeded" in rate["reason"]
    batches = d.username_batches(["@joerogan", "joerogan", "lexfridman"])
    assert batches == [["joerogan", "lexfridman"]]
    urls = d.carota_feed_candidates("https://carotawealth.substack.com/feed")
    assert urls[0] == "https://carotawealth.substack.com/feed"
    assert "https://carotawealth.substack.com/feed.xml" in urls
    assert len(urls) == len(set(urls))


def test_carota_reads_site_and_keeps_cached_titles():
    import urllib.error
    from datetime import datetime
    from zoneinfo import ZoneInfo
    import fetch
    calls = []
    sitemap = b"""<?xml version="1.0"?><urlset>
      <url><loc>https://carotawealth.com/research</loc></url>
    </urlset>"""
    page = """<html><body>
      <h2 class="sec-title">Market <em>Overview</em></h2>
      <p class="sec-sub">Cross-asset view spanning U.S. indices, hard assets, and forex in one live dashboard for the desk.</p>
      <h2 class="sec-title">The Inflation Number Changed. Your Cost of Living Didn't.</h2>
      <p class="sec-sub">This site section repeats a cached essay title and should collapse to one row.</p>
    </body></html>""".encode()

    def fake_get(url, timeout=45, headers=None, user_agent=None):
        calls.append(url)
        if url.endswith("sitemap.xml"):
            return sitemap, url, 200
        if url.rstrip("/").endswith("/research"):
            return page, "https://carotawealth.com/research", 200
        raise urllib.error.HTTPError(url, 404, "Not Found", hdrs=None, fp=None)

    cached = [{
        "id": "carota:old", "kind": "substack", "lane": "substack", "sourceId": "carota",
        "source": "Carota Wealth", "title": "The Inflation Number Changed. Your Cost of Living Didn't.",
        "guest": "", "note": "Cached official essay.", "url": "https://carotawealth.substack.com/p/the-inflation-number-changed-your",
        "published": "2026-10-02T11:54:37-05:00", "date": "2026-10-02", "label": "Oct 2, 2026 11:54 AM CT",
        "weekday": "Fri", "timeKnown": True, "tags": ["substack", "carota"],
    }]
    real = fetch.get_bytes
    fetch.get_bytes = fake_get
    try:
        spec = {"id": "carota", "name": "Carota Wealth", "_retain": 120}
        items, home, channel = fetch.fetch_carota(spec, datetime(2026, 10, 28, 12, tzinfo=ZoneInfo("America/Chicago")), cached)
    finally:
        fetch.get_bytes = real
    assert all("substack.com" not in url for url in calls)
    titles = [item["title"] for item in items]
    assert titles.count("The Inflation Number Changed. Your Cost of Living Didn't.") == 1
    kept = [item for item in items if item["title"].startswith("The Inflation")][0]
    assert kept["date"] == "2026-10-02"
    assert "/p/" in kept["url"]
    assert any(item["title"] == "Market Overview" and item["url"].endswith("#market-overview") for item in items)
    assert home == "https://carotawealth.com/research"
    assert channel == "Carota Wealth"


def test_x_millis_posts_are_not_dropped():
    import fetch
    reason = fetch.tweet_skip_reason(
        {"id": "99", "text": "Public post from the account.", "created_at": "2026-10-28T19:02:49.000Z"},
        "2026-06-01",
    )
    assert reason is None
    assert fetch.tweet_skip_reason(
        {"id": "99", "text": "hello", "created_at": "2026-10-28T19:02:49.000Z", "referenced_tweets": [{"type": "replied_to"}]},
        "2026-06-01",
    ) == "repost"


def test_board_helpers():
    import boards
    assert boards.index_change(100, 80) == (20.0, 25.0)
    assert boards.index_change(None, 10) == (None, None)
    assert boards.quake_severity(7.1) == "STANDBY"
    assert boards.quake_severity(7.1, "12 km NE of Knoxville, Tennessee") == "CRITICAL"
    assert boards.quake_severity(6.2) == "STANDBY"
    assert boards.quake_severity(6.5, "Vanuatu region") == "STANDBY"
    assert boards.quake_severity(6.2, "Ridgecrest, California") == "ACTION"
    assert boards.quake_severity(5.6, "Nashville, Tennessee") == "ALERT"
    assert boards.quake_severity(4.6) == "STANDBY"
    assert boards.keep_quake(5.0, "Hasaki, Japan", False, "", 0) is False
    assert boards.keep_quake(5.7, "Hasaki, Japan", False, "", 0) is True
    assert boards.keep_quake(6.4, "off Honshu, Japan", False, "yellow", 0) is True
    assert boards.keep_quake(4.8, "10 km NW of Pinnacles, California") is True
    old = {"severity": "ALERT", "published": "2026-10-28T12:00:00-05:00", "title": "old wire"}
    fresh = {"severity": "ALERT", "published": "2026-11-09T08:00:00-06:00", "title": "new wire"}
    from datetime import datetime
    boards.demote_stale_alerts([old, fresh], datetime.fromisoformat("2026-11-09T09:26:00-06:00"))
    assert old["severity"] == "STANDBY"
    assert fresh["severity"] == "ALERT"
    assert boards._storm_severity("There are no tropical cyclones at this time.", "") == "STANDBY"
    assert boards._storm_severity("Atlantic Tropical Weather Outlook", "No cyclones") == "STANDBY"
    assert boards._sentry_level({"ts_max": "0", "ps_max": "-6.15", "ip": "2.9e-06"}) == ""
    assert boards._sentry_level({"ts_max": "1", "ps_max": "-4", "ip": "0"}) == "ALERT"
    assert boards._sentry_soon({"range": "2095-2122"}, 2026) is False
    assert boards._sentry_soon({"range": "2028-2030"}, 2026) is True
    assert boards.alert_severity("Tornado Warning", "Extreme") == "CRITICAL"
    assert boards.alert_severity("Flood Warning", "Severe") == "ACTION"
    assert boards.alert_severity("Flood Watch", "Minor") == "ALERT"


def test_urls_and_ids():
    assert d.http_url("https://example.com/a") == "https://example.com/a"
    assert d.http_url("javascript:alert(1)") == ""
    assert d.make_id("jre", "https://example.com/a") == d.make_id("jre", "https://example.com/a")
    assert d.make_id("jre", "https://example.com/a") != d.make_id("lex", "https://example.com/a")


def test_trend_filter_and_confidence():
    import citizen
    kept = citizen.filter_trends([
        {"trend_name": "Hurricane in the Gulf", "tweet_count": 12000},
        {"trend_name": "Taylor Swift", "tweet_count": 900000},
        {"trend_name": "gold inflation", "tweet_count": 4000},
        {"trend_name": "Secretary of War", "tweet_count": 80000},
    ], "US")
    names = {row["name"] for row in kept}
    assert "Hurricane in the Gulf" in names
    assert "Taylor Swift" not in names
    assert "gold inflation" in names
    assert "Secretary of War" not in names
    terms = citizen.board_terms(
        [
            {"kind": "quake", "title": "M5.8 150 km SW of Merizo Village, Guam", "mag": 5.8},
            {"kind": "cyber", "title": "USDA hit with cyberattack: Sources - ABC News"},
            {"kind": "infra", "title": "Internet services disrupted across Pakistan", "asset": "cable", "region": "Baltic Sea"},
        ],
        [{"country": "Sudan", "title": "Drone attacks kill four near Sudan’s capital"}],
        {"markets": [{"topic": "inflation"}], "labs": [{"topic": "OpenAI"}]},
    )
    assert len(terms) <= 40
    assert any(term["term"] == "guam" for term in terms)
    assert any(term["term"] == "usda" for term in terms)
    assert all(term["term"] not in {"the", "news", "update"} for term in terms)
    guam = citizen.filter_trends([
        {"trend_name": "Guam", "tweet_count": 1000},
        {"trend_name": "USDA", "tweet_count": 800},
        {"trend_name": "Taylor Swift", "tweet_count": 9},
    ], "US", terms)
    matched = {row["name"]: row["matched"] for row in guam}
    assert "Guam" in matched and matched["Guam"].startswith("matches:")
    assert "USDA" in matched and "USDA" in matched["USDA"]
    assert "Taylor Swift" not in matched
    weak = citizen.board_terms(
        [{"kind": "cyber", "title": "FBI reportedly facing second data breach involving National Crime Information Center"}],
        [{"country": "Ukraine", "title": "Missile strikes on Ukraine"}],
        {},
    )
    assert all(term["term"] not in {"national", "security", "crime", "information", "center"} for term in weak)
    weak_kept = citizen.filter_trends([
        {"trend_name": "National Security", "tweet_count": 5000},
        {"trend_name": "Ukraine", "tweet_count": 8000},
    ], "US", weak)
    weak_names = {row["name"]: row["matched"] for row in weak_kept}
    assert "National Security" not in weak_names
    assert "Ukraine" in weak_names and weak_names["Ukraine"] == "matches: Ukraine"
    assert citizen.match_board_term("National Security", weak) == ""
    assert "none of the names matched" in citizen.x_trends_note(0, 80).lower()
    assert citizen.x_trends_note(1, 80).endswith("1 of 80 X trends matched today's board.")
    assert "none of the names matched" not in citizen.x_trends_note(1, 80).lower()
    assert "None of today's search trends matched" in citizen.google_trends_note(0, 10)
    assert "2 of 10 Google trends matched today's board" in citizen.google_trends_note(2, 10)
    shaped = citizen.shape_trend_panel({
        "raw": [
            {"place": "US", "trend_name": "Cubs", "tweet_count": 10},
            {"place": "US", "trend_name": "Cubs", "tweet_count": 50},
            {"place": "worldwide", "trend_name": "Cubs", "tweet_count": 5},
            {"place": "US", "trend_name": "東京", "tweet_count": 3},
            {"place": "worldwide", "trend_name": "Ukraine", "tweet_count": None},
            {"place": "worldwide", "trend_name": "Nvidia", "tweet_count": 100},
            {"place": "worldwide", "trend_name": "National Security", "tweet_count": 9000},
        ],
        "google_all": [
            {"name": "東京", "place": "US", "volume": "200K+", "headlines": [
                {"title": "Tokyo story", "url": "https://example.com/t", "source": "NHK"},
                {"title": "skip", "url": "javascript:alert(1)", "source": "bad"},
            ]},
            {"name": "Weather", "place": "US", "volume": "50K+", "headlines": []},
        ],
    }, weak)
    us_names = [row["name"] for row in shaped["x_us"]]
    assert us_names.count("Cubs") == 1
    assert shaped["x_us"][0]["name"] == "Cubs" and shaped["x_us"][0]["volume"] == 50
    assert "東京" in us_names
    world = shaped["x_world"]
    assert [row["name"] for row in world] == ["National Security", "Nvidia", "Cubs", "Ukraine"]
    ukraine = next(row for row in world if row["name"] == "Ukraine")
    assert ukraine["matched"] == "matches: Ukraine"
    assert ukraine["volume"] is None
    assert world[0]["matched"] == ""
    assert shaped["google_all"][0]["name"] == "東京"
    assert shaped["google_all"][0]["headlines"] == [{"title": "Tokyo story", "url": "https://example.com/t", "source": "NHK"}]
    assert len(shaped["raw"]) == 6
    assert citizen.trend_is_offline({"mode": "trends", "status": "ok", "note": "X trends by WOEID (US 23424977). The endpoint answered and none of the names matched."}) is False
    assert citizen.trend_is_offline({"mode": "offline"}) is True
    assert citizen.trend_is_offline({"mode": "trends", "note": "endpoint answered"}) is False
    assert citizen.topic_of("Iran war") == "iran-war"
    assert citizen.topic_of("Eisenkot asked to form Israel's government") == "israel"
    assert citizen.topic_of("COP31 opens in Antalya") == "climate"
    assert citizen.topic_of("G7 ministers meet Rubio in Paris") == "g7"
    assert citizen.topic_of("Trump casts doubt on the midterms") == "election"
    assert citizen.topic_of("Krakow attack wounds several") == "attack"
    stamped = citizen.news_velocity([
        {"kind": "war-iran", "title": "Iran war one", "source": "A", "url": "https://a.example/1", "published": "2026-11-05T02:00:00-06:00", "date": "2026-11-05"},
        {"kind": "war-iran", "title": "Iran war two", "source": "B", "url": "https://b.example/2", "published": "2026-11-05T10:00:00-06:00", "date": "2026-11-05"},
        {"kind": "war-iran", "title": "Iran war three", "source": "C", "url": "https://c.example/3", "published": "2026-11-04T10:00:00-06:00", "date": "2026-11-04"},
    ])
    assert stamped[0]["date"] == "2026-11-05"
    from datetime import datetime
    found = citizen.news_velocity([
        {"kind": "war-ukraine", "title": "Ukraine one", "source": "A", "url": "https://a.example/1", "published": "2026-11-04T19:15:23-06:00", "date": "2026-11-04"},
        {"kind": "war-ukraine", "title": "Ukraine two", "source": "B", "url": "https://b.example/2", "published": "2026-11-04T19:15:23-06:00", "date": "2026-11-04"},
        {"kind": "war-ukraine", "title": "Ukraine three", "source": "C", "url": "https://c.example/3", "published": "2026-11-04T19:15:23-06:00", "date": "2026-11-04"},
    ], datetime.fromisoformat("2026-11-05T16:57:59-06:00"))
    assert found[0]["published"].startswith("2026-11-05T16:57:59")
    assert found[0]["date"] == "2026-11-05"
    x_only = citizen.confidence_for({"lane": "x", "kind": "trend"})
    assert x_only["confidence"] == "rumor"
    confirmed = citizen.confidence_for({"lane": "x", "kind": "trend"}, extra_domains=2)
    assert confirmed["confidence"] != "confirmed"
    official = citizen.confidence_for({"lane": "official", "kind": "quake"}, extra_domains=1)
    assert official["confidence"] == "confirmed"
    line = citizen.so_what({"kind": "nws", "severity": "ACTION", "title": "Flood Warning", "note": "Bradley, TN"})
    assert "Bradley" in line
    assert "Gulf" not in line
    flyby = citizen.so_what({"kind": "neo", "severity": "CRITICAL", "title": "Close approach 2019 XF2"})
    assert flyby == "no action needed"
    assert "water" not in flyby
    assert citizen.so_what({"kind": "quake", "severity": "ACTION", "title": "M6.1 Fiji region"}) == "no action needed"
    quiet = citizen.so_what({"kind": "episode", "severity": "STANDBY", "lane": "podcast"})
    assert quiet == ""


def test_triggers_outlook_and_impact():
    import citizen
    threats = [{
        "id": "storm-1",
        "kind": "storm",
        "title": "Hurricane moving into the Gulf",
        "note": "Tropical storm in the Gulf",
        "url": "https://www.nhc.noaa.gov/",
        "severity": "ALERT",
        "date": "2026-11-01",
    }]
    assets = {"series": [{
        "id": "gold",
        "name": "Gold",
        "changePct": 3.4,
        "source": "https://finance.yahoo.com/quote/GC=F",
        "points": [
            {"date": "2026-10-30", "price": 100},
            {"date": "2026-10-31", "price": 101},
            {"date": "2026-11-01", "price": 102},
            {"date": "2026-11-02", "price": 104},
            {"date": "2026-11-04", "price": 103},
        ],
    }]}
    boilerplate = [{
        "id": "outlook",
        "kind": "storm",
        "title": "Atlantic Tropical Weather Outlook",
        "note": "For the North Atlantic...Caribbean Sea and the Gulf of America: A non-tropical low in the central Atlantic.",
        "url": "https://www.nhc.noaa.gov/",
        "severity": "ALERT",
        "date": "2026-11-04",
    }]
    quiet = citizen.evaluate_triggers(boilerplate, {"series": []}, {"items": []})
    assert "gulf-storm" not in {row["id"] for row in quiet["items"]}
    fired = citizen.evaluate_triggers(threats, assets, {"items": []})
    ids = {row["id"] for row in fired["items"]}
    assert "gulf-storm" in ids
    assert "gold-3" in ids
    assert threats[0]["severity"] == "ACTION"
    assert fired["checklist"] == ["fuel", "water", "cash", "meds"]
    history = {"days": [{"date": "2026-10-31", "threats": [{"id": "storm-1", "severity": "STANDBY"}]}]}
    citizen.apply_outlook(threats, history, "2026-11-01")
    assert threats[0]["arrowDay"] == "↑"
    window = citizen.event_window(assets["series"][0]["points"], "2026-11-01")
    assert window["m1"] == 1.0
    assert window["p1"] == round((104 / 101 - 1) * 100, 2)
    report = citizen.impact_report(threats, assets)
    assert report["events"] and report["events"][0]["moves"][0]["p1"] == window["p1"]
    doc = citizen.trends_from_search([{"category": "earthquake", "query": "earthquake", "tweets": [{"id": "10", "text": "quake"}], "resultCount": 4}])
    assert doc["mode"] == "recent-search"
    assert "not available" in doc["note"]
    citizen.annotate_trends(doc, [])
    assert doc["items"][0]["confidence"] == "rumor"
    brief = citizen.morning_brief(threats, doc, fired, assets, {"items": []})
    assert "Gulf" in brief or "Hurricane" in brief
    assert "flyby" not in brief.lower() or "not an emergency" in brief.lower()
    stored = citizen.record_history({"days": []}, "2026-11-01", threats, doc, fired, "Nov 1")
    later = citizen.record_history(stored, "2026-11-08", [{"id": "storm-1", "title": "Hurricane", "severity": "CRITICAL", "kind": "storm"}], doc, fired, "Nov 8")
    look = citizen.weekly_lookback(later, "2026-11-08")
    assert look["escalated"]
    assert any(call["verdict"] == "right" for call in look["calls"]) or look["escalated"]


def test_blackout_rumor_hides_after_nov_18():
    from datetime import date
    event = date(2026, 11, 17)
    hide_after = date(2026, 11, 18)
    def visible(day):
        return day <= hide_after
    def days_until(day):
        return (event - day).days
    assert days_until(date(2026, 11, 9)) == 8
    assert days_until(date(2026, 11, 17)) == 0
    assert visible(date(2026, 11, 18)) is True
    assert visible(date(2026, 11, 19)) is False
    page = open("template.html", encoding="utf-8").read()
    assert "2026-11-18" in page
    assert "No blackout, internet shutdown, or bank wipe is scheduled." in page


def test_conflict_kind_requires_the_headline():
    import boards
    import citizen
    massie = "Rep. Thomas Massie of Kentucky launches bid to impeach Defense Secretary Pete Hegseth - MPR News"
    assert boards.classify_desk(massie, "", "war-iran") == "usgov"
    assert boards.classify_desk("Trump says Iran war to end fairly soon", "", "war-iran") == "war-iran"
    assert boards.classify_desk("Markets rally after the open", "", "war-iran") == "news"
    assert "Skip travel" not in citizen.so_what({"kind": "war-iran", "severity": "ALERT", "title": massie, "note": ""})
    assert "Skip travel" in citizen.so_what({"kind": "war-iran", "severity": "ALERT", "title": "Trump says the Iran war is still on", "note": ""})


def test_same_story_prefers_the_newest_outlet():
    import boards
    opb = "Israel's president taps opposition candidate, not Netanyahu, to form a government - Oregon Public Broadcasting - OPB"
    reuters = "Israeli president picks Gadi Eisenkot, Netanyahu rival, to try to form government - Reuters"
    pbs = "Israel's president takes first steps on building new government after accepting election results - PBS"
    assert boards.same_story(opb, reuters)
    assert boards.same_story(opb, pbs)
    killed = "Polish gunman who killed 6 people in Krakow has 'ultranationalistic' views, authorities say - NPR"
    died = "Suspect in mass shooting in Krakow, Poland, dies in hospital - AP"
    square = "At least 6 killed, several injured in shooting at Polish market square: Police - ABC News"
    assert boards.same_story(killed, died)
    assert boards.same_story(killed, square)
    talks = "Russia, Ukraine and US meet for Abu Dhabi talks as Trump says war can end soon - ABC News"
    oleshky = "Oleshky Ceasefire Demonstrates That Russia Has the Capability, but Not the Will, to End Civilian Suffering in Ukraine"
    assert boards.same_story(talks, oleshky) is False
    time_pm = "How Israel Will Choose Its Next Prime Minister, Explained - Time Magazine"
    eisenkot = "Israel's parliament sworn in as Eisenkot tries to forge a government - Reuters"
    assert boards.same_story(time_pm, eisenkot)
    assert boards.same_story(time_pm, "Israel strikes targets in Gaza - Reuters") is False
    peace = "US attempts new peace push at first Russia-Ukraine talks in nine months - Reuters"
    abu = "Russia, Ukraine and US meet for Abu Dhabi talks as Trump says war can end soon - ABC News"
    assert boards.same_story(peace, abu)
    assert boards.same_story(peace, oleshky) is False
    cop_space = "What to Expect at COP 31: Key issues and how the negotiations work"
    cop_tight = "COP31 to take place 9-20 November 2026 in Antalya, Türkiye"
    assert boards.same_story(cop_space, cop_tight)
    assert boards.classify_desk(cop_space, "", "climate") == "climate"
    assert "quiet tropical line" not in boards.storm_watch_note([{"kind": "tropical", "title": "Tropical Storm Pena"}])
    assert "quiet tropical line" in boards.storm_watch_note([{"kind": "tropical", "title": "No active tropical systems"}])
    sources = boards.storm_source_rows({"items": [{"kind": "tropical", "label": "Nov 11, 2026 8:59 AM CT", "date": "2026-11-11", "published": "2026-11-11T08:59:00-06:00"}, {"kind": "spc-outlook", "label": "Nov 11, 2026 8:59 AM CT", "date": "2026-11-11", "published": "2026-11-11T08:59:00-06:00"}], "gaps": []})
    nhc = next(row for row in sources if row["short"] == "NHC")
    spc = next(row for row in sources if row["short"] == "SPC")
    assert nhc["count"] == 1 and nhc["lastLabel"].startswith("Nov 11")
    assert spc["count"] == 1 and spc["lastDate"] == "2026-11-11"
    rows = [
        {"title": opb, "kind": "israel", "published": "2026-11-08T10:00:00-06:00"},
        {"title": reuters, "kind": "israel", "published": "2026-11-08T12:00:00-06:00"},
        {"title": pbs, "kind": "israel", "published": "2026-11-04T08:00:00-06:00"},
        {"title": square, "kind": "attack", "published": "2026-11-09T11:00:00-06:00"},
        {"title": killed, "kind": "attack", "published": "2026-11-07T09:00:00-06:00"},
        {"title": died, "kind": "attack", "published": "2026-11-09T09:00:00-06:00"},
    ]
    kept = boards.fold_desk_rows(rows)
    titles = [row["title"] for row in kept]
    assert titles.count(reuters) == 1
    assert opb not in titles and pbs not in titles
    assert square in titles and died not in titles and killed not in titles
    prev = [{"id": "npr", "title": "Israeli president picks Gadi Eisenkot, Netanyahu rival, to try to form government - NPR", "severity": "ALERT"}]
    current = {"id": "opb", "title": opb, "severity": "ALERT"}
    assert boards.prior_item(current, prev)["id"] == "npr"


def test_tema_news_releases_parse():
    import citizen
    from datetime import datetime
    html = '''
      <a href="/tema/news.html">News</a>
      <a href="/tema/news/2026/11/6/flash-report--2---polk-county-flooding.html">Flash Report #2 - Polk County Flooding</a>
      <a href="/tema/news/2026/11/6/flash-report--2---polk-county-flooding.html">Read full story</a>
      <a href="/tema/news/2026/4/13/readytn-faith.html">ReadyTN Faith Program Launches</a>
    '''
    rows = citizen.tema_notices(html, datetime.fromisoformat("2026-11-08T12:00:00-06:00"))
    assert len(rows) == 1
    assert rows[0]["date"] == "2026-11-06"
    assert rows[0]["url"].startswith("https://www.tn.gov/tema/news/2026/11/6/")
    assert rows[0]["severity"] == "STANDBY"
    assert "williamson" not in rows[0]["tags"]
    assert "Nov" in rows[0]["label"]
    page = open(".github/workflows/refresh.yml", encoding="utf-8").read()
    assert "workflow_dispatch:" in page
    assert 'cron: "7 9 * * *"' in page
    assert 'cron: "53 16 * * *"' in page
    template = open("template.html", encoding="utf-8").read()
    assert "function leadItem" in template
    assert "function changeStatus" in template
    assert "board[0]" not in template.split("function paintSections")[1].split("function marketBullets")[0]


def test_storm_watch_severity_and_european_names():
    import boards
    import citizen
    assert boards.alert_severity("Tornado Watch", "Severe") == "ALERT"
    assert boards.alert_severity("Tornado Warning", "Extreme") == "CRITICAL"
    assert boards.alert_severity("Hurricane Warning", "Extreme") == "CRITICAL"
    assert boards.alert_severity("Tropical Storm Warning", "Severe") == "ACTION"
    assert boards.alert_severity("Tropical Storm Watch", "Moderate") == "ALERT"
    assert boards.alert_severity("Flash Flood Warning", "Severe") == "ACTION"
    assert boards.alert_severity("Flash Flood Watch", "Moderate") == "ALERT"
    shelter = citizen.so_what({"kind": "nws", "severity": "CRITICAL", "title": "Tornado Warning", "note": "Williamson County"})
    assert shelter.startswith("Take shelter now")
    pena = {
        "id": "cp042026",
        "name": "Pena",
        "classification": "TS",
        "intensity": "40",
        "latitude": "10.5N",
        "longitude": "166.0W",
        "latitudeNumeric": 10.5,
        "longitudeNumeric": -166.0,
        "movementDir": 270,
        "movementSpeed": 8,
        "publicAdvisory": {"url": "https://www.nhc.noaa.gov/text/HFOTCPCP4.shtml"},
    }
    far = boards.describe_storm(pena, "There are no coastal watches or warnings in effect.", [])
    assert far["severity"] == "STANDBY"
    assert "Pena" in far["title"] and "40 kt" in far["note"] and "Moving W" in far["note"]
    assert far["url"].startswith("https://www.nhc.noaa.gov/")
    positions = boards.forecast_positions("INIT  11/0300Z 36.0N 87.0W  70 KT  80 MPH\n12H  11/1200Z 36.2N 86.5W  35 KT  40 MPH")
    assert boards.tropical_severity(positions, "", False, 70) == "CRITICAL"
    assert boards.tropical_severity([(28.0, -88.0, 90)], "A Hurricane Warning is in effect for the Louisiana coast.", True, 90) == "ALERT"
    assert boards.tropical_severity([(28.0, -88.0, 90)], "There are no coastal watches or warnings in effect.", False, 90) == "STANDBY"
    assert boards.spc_watch_severity("Tornado Watch 412", "Williamson County TN") == "ACTION"
    assert boards.spc_watch_severity("Severe Thunderstorm Watch 200", "Davidson County") == "ALERT"
    assert boards.spc_watch_severity("Tornado Watch 9", "Oklahoma") == "STANDBY"
    assert boards.spc_watch_severity("SPC - No watches are valid as of Tue Nov 10", "") == "STANDBY"
    box = {"type": "Polygon", "coordinates": [[[-88.0, 34.0], [-85.0, 34.0], [-85.0, 37.0], [-88.0, 37.0], [-88.0, 34.0]]]}
    label, sev = boards.outlook_at_point([{"properties": {"DN": 3, "LABEL2": "Marginal Risk"}, "geometry": box}])
    assert label == "Marginal" and sev == "STANDBY"
    label, sev = boards.outlook_at_point([{"properties": {"DN": 5, "LABEL2": "Enhanced"}, "geometry": box}])
    assert sev == "ACTION"
    label, sev = boards.outlook_at_point([{"properties": {"DN": 4, "LABEL2": "Slight"}, "geometry": {"type": "Polygon", "coordinates": [[[-80, 25], [-79, 25], [-79, 26], [-80, 26], [-80, 25]]]}}])
    assert label == "No thunderstorm risk" and sev == "STANDBY"
    charles = "Storm Charles brings flooding to Madeira and Portugal"
    assert boards.classify_desk(charles, "", "windstorm") == "windstorm"
    assert boards.same_story(
        "Portugal shuts down as Storm Charles approaches - Fall River Herald News",
        "‘Storm Charles’ forces Champions League cancellation - Diario AS",
    )
    assert boards.european_named_storm("Hurricane Charles nears the Florida coast", "") is False
    assert boards.classify_desk("Markets rally", "", "windstorm") == "news"
    advice = citizen.so_what({"kind": "windstorm", "severity": "STANDBY", "title": charles, "note": ""})
    assert "No action for 37179" in advice
    assert "European named storm" in advice
    quiet = boards._quiet_tropical(__import__("datetime").datetime(2026, 11, 11, tzinfo=__import__("datetime").timezone.utc))
    assert quiet["title"] == "No active tropical systems"
    assert quiet["severity"] == "STANDBY"
    page = open("template.html", encoding="utf-8").read()
    assert "Storm watch" in page
    assert "function stormItems" in page


def test_material_updates_clusters_and_returning_items():
    import boards
    won = "Trump says US won Iran war, Iran responds - NPR"
    ending = "Trump says Iran war to end fairly soon, plays down prospects of new strikes - CNBC"
    over = "Trump after meeting with Qatari PM says he believes war with Iran is militarily effectively over - AP News"
    assert boards.same_story(won, ending)
    assert boards.headline_shift(won, ending)
    assert boards.headline_shift(won, over)
    assert boards.story_update(won, ending, "ALERT", "ALERT")
    opb = "Israel's president taps opposition candidate, not Netanyahu, to form a government - OPB"
    reuters = "Israeli president picks Gadi Eisenkot, Netanyahu rival, to try to form government - Reuters"
    assert boards.same_story(opb, reuters)
    assert boards.headline_shift(opb, reuters) is False
    poland = [
        {"title": "What to Know About the Mass Shooting in Poland - The New York Times", "source": "The New York Times", "severity": "ALERT", "published": "2026-11-10T18:00:00-06:00", "kind": "attack"},
        {"title": "Gunman with far-right views who killed 6 in Poland shooting rampage dies in hospital, police say - NBC News", "source": "NBC News", "severity": "ALERT", "published": "2026-11-09T12:00:00-06:00", "kind": "attack"},
        {"title": "At least 6 killed, several injured in shooting at Polish market square: Police - ABC News", "source": "ABC News", "severity": "ALERT", "published": "2026-11-09T09:00:00-06:00", "kind": "attack"},
        {"title": "Poland under disinformation attack after Kraków’s massacre - European Interest", "source": "European Interest", "severity": "ALERT", "published": "2026-11-08T09:00:00-06:00", "kind": "attack"},
    ]
    clustered = boards.cluster_rows(poland)
    assert len(clustered) == 1
    assert clustered[0]["related"] == 3
    assert "NBC News" in clustered[0]["relatedSources"]
    cop = boards.cluster_rows([
        {"title": "War, conflict must not distract from climate action, leaders warn COP31 - Reuters", "severity": "ALERT", "published": "2026-11-10T10:00:00-06:00"},
        {"title": "What to Expect at COP 31: Key issues and how the negotiations work", "severity": "ALERT", "published": "2026-11-05T10:00:00-06:00"},
    ])
    assert len(cop) == 1 and cop[0]["related"] == 1
    israel = boards.cluster_rows([
        {"title": "How Israel Will Choose Its Next Prime Minister, Explained - Time Magazine", "severity": "ALERT", "published": "2026-11-10T15:00:00-06:00"},
        {"title": "Israel's parliament sworn in as Eisenkot tries to forge a government - Reuters", "severity": "ALERT", "published": "2026-11-10T12:00:00-06:00"},
    ])
    assert len(israel) == 1
    history = {"days": [
        {"date": "2026-11-04", "threats": [{"id": "bbc", "title": "Iran's chief negotiator says Americans voted 'no to war' - BBC", "severity": "STANDBY"}]},
        {"date": "2026-11-09", "threats": [{"id": "cnbc", "title": ending, "severity": "ALERT"}]},
        {"date": "2026-11-10", "threats": [{"id": "ap", "title": over, "severity": "ALERT"}]},
    ]}
    returning = {"id": "bbc", "title": "Iran's chief negotiator says Americans voted 'no to war' - BBC", "date": "2026-11-04", "severity": "STANDBY"}
    earlier = boards.recent_story(returning, history["days"], "2026-11-11")
    assert earlier and earlier["id"] == "bbc"
    assert boards.story_update(returning["title"], earlier["title"], "STANDBY", "STANDBY") is False
    lead = {"id": "npr", "title": won, "date": "2026-11-11", "severity": "ALERT"}
    prior = boards.recent_story(lead, history["days"], "2026-11-11")
    assert prior and prior["id"] == "ap"
    assert boards.story_update(lead["title"], prior["title"], "ALERT", "ALERT")
    assert boards.old_standby_return(returning, "2026-11-11")
    assert boards.old_standby_return(lead, "2026-11-11") is False


def test_tema_county_age_and_local_relevance():
    import citizen
    from datetime import datetime
    html = '''
      <a href="/tema/news/2026/11/6/flash-report--2---polk-county-flooding.html">Flash Report #2 - Polk County Flooding</a>
      <a href="/tema/news/2026/11/5/flash-report--1---polk-county-flooding.html">Flash Report #1 - Polk County Flooding</a>
      <a href="/tema/news/2026/11/6/williamson-flood.html">Flash Flood Warning for Williamson County</a>
    '''
    fresh = datetime.fromisoformat("2026-11-07T12:00:00-06:00")
    rows = citizen.tema_notices(html, fresh)
    titles = [row["title"] for row in rows]
    assert any("Williamson County" in title for title in titles)
    assert sum("Polk" in title for title in titles) == 1
    assert any(title.startswith("Flash Report #2") for title in titles)
    polk = next(row for row in rows if "Polk" in row["title"])
    home = next(row for row in rows if "Williamson" in row["title"])
    assert polk["severity"] == "STANDBY"
    assert "williamson" not in polk["tags"]
    assert "polk" in polk["tags"]
    assert "Nov" in polk["label"] and polk["date"] == "2026-11-06"
    assert home["severity"] == "ALERT"
    assert "williamson" in home["tags"]
    stale = citizen.tema_notices(html, datetime.fromisoformat("2026-11-11T09:00:00-06:00"))
    assert stale == []


def test_nov12_rules():
    import deskextra
    from datetime import datetime, timezone
    east = {"geocode": {"UGC": ["TNC093", "TNC029"], "SAME": ["047093"]}, "areaDesc": "Johnson; Cocke; Sevier"}
    assert deskextra.tn_alert_scope(east) == "elsewhere"
    home = {"geocode": {"UGC": ["TNC187"], "SAME": ["047187"]}, "areaDesc": "Williamson"}
    assert deskextra.tn_alert_scope(home) == "williamson"
    neighbor = {"geocode": {"SAME": ["047037"]}, "areaDesc": "Davidson"}
    assert deskextra.tn_alert_scope(neighbor) == "adjacent"
    # 2026-11-12 05:00 UTC is midnight in New York and 23:00 the day before in Chicago.
    stamp = datetime(2026, 11, 12, 5, 0, tzinfo=timezone.utc).timestamp()
    assert deskextra.exchange_day(stamp, "America/New_York") == "2026-11-12"
    assert deskextra.exchange_day(stamp, "America/Chicago") == "2026-11-11"
    kushner = {"title": "Ukraine peace talks: Jared Kushner and Steve Witkoff arrive in Russia for meeting with Putin - DW.com", "published": "2026-11-12T06:00:00-06:00"}
    abu = {"title": "Russia and Ukraine hold nearly 4 hours of U.S.-mediated talks in Abu Dhabi - PBS", "published": "2026-11-10T12:00:00-06:00"}
    import boards
    assert boards.same_story(kushner["title"], abu["title"])
    assert boards.headline_shift(kushner["title"], abu["title"])
    letter_a = {"title": "White House tells Democrats that investigating Trump administration could be criminal - Reuters", "published": "2026-11-11T10:00:00-06:00"}
    letter_b = {"title": "Read the letter the White House's top lawyer sent Rep. Garcia over threats to investigate Trump - PBS", "published": "2026-11-11T15:00:00-06:00"}
    assert deskextra.same_topic_recent(letter_a, letter_b)
    assert deskextra.published_within_hours({"published": "2026-11-12T08:00:00-06:00"}, datetime.fromisoformat("2026-11-12T20:00:00-06:00"), 36)
    assert deskextra.published_within_hours({"published": "2026-11-10T08:00:00-06:00"}, datetime.fromisoformat("2026-11-12T20:00:00-06:00"), 36) is False
    assert deskextra.correlation_ready(4) is False
    assert deskextra.correlation_ready(10) is True
    assert deskextra.quake_counts_for_market({"kind": "quake", "severity": "STANDBY"}) is False
    assert deskextra.keep_strike("House explosion in Clarksville injures two") is False
    assert deskextra.keep_strike("Drone strike hits Russian oil refinery in Kirishi") is True
    assert deskextra.strike_severity("Drone strike at Ust-Luga oil terminal") == "ALERT"
    assert deskextra.strike_severity("Missile hits a barracks in Syria") == "STANDBY"
    assert deskextra.strike_severity("Strike on US energy infrastructure in Texas") == "ACTION"
    rates = deskextra.parse_bis_rates("FREQ,REF_AREA,UNIT_MEASURE,UNIT_MULT,TIME_FORMAT,COMPILATION,DECIMALS,SOURCE_REF,SUPP_INFO_BREAKS,TITLE,TIME_PERIOD,OBS_VALUE,OBS_STATUS,OBS_CONF,OBS_PRE_BREAK\nM,JP,368,0,,,,,,Policy,2026-09,1.25,A,F,\n")
    assert rates["JP"]["value"] == 1.25
    jgb = deskextra.parse_mof_jgb_10y("Date,1Y,2Y,3Y,4Y,5Y,6Y,7Y,8Y,9Y,10Y\n2026/11/11,1.6,1.8,1.9,2.1,2.2,2.3,2.4,2.5,2.6,2.84,3.3\n")
    assert jgb["value"] == 2.84 and jgb["asOf"] == "2026-11-11"
    assert deskextra.macro_is_fresh({"checkedAt": "2026-11-10"}, "2026-11-12") is True
    assert deskextra.macro_is_fresh({"checkedAt": "2026-11-01"}, "2026-11-12") is False
    quote = deskextra.moex_level({"marketdata": {"columns": ["CURRENTVALUE", "OPENVALUE"], "data": [[2491.02, 2500.0]]}})
    assert quote["level"] == 2491.02
    lines = deskextra.gold_driver_lines({"gold": -1.2, "dxy": 1.4, "y10_bp": 20})
    assert lines and "stronger dollar" in lines[0] and "not proof" in lines[0]
    assert deskextra.vix_zone(12) == "below 15"
    assert deskextra.vix_zone(30) == "above 25"
    assert deskextra.rising_volume_points(5, 1) == 3
    assert deskextra.rising_state(6, first_seen_days=10, rising_before=False, today=4, avg3=4, avg14=2, max90=5, severity_step_days=0) == "RISING"
    assert deskextra.rising_state(4, first_seen_days=2, rising_before=False, today=2, avg3=2, avg14=2, max90=2, severity_step_days=0) == "EMERGING"
    kept = boards.cluster_rows([{"title": "Poland shooting", "related": 7, "relatedSources": ["NBC"], "severity": "ALERT", "published": "2026-11-10"}])
    assert kept[0]["related"] == 7 and kept[0]["relatedSources"] == ["NBC"]
    points = [{"date": f"2026-01-{day:02d}", "price": 100 + day} for day in range(1, 11)]
    assert deskextra.window_change(points, 5) == round(100 * (110 - 105) / 105, 2)
    assert deskextra.implied_funds_rate(96.3) == 3.7
    assert deskextra.curve_flag(-0.2) == "inverted"
    assert deskextra.curve_flag(0.4) == "positive"
    assert deskextra.wiki_confirms("Drone strike hits Ust-Luga oil terminal", "Fire at Ust-Luga after a drone attack.")
    assert deskextra.wiki_confirms("House explosion in Clarksville", "No mention of that town.") is False
    log, items, changes = deskextra.update_trendlog({"topics": [], "states": {}}, {"days": [
        {"date": "2026-11-10", "threats": [{"kind": "war-iran", "title": "Iran talks", "severity": "ALERT"}]},
        {"date": "2026-11-11", "threats": [{"kind": "war-iran", "title": "Iran talks", "severity": "ALERT"}] * 4},
    ]}, "2026-11-12", [{"kind": "war-iran", "title": "evacuation ordered in Iran", "severity": "ALERT"}] * 6)
    assert any(row["topic"] == "war-iran" for row in items)
    assert changes and changes[0]["section"] == "Rising situations"
    assert len(log["topics"]) < 5000
    ratio_lines = deskextra.gold_driver_lines({"gs_level": 77.5, "gs_change": 4.55, "copper": -2})
    assert any("77.5" in line for line in ratio_lines)
    assert all("ratio 4.55" not in line for line in ratio_lines)
    assert deskextra.format_copper_gold(0.0016) == "1.60 per 1,000"
    dirty = "Drone strike on key northern port of Ust-Luga sparks major fire - https://theins.press/en"
    assert "http" not in deskextra.clean_strike_title(dirty)
    assert deskextra.strike_fields(dirty)["country"] == "Russia"
    assert deskextra.strike_fields("Drone Strike in Egypt Sparks Security Concerns About Suez Oil Exports")["country"] == "Egypt"
    assert deskextra.story_family("Europe top diplomats press Rubio on Ukraine at G7 - AFP.com") == "g7"
    assert deskextra.story_family("Read the letter the White House's top lawyer sent Rep. Garcia over threats to investigate Trump - PBS") == "wh-letter"
    assert deskextra.story_family("Trump White House maps path to govern without Congress if Democrats win - Reuters") == ""
    assert deskextra.topic_still_live(
        "Secretary of State Marco Rubio Speaks to Reporters at G7 Meeting - C-SPAN",
        [{"title": "Europe top diplomats press Rubio on Ukraine at G7 - AFP.com"}],
    )
    assert deskextra.topic_still_live(
        "Midterm Elections 2026: Congress Polls, Charts and More - NBC News",
        [{"title": "‘Draft Marco’ effort grows on Capitol Hill after midterms bloodbath - Politico"}],
    )
    assert deskextra.topic_still_live(
        "The Iran War Unexpectedly Drove Down Carbon Emissions This Year - The New York Times",
        [{"title": "Most Americans want new Democratic Congress to end Trump's Iran war, Reuters/Ipsos poll finds - Reuters"}],
    )
    named = deskextra.tn_codes_from_area("Johnson; Sevier Smoky Mountains. Elsewhere in Tennessee, not Williamson County or an adjacent county.")
    assert "TNC091" in named["ugc"] and "047155" in named["same"]
    assert "TNC187" not in named["ugc"]
    flat = deskextra.moex_level({"marketdata": {"columns": ["CURRENTVALUE", "OPENVALUE"], "data": [[2500.0, 2500.0]]}})
    assert flat["changePct"] == 0
    russia = next(row for row in boards.REGIONS if row["id"] == "russia")
    assert russia["venues"][0]["symbol"] == "IMOEX"
    asia = next(row for row in boards.REGIONS if row["id"] == "asia")
    assert [venue["indexName"] for venue in asia["venues"]] == ["Hang Seng"]
    g7 = boards.cluster_rows([
        {"title": "G7 allies to assess impact of Trump's midterm setback at Paris talks - Reuters", "severity": "ALERT", "source": "Reuters"},
        {"title": "Europe top diplomats press Rubio on Ukraine at G7 - AFP.com", "severity": "ALERT", "source": "AFP"},
        {"title": "Priorities of the G7 Foreign Ministers' Meeting in Paris - Ministère", "severity": "STANDBY", "source": "French MFA"},
    ])
    assert len(g7) == 1 and g7[0]["related"] == 2
    letters = boards.cluster_rows([
        {"title": "White House tells Democrats that investigating Trump administration could be criminal - Reuters", "severity": "ALERT", "source": "Reuters"},
        {"title": "Read the letter the White House's top lawyer sent Rep. Garcia over threats to investigate Trump - PBS", "severity": "ALERT", "source": "PBS"},
    ])
    assert len(letters) == 1 and letters[0]["related"] == 1
    import citizen
    sample = {"days": [
        {"date": "2026-11-05", "threats": [{"id": "a", "title": "Trump White House maps path to govern without Congress if Democrats win - Reuters", "severity": "ALERT"}]},
        {"date": "2026-11-11", "threats": [{"id": "b", "title": "White House sends warning to Democrats about investigating the Trump administration - PBS", "severity": "ALERT"}]},
        {"date": "2026-11-12", "threats": [
            {"id": "d", "title": "White House tells Democrats that investigating Trump administration could be criminal - Reuters", "severity": "ALERT"},
            {"id": "e", "title": "Europe top diplomats press Rubio on Ukraine at G7 - AFP.com", "severity": "ALERT"},
            {"id": "f", "title": "Priorities of the G7 Foreign Ministers' Meeting in Paris - Ministère", "severity": "STANDBY"},
            {"id": "c", "title": "G7 allies to assess impact of Trump's midterm setback at Paris talks - Reuters", "severity": "ALERT"},
        ]},
    ]}
    look = citizen.weekly_lookback(sample, "2026-11-12")
    g7_rows = [row for row in look["newSince"] if deskextra.story_family(row["title"]) == "g7"]
    letter_rows = [row for row in look["newSince"] if deskextra.story_family(row["title"]) == "wh-letter"]
    assert len(g7_rows) == 1 and g7_rows[0]["related"] >= 2
    assert len(letter_rows) == 1 and letter_rows[0]["related"] >= 1


def test_hazard_source_parsers():
    import boards
    import citizen
    import deskextra
    gdacs = deskextra.parse_gdacs_events({
        "features": [
            {"geometry": {"coordinates": [11.1, 43.4]}, "properties": {
                "name": "Flood in Italy", "alertlevel": "Green", "fromdate": "2026-09-01T00:00:00",
                "country": "Italy", "url": {"report": "https://www.gdacs.org/report.aspx?eventtype=FL&eventid=1"},
            }},
            {"geometry": {"coordinates": [30.0, -3.0]}, "properties": {
                "name": "Drought in Burundi", "episodealertlevel": "Orange", "fromdate": "2026-05-21T00:00:00",
                "country": "Burundi", "url": {"report": "https://www.gdacs.org/report.aspx?eventtype=DR&eventid=2"},
            }},
            {"geometry": {"coordinates": [120.0, 14.0]}, "properties": {
                "name": "Flood in the Philippines", "alertlevel": "Green", "fromdate": "2026-11-10T00:00:00",
                "country": "Philippines", "url": {"report": "https://www.gdacs.org/report.aspx?eventtype=FL&eventid=3"},
            }},
            {"geometry": {"coordinates": [-60.0, 5.0]}, "properties": {
                "name": "Drought in Brazil", "alertlevel": "Orange", "fromdate": "2022-09-21T00:00:00",
                "country": "Brazil", "url": {"report": "https://www.gdacs.org/report.aspx?eventtype=DR&eventid=9"},
            }},
        ]
    }, "2026-11-12")
    assert [row["title"] for row in gdacs] == ["Drought in Burundi", "Flood in the Philippines"]
    assert gdacs[0]["severity"] == "ALERT"
    assert gdacs[1]["severity"] == "STANDBY" and gdacs[1]["lat"] == 14.0
    html = '''
    <article class="rw-disaster-map__article rw-river-article" data-disaster-lon="-72.43" data-disaster-lat="19.18" data-disaster-status="alert">
      <h3 class="rw-river-article__title"><a href="https://reliefweb.int/disaster/fl-2026-000201-hti">Haiti: Floods - Oct 2026</a></h3>
      <div class="rw-river-article__content"><p>Since 24 October 2026, heavy rains have flooded communes.</p>
        <a href="https://reliefweb.int/disaster/ep-2025-000130-cog">Congo: Cholera Outbreak - Jul 2025</a>
      </div>
    </article>
    '''
    relief = deskextra.parse_relief_disasters(html, "2026-11-12")
    assert len(relief) == 1
    assert relief[0]["title"] == "Haiti: Floods - Oct 2026"
    assert relief[0]["severity"] == "ACTION" and relief[0]["date"] == "2026-10-24"
    assert relief[0]["lat"] == 19.18
    who = deskextra.parse_who_dons({"value": [
        {"Title": "Ebola disease caused by Bundibugyo virus, Democratic Republic of the Congo", "ItemDefaultUrl": "/2026-DON625", "PublicationDate": "2026-11-06T17:27:28Z", "Summary": "<p>Cases are under follow-up.</p>"},
        {"Title": "Weekly COVID data package", "ItemDefaultUrl": "/old", "PublicationDate": "2026-11-11T00:00:00Z"},
        {"Title": "Middle East respiratory syndrome coronavirus - Kingdom of Saudi Arabia", "ItemDefaultUrl": "/mers", "PublicationDate": "2026-10-15T00:00:00Z"},
    ]}, "2026-11-12")
    assert len(who) == 1 and who[0]["severity"] == "ALERT"
    assert who[0]["url"].endswith("/2026-DON625")
    assert "Cases are under follow-up." in who[0]["note"]
    rss = '''<?xml version="1.0"?><rss version="2.0"><channel>
      <item><title>Health Alert: Rabies post-exposure prophylaxis</title><link>https://www.cdc.gov/han/2026/han00532.html</link><pubDate>Tue, 10 Nov 2026 15:00:00 GMT</pubDate><description>Clinicians should review exposure.</description></item>
      <item><title>Health Advisory: Cyclosporiasis cases in multiple states</title><link>https://www.cdc.gov/han/2026/han00531.html</link><pubDate>Mon, 02 Nov 2026 15:00:00 GMT</pubDate></item>
      <item><title>Health Update: Old influenza note</title><link>https://www.cdc.gov/han/2025/old.html</link><pubDate>Mon, 06 Oct 2025 15:00:00 GMT</pubDate></item>
    </channel></rss>'''
    han = deskextra.parse_cdc_han_rss(rss, "2026-11-12")
    assert [row["severity"] for row in han] == ["ACTION", "ALERT"]
    assert han[0]["date"] == "2026-11-10"
    archive = deskextra.parse_cdc_archive('<html><a href="/han/php/notices/han00530.html">HAN-00530: Ebola Disease Outbreak</a></html>')
    assert archive[0]["url"] == "https://www.cdc.gov/han/php/notices/han00530.html"
    assert archive[0]["severity"] == "ACTION"
    assert deskextra.parse_cdc_archive("<html><h1>Access Denied</h1></html>") == []
    assert deskextra.cdc_marks_offline([]) is False
    assert deskextra.cdc_marks_offline(["CDC HAN: the official syndication feed answered with no notices"]) is False
    assert deskextra.cdc_marks_offline(["CDC HAN: curl: (22) HTTP 403"]) is True
    old_drought = {"kind": "gdacs", "severity": "ACTION", "published": "2026-04-20T19:00:00-05:00", "tags": ["gdacs", "action"]}
    fresh_drought = {"kind": "gdacs", "severity": "ACTION", "published": "2026-11-12T12:00:00-06:00", "tags": ["gdacs", "action"]}
    other = {"kind": "storm", "severity": "ACTION", "published": "2026-04-20T19:00:00-05:00", "tags": ["storm", "action"]}
    boards.demote_stale_alerts(
        [old_drought, fresh_drought, other],
        datetime.fromisoformat("2026-11-12T15:00:00-06:00"),
    )
    assert old_drought["severity"] == "STANDBY" and old_drought["demoted"] == "older than 72h"
    assert "action" not in old_drought["tags"] and "standby" in old_drought["tags"]
    assert fresh_drought["severity"] == "ACTION"
    assert other["severity"] == "ACTION"
    npr = "Midterm voters ended the long-running GOP dominance in state legislatures - NPR"
    pbs = "Democrats try out a strange new emotion at post-midterms What's Next conference: hope - PBS"
    assert boards.politics_without_threat(npr)
    assert boards.politics_without_threat(pbs)
    assert boards.politics_without_threat("Ukraine launches biggest drone attack on Russia since war began - NBC News") is False
    assert boards.politics_without_threat("Iran raises stakes with new drone attacks as Trump signals a waiting game - CNN") is False
    nbc = {"title": "Ukraine launches biggest drone attack on Russia since war began - NBC News", "url": "https://example.com/nbc", "source": "NBC News", "date": "2026-11-16", "published": "2026-11-16T07:44:43-06:00"}
    old = {"title": "Drone strike on key northern port of Ust-Luga sparks major fire", "url": "https://example.com/old", "source": "The Insider", "date": "2026-11-11", "published": "2026-11-11T02:00:00-06:00", "country": "Russia", "severity": "ALERT", "target_type": "transport", "means": "drone"}
    merged = deskextra.merge_strikes({"items": [old]}, [deskextra.strike_from_row(nbc)], "2026-11-16")
    titles = [row["title"] for row in merged["items"]]
    assert any("biggest drone attack" in title for title in titles)
    assert any("Ust-Luga" in title for title in titles)
    card = deskextra.rising_from_trends({"items": [{"name": "ukraine war", "rise": "4 outlets this window", "sourceCount": 4, "samples": [{"text": "Ukraine launches biggest drone attack", "url": "https://example.com/nbc", "source": "NBC"}]}]}, [])
    assert card and card[0]["state"] == "RISING" and card[0]["topic"] == "ukraine war"
    assert card[0]["links"][0]["url"] == "https://example.com/nbc"
    rows = boards._cap_quakes([
        {"severity": "STANDBY", "usImpact": True, "published": "2026-11-11T00:00:00-06:00", "url": "https://example.com/guam", "title": "Guam"},
        {"severity": "STANDBY", "usImpact": False, "published": "2026-11-16T01:00:00Z", "url": "https://example.com/japan", "title": "Japan"},
        {"severity": "STANDBY", "usImpact": False, "published": "2026-11-15T01:00:00Z", "url": "https://example.com/fiji", "title": "Fiji"},
    ])
    assert any(row["title"] == "Japan" for row in rows)
    library = 'Library of Congress to Unveil “Voices of the Early Americas,” Featuring Rare Artifacts, Maps and Indigenous Histories - Library of Congress (.gov)'
    assert boards.nonthreat_copy(library)
    assert boards.nonthreat_copy("Ukraine launches biggest drone attack on Russia since war began - NBC News") is False
    assert deskextra.strike_country("Ukraine launches biggest drone attack on Russia since war began - NBC News") == "Russia"
    assert deskextra.strike_country("Iran launches drone attacks against US military base in Bahrain - The Guardian") == "Bahrain"
    assert deskextra.strike_country("Black Sea drone strikes hit four ships near Romanian coast - Seatrade Maritime News") == "Black Sea"
    assert deskextra.strike_country("US intercepts two Iranian drones as IRGC claims strike on radar in Bahrain - The Jerusalem Post") == "Bahrain"
    assert deskextra.strike_country("U.S. investigates suspected ‘unauthorized drone activity’ at U.K. air base - The Washington Post") == "United Kingdom"
    assert deskextra.strike_country("Mass drone attack on Moscow grounds flights at region's airports") == "Russia"
    estonia = "NATO member Estonia to close Russia border after attempted 'sabotage' of drone maker - CNBC"
    assert deskextra.keep_strike(estonia) is False
    assert deskextra.keep_strike("Drone strike hits Russian oil refinery in Kirishi") is True
    assert deskextra.cyber_noise("Vendor webinar: top 10 tips to stay safe online")
    assert deskextra.cyber_noise("Startup announces a product launch and funding round")
    assert deskextra.cyber_severity("Weekly tips for better passwords") == ""
    assert deskextra.cyber_severity("Microsoft Rules Out Cyberattack in Outage") == ""
    assert deskextra.cyber_severity("Google says Russian-speaking hackers ran an automated AI cyberattack") == "STANDBY"
    assert deskextra.cyber_severity("City website hit by a DDoS attack") == "STANDBY"
    assert deskextra.cyber_severity("Ransomware attack shuts a hospital network") == "ALERT"
    assert deskextra.cyber_severity("Norway's Equinor detects ongoing cyberattack, oil and gas output unaffected - Reuters") == "ALERT"
    assert deskextra.cyber_severity("How to Tell If It's a Cyberattack or Just an Outage - WIRED") == ""
    equinor = deskextra.cyber_dedupe([
        {"title": "Norway's Equinor detects ongoing cyberattack - Reuters", "source": "Reuters", "severity": "ALERT", "url": "https://example.com/r"},
        {"title": "Energy giant Equinor investigates cyberattack - Cybersecurity Dive", "source": "Cybersecurity Dive", "severity": "STANDBY", "url": "https://example.com/d"},
    ])
    assert len(equinor) == 1 and equinor[0]["severity"] == "ALERT" and equinor[0]["sourceCount"] == 2
    optimizely = deskextra.cyber_dedupe([
        {"title": "Optimizely confirms massive cyberattack - CSO Online", "source": "CSO Online", "severity": "STANDBY"},
        {"title": "Cyberattack targets Optimizely - ClickOnDetroit", "source": "ClickOnDetroit", "severity": "STANDBY"},
    ])
    assert len(optimizely) == 1 and optimizely[0]["sourceCount"] == 2
    for headline in (
        "Trump Grows Frustrated With Vance Over Iran War Critique",
        "OPEC speaks up for fossil fuels at COP31 climate talks",
        "Israeli parliament elects new speaker",
        "France is not co-belligerent in Ukraine, French minister says",
        "Kaja Kallas Attended the G7 Foreign Affairs Ministers Meeting",
        "White House memo requiring agencies to get approval before testifying",
        "Rubio Says Economic Pressure on Iran is Working",
        "Sviatlana Tsikhanouskaya paid tribute to victims of the attack in Krakow",
    ):
        assert boards.statement_not_event(headline), headline
    assert boards.statement_not_event("Ukraine launches biggest drone attack on Russia since war began") is False
    assert deskextra.strike_country("Sudan: Devastating RSF drone strikes on civilians in El Obeid") == "Sudan"
    assert deskextra.strike_country("Whistleblower: Deadly drone strike in Kuwait could have been avoided") == "Kuwait"
    assert deskextra.strike_country("Iran says army targets U.S. drone and missile sites in Kuwait") == "Kuwait"
    assert deskextra.strike_country("Iranian army says drone strikes targeted US installations at Kuwait air base") == "Kuwait"
    assert deskextra.keep_strike("Sviatlana Tsikhanouskaya paid tribute to victims of the attack in Krakow") is False
    assert deskextra.keep_strike("Krakow basilica holds mass for man who committed deadly terror attack") is False
    assert deskextra.keep_strike("Ukraine allies reject U.S. criticism of deep strikes inside Russia") is False
    linked = deskextra.attach_rising_links(
        [{"topic": "quake", "state": "RISING", "reasons": "1.8x usual volume"}],
        [{"kind": "quake", "title": "M5.0 Philippines", "url": "https://example.com/q", "source": "USGS"}],
    )
    assert linked[0]["links"][0]["url"] == "https://example.com/q"
    standby_heads = (
        "G7 Foreign Ministers' meeting: Press remarks by the High Representative/Vice-President Kaja Kallas upon arrival",
        "Democrats flipped 9 U.S. Senate seats — the most in almost 70 years - PBS",
        "The Supreme Court before it stood apart - SCOTUSblog",
        "Secretary of State Marco Rubio on Major Technical Failures & Outage Incidents - C-SPAN",
        "Remarks by Under Secretary of War for Policy Elbridge Colby at the Ukraine Defense Contact Group (As Delivered)",
        "Dispatch from Kyiv: Let Ukraine strike Russia’s missile launchers at the source - Atlantic Council",
        "Iran Update, November 18, 2026 - Institute for the Study of War",
        "Mideast nations ramp up efforts to avert all-out war as Israel urges Iran strikes, officials say - AP News",
        "York victim of Krakow attack on his way home, family confirms - BBC",
    )
    for headline in standby_heads:
        assert boards.news_event_severity(headline) == "STANDBY", headline
    assert boards.news_event_severity("Iran fires at U.S. facility in Bahrain as Tehran resumes strikes on Arab neighbors - PBS") == "ALERT"
    riyadh = "Damage from missile attack reported in Riyadh's financial district, and other Mideast news - AP News"
    assert boards.news_event_severity(riyadh) == "ALERT"
    assert boards.event_lead(riyadh).lower().startswith("damage from missile attack")
    assert deskextra.strike_country(riyadh) == "Saudi Arabia"
    assert deskextra.strike_country("Drone strike near Doha") == "Qatar"
    assert deskextra.strike_country("Explosion in Dubai") == "United Arab Emirates"
    assert deskextra.strike_country("Missile hits Muscat") == "Oman"
    assert deskextra.strike_severity(riyadh) == "ALERT"
    disinfo = "How disinformation exploited the Krakow tragedy to attack the usual targets, and how Elon Musk made things worse - EDMO"
    assert boards.news_event_severity(disinfo) == "STANDBY"
    assert deskextra.keep_strike(disinfo) is False
    assert boards.news_event_severity("Critics attack the president's reputation in a new essay") == "STANDBY"
    icans = {"title": "First three-way summit between China, Russia and the US - ICAN", "source": "ICAN", "url": "https://example.com/ican", "date": "2026-11-19", "published": "2026-11-19T06:00:00-06:00"}
    reuters = {"title": "Trump, Putin and Xi hold a summit - Reuters", "source": "Reuters", "url": "https://example.com/reuters", "date": "2026-11-19", "published": "2026-11-19T05:00:00-06:00"}
    clustered = boards.global_dedupe([icans, reuters])
    assert len(clustered) == 1
    assert clustered[0]["source"] == "Reuters"
    assert clustered[0]["sourceCount"] == 2
    assert any(link["source"] == "ICAN" for link in clustered[0]["links"])
    stale = boards.finish_global([
        {"kind": "global", "title": "Europe to send united front to potential peace talks - DW", "source": "DW", "date": "2026-11-13", "url": "https://example.com/dw"},
        {"kind": "global", "title": "Trump, Putin and Xi hold a summit - Reuters", "source": "Reuters", "date": "2026-11-19", "url": "https://example.com/reuters"},
    ], "2026-11-19")
    assert all("peace talks" not in (row.get("title") or "") for row in stale)
    assert any(row.get("source") == "Reuters" for row in stale)
    assert deskextra.infra_cause("Investigators say sabotage is suspected on the Balticconnector") == "suspected sabotage"
    assert deskextra.infra_cause("Nord Stream damage, cause still unknown") == "unconfirmed"
    assert deskextra.infra_cause("Operator calls the leak a technical failure") == "accident"
    assert deskextra.infra_cause("Police say the cable cut was confirmed sabotage") == "confirmed sabotage"
    assert deskextra.infra_severity("Undersea cable cut in the Red Sea", cause="unconfirmed") == "ALERT"
    assert deskextra.infra_severity("Anchor dragged across a Baltic cable", cause="suspected sabotage") == "ACTION"
    assert deskextra.infra_severity("Routine maintenance on Langeled", cause="unconfirmed") == "STANDBY"
    assert deskextra.infra_severity("Hong Kong drops charge against captain over Baltic pipeline damage") == "STANDBY"
    assert deskextra.infra_market_note(-2.5, 4.5) == "Brent -2.5% over 5 days · TTF 4.5% over 5 days"
    stamped = deskextra.stamp_infra_notes([{"note": "", "kind": "infra"}], deskextra.infra_market_note(-2.54, 4.45))
    assert "Brent" in stamped[0]["note"] and "TTF" in stamped[0]["note"]
    tile_rows = [{"id": "threat-infra", "count": 0, "lastDate": "", "lastLabel": ""}]
    incidents = [
        {"title": "Baltic", "published": "2026-11-18T07:17:00-06:00", "date": "2026-11-18", "label": "Nov 18, 2026 7:17 AM CT"},
        {"title": "Pakistan", "published": "2026-11-19T03:59:26-06:00", "date": "2026-11-19", "label": "Nov 19, 2026 3:59 AM CT"},
    ]
    tile = boards.apply_infra_source(tile_rows, incidents)
    assert tile["count"] == 2 and tile["lastDate"] == "2026-11-19" and tile["lastLabel"] == "Nov 19, 2026 3:59 AM CT"
    assert deskextra.infra_severity("Internet services disrupted across Pakistan due to undersea cable fault") == "ALERT"
    assert deskextra.infra_severity("Gulf of Mexico pipeline rupture cuts US supply", cause="unconfirmed") == "CRITICAL"
    assert deskextra.infra_noise("How to understand an undersea cable explainer") is True
    paired = deskextra.infra_dedupe([
        {"title": "Baltic Sea cable damaged", "source": "Reuters", "url": "https://example.com/a", "asset": "cable", "region": "Baltic Sea", "cause": "unconfirmed", "date": "2026-11-18", "severity": "ALERT"},
        {"title": "Second Baltic Sea cable cut", "source": "BBC", "url": "https://example.com/b", "asset": "cable", "region": "Baltic Sea", "cause": "unconfirmed", "date": "2026-11-19", "severity": "ALERT"},
        {"title": "Nord Stream leak, sabotage suspected", "source": "AP", "url": "https://example.com/c", "asset": "Nord Stream", "region": "Baltic Sea", "cause": "suspected sabotage", "date": "2026-11-19", "severity": "ACTION"},
    ])
    assert len(paired) == 2
    cable = next(row for row in paired if row["asset"] == "cable")
    assert cable["severity"] == "ACTION" and cable["sourceCount"] == 2 and cable["open"] is True
    assert boards.promote_alert_strikes([], {"items": [{"title": "Damage from missile attack reported in Riyadh", "url": "https://example.com/r", "source": "AP", "severity": "ALERT", "published": "2026-11-19T08:00:00-06:00", "country": "Saudi Arabia"}]})[0]["severity"] == "ALERT"
    assert boards.news_event_severity("Ukraine: Civilian casualties in 2026 already far exceed previous years’ tolls - UN News") == "ALERT"
    assert boards.quake_severity(6.2, "Ridgecrest, California") == "ACTION"
    assert boards.global_event_type("G7 Foreign Ministers' meeting: Press remarks by Kaja Kallas upon arrival") == ""
    assert boards.global_event_type("Takeaways from the Trump-Xi-Putin summit and GTA VI launches: Morning Rundown") == ""
    assert "US" in boards.major_powers("First three-way summit between China, Russia and the US")
    assert boards.global_event_type("Trump, Putin and Xi to hold a trilateral summit") == "summit"
    assert boards.global_severity("Trump, Putin and Xi to hold a trilateral summit", outlets=1) == "ALERT"
    assert boards.global_severity("NATO summit opens in The Hague", outlets=1) == "STANDBY"
    assert boards.global_severity("NATO summit opens in The Hague", outlets=3) == "ALERT"
    merged_global = boards.global_dedupe([
        {"title": "Trump and Putin plan a summit", "source": "Reuters", "severity": "ALERT", "date": "2026-11-19"},
        {"title": "Trump and Putin plan a summit", "source": "BBC", "severity": "STANDBY", "date": "2026-11-19"},
    ])
    assert len(merged_global) == 1 and merged_global[0]["sourceCount"] == 2
    campaign = deskextra.cyber_dedupe([
        {"title": "Optimizely confirms massive cyberattack on customer websites injected stealer malware", "source": "CSO Online", "severity": "STANDBY", "date": "2026-11-17"},
        {"title": "Cyberattack hits 178 organizations: Credit cards, crypto, other data at risk", "source": "Syracuse.com", "severity": "STANDBY", "date": "2026-11-17"},
        {"title": "Some of the world's most-visited websites targeted by cyberattack", "source": "WBAL-TV", "severity": "STANDBY", "date": "2026-11-18"},
    ])
    assert len(campaign) == 1 and campaign[0]["sourceCount"] == 3
    assert deskextra.keep_strike("York victim of Krakow attack on his way home, family confirms - BBC") is False
    assert deskextra.keep_strike("CISA Warns of 4 Exploited Flaws Linked to Ransomware, Cryptomining, and LLMjacking Attacks") is False
    assert deskextra.keep_strike("Mideast nations ramp up efforts to avert all-out war as Israel urges Iran strikes") is False
    assert deskextra.keep_strike("Dispatch from Kyiv: Let Ukraine strike Russia’s missile launchers at the source") is False
    assert deskextra.keep_strike('The Kraków Attack and the Alleged End of Poland\'s "Innocence" - ICCT') is False
    assert deskextra.keep_strike("Trump Weighs New Strikes on Iran as Israel Presses for Action") is False
    assert deskextra.keep_strike("Trump warns of new strikes against Iran after new year") is False
    assert deskextra.keep_strike("Gold Star families frustrated with Pentagon investigation into Iran drone strike that killed 6 soldiers") is False
    assert boards.news_event_severity("What did Xi Jinping get from the bear hug with Trump at the Shenzhen summit? - NPR") == "STANDBY"
    assert boards.news_event_severity("COP31 Climate Summit That Could Not Say Fossil Fuels Ends With No Deal") == "STANDBY"
    assert boards.global_severity("COP31 Climate Summit Ends With No Deal") == "STANDBY"
    assert boards.news_event_severity("UN arms conference falls short of treaty mandate on autonomous weapons") == "STANDBY"
    stale_relief = boards.shape_board([
        {"kind": "relief", "title": "Haiti: Floods", "date": "2026-07-31", "severity": "STANDBY"},
        {"kind": "relief", "title": "Fresh flood", "date": "2026-11-20", "severity": "ALERT"},
        {"kind": "quake", "title": "M4.6 Papua New Guinea", "mag": 4.6, "date": "2026-11-22", "severity": "STANDBY", "lat": 1, "lon": 1},
        {"kind": "quake", "title": "M6.5 Vanuatu region", "mag": 6.5, "date": "2026-11-22", "severity": "ACTION", "lat": -13.5, "lon": 172.2, "note": "A tsunami flag is set."},
        {"kind": "gdacs", "title": "Earthquake in Vanuatu Islands Region", "date": "2026-11-22", "lat": -13.7, "lon": 170.8, "severity": "STANDBY"},
    ], "2026-11-23")
    assert all(row.get("kind") != "relief" or row.get("date") == "2026-11-20" for row in stale_relief)
    assert all("Vanuatu Islands" not in (row.get("title") or "") for row in stale_relief)
    vanuatu = next(row for row in stale_relief if "Vanuatu region" in row["title"])
    assert vanuatu["severity"] == "STANDBY"
    kept_heads = boards.tidy_headlines([
        {"title": "Ackman Urges Fed to Raise Inflation Target to 3 Percent - SuaraGarut.ID", "source": "SuaraGarut.ID", "url": "https://example.com/a"},
        {"title": "Ackman Urges Fed to Raise Inflation Target to 3 Percent - Demokratis.co.id", "source": "Demokratis.co.id", "url": "https://example.com/b"},
        {"title": "Ackman Urges Fed to Raise Inflation Target to 3 Percent - Reuters", "source": "Reuters", "url": "https://example.com/c"},
    ])
    assert len(kept_heads) == 1 and kept_heads[0]["source"] == "Reuters"
    markets = {"regions": [{"name": "USA", "venues": [{"indexName": "S&P 500", "name": "NYSE", "changePct": -3.7, "asOf": "2026-11-20"}]}]}
    brief = citizen.morning_brief([], {"items": []}, {"items": []}, {}, {"items": []}, markets, "2026-11-23")
    assert "today" not in brief.split(".")[0]
    assert "Friday" in brief
    assert deskextra.keep_strike("Iran says army targets U.S. drone and missile sites in Kuwait") is True
    kuwait = deskextra.merge_strikes({}, [
        {"title": "Iran says army targets U.S. drone and missile sites in Kuwait", "url": "https://example.com/cnbc", "source": "CNBC", "date": "2026-11-17", "published": "2026-11-17T10:00:00-06:00", "country": "Kuwait", "severity": "STANDBY"},
        {"title": "Iranian army says drone strikes targeted US installations at Kuwait air base", "url": "https://example.com/aa", "source": "Anadolu", "date": "2026-11-17", "published": "2026-11-17T12:00:00-06:00", "country": "Kuwait", "severity": "STANDBY"},
        {"title": "The Krakow Attack and the Alleged End of Poland's Innocence", "url": "https://example.com/icct", "source": "ICCT", "date": "2026-11-19", "country": ""},
    ], "2026-11-19")
    assert len(kuwait["items"]) == 1 and kuwait["items"][0]["country"] == "Kuwait" and kuwait["items"][0]["sourceCount"] == 2
    spikes = deskextra.dedupe_spikes([
        {"topic": "inflation", "outlets": 4, "links": [{"url": "https://example.com/a", "source": "Reuters"}]},
        {"topic": "Inflation", "outlets": 6, "links": [{"url": "https://example.com/b", "source": "BBC"}]},
    ])
    assert len(spikes) == 1 and spikes[0]["topic"] == "Inflation" and spikes[0]["outlets"] == 6
    assert deskextra.strike_from_row({"kind": "cyber", "title": "Ransomware attack shuts a hospital", "url": "https://example.com/c"}) is None
    spikes = deskextra.section_spikes([
        {"title": "OpenAI releases a new frontier model", "source": "The Verge", "url": "https://example.com/a"},
        {"title": "OpenAI releases a new frontier model", "source": "Reuters", "url": "https://example.com/b"},
        {"title": "How to use OpenAI for a webinar", "source": "Blog", "url": "https://example.com/c"},
    ])
    assert spikes and spikes[0]["topic"] == "OpenAI" and spikes[0]["links"]
    assert deskextra.cyber_severity("Zero-day exploited in widely used email gateway") == "ALERT"
    assert deskextra.cyber_severity("CVE-2026-1 example", kev=True) == "ALERT"
    assert deskextra.cyber_severity("Global outage hits power grids in multiple countries") == "ACTION"
    assert deskextra.cyber_severity("Nationwide power grid outage after a U.S. critical infrastructure cyberattack") == "CRITICAL"
    kept = deskextra.cyber_dedupe([
        {"title": "CVE-2026-10 Example vendor bug"},
        {"title": "CVE-2026-10 same bug, other outlet"},
        {"title": "Ransomware hits a hospital network today - The Record"},
        {"title": "Ransomware hits a hospital network today - SecurityWeek"},
    ])
    assert len(kept) == 2


def test_infra_collector_when_feeds_fail():
    """The live refresh hit this with no cached rows and feeds that fail.

    collect_infra must return a gap instead of raising UnboundLocalError on boards.
    """
    import boards
    import fetch
    saved_head, saved_rss = boards._headlines, boards._rss_items

    def down(*_args, **_kwargs):
        raise RuntimeError("feed down")

    boards._headlines = down
    boards._rss_items = down
    try:
        rows, gaps = fetch.collect_infra(datetime(2026, 11, 19, 11, 8))
    finally:
        boards._headlines, boards._rss_items = saved_head, saved_rss
    assert rows == []
    assert gaps
    assert all("boards" not in gap for gap in gaps)
    assert any("feed down" in gap for gap in gaps)


if __name__ == "__main__":
    test_x_created_at_with_milliseconds()
    test_ct_conversion()
    test_jre_skips_and_keeps_main_feed()
    test_other_shows_stay_on_their_feeds()
    test_cross_promo_and_notes()
    test_numbered_parts_stay_separate()
    test_dedupe_by_description_not_title()
    test_guest_parser()
    test_page_hash_ignores_clocks()
    test_x_paths_never_include_dms()
    test_bearer_and_x_errors()
    test_carota_reads_site_and_keeps_cached_titles()
    test_x_millis_posts_are_not_dropped()
    test_board_helpers()
    test_urls_and_ids()
    test_trend_filter_and_confidence()
    test_triggers_outlook_and_impact()
    test_blackout_rumor_hides_after_nov_18()
    test_conflict_kind_requires_the_headline()
    test_same_story_prefers_the_newest_outlet()
    test_tema_news_releases_parse()
    test_storm_watch_severity_and_european_names()
    test_material_updates_clusters_and_returning_items()
    test_tema_county_age_and_local_relevance()
    test_nov12_rules()
    test_hazard_source_parsers()
    test_infra_collector_when_feeds_fail()
    print("ok")
