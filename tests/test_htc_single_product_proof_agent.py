from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from htc_single_product_proof_agent import final_state_from_fixer, proof_key, validate_final_state_against_packet, write_queue_record
from htc_vllm_auditor_runner import duplicate_upc_conflicts


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


def test_recipe_join_policy_scope_drops_product_and_full_code_writes():
    final = final_state_from_fixer(
        "N0000009",
        {
            "fixer_verdict": "stage_recipe_join_policy",
            "staged_change": {
                "recipe_join_policy": {"join_level": "blocked"},
                "write_scope": ["product_htc_assignment", "full_code_assignment", "recipe_join_policy"],
            },
        },
    )

    assert final["action"] == "stage_recipe_join_policy"
    assert final["write_scope"] == ["recipe_join_policy"]


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
                "write_scope": ["product_htc_assignment", "full_code_assignment"],
            },
        },
    )

    assert final["action"] == "stage_full_code_repair"
    assert final["verdict"] == "verified_current"
    assert final["write_scope"] == ["full_code_assignment"]


def test_no_change_with_full_code_becomes_full_code_repair():
    final = final_state_from_fixer(
        "8705000A",
        {
            "fixer_verdict": "no_change_verified_current",
            "accepted_htc_code": "8705000A",
            "accepted_htc_full_code": "~8705000A-4BD00A-1000",
            "staged_change": {
                "write_scope": ["product_htc_assignment", "full_code_assignment"],
            },
        },
    )

    assert final["action"] == "stage_full_code_repair"
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
                "product": {"upc": "123", "name": "Hard Product", "htc_code": "D000600$"},
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
    assert "compare_code_neighbors:D000600$,D102000R" in tools
    assert "fetch_corpus_rows_for_htc_code:D000600$" in tools
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
            "htc_code": "M001000N",
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


def test_full_code_validation_strips_bad_full_code_but_keeps_base_update():
    final = {
        "action": "stage_htc_update",
        "verdict": "verified_update",
        "accepted_htc_code": "J0130004",
        "accepted_htc_full_code": "~J0130004-40346E-0000",
        "facet_updates": {"htc_full_code": "~J0130004-40346E-0000", "modifier": "Distilled"},
        "recipe_join_policy": {"join_level": "full_code", "ordinary_ingredient_substitute": "yes"},
        "write_scope": ["product_htc_assignment", "full_code_assignment"],
        "production_writes": False,
    }
    packet = {
        "product": {
            "name": "Great Value Apple Cider Vinegar, 32 fl oz",
            "tree_product_identity": "Apple Cider Vinegar",
            "tree_canonical_path": "Pantry > Vinegar > Apple Cider Vinegar",
            "htc_code": "FB00000F",
        },
        "direct_consensus_candidates": [
            {
                "htc_full_code": "~J0130004-40346E-0000",
                "modifier": "Distilled",
                "retail_leaf_path": "Pantry > Vinegar > Apple Cider Vinegar > Distilled",
            }
        ],
    }

    validated = validate_final_state_against_packet(final, packet)

    assert validated["action"] == "stage_htc_update"
    assert validated["verdict"] == "verified_update"
    assert validated["accepted_htc_code"] == "J0130004"
    assert validated["accepted_htc_full_code"] == ""
    assert "htc_full_code" not in validated["facet_updates"]
    assert validated["recipe_join_policy"]["join_level"] == "base_htc"
    assert validated["write_scope"] == ["product_htc_assignment"]
    assert "stripped" in validated["facet_notes"]
    assert validated["validation_warnings"][0]["absent_modifier_terms"] == ["distilled"]


def test_full_code_strip_keeps_variant_join_policy_when_not_ordinary_substitute():
    final = {
        "action": "stage_htc_update",
        "verdict": "verified_update",
        "accepted_htc_code": "M01D000$",
        "accepted_htc_full_code": "~M01D000$-96CEA3-0001",
        "recipe_join_policy": {
            "join_level": "full_code",
            "ordinary_ingredient_substitute": "no",
            "incompatible_recipe_terms": ["ordinary adult recipe ingredient terms"],
        },
        "write_scope": ["product_htc_assignment", "full_code_assignment", "recipe_join_policy"],
        "production_writes": False,
    }
    packet = {
        "product": {
            "name": "Earth's Best Organic Multi-Grain Infant Baby Cereal",
            "htc_code": "860W0001",
        },
        "direct_consensus_candidates": [
            {
                "htc_full_code": "~M01D000$-96CEA3-0001",
                "modifier": "Plum Berry Barley > Organic",
                "retail_leaf_path": "Baby & Toddler > Baby Food > Plum Berry Barley > Organic",
            }
        ],
    }

    validated = validate_final_state_against_packet(final, packet)

    assert validated["action"] == "stage_htc_update"
    assert validated["accepted_htc_full_code"] == ""
    assert validated["recipe_join_policy"]["join_level"] == "variant_or_explicit_only"
    assert validated["recipe_join_policy"]["ordinary_ingredient_substitute"] == "no"


def test_full_code_validation_accepts_supported_facet_synonyms():
    cases = [
        (
            {
                "name": "Great Value No Added Sweeteners 100% Apple Juice",
                "htc_code": "D102000R",
            },
            {
                "htc_full_code": "~D102000R-2457E3-0000",
                "modifier": "No Sugar Added",
                "retail_leaf_path": "Beverage > Juice > Apple Juice > No Sugar Added",
            },
        ),
        (
            {
                "name": "Nestle Carnation Vitamin D Added Evaporated Milk",
                "tree_product_identity": "Evaporated Milk",
                "htc_code": "1B02000J",
            },
            {
                "htc_full_code": "~1B02000J-EF2CA2-0000",
                "modifier": "Fortified",
                "retail_leaf_path": "Dairy > Milk > Evaporated Milk > Fortified",
            },
        ),
        (
            {
                "name": "Mott's 100% Original Apple Juice",
                "htc_code": "D102000R",
            },
            {
                "htc_full_code": "~D102000R-A116C9-0000",
                "modifier": "Plain",
                "retail_leaf_path": "Beverage > Juice > Apple Juice > Plain",
            },
        ),
    ]
    for product, witness in cases:
        final = {
            "action": "stage_full_code_repair",
            "verdict": "verified_current",
            "accepted_htc_code": product["htc_code"],
            "accepted_htc_full_code": witness["htc_full_code"],
            "production_writes": False,
        }
        packet = {"product": product, "direct_consensus_candidates": [witness]}

        validated = validate_final_state_against_packet(final, packet)

        assert validated["action"] == "stage_full_code_repair"
        assert "validation_errors" not in validated
        assert "validation_warnings" not in validated


def test_duplicate_upc_conflicts_detects_inconsistent_batch_decisions(tmp_path):
    rows = [
        (1, {"rowid": "10", "upc": "123", "name": "Same Product"}),
        (2, {"rowid": "11", "upc": "123", "name": "Same Product"}),
    ]
    for row_number, row, action in [
        (1, rows[0][1], "stage_recipe_join_policy"),
        (2, rows[1][1], "stage_htc_update"),
    ]:
        path = tmp_path / f"proof_{proof_key(row_number, row)}.json"
        path.write_text(json.dumps({
            "product": {"rowid": row["rowid"], "upc": row["upc"], "name": row["name"], "htc_code": "D300000J"},
            "final": {
                "action": action,
                "verdict": "verified_current" if action == "stage_recipe_join_policy" else "verified_update",
                "accepted_htc_code": "" if action == "stage_recipe_join_policy" else "D3C1000Y",
                "accepted_htc_full_code": "",
                "write_scope": ["recipe_join_policy"] if action == "stage_recipe_join_policy" else ["product_htc_assignment"],
            },
        }), encoding="utf-8")

    conflicts = duplicate_upc_conflicts(tmp_path, rows)

    assert len(conflicts) == 1
    assert conflicts[0]["upc"] == "123"
    assert conflicts[0]["conflict"] == "duplicate_upc_inconsistent_decisions"
