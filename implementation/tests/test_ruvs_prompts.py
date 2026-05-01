from ruvs.schemas import Packet, ProductCandidate
from ruvs.prompts import build_stamp_messages, STAMP_SYSTEM_PROMPT


def _packet():
    return Packet(
        recipe_id=506745, line_idx=4, config_bucket="hh4|none|3meal",
        recipe_text="1 lb butter", parsed_item="butter", recipe_grams=454.0,
        hestia_canonical="Butter, salted",
        audit_candidates=[{"canonical_label": "Butter", "match_score": 3.01}],
        fndds_desc="butter, salted", sr28_desc="Butter, salted",
        esha_desc="Butter (salted)",
        walmart_candidates=[ProductCandidate(upc="78742370", title="Great Value Salted Butter", grams=454.0, price_cents=349, retail="walmart")],
        kroger_candidates=[],
    )


def test_system_prompt_encodes_default_prep_state_rule():
    assert "default" in STAMP_SYSTEM_PROMPT.lower() and "raw" in STAMP_SYSTEM_PROMPT.lower()
    assert "breaded" in STAMP_SYSTEM_PROMPT.lower()
    assert "popcorn" in STAMP_SYSTEM_PROMPT.lower()


def test_system_prompt_forbids_numeric_grams():
    assert "do not" in STAMP_SYSTEM_PROMPT.lower() or "never" in STAMP_SYSTEM_PROMPT.lower()
    assert "grams" in STAMP_SYSTEM_PROMPT.lower() and "compute" in STAMP_SYSTEM_PROMPT.lower()


def test_system_prompt_lists_facet_enums():
    for facet in ["canonical_correct", "form_correct", "granularity_correct",
                  "grams_plausible", "cook_state_handled", "package_math_sane",
                  "ambiguity_flagged"]:
        assert facet in STAMP_SYSTEM_PROMPT


def test_user_message_includes_packet_fields():
    msgs = build_stamp_messages(_packet())
    assert msgs[0]["role"] == "system"
    assert msgs[1]["role"] == "user"
    user = msgs[1]["content"]
    assert "1 lb butter" in user
    assert "Butter, salted" in user
    assert "Great Value Salted Butter" in user
    assert "506745" in user
