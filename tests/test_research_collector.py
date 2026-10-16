import json

import pytest

import research_collector as rc


@pytest.fixture
def isolated_store(tmp_path, monkeypatch):
    monkeypatch.setattr(rc, "DATA_DIR", tmp_path)
    monkeypatch.setattr(rc, "CANDIDATES_FILE", tmp_path / "candidates.json")


def test_parse_rss_and_create_unverified_candidate():
    xml = b"""<?xml version="1.0"?>
    <rss><channel><item>
      <title>Payment security research</title>
      <link>https://research.example.org/paper</link>
      <description>Example summary</description>
      <pubDate>Tue, 13 Oct 2026 10:00:00 GMT</pubDate>
    </item></channel></rss>"""

    item = rc.parse_feed(xml, rc.FEEDS[0])[0]

    assert item["title"] == "Payment security research"
    assert item["evidence_status"] == "not_verified"
    assert item["review_status"] == "unreviewed"
    assert item["source_region"] == "international"


def test_parse_atom_feed():
    xml = b"""<?xml version="1.0"?>
    <feed xmlns="http://www.w3.org/2005/Atom">
      <entry>
        <title>New research</title>
        <link href="https://research.example.org/item" rel="alternate"/>
        <summary>Research summary</summary>
      </entry>
    </feed>"""

    items = rc.parse_feed(xml, rc.FEEDS[0])

    assert len(items) == 1
    assert items[0]["title"] == "New research"


def test_reject_non_https_article_link():
    xml = b"""<rss><channel><item>
      <title>Unsafe link</title>
      <link>http://example.org/item</link>
    </item></channel></rss>"""

    assert rc.parse_feed(xml, rc.FEEDS[0]) == []


def test_deduplicate_candidates(isolated_store, monkeypatch):
    sample = {
        "candidate_id": "same-id",
        "discovered_at": "2026-10-14T00:00:00+00:00",
        "source_name": "Test",
        "source_feed": "https://www.cisa.gov/cybersecurity-advisories/all.xml",
        "source_region": "international",
        "topic": "security",
        "title": "Example",
        "summary": "Summary",
        "article_url": "https://example.org/item",
        "published_at_source": "",
        "review_status": "unreviewed",
        "evidence_status": "not_verified",
        "lesson_for_africa": None,
        "trustng_relevance": None,
    }

    monkeypatch.setattr(rc, "_fetch_feed", lambda feed: b"<rss/>")
    monkeypatch.setattr(rc, "parse_feed", lambda data, feed: [sample])
    monkeypatch.setattr(rc.time, "sleep", lambda _: None)

    first = rc.collect_once()
    second = rc.collect_once()

    assert first["new_candidates"] == 1
    assert first["duplicates_skipped"] == len(rc.FEEDS) - 1
    assert second["new_candidates"] == 0
    assert second["duplicates_skipped"] == len(rc.FEEDS)


def test_human_review_is_recorded(isolated_store, monkeypatch):
    item = {
        "candidate_id": "review-me",
        "discovered_at": "2026-10-14T00:00:00+00:00",
        "source_name": "Test",
        "source_feed": "https://www.cisa.gov/cybersecurity-advisories/all.xml",
        "source_region": "international",
        "topic": "security",
        "title": "Example",
        "summary": "Summary",
        "article_url": "https://example.org/item",
        "published_at_source": "",
        "review_status": "unreviewed",
        "evidence_status": "not_verified",
        "lesson_for_africa": None,
        "trustng_relevance": None,
    }
    rc._write_candidates([item])

    result = rc.mark_candidate_reviewed(
        "review-me",
        evidence_status="partially_verified",
        trustng_relevance=4,
        lesson_for_africa="Test relevance against local payment systems.",
    )

    assert result["review_status"] == "reviewed"
    assert result["evidence_status"] == "partially_verified"


def test_unknown_candidate_cannot_be_reviewed(isolated_store):
    with pytest.raises(ValueError):
        rc.mark_candidate_reviewed(
            "missing",
            evidence_status="independently_verified",
            trustng_relevance=3,
            lesson_for_africa="Review the evidence.",
        )


def test_source_catalog_covers_global_and_african_jurisdictions():
    catalog = rc.source_catalog()
    jurisdictions = {item["jurisdiction"] for item in catalog}

    assert len(catalog) >= 20
    assert "Saudi Arabia" in jurisdictions
    assert "United Arab Emirates" in jurisdictions
    assert "European Union" in jurisdictions
    assert "United Kingdom" in jurisdictions
    assert "United States" in jurisdictions
    assert "China" in jurisdictions
    assert "Nigeria" in jurisdictions
    assert "Ghana" in jurisdictions
    assert all("url" in item for item in catalog)


def test_reference_sources_are_not_automatically_collected():
    catalog = rc.source_catalog()
    references = [
        item for item in catalog
        if item["source_type"] != "rss_or_atom_feed"
    ]

    assert references
    assert all(item["collection_enabled"] is False for item in references)


def test_feed_redirect_host_check():
    assert rc._host_is_allowed(
        "https://www.cisa.gov/example",
        "www.cisa.gov",
    )
    assert not rc._host_is_allowed(
        "https://malicious.example/example",
        "www.cisa.gov",
    )
