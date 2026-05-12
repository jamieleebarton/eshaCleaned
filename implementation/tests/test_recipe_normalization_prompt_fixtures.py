import json
import unittest
from collections import Counter
from pathlib import Path

from implementation.validate_recipe_normalization_nebius_output import load_jsonl, validate


ROOT = Path(__file__).resolve().parents[2]
PACK = ROOT / "implementation" / "output" / "recipe_normalization_prompt_test_pack.jsonl"


REQUIRED_CASES = {
    "percent_purity_bran_brand",
    "percent_purity_bran_ambiguous",
    "percent_purity_fruit_juice_unknown",
    "percent_purity_pumpkin",
    "protein_powder_percent_flavor",
    "parser_fragment",
    "section_header",
    "section_scoped_ingredient",
    "shared_sense_pepper",
    "shared_sense_coriander",
    "shared_sense_chili",
    "head_noun_trap",
    "parenthetical_examples",
    "bone_in_yield",
    "parsed_item_hides_display_options",
    "blend_identity_preservation",
    "true_alternative_bean_mix",
    "true_alternative_cheese_blend",
}


class RecipeNormalizationPromptFixtureTests(unittest.TestCase):
    def test_fixture_contains_required_new_failure_cases(self):
        rows = load_jsonl(PACK)
        counts = Counter(
            stress["case"]
            for row in rows
            for stress in row.get("stress_lines", [])
        )

        missing = sorted(case for case in REQUIRED_CASES if counts[case] == 0)
        self.assertEqual([], missing)
        self.assertGreaterEqual(len(rows), 42)
        self.assertGreaterEqual(sum(counts.values()), 90)

    def test_bad_candidate_trips_validator_for_new_cases(self):
        source_rows = load_jsonl(PACK)
        candidate_rows = []
        for source in source_rows:
            by_line = {}
            for stress in source.get("stress_lines", []):
                line_index = stress["line_index"]
                if line_index in by_line:
                    continue
                grams = stress.get("grams")
                by_line[line_index] = {
                    "line_index": line_index,
                    "original_display": stress.get("display", ""),
                    "original_item": stress.get("item", ""),
                    "normalized": {
                        "machine_name": str(stress.get("display", "")).lower(),
                        "product_identity": stress.get("item", ""),
                        "brand_removed": [],
                        "variant": [],
                        "flavor": [],
                        "form_texture_cut": [],
                        "processing_storage": [],
                        "claims": [],
                        "prep": [],
                    },
                    "role": "consumed",
                    "quantity": {"source_grams": grams},
                    "consumption": {
                        "calculation_status": "CALCULATION_READY",
                        "consumption_policy": "all_input",
                        "consumed_grams": grams,
                    },
                    "components": [],
                    "alternatives": [],
                    "confidence": 0.9,
                }
            candidate_rows.append(
                {
                    "recipe_id": source["recipe_id"],
                    "title": source.get("title", ""),
                    "ingredients": list(by_line.values()),
                }
            )

        findings = validate(source_rows, candidate_rows)
        error_codes = {finding.code for finding in findings if finding.severity == "error"}
        expected_error_codes = {
            "percent_purity_lost",
            "unknown_fruit_juice_ready",
            "parser_fragment_role",
            "section_header_role",
            "pepper_sense_wrong",
            "coriander_sense_wrong",
            "head_noun_compound_lost",
            "parenthetical_examples_lost",
            "bone_in_all_input",
            "display_options_hidden_by_item",
        }
        self.assertTrue(expected_error_codes & error_codes, json.dumps(sorted(error_codes), indent=2))
        self.assertGreaterEqual(sum(1 for finding in findings if finding.severity == "error"), 20)

    def test_blend_identity_tests_reject_single_food_collapse(self):
        source_rows = []
        candidate_rows = []
        for row in load_jsonl(PACK):
            blend_stress = [
                stress for stress in row.get("stress_lines", [])
                if stress.get("case") == "blend_identity_preservation"
            ]
            if not blend_stress:
                continue
            source_rows.append({**row, "stress_lines": blend_stress})
            ingredients = []
            for stress in blend_stress:
                display = str(stress.get("display", "")).lower()
                collapsed = "pinto beans" if "bean" in display else "cheese"
                ingredients.append(
                    {
                        "line_index": stress["line_index"],
                        "original_display": stress.get("display", ""),
                        "original_item": stress.get("item", ""),
                        "normalized": {
                            "machine_name": collapsed,
                            "product_identity": collapsed,
                        },
                        "role": "consumed",
                        "quantity": {"source_grams": stress.get("grams")},
                        "consumption": {
                            "calculation_status": "CALCULATION_READY",
                            "consumption_policy": "all_input",
                            "consumed_grams": stress.get("grams"),
                        },
                        "components": [],
                        "alternatives": [],
                        "confidence": 0.9,
                    }
                )
            candidate_rows.append({"recipe_id": row["recipe_id"], "ingredients": ingredients})

        findings = validate(source_rows, candidate_rows)
        error_codes = {finding.code for finding in findings if finding.severity == "error"}
        self.assertIn("blend_collapsed_to_single_food", error_codes)
        self.assertIn("bean_mix_proxy_single_bean", error_codes)

    def test_bean_mix_equivalent_alternative_must_not_block(self):
        source_rows = []
        for row in load_jsonl(PACK):
            stresses = [
                stress for stress in row.get("stress_lines", [])
                if stress.get("case") == "true_alternative_bean_mix"
            ]
            if stresses:
                source_rows.append({**row, "stress_lines": stresses})

        self.assertEqual(1, len(source_rows))
        stress = source_rows[0]["stress_lines"][0]
        candidate_rows = [
            {
                "recipe_id": source_rows[0]["recipe_id"],
                "ingredients": [
                    {
                        "line_index": stress["line_index"],
                        "original_display": stress["display"],
                        "original_item": stress["item"],
                        "rewritten_ingredient": "1 bag (about 16 oz) 7 bean mix OR 15 bean mix, rinsed and soaked overnight",
                        "normalized": {
                            "machine_name": "bean mix",
                            "product_identity": "bean mix",
                        },
                        "matchability": {"status": "BLOCKED"},
                        "role": "alternative_group",
                        "quantity": {"source_grams": stress["grams"]},
                        "consumption": {
                            "calculation_status": "BLOCKED",
                            "consumption_policy": "selected_option_required",
                            "consumed_grams": None,
                        },
                        "components": [],
                        "alternatives": [
                            {"normalized": {"machine_name": "7 bean mix"}},
                            {"normalized": {"machine_name": "15 bean mix"}},
                        ],
                    }
                ],
            }
        ]

        findings = validate(source_rows, candidate_rows)
        error_codes = {finding.code for finding in findings if finding.severity == "error"}
        self.assertIn("bean_mix_equivalent_not_selected", error_codes)
        self.assertIn("bean_mix_equivalent_policy_missing", error_codes)


if __name__ == "__main__":
    unittest.main()
