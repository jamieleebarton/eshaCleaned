from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from htc_product_auditor_agent import CandidateScore, HtcReference, score_candidate, verify_decision, weighted_tokens


def candidate(**overrides):
    base = {
        "htc_code": "X0000000",
        "score": 4.0,
        "title_overlap": 0.5,
        "search_overlap": 0.5,
        "path_overlap": 0.0,
        "aisle_overlap": 0.2,
        "string_similarity": 0.2,
        "current_match_bonus": 0.0,
        "authority_penalty": 0.0,
        "canonical_path": "Beverage > Juice > Apple Juice",
        "retail_leaf_path": "Beverage > Juice > Apple Juice",
        "product_identity": "Apple Juice",
        "row_count": 10,
        "evidence_terms": ["apple", "juice"],
        "missing_required_identity_terms": [],
        "title_samples": ["Apple Juice"],
    }
    base.update(overrides)
    return CandidateScore(**base)


def test_juice_candidate_with_missing_identity_terms_needs_more_evidence():
    row = {
        "name": "Great Value No Added Sweeteners 100% Apple Juice, 64 fl oz",
        "htc_code": "D000600$",
        "raw_htc_code": "D000600$",
    }
    verdict, confidence, _margin, reason = verify_decision(
        row,
        [
            candidate(
                htc_code="C0ME0004",
                canonical_path="Pantry > Sweeteners > Honey",
                retail_leaf_path="Pantry > Sweeteners > Honey > Apple Blossom",
                product_identity="Honey",
                missing_required_identity_terms=["juice", "path_missing:juice_or_beverage"],
            )
        ],
    )
    assert verdict == "needs_more_evidence"
    assert confidence == "low"
    assert reason == "candidate_missing_required_identity_terms"


def test_sparse_candidate_cannot_be_verified_update():
    row = {
        "name": "Capri Sun 100% Juice Apple, 10 ct Box",
        "htc_code": "D000600$",
        "raw_htc_code": "D000600$",
    }
    verdict, confidence, _margin, reason = verify_decision(
        row,
        [
            candidate(
                htc_code="70E6000B",
                canonical_path="Frozen > Frozen Fruit > Concentrate",
                retail_leaf_path="Frozen > Frozen Fruit > Concentrate > Cranberry Apple",
                product_identity="Concentrate",
                row_count=1,
            )
        ],
    )
    assert verdict == "needs_more_evidence"
    assert confidence == "low"
    assert reason == "candidate_reference_support_too_sparse"


def test_verified_update_has_no_human_review_status():
    row = {
        "name": "7UP Caffeine Free Lemon Lime Soda Pop",
        "htc_code": "D000600$",
        "raw_htc_code": "D000600$",
    }
    verdict, confidence, _margin, _reason = verify_decision(
        row,
        [
            candidate(
                htc_code="D2020007",
                canonical_path="Beverage > Carbonated > Soda",
                retail_leaf_path="Beverage > Carbonated > Soda > Lemon Lime",
                product_identity="Soda",
                row_count=50,
            )
        ],
    )
    assert verdict == "verified_update"
    assert confidence == "high"
    assert "review" not in verdict


def test_candidate_with_extra_absent_flavor_is_blocked():
    row = {
        "name": "Juicy Juice 100% Juice, Apple, 64 fl oz Bottle",
        "search_term": "100% apple juice",
        "category_path_walmart": "Home Page/Food/Beverages/Juices/Apple Juice",
        "htc_code": "D000600$",
        "raw_htc_code": "D000600$",
    }
    ref = HtcReference(
        htc_code="D15M000B",
        row_count=9,
        canonical_path="Beverage > Juice > Apple Raspberry",
        retail_leaf_path="Beverage > Juice > Apple Raspberry",
        product_identity="Apple Raspberry",
        branded_food_category="Juice",
        title_samples=["APPLE RASPBERRY FLAVORED JUICE COCKTAIL"],
        terms=["apple", "beverage", "juice", "raspberry"],
        path_terms=["apple", "beverage", "juice", "raspberry"],
        category_terms=["juice"],
        similarity_terms=["apple", "beverage", "juice", "raspberry"],
    )
    scored = score_candidate(row, ref, weighted_tokens(row), {})
    assert "incompatible_flavor:raspberry" in scored.missing_required_identity_terms


def test_noisy_search_term_cannot_supply_absent_title_flavor():
    row = {
        "name": "Great Value Cranberry Raspberry Juice Cocktail, 64 fl oz",
        "search_term": "apple raspberry juice",
        "category_path_walmart": "Home Page/Food/Beverages/Juices/All Juices",
        "htc_code": "D000600$",
        "raw_htc_code": "D000600$",
    }
    ref = HtcReference(
        htc_code="D1BA000G",
        row_count=4,
        canonical_path="Beverage > Juice > Cranberry Raspberry Apple",
        retail_leaf_path="Beverage > Juice > Cranberry Raspberry Apple",
        product_identity="Juice",
        branded_food_category="Juice",
        title_samples=["CRANBERRY RASPBERRY FLAVORED JUICE COCKTAIL BLENDED WITH APPLE JUICE FROM CONCENTRATE"],
        terms=["apple", "beverage", "cranberry", "juice", "raspberry"],
        path_terms=["apple", "beverage", "cranberry", "juice", "raspberry"],
        category_terms=["juice"],
        similarity_terms=["apple", "beverage", "cranberry", "juice", "raspberry"],
    )
    scored = score_candidate(row, ref, weighted_tokens(row), {})
    assert "title_absent_flavor:apple" in scored.missing_required_identity_terms


def test_sparse_candidate_with_absent_variety_is_blocked():
    row = {
        "name": "Juicy Juice 100% Juice, Apple, 64 fl oz Bottle",
        "search_term": "100% apple juice",
        "category_path_walmart": "Home Page/Food/Beverages/Juices/Apple Juice",
        "htc_code": "D000600$",
        "raw_htc_code": "D000600$",
    }
    ref = HtcReference(
        htc_code="D1H8000M",
        row_count=2,
        canonical_path="Beverage > Juice > Apple Juice > Gravenstein",
        retail_leaf_path="Beverage > Juice > Apple Juice > Gravenstein",
        product_identity="Gravenstein Apple Juice",
        branded_food_category="Juice",
        title_samples=["GRAVENSTEIN APPLE JUICE"],
        terms=["apple", "beverage", "gravenstein", "juice"],
        path_terms=["apple", "beverage", "gravenstein", "juice"],
        category_terms=["juice"],
        similarity_terms=["apple", "beverage", "gravenstein", "juice"],
    )
    scored = score_candidate(row, ref, weighted_tokens(row), {})
    assert any(
        term.startswith("sparse_candidate_adds_absent_path_terms:gravenstein")
        for term in scored.missing_required_identity_terms
    )


def test_sparse_claim_leaf_is_blocked_for_identity_assignment():
    row = {
        "name": "Juicy Juice 100% Juice, Apple, 64 fl oz Bottle",
        "search_term": "100% apple juice",
        "category_path_walmart": "Home Page/Food/Beverages/Juices/Apple Juice",
        "htc_code": "D000600$",
        "raw_htc_code": "D000600$",
    }
    ref = HtcReference(
        htc_code="D1H5000S",
        row_count=2,
        canonical_path="Beverage > Juice > Apple Juice",
        retail_leaf_path="Beverage > Juice > Apple Juice > 100",
        product_identity="Apple Juice",
        branded_food_category="Juice",
        title_samples=["100% APPLE JUICE"],
        terms=["apple", "beverage", "juice"],
        path_terms=["apple", "beverage", "juice"],
        category_terms=["juice"],
        similarity_terms=["apple", "beverage", "juice"],
    )
    scored = score_candidate(row, ref, weighted_tokens(row), {})
    assert "sparse_candidate_claim_or_variant_leaf:100" in scored.missing_required_identity_terms
