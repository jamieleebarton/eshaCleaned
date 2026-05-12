import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "implementation"))

from nebius_contract_patch_builder import auto_relax_spec, build_patch, extract_spec  # noqa: E402


def _packet(rows):
    return {"product_search": {"rows": rows}}


def _final(spec):
    return {"decision": "tighten_current_contract", "structured_contract": spec}


class AutoRelaxSpecTest(unittest.TestCase):
    def test_drops_ingredient_term_absent_from_accepted_gtin(self):
        packet = _packet([
            {
                "gtin_upc": "111",
                "description": "Sliced Apples for Pies",
                "category": "Canned Fruit",
                "ingredients": "Apples, Water",
            }
        ])
        final = _final({
            "esha_code": "49691",
            "esha_description": "Topping, dessert, apple pie filling",
            "allowed_categories": ["Canned Fruit"],
            "required_description_terms": ["apple"],
            "required_ingredient_terms": ["apple", "sugar", "cornstarch"],
            "accepted_gtins": ["111"],
            "rejected_gtins": [],
        })
        spec = extract_spec(packet, final)
        relaxed = auto_relax_spec(packet, spec)
        relaxed_values = {r["value"] for r in relaxed}
        self.assertEqual(relaxed_values, {"sugar", "cornstarch"})
        self.assertEqual(spec["required_ingredient_terms"], ["apple"])

    def test_keeps_terms_present_across_all_accepted(self):
        packet = _packet([
            {"gtin_upc": "1", "description": "Apple Pie Filling", "category": "Desserts", "ingredients": "Apples, Sugar"},
            {"gtin_upc": "2", "description": "Apple Pie Topping", "category": "Desserts", "ingredients": "Apples, Sugar, Cinnamon"},
        ])
        final = _final({
            "esha_code": "49691",
            "allowed_categories": ["Desserts"],
            "required_description_terms": ["apple"],
            "required_ingredient_terms": ["apple", "sugar"],
            "accepted_gtins": ["1", "2"],
            "rejected_gtins": [],
        })
        spec = extract_spec(packet, final)
        relaxed = auto_relax_spec(packet, spec)
        self.assertEqual(relaxed, [])
        self.assertEqual(spec["required_ingredient_terms"], ["apple", "sugar"])

    def test_build_patch_flips_from_semantic_failure_to_built(self):
        packet = _packet([
            {
                "gtin_upc": "111",
                "description": "Sliced Apples for Pies",
                "category": "Canned Fruit",
                "ingredients": "Apples, Water",
            }
        ])
        final = _final({
            "esha_code": "49691",
            "esha_description": "Topping, dessert, apple pie filling",
            "allowed_categories": ["Canned Fruit"],
            "required_description_terms": ["apple"],
            "required_ingredient_terms": ["apple", "sugar", "cornstarch"],
            "accepted_gtins": ["111"],
            "rejected_gtins": [],
        })
        built = build_patch(packet, final)
        self.assertEqual(built["status"], "patch_built")
        self.assertTrue(built["validation"]["ok"])
        self.assertEqual(
            {r["value"] for r in built["auto_relaxed_terms"]},
            {"sugar", "cornstarch"},
        )

    def test_all_terms_pruned_yields_semantic_failure(self):
        packet = _packet([
            {"gtin_upc": "111", "description": "Mystery Product", "category": "Canned Fruit", "ingredients": "Water"}
        ])
        final = _final({
            "esha_code": "49691",
            "allowed_categories": ["Canned Fruit"],
            "required_description_terms": ["apple", "pie"],
            "required_ingredient_terms": ["sugar"],
            "accepted_gtins": ["111"],
            "rejected_gtins": [],
        })
        built = build_patch(packet, final)
        self.assertEqual(built["status"], "semantic_validation_failed")
        self.assertIsNone(built["patch"])


if __name__ == "__main__":
    unittest.main()
