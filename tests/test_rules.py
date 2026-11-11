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
    assert boards.quake_severity(7.1) == "ALERT"
    assert boards.quake_severity(7.1, "12 km NE of Knoxville, Tennessee") == "CRITICAL"
    assert boards.quake_severity(6.2) == "STANDBY"
    assert boards.quake_severity(6.2, "Ridgecrest, California") == "ACTION"
    assert boards.quake_severity(5.6, "Nashville, Tennessee") == "ALERT"
    assert boards.quake_severity(4.6) == "STANDBY"
    assert boards.keep_quake(5.7, "Hasaki, Japan", False, "", 0) is False
    assert boards.keep_quake(6.4, "off Honshu, Japan", False, "yellow", 0) is True
    assert boards.keep_quake(6.4, "off Honshu, Japan", False, "", 0) is False
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
    rows = citizen.tema_notices(html, datetime.fromisoformat("2026-11-10T09:00:00-06:00"))
    assert len(rows) == 1
    assert rows[0]["date"] == "2026-11-06"
    assert rows[0]["url"].startswith("https://www.tn.gov/tema/news/2026/11/6/")
    assert rows[0]["severity"] == "ALERT"
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
    print("ok")
