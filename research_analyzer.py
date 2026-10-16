"""Transparent, human-supervised triage for TrustNG research candidates.

Keyword matching estimates mission relevance. It does not verify claims,
measure real-world severity, or authorize implementation.
"""

import json
from pathlib import Path

import research_collector


DATA_DIR = research_collector.DATA_DIR
TRIAGE_FILE = DATA_DIR / "research_triage.json"

KEYWORD_GROUPS = {
    "fraud_and_financial_crime": {
        "keywords": (
            "fraud", "financial crime", "money laundering",
            "scam", "forgery", "illicit finance", "account takeover",
            "anti-money laundering", "aml", "know your customer", "kyc",
        ),
        "weight": 5,
    },
    "payments_and_transactions": {
        "keywords": (
            "payment", "transaction", "payments system",
            "cross-border", "remittance", "settlement",
            "transfer", "stablecoin", "mobile money", "digital wallet",
            "payment card", "open banking", "open finance",
        ),
        "weight": 4,
    },
    "cybersecurity": {
        "keywords": (
            "cyber", "security", "vulnerability", "ransomware",
            "phishing", "credential", "authentication",
            "access control", "encryption", "threat",
        ),
        "weight": 4,
    },
    "ai_and_machine_learning": {
        "keywords": (
            "artificial intelligence", "machine learning",
            "frontier ai", "automated decision", "model risk",
            "algorithmic", "anomaly detection",
        ),
        "weight": 4,
    },
    "risk_and_banking": {
        "keywords": (
            "risk management", "financial stability", "banking",
            "bank", "capital requirement", "prudential",
            "operational resilience", "liquidity",
        ),
        "weight": 3,
    },
    "privacy_and_data": {
        "keywords": (
            "privacy", "data protection", "personal data",
            "data breach", "data integrity", "confidentiality",
        ),
        "weight": 3,
    },
    "infrastructure_and_resilience": {
        "keywords": (
            "infrastructure", "resilience", "reliability",
            "incident response", "business continuity",
            "supply chain", "systemic risk",
        ),
        "weight": 2,
    },
}

# These terms indicate a direct connection to TrustNG's financial-risk mission.
DIRECT_MISSION_TERMS = (
    "payment", "financial sector", "financial services",
    "fintech", "fraud", "money laundering", "illicit finance",
    "remittance", "stablecoin", "mobile money",
    "digital wallet", "payment card", "account takeover",
    "open banking", "open finance", "anti-money laundering",
    "financial crime", "know your customer", "cross-border payment",
)

# Broader security, AI, privacy, and resilience topics may be useful,
# but should not automatically receive the highest review priority.
ADJACENT_CATEGORIES = {
    "cybersecurity",
    "ai_and_machine_learning",
    "privacy_and_data",
    "infrastructure_and_resilience",
}


def score_candidate(candidate):
    """Return a heuristic score with explicit mission relevance."""

    title = str(candidate.get("title", ""))
    summary = str(candidate.get("summary", ""))
    topic = str(candidate.get("topic", ""))
    text = " ".join((title, summary, topic)).lower()

    score = 0
    categories = []
    matched_terms = []

    for category, rule in KEYWORD_GROUPS.items():
        matches = [
            keyword for keyword in rule["keywords"]
            if keyword in text
        ]
        if matches:
            categories.append(category)
            matched_terms.extend(matches)
            score += rule["weight"] * min(len(matches), 3)

    title_text = title.lower()
    summary_text = summary.lower()

    # A direct title signal must describe a financial-risk topic,
    # not merely contain a broad word such as "bank" or "transaction".
    title_direct_terms = (
        "payment", "financial sector", "financial services",
        "fintech", "fraud", "money laundering", "illicit finance",
        "remittance", "settlement", "stablecoin", "mobile money",
        "digital wallet", "payment card", "account takeover",
        "open banking", "open finance", "anti-money laundering",
        "financial crime", "know your customer",
        "cross-border payment",
    )

    title_direct_matches = [
        term for term in title_direct_terms
        if term in title_text
    ]
    summary_direct_matches = [
        term for term in DIRECT_MISSION_TERMS
        if term in summary_text
    ]

    # Incidental mentions in a long advisory or broad topic labels
    # must not establish direct mission relevance on their own.
    direct_matches = list(dict.fromkeys(
        title_direct_matches + summary_direct_matches
    ))

    is_direct = (
        bool(title_direct_matches)
        or len(summary_direct_matches) >= 2
    )

    if is_direct:
        mission_relevance = "direct"
        priority = (
            "high" if score >= 12
            else "medium" if score >= 5
            else "low"
        )
    elif any(category in ADJACENT_CATEGORIES for category in categories):
        mission_relevance = "adjacent"
        priority = "medium" if score >= 5 else "low"
    else:
        mission_relevance = "general"
        priority = "low"

    return {
        "candidate_id": candidate.get("candidate_id"),
        "title": title,
        "source_name": candidate.get("source_name", ""),
        "source_region": candidate.get("source_region", ""),
        "article_url": candidate.get("article_url", ""),
        "published_at_source": candidate.get("published_at_source", ""),
        "review_status": candidate.get("review_status", "unreviewed"),
        "evidence_status": candidate.get("evidence_status", "not_verified"),
        "relevance_score": score,
        "suggested_priority": priority,
        "mission_relevance": mission_relevance,
        "matched_categories": categories,
        "matched_terms": matched_terms,
        "direct_mission_matches": direct_matches,
        "human_review_required": True,
        "verification_claimed": False,
        "implementation_authorized": False,
    }


def rank_candidates(candidates=None, include_reviewed=False):
    """Rank candidates by mission relevance, then heuristic score."""

    if candidates is None:
        candidates = research_collector.list_candidates()

    results = []

    for candidate in candidates:
        if not include_reviewed and candidate.get("review_status") == "reviewed":
            continue
        results.append(score_candidate(candidate))

    relevance_order = {"direct": 2, "adjacent": 1, "general": 0}
    results.sort(
        key=lambda item: (
            relevance_order[item["mission_relevance"]],
            item["relevance_score"],
            item["published_at_source"],
            item["title"],
        ),
        reverse=True,
    )
    return results


def save_triage(include_reviewed=False):
    """Save a shortlist separately from original candidate records."""

    results = rank_candidates(include_reviewed=include_reviewed)
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    temporary = TRIAGE_FILE.with_suffix(".tmp")
    with temporary.open("w", encoding="utf-8") as file:
        json.dump(results, file, indent=2, ensure_ascii=False)
        file.flush()
        import os
        os.fsync(file.fileno())

    temporary.replace(TRIAGE_FILE)

    return {
        "candidates_ranked": len(results),
        "high_priority": sum(
            item["suggested_priority"] == "high" for item in results
        ),
        "medium_priority": sum(
            item["suggested_priority"] == "medium" for item in results
        ),
        "low_priority": sum(
            item["suggested_priority"] == "low" for item in results
        ),
        "output_file": str(TRIAGE_FILE),
        "automatic_verification": False,
        "production_changes_authorized": False,
    }


if __name__ == "__main__":
    print(json.dumps(save_triage(), indent=2))
