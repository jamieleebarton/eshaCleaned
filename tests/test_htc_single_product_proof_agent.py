from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from htc_single_product_proof_agent import final_state_from_fixer, validate_final_state_against_packet, write_queue_record


def test_final_state_stages_recipe_join_policy_from_auditor_compatibility():
    final = final_state_from_fixer(
        "868E000H",
        {"fixer_verdict": "machine_evidence_expansion"},
        proposal={},
        verifier={
            "verifier_verdict": "verified_current",
            "recipe_join_risk": "audience_mismatch",
            "recipe_compatibility": {
                "ordinary_ingredient_substitute": "no",
                "compatible_recipe_terms": ["baby oatmeal cereal"],
                "incompatible_recipe_terms": ["oatmeal", "hot cereal"],
                "join_level": "blocked",
                "evidence": ["product is baby-specific"],
            },
        },
    )

    assert final["action"] == "stage_recipe_join_policy"
    assert final["verdict"] == "verified_current"
    assert final["write_scope"] == ["recipe_join_policy"]
    assert final["recipe_join_policy"]["ordinary_ingredient_substitute"] == "no"
    assert final["recipe_join_policy"]["blocks"][0]["recipe_query"] == "oatmeal"


def test_final_state_does_not_stage_policy_when_auditor_is_unresolved():
    final = final_state_from_fixer(
        "D000600$",
        {"fixer_verdict": "machine_evidence_expansion"},
        proposal={
            "recipe_compatibility": {
                "ordinary_ingredient_substitute": "yes",
                "compatible_recipe_terms": ["juice cocktail"],
                "join_level": "full_code",
            },
        },
        verifier={
            "verifier_verdict": "needs_more_evidence",
            "recipe_compatibility": {
                "ordinary_ingredient_substitute": "uncertain",
                "join_level": "uncertain",
            },
        },
    )

    assert final["action"] == "machine_evidence_expansion"
    assert final["recipe_join_policy"] == {}


def test_final_state_stages_full_code_repair_action():
    final = final_state_from_fixer(
        "868E000H",
        {
            "fixer_verdict": "stage_full_code_repair",
            "accepted_htc_code": "868E000H",
            "accepted_htc_full_code": "~868E000H-ABC123-0001",
            "staged_change": {
                "write_scope": ["full_code_assignment"],
                "facet_updates": {"audience": ["baby"]},
            },
        },
    )

    assert final["action"] == "stage_full_code_repair"
    assert final["accepted_htc_code"] == "868E000H"
    assert final["accepted_htc_full_code"] == "~868E000H-ABC123-0001"
    assert final["write_scope"] == ["full_code_assignment"]


def test_stage_htc_update_same_base_with_full_code_becomes_full_code_repair():
    final = final_state_from_fixer(
        "8705000A",
        {
            "fixer_verdict": "stage_htc_update",
            "accepted_htc_code": "8705000A",
            "accepted_htc_full_code": "~8705000A-4BD00A-1000",
            "staged_change": {
                "facet_updates": {"modifier": "Buttermilk > High Protein"},
            },
        },
    )

    assert final["action"] == "stage_full_code_repair"
    assert final["verdict"] == "verified_current"
    assert final["write_scope"] == ["full_code_assignment"]


def test_machine_evidence_queue_falls_back_to_packet_tools(tmp_path):
    write_queue_record(
        tmp_path,
        {
            "output": "proof.json",
            "product": {
                "rowid": "1",
                "upc": "123",
                "name": "Hard Product",
                "htc_code": "D000600$",
            },
            "proposal": {"selected_htc_code": "D102000R"},
            "verifier": {
                "verifier_verdict": "needs_more_evidence",
                "required_next_tools": [],
            },
            "evidence_packet": {
                "product": {"upc": "123", "name": "Hard Product"},
                "workbench_dashboard": {
                    "candidate_families": [
                        {"family_id": "apple_juice"}
                    ]
                },
            },
            "final": {
                "action": "machine_evidence_expansion",
                "verdict": "needs_more_evidence",
            },
        },
    )

    rows = [
        json.loads(line)
        for line in (tmp_path / "machine_evidence_expansion.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    tools = rows[0]["required_next_tools"]
    assert tools
    assert "expand_candidate_family:apple_juice" in tools
    assert "fetch_corpus_rows_for_htc_code:D102000R" in tools


def test_full_code_validation_blocks_absent_modifier_terms():
    final = {
        "action": "stage_htc_update",
        "verdict": "verified_update",
        "accepted_htc_code": "M001000N",
        "accepted_htc_full_code": "~M001000N-8FFF68-0001",
        "production_writes": False,
    }
    packet = {
        "product": {
            "name": "Earth's Best Organic Whole Grain Oatmeal Baby Cereal",
            "search_term": "baby oatmeal",
            "tree_modifier": "Oatmeal Organic Whole Grain",
        },
        "direct_consensus_candidates": [
            {
                "htc_full_code": "~M001000N-8FFF68-0001",
                "modifier": "Apple Spinach Avocado > Organic",
                "retail_leaf_path": "Baby & Toddler > Baby Food > Apple Spinach Avocado > Organic",
            }
        ],
    }

    validated = validate_final_state_against_packet(final, packet)

    assert validated["action"] == "machine_evidence_expansion"
    assert validated["verdict"] == "needs_more_evidence"
    assert validated["validation_errors"][0]["absent_modifier_terms"] == ["apple", "avocado", "spinach"]
