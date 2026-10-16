import research_analyzer as analyzer


def test_relevant_payment_security_candidate_scores_higher():
    relevant = {
        "candidate_id": "a",
        "title": "AI cyber threats in payment systems",
        "summary": "Fraud detection and transaction security",
        "topic": "payments",
    }
    unrelated = {
        "candidate_id": "b",
        "title": "Maritime trade and population trends",
        "summary": "Economic research",
        "topic": "general",
    }

    assert (
        analyzer.score_candidate(relevant)["relevance_score"]
        > analyzer.score_candidate(unrelated)["relevance_score"]
    )


def test_score_explains_why_candidate_matched():
    result = analyzer.score_candidate({
        "candidate_id": "a",
        "title": "Cybersecurity vulnerability",
        "summary": "Authentication threat",
    })

    assert "cybersecurity" in result["matched_categories"]
    assert result["matched_terms"]
    assert result["human_review_required"] is True


def test_triage_never_claims_verification_or_authorizes_implementation():
    result = analyzer.score_candidate({
        "candidate_id": "a",
        "title": "Banking security",
    })

    assert result["verification_claimed"] is False
    assert result["implementation_authorized"] is False
    assert result["human_review_required"] is True


def test_rank_candidates_places_more_relevant_items_first():
    candidates = [
        {
            "candidate_id": "general",
            "title": "General economic outlook",
            "summary": "Population and trade",
        },
        {
            "candidate_id": "security",
            "title": "Cybersecurity threats to payment transactions",
            "summary": "Fraud and authentication risks",
        },
    ]

    ranked = analyzer.rank_candidates(candidates)

    assert ranked[0]["candidate_id"] == "security"


def test_reviewed_candidates_are_excluded_by_default():
    candidates = [
        {
            "candidate_id": "reviewed",
            "title": "Payment security",
            "review_status": "reviewed",
        },
        {
            "candidate_id": "new",
            "title": "Payment security",
            "review_status": "unreviewed",
        },
    ]

    ranked = analyzer.rank_candidates(candidates)

    assert [item["candidate_id"] for item in ranked] == ["new"]


def test_generic_product_cyber_advisory_is_not_automatically_high_priority():
    result = analyzer.score_candidate({
        "candidate_id": "generic-cyber",
        "title": "Camera firmware vulnerability",
        "summary": "A product vulnerability and security threat",
        "topic": "cybersecurity",
    })

    assert result["mission_relevance"] == "adjacent"
    assert result["suggested_priority"] != "high"
    assert result["verification_claimed"] is False
    assert result["implementation_authorized"] is False


def test_financial_sector_cyber_research_can_receive_high_priority():
    result = analyzer.score_candidate({
        "candidate_id": "financial-cyber",
        "title": "AI cyber threats in the financial sector",
        "summary": (
            "Fraud risks, payment transaction security, "
            "banking authentication and financial crime"
        ),
        "topic": "payments and cybersecurity",
    })

    assert result["mission_relevance"] == "direct"
    assert result["suggested_priority"] == "high"
    assert result["direct_mission_matches"]


def test_directly_relevant_research_ranks_before_general_cybersecurity():
    candidates = [
        {
            "candidate_id": "general",
            "title": "Camera firmware vulnerability",
            "summary": "A security threat",
            "topic": "cybersecurity",
        },
        {
            "candidate_id": "payments",
            "title": "Fraud risks in payment transactions",
            "summary": "Financial crime and payment security",
            "topic": "payments",
        },
    ]

    ranked = analyzer.rank_candidates(candidates)

    assert ranked[0]["candidate_id"] == "payments"
    assert ranked[1]["candidate_id"] == "general"


def test_ranking_never_changes_evidence_or_authorizes_implementation():
    result = analyzer.score_candidate({
        "candidate_id": "unverified",
        "title": "Fraud detection for banking payments",
        "evidence_status": "not_verified",
    })

    assert result["evidence_status"] == "not_verified"
    assert result["verification_claimed"] is False
    assert result["implementation_authorized"] is False
    assert result["human_review_required"] is True


def test_camera_advisory_is_not_direct_only_because_financial_services_are_mentioned():
    result = analyzer.score_candidate({
        "candidate_id": "camera",
        "title": "VIVOTEK Camera Firmware",
        "summary": (
            "Remote command execution vulnerability. "
            "Critical infrastructure sectors include financial services."
        ),
        "topic": "cybersecurity",
    })

    assert result["mission_relevance"] == "adjacent"
    assert result["suggested_priority"] != "high"


def test_climate_ai_paper_is_not_direct_from_broad_topic_label():
    result = analyzer.score_candidate({
        "candidate_id": "climate-ai",
        "title": "Artificial intelligence and climate change",
        "summary": (
            "AI can improve energy efficiency, climate forecasting, "
            "adaptation and risk management."
        ),
        "topic": "financial_system_research",
    })

    assert result["mission_relevance"] == "adjacent"
    assert result["direct_mission_matches"] == []


def test_financial_sector_cyber_title_remains_direct():
    result = analyzer.score_candidate({
        "candidate_id": "financial-cyber",
        "title": (
            "When machines attack: AI cyber threats "
            "in the financial sector"
        ),
        "summary": "Frontier AI cyber threats and policy responses.",
        "topic": "financial_system_research",
    })

    assert result["mission_relevance"] == "direct"
    assert result["direct_mission_matches"]


def test_incidental_bank_and_settlement_mentions_do_not_make_research_direct():
    result = analyzer.score_candidate({
        "candidate_id": "blockchain-statistics",
        "title": "Verifiable official statistics: a blockchain-based approach",
        "summary": (
            "This approach discusses official data quality. "
            "Some examples mention banks and settlement."
        ),
        "topic": "general research",
    })

    assert result["mission_relevance"] != "direct"
    assert result["verification_claimed"] is False
    assert result["implementation_authorized"] is False


def test_stablecoin_research_remains_direct():
    result = analyzer.score_candidate({
        "candidate_id": "stablecoin-deposits",
        "title": "Are stablecoins and bank deposits substitutes?",
        "summary": "Research on stablecoins and bank deposits.",
    })

    assert result["mission_relevance"] == "direct"
