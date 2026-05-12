from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path


REPO = Path("/Users/jamiebarton/Desktop/esha_audit_bundle")
QUEUE_PATH = REPO / "retail_mapper" / "v2" / "build_codex_deepseek_taxonomy_queue.py"
CALLER_PATH = REPO / "retail_mapper" / "v2" / "call_deepseek_codex_taxonomy_review.py"


def load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class CodexDeepSeekTaxonomyReviewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.queue = load_module(QUEUE_PATH, "codex_deepseek_taxonomy_queue")
        cls.caller = load_module(CALLER_PATH, "codex_deepseek_taxonomy_caller")

    def test_bfc_department_mismatch_scores_review_case(self):
        homes = {
            "Ice Cream & Frozen Yogurt": {
                "dominant_department": "Frozen",
                "dominant_department_pct": "0.99",
                "department_status": "strong",
                "dominant_top2": "Frozen > Ice Cream",
                "dominant_top2_pct": "0.8",
                "top2_status": "strong",
                "dominant_top3": "Frozen > Ice Cream",
                "dominant_top3_pct": "0.8",
                "top3_status": "strong",
            }
        }
        row = {
            "fdc_id": "1",
            "title": "VANILLA ICE CREAM SANDWICH",
            "branded_food_category": "Ice Cream & Frozen Yogurt",
            "canonical_path": "Meal > Sandwiches > Sandwich",
        }

        reasons, score, signal = self.queue.row_reason_and_score(
            row,
            homes=homes,
            dept_example_ids=set(),
            path_outlier_signals={},
            ice_cream_residual_ids=set(),
        )

        self.assertIn("bfc_department_mismatch", reasons)
        self.assertIn("bfc_top2_mismatch", reasons)
        self.assertIn("known_lexical_hijack_word", reasons)
        self.assertGreater(score, 1000)
        self.assertEqual("Frozen", signal["expected_department"])

    def test_select_cases_caps_per_bfc_and_keeps_highest_priority(self):
        cases = [
            {"fdc_id": "1", "branded_food_category": "A", "priority_score": 10},
            {"fdc_id": "2", "branded_food_category": "A", "priority_score": 20},
            {"fdc_id": "3", "branded_food_category": "B", "priority_score": 5},
        ]

        selected = self.queue.select_cases(cases, max_cases=10, per_bfc_limit=1)

        self.assertEqual(["2", "3"], [case["fdc_id"] for case in selected])

    def test_high_precision_rejects_pure_top2_mismatch(self):
        case = {
            "fdc_id": "1",
            "branded_food_category": "Broad BFC",
            "reason_codes": ["bfc_top2_mismatch", "bfc_top3_mismatch"],
            "_signal": {"severity_score": 0},
        }

        self.assertFalse(
            self.queue.is_high_precision_case(case, path_severity_threshold=1000)
        )

    def test_high_precision_keeps_department_mismatch_with_audit_example(self):
        case = {
            "fdc_id": "1",
            "branded_food_category": "Alcohol",
            "reason_codes": ["bfc_department_mismatch", "department_misplaced_audit_example"],
            "_signal": {"severity_score": 10},
        }

        self.assertTrue(
            self.queue.is_high_precision_case(case, path_severity_threshold=1000)
        )

    def test_parse_json_object_accepts_fenced_json(self):
        parsed = self.caller.parse_json_object(
            '```json\n{"verdict":"correct","confidence":0.91}\n```'
        )

        self.assertEqual("correct", parsed["verdict"])
        self.assertEqual(0.91, parsed["confidence"])

    def test_validate_decision_flags_bad_schema(self):
        decision = self.caller.validate_decision({"verdict": "maybe", "confidence": "bad"})

        self.assertIn("_schema_error", decision)
        self.assertEqual(0.0, decision["confidence"])


if __name__ == "__main__":
    unittest.main()
