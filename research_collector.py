"""TrustNG's first controlled external research collector."""

import hashlib
import json
import os
import time
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse


DATA_DIR = Path(
    os.environ.get(
        "TRUSTNG_INTELLIGENCE_DIR",
        str(Path(__file__).resolve().parent / "intelligence_data"),
    )
)
CANDIDATES_FILE = DATA_DIR / "research_candidates.json"

# Fixed, reviewed feed list. No user-supplied feed URLs are accepted.
FEEDS = [
    {
        "name": "CISA Cybersecurity Advisories",
        "url": "https://www.cisa.gov/cybersecurity-advisories/all.xml",
        "region": "international",
        "topic": "cybersecurity",
        "host": "www.cisa.gov",
    },
    {
        "name": "BIS Research Papers",
        "url": "https://www.bis.org/doclist/bis_fsi_publs.rss",
        "region": "international",
        "topic": "financial_system_research",
        "host": "www.bis.org",
    },
    {
        "name": "ECB Publications",
        "url": "https://www.ecb.europa.eu/rss/pub.html",
        "region": "international",
        "topic": "financial_policy_and_research",
        "host": "www.ecb.europa.eu",
    },
]


# Official research catalogue. These URLs are reference sources, not
# automatically collected feeds. Enable collection only after validating
# the site's format, host, access policy, and update behavior.
RESEARCH_SOURCES = [
    {
        "name": "Saudi Central Bank - Open Banking",
        "url": "https://openbanking.sama.gov.sa/index-en.html",
        "jurisdiction": "Saudi Arabia",
        "region": "international",
        "topic": "open_banking_and_api_standards",
        "source_type": "regulatory_authority",
    },
    {
        "name": "Saudi Central Bank",
        "url": "https://www.sama.gov.sa/en-US/Pages/default.aspx",
        "jurisdiction": "Saudi Arabia",
        "region": "international",
        "topic": "banking_payments_cybersecurity",
        "source_type": "regulatory_authority",
    },
    {
        "name": "Central Bank of the UAE - Open Finance Regulation",
        "url": "https://rulebook.centralbank.ae/en/rulebook/open-finance-regulation",
        "jurisdiction": "United Arab Emirates",
        "region": "international",
        "topic": "open_finance_and_api_security",
        "source_type": "regulatory_authority",
    },
    {
        "name": "Dubai Financial Services Authority",
        "url": "https://www.dfsa.ae/",
        "jurisdiction": "United Arab Emirates",
        "region": "international",
        "topic": "financial_services_and_fintech",
        "source_type": "regulatory_authority",
    },
    {
        "name": "European Banking Authority",
        "url": "https://www.eba.europa.eu/",
        "jurisdiction": "European Union",
        "region": "international",
        "topic": "banking_risk_payments_and_regulation",
        "source_type": "regulatory_authority",
    },
    {
        "name": "EU Digital Operational Resilience Act",
        "url": "https://eur-lex.europa.eu/eli/reg/2022/2554/oj",
        "jurisdiction": "European Union",
        "region": "international",
        "topic": "digital_operational_resilience",
        "source_type": "legislation",
    },
    {
        "name": "European Data Protection Board",
        "url": "https://www.edpb.europa.eu/",
        "jurisdiction": "European Union",
        "region": "international",
        "topic": "privacy_and_data_protection",
        "source_type": "regulatory_authority",
    },
    {
        "name": "UK Financial Conduct Authority",
        "url": "https://www.fca.org.uk/firms/innovation/regulatory-sandbox",
        "jurisdiction": "United Kingdom",
        "region": "international",
        "topic": "fintech_testing_and_regulation",
        "source_type": "regulatory_authority",
    },
    {
        "name": "Bank of England",
        "url": "https://www.bankofengland.co.uk/",
        "jurisdiction": "United Kingdom",
        "region": "international",
        "topic": "financial_stability_and_payments",
        "source_type": "central_bank",
    },
    {
        "name": "US National Institute of Standards and Technology - AI Risk Management",
        "url": "https://www.nist.gov/itl/ai-risk-management-framework",
        "jurisdiction": "United States",
        "region": "international",
        "topic": "ai_governance_and_model_risk",
        "source_type": "standards_body",
    },
    {
        "name": "US Financial Crimes Enforcement Network",
        "url": "https://www.fincen.gov/",
        "jurisdiction": "United States",
        "region": "international",
        "topic": "financial_crime_and_aml",
        "source_type": "regulatory_authority",
    },
    {
        "name": "US Federal Reserve",
        "url": "https://www.federalreserve.gov/",
        "jurisdiction": "United States",
        "region": "international",
        "topic": "banking_payments_and_financial_stability",
        "source_type": "central_bank",
    },
    {
        "name": "People's Bank of China",
        "url": "https://www.pbc.gov.cn/en/3688006/index.html",
        "jurisdiction": "China",
        "region": "international",
        "topic": "banking_digital_finance_and_payments",
        "source_type": "central_bank",
    },
    {
        "name": "Monetary Authority of Singapore",
        "url": "https://www.mas.gov.sg/",
        "jurisdiction": "Singapore",
        "region": "international",
        "topic": "fintech_cybersecurity_and_payments",
        "source_type": "regulatory_authority",
    },
    {
        "name": "Reserve Bank of India",
        "url": "https://www.rbi.org.in/",
        "jurisdiction": "India",
        "region": "international",
        "topic": "payments_banking_and_fraud_risk",
        "source_type": "central_bank",
    },
    {
        "name": "Financial Action Task Force",
        "url": "https://www.fatf-gafi.org/en/home.html",
        "jurisdiction": "International",
        "region": "international",
        "topic": "aml_cft_and_financial_crime",
        "source_type": "international_standard_setter",
    },
    {
        "name": "Financial Stability Board",
        "url": "https://www.fsb.org/",
        "jurisdiction": "International",
        "region": "international",
        "topic": "financial_stability_and_operational_risk",
        "source_type": "international_standard_setter",
    },
    {
        "name": "BIS Committee on Payments and Market Infrastructures",
        "url": "https://www.bis.org/cpmi/",
        "jurisdiction": "International",
        "region": "international",
        "topic": "payment_systems_and_cross_border_payments",
        "source_type": "international_standard_setter",
    },
    {
        "name": "PCI Security Standards Council",
        "url": "https://www.pcisecuritystandards.org/",
        "jurisdiction": "International",
        "region": "international",
        "topic": "payment_card_data_security",
        "source_type": "industry_standard",
    },
    {
        "name": "Central Bank of Nigeria",
        "url": "https://www.cbn.gov.ng/",
        "jurisdiction": "Nigeria",
        "region": "africa",
        "topic": "payments_banking_and_fintech",
        "source_type": "central_bank",
    },
    {
        "name": "Nigeria Data Protection Commission",
        "url": "https://ndpc.gov.ng/",
        "jurisdiction": "Nigeria",
        "region": "africa",
        "topic": "privacy_and_data_protection",
        "source_type": "regulatory_authority",
    },
    {
        "name": "Bank of Ghana",
        "url": "https://www.bog.gov.gh/",
        "jurisdiction": "Ghana",
        "region": "africa",
        "topic": "payments_fintech_and_banking",
        "source_type": "central_bank",
    },
    {
        "name": "South African Reserve Bank",
        "url": "https://www.resbank.co.za/",
        "jurisdiction": "South Africa",
        "region": "africa",
        "topic": "payments_financial_stability_and_banking",
        "source_type": "central_bank",
    },
    {
        "name": "Central Bank of Kenya",
        "url": "https://www.centralbank.go.ke/",
        "jurisdiction": "Kenya",
        "region": "africa",
        "topic": "mobile_money_payments_and_fintech",
        "source_type": "central_bank",
    },
]

MAX_FEED_BYTES = 2_000_000
MAX_ITEMS_PER_FEED = 50
REQUEST_TIMEOUT_SECONDS = 15
MIN_SECONDS_BETWEEN_REQUESTS = 1


def _now():
    return datetime.now(timezone.utc).isoformat()


def _read_candidates():
    if not CANDIDATES_FILE.exists():
        return []

    with CANDIDATES_FILE.open("r", encoding="utf-8") as file:
        data = json.load(file)

    if not isinstance(data, list):
        raise ValueError("Research candidate store must contain a JSON list.")

    return data


def _write_candidates(candidates):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    temporary = CANDIDATES_FILE.with_suffix(".tmp")

    with temporary.open("w", encoding="utf-8") as file:
        json.dump(candidates, file, indent=2, ensure_ascii=False)
        file.flush()
        os.fsync(file.fileno())

    temporary.replace(CANDIDATES_FILE)


def _clean_text(value):
    if value is None:
        return ""
    return " ".join(str(value).split())


def _host_is_allowed(url, expected_host):
    parsed = urlparse(url)
    return (
        parsed.scheme == "https"
        and parsed.hostname == expected_host
        and parsed.username is None
        and parsed.password is None
    )


def _fetch_feed(feed):
    request = urllib.request.Request(
        feed["url"],
        headers={
            "User-Agent": "TrustNG-ResearchCollector/0.1",
            "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml",
        },
    )

    with urllib.request.urlopen(
        request, timeout=REQUEST_TIMEOUT_SECONDS
    ) as response:
        final_url = response.geturl()

        if not _host_is_allowed(final_url, feed["host"]):
            raise ValueError("Feed redirected to an unapproved host.")

        body = response.read(MAX_FEED_BYTES + 1)

    if len(body) > MAX_FEED_BYTES:
        raise ValueError("Feed exceeded the maximum allowed size.")

    return body


def _tag_name(tag):
    return tag.rsplit("}", 1)[-1].lower()


def _child_text(element, *names):
    wanted = set(names)

    for child in element.iter():
        if child is element:
            continue

        if _tag_name(child.tag) in wanted and child.text:
            text = _clean_text(child.text)
            if text:
                return text

    return ""


def parse_feed(xml_bytes, feed):
    """Parse RSS or Atom into unverified research candidates."""

    root = ET.fromstring(xml_bytes)
    items = []

    for element in root.iter():
        if _tag_name(element.tag) not in {"item", "entry"}:
            continue

        title = _child_text(element, "title")
        link = ""

        for child in element.iter():
            if _tag_name(child.tag) != "link":
                continue

            href = child.attrib.get("href", "").strip()
            rel = child.attrib.get("rel", "alternate")

            if href and rel in {"alternate", ""}:
                link = href
                break

            if child.text and child.text.strip():
                link = child.text.strip()
                break

        summary = _child_text(
            element, "description", "summary", "abstract", "content"
        )
        published = _child_text(
            element, "pubdate", "published", "updated", "date"
        )

        if not title or not link:
            continue

        parsed_link = urlparse(link)
        if parsed_link.scheme != "https" or not parsed_link.hostname:
            continue

        candidate_id = hashlib.sha256(
            link.encode("utf-8")
        ).hexdigest()

        items.append({
            "candidate_id": candidate_id,
            "discovered_at": _now(),
            "source_name": feed["name"],
            "source_feed": feed["url"],
            "source_region": feed["region"],
            "topic": feed["topic"],
            "title": title[:500],
            "summary": summary[:4000],
            "article_url": link,
            "published_at_source": published[:200],
            "review_status": "unreviewed",
            "evidence_status": "not_verified",
            "lesson_for_africa": None,
            "trustng_relevance": None,
        })

        if len(items) >= MAX_ITEMS_PER_FEED:
            break

    return items


def collect_once():
    """
    Fetch the fixed feeds once, save new candidates, and report errors.
    A failed feed does not prevent the other feeds from being checked.
    """

    existing = _read_candidates()
    known_ids = {item["candidate_id"] for item in existing}
    report = {
        "started_at": _now(),
        "feeds_checked": 0,
        "new_candidates": 0,
        "duplicates_skipped": 0,
        "errors": [],
    }

    for index, feed in enumerate(FEEDS):
        if index:
            time.sleep(MIN_SECONDS_BETWEEN_REQUESTS)

        report["feeds_checked"] += 1

        try:
            xml_bytes = _fetch_feed(feed)
            parsed = parse_feed(xml_bytes, feed)

            for candidate in parsed:
                candidate_id = candidate["candidate_id"]

                if candidate_id in known_ids:
                    report["duplicates_skipped"] += 1
                    continue

                existing.append(candidate)
                known_ids.add(candidate_id)
                report["new_candidates"] += 1

        except Exception as exc:
            # Save the error message, not credentials or response contents.
            report["errors"].append({
                "source": feed["name"],
                "error_type": type(exc).__name__,
                "message": str(exc)[:300],
            })

    _write_candidates(existing)
    report["finished_at"] = _now()
    report["total_candidates_stored"] = len(existing)

    return report


def list_candidates(review_status=None, source_region=None):
    candidates = _read_candidates()

    if review_status is not None:
        candidates = [
            item for item in candidates
            if item["review_status"] == review_status
        ]

    if source_region is not None:
        candidates = [
            item for item in candidates
            if item["source_region"] == source_region
        ]

    return sorted(
        candidates,
        key=lambda item: item["discovered_at"],
        reverse=True,
    )


def mark_candidate_reviewed(
    candidate_id,
    *,
    evidence_status,
    trustng_relevance,
    lesson_for_africa,
    reviewer=None,
    notes=None,
):
    """Record a human's review; this does not verify the source automatically."""

    allowed_evidence = {
        "not_verified",
        "partially_verified",
        "independently_verified",
        "rejected",
    }
    if evidence_status not in allowed_evidence:
        raise ValueError("Invalid evidence_status.")

    if not isinstance(trustng_relevance, int) or not 1 <= trustng_relevance <= 5:
        raise ValueError("trustng_relevance must be an integer from 1 to 5.")

    if not isinstance(lesson_for_africa, str) or not lesson_for_africa.strip():
        raise ValueError("lesson_for_africa must not be empty.")
    if reviewer is not None and (
        not isinstance(reviewer, str) or not reviewer.strip()
    ):
        raise ValueError("reviewer must not be empty.")
    if notes is not None and (
        not isinstance(notes, str) or not notes.strip()
    ):
        raise ValueError("notes must not be empty.")
    if (reviewer is None) != (notes is None):
        raise ValueError("reviewer and notes must be provided together.")

    candidates = _read_candidates()

    for candidate in candidates:
        if candidate["candidate_id"] != candidate_id:
            continue

        candidate["review_status"] = "reviewed"
        candidate["evidence_status"] = evidence_status
        candidate["trustng_relevance"] = trustng_relevance
        candidate["lesson_for_africa"] = lesson_for_africa.strip()
        candidate["reviewed_at"] = _now()

        if reviewer is not None and notes is not None:
            candidate["review"] = {
                "reviewer": reviewer.strip(),
                "notes": notes.strip(),
                "decision": evidence_status,
                "reviewed_at": candidate["reviewed_at"],
            }

        _write_candidates(candidates)
        return candidate

    raise ValueError("Unknown research candidate.")


def source_catalog():
    """List configured feeds and official reference sources.

    Reference sources are catalogued for research, but are not automatically
    fetched unless they have a separately reviewed feed adapter.
    """
    feeds = [
        {
            "name": feed["name"],
            "region": feed["region"],
            "jurisdiction": "International",
            "topic": feed["topic"],
            "url": feed["url"],
            "source_type": "rss_or_atom_feed",
            "collection_enabled": True,
        }
        for feed in FEEDS
    ]

    references = [
        {
            **item,
            "collection_enabled": False,
        }
        for item in RESEARCH_SOURCES
    ]

    return feeds + references


if __name__ == "__main__":
    print(json.dumps(collect_once(), indent=2))
