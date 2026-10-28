#!/usr/bin/env python3
"""Rules that do not need the network."""
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import desklib as d


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
    for blocked in ("/2/dm_events", "/2/dm_conversations", "/1.1/direct_messages/events/list.json", "/2/users/9/dm"):
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


def test_carota_fallback_after_403():
    import io
    import urllib.error
    from datetime import datetime
    from zoneinfo import ZoneInfo
    import fetch
    calls = []
    real = fetch.get_bytes
    rss = b"""<?xml version="1.0"?><rss version="2.0"><channel>
      <title>The Wealth Regime</title>
      <link>https://carotawealth.substack.com</link>
      <item>
        <title>Inflation note</title>
        <link>https://carotawealth.substack.com/p/inflation-note</link>
        <pubDate>Fri, 02 Oct 2026 16:54:37 GMT</pubDate>
        <description>The government revised how inflation is measured and the grocery store did not follow that revision.</description>
      </item>
    </channel></rss>"""

    def fake(url, timeout=45, headers=None, user_agent=None):
        calls.append((url, user_agent))
        if url == "https://carotawealth.substack.com/feed":
            raise urllib.error.HTTPError(url, 403, "Forbidden", hdrs=None, fp=io.BytesIO(b"blocked"))
        return rss, url, 200

    fetch.get_bytes = fake
    try:
        spec = {
            "id": "carota", "name": "Carota Wealth", "feed": "https://carotawealth.substack.com/feed",
            "skipTitle": [], "rejectChannel": [], "_retain": 120,
        }
        items, home, channel = fetch.fetch_carota(spec, datetime.now(ZoneInfo("America/Chicago")))
    finally:
        fetch.get_bytes = real
    assert calls[0][0] == "https://carotawealth.substack.com/feed"
    assert calls[0][1] == fetch.BROWSER_UA
    assert calls[1][0] == "https://carotawealth.substack.com/feed.xml"
    assert len(items) == 1
    assert channel == "The Wealth Regime"
    assert home == "https://carotawealth.substack.com"


def test_urls_and_ids():
    assert d.http_url("https://example.com/a") == "https://example.com/a"
    assert d.http_url("javascript:alert(1)") == ""
    assert d.make_id("jre", "https://example.com/a") == d.make_id("jre", "https://example.com/a")
    assert d.make_id("jre", "https://example.com/a") != d.make_id("lex", "https://example.com/a")


if __name__ == "__main__":
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
    test_carota_fallback_after_403()
    test_urls_and_ids()
    print("ok")
