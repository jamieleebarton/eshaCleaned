import json
from ruvs.schemas import (
    Packet, ProductCandidate, LineVerdict,
    FixRow, Patch, FACETS, FACET_ENUMS,
)


def test_facet_enums_match_spec():
    assert FACETS == [
        "canonical_correct", "form_correct", "granularity_correct",
        "grams_plausible", "cook_state_handled", "package_math_sane",
        "ambiguity_flagged",
    ]
    assert FACET_ENUMS["canonical_correct"] == ("ok", "wrong", "ambiguous")
    assert FACET_ENUMS["form_correct"] == ("ok", "wrong_form", "n/a")
    assert FACET_ENUMS["ambiguity_flagged"] == ("none", "range", "or_option", "generic_term")


def test_packet_roundtrip():
    p = Packet(
        recipe_id=506745, line_idx=4, config_bucket="household=4|dietary=none|pattern=3meal",
        recipe_text="1 lb butter", parsed_item="butter", recipe_grams=454.0,
        hestia_canonical="Butter, salted",
        audit_candidates=[{"canonical_label": "Butter", "match_score": 3.01}],
        fndds_desc="butter, salted", sr28_desc="Butter, salted",
        esha_desc="Butter (salted)",
        walmart_candidates=[ProductCandidate(upc="78742370", title="Great Value Salted Butter", grams=454.0, price_cents=349)],
        kroger_candidates=[],
    )
    j = p.to_json()
    p2 = Packet.from_json(j)
    assert p2 == p


def test_line_verdict_validates_facets():
    import pytest
    # ambiguity_flagged uses ("none", ...) not "ok"; build clean facets accordingly
    facets = {f: ("none" if f == "ambiguity_flagged" else "ok") for f in FACETS}
    v = LineVerdict(
        recipe_id=506745, line_idx=4, config_bucket="x", model="deepseek-v3.2-fast",
        run_id="r1", facets=facets, evidence={}, fix_proposed=None, ts="2026-05-01T00:00:00Z",
    )
    assert v.is_clean()
    facets["form_correct"] = "wrong_form"
    v2 = LineVerdict(
        recipe_id=506745, line_idx=4, config_bucket="x", model="m", run_id="r1",
        facets=facets, evidence={}, fix_proposed=None, ts="2026-05-01T00:00:00Z",
    )
    assert not v2.is_clean()
    with pytest.raises(ValueError, match="invalid facet value"):
        LineVerdict(
            recipe_id=1, line_idx=0, config_bucket="x", model="m", run_id="r1",
            facets={**facets, "form_correct": "BANANA"},
            evidence={}, fix_proposed=None, ts="2026-05-01T00:00:00Z",
        )


def test_patch_types():
    p = Patch(
        patch_type="wishlist", canonical="beef gravy",
        delta={"deny_form": ["dry", "instant"], "require_form": ["liquid", "jarred"]},
        affected_recipes=[506745], source_run_id="r1",
    )
    assert p.patch_type == "wishlist"
    j = json.loads(p.to_json())
    assert j["delta"]["deny_form"] == ["dry", "instant"]
