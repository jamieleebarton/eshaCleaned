from __future__ import annotations

import sys
import unittest
from pathlib import Path

IMPL = Path(__file__).resolve().parents[1]
if str(IMPL) not in sys.path:
    sys.path.insert(0, str(IMPL))

from build_wrong_assignment_audit import classify_row


ESHA = {
    "36986": "Sauerkraut",
    "14669": "Cream Substitute, flavored, liquid",
    "19141": "Shrimp, cooked",
    "24339": "Coffee, brewed",
    "14480": "Almond Milk, Almond Breeze, original, unsweetened",
    "41953": "Cranberries, fresh",
}


def row(**overrides: str) -> dict[str, str]:
    base = {
        "fdc_id": "1",
        "gtin_upc": "1",
        "product_description": "",
        "branded_food_category": "",
        "brand_owner": "",
        "brand_name": "",
        "best_esha_code": "",
        "best_esha_description": "",
        "best_esha_head": "",
        "assignment_source": "",
        "self_heal_status": "",
        "self_heal_reason": "",
        "product_cluster_id": "",
        "category_lane": "",
        "product_form": "",
        "primary_food": "",
        "title_identity_terms": "",
        "ingredient_core_terms": "",
        "fixy_fndds_code": "",
        "fixy_fndds_description": "",
        "fndds_main_code": "",
        "fndds_main_description": "",
        "wweia_category_code": "",
        "wweia_category_description": "",
        "fixy_product_description": "",
        "fixy_category": "",
        "fixy_match_source": "",
        "candidate_mode": "",
        "candidate_reason": "",
        "surface_alignment_ok": "",
        "surface_missing_terms": "",
        "product_vs_cluster_dominant": "",
        "top_current_esha_codes": "",
        "top_current_esha_descriptions": "",
        "top_product_forms": "",
        "top_categories": "",
        "top_title_terms": "",
        "top_ingredient_terms": "",
        "sample_products": "",
        "fixy_cluster_fix_action": "",
        "fixy_cluster_fix_reason": "",
    }
    base.update(overrides)
    return base


class WrongAssignmentAuditTests(unittest.TestCase):
    def test_sauerkraut_is_not_sour_pickles(self) -> None:
        out = classify_row(
            row(
                product_description="SHREDDED SAUERKRAUT",
                branded_food_category="Pickles, Olives, Peppers & Relishes",
                best_esha_code="13358",
                best_esha_description="Pickles, sour",
                best_esha_head="Pickles",
                fixy_fndds_description="sauerkraut",
            ),
            ESHA,
        )

        self.assertIsNotNone(out)
        self.assertEqual(out["mismatch_bucket"], "same_macro_identity_conflict")
        self.assertEqual(out["candidate_esha_code"], "36986")
        self.assertIn("sauerkraut", out["missing_terms_from_current_esha"])
        self.assertIn("pickle", out["conflicting_terms_in_current_esha"])

    def test_coffee_with_almond_milk_is_not_almond_milk(self) -> None:
        out = classify_row(
            row(
                product_description="CALIFIA FARMS, XX ESPRESSO COLD BREW COFFEE WITH ALMONDMILK",
                branded_food_category="Other Drinks",
                product_form="coffee",
                best_esha_code="16455",
                best_esha_description="Almond Milk, plain",
                best_esha_head="Almond Milk",
                fixy_fndds_description="coffee latte",
            ),
            ESHA,
        )

        self.assertIsNotNone(out)
        self.assertEqual(out["mismatch_bucket"], "component_flavor_conflict")
        self.assertEqual(out["candidate_esha_code"], "24339")
        self.assertIn("coffee", out["missing_terms_from_current_esha"])

    def test_creamer_is_not_almond_milk(self) -> None:
        out = classify_row(
            row(
                product_description="UNSWEETENED ALMONDMILK CREAMER, UNSWEETENED",
                branded_food_category="Milk Additives",
                product_form="creamer",
                best_esha_code="14480",
                best_esha_description="Almond Milk, Almond Breeze, original, unsweetened",
                best_esha_head="Almond Milk",
                fixy_fndds_description="coffee creamer liquid",
            ),
            ESHA,
        )

        self.assertIsNotNone(out)
        self.assertEqual(out["mismatch_bucket"], "form_conflict")
        self.assertEqual(out["candidate_esha_code"], "14669")
        self.assertIn("creamer", out["missing_terms_from_current_esha"])

    def test_corrected_creamer_is_not_flagged_because_almond_is_component(self) -> None:
        out = classify_row(
            row(
                product_description="UNSWEETENED ALMONDMILK CREAMER, UNSWEETENED",
                branded_food_category="Milk Additives",
                product_form="creamer",
                best_esha_code="14669",
                best_esha_description="Cream Substitute, flavored, liquid",
                best_esha_head="Cream Substitute",
                fixy_fndds_description="coffee creamer liquid",
            ),
            ESHA,
        )

        self.assertIsNone(out)

    def test_fixy_seltzer_pair_beats_product_title_almond_milk(self) -> None:
        out = classify_row(
            row(
                product_description="VANILLA ALMONDMILK",
                branded_food_category="Plant Based Milk",
                best_esha_code="16453",
                best_esha_description="Almond Milk, vanilla",
                best_esha_head="Almond Milk",
                fixy_fndds_code="92410251",
                fixy_fndds_description="seltzer water fl",
            ),
            ESHA,
        )

        self.assertIsNotNone(out)
        self.assertEqual(out["mismatch_bucket"], "fixy_pair_cross_macro_conflict")
        self.assertIn("seltzer", out["fixy_identity"])
        self.assertIn("almond milk", out["current_esha_identity"])

    def test_fixy_eggnog_pair_beats_product_title_almond_milk(self) -> None:
        out = classify_row(
            row(
                product_description="NOG ALMONDMILK, NOG",
                branded_food_category="Plant Based Milk",
                best_esha_code="16455",
                best_esha_description="Almond Milk, plain",
                best_esha_head="Almond Milk",
                fixy_fndds_code="11531000",
                fixy_fndds_description="eggnog",
            ),
            ESHA,
        )

        self.assertIsNotNone(out)
        self.assertEqual(out["mismatch_bucket"], "fixy_pair_same_group_conflict")
        self.assertIn("egg nog", out["fixy_identity"])
        self.assertIn("almond milk", out["current_esha_identity"])

    def test_matching_almond_milk_fixy_pair_is_not_flagged(self) -> None:
        out = classify_row(
            row(
                product_description="UNSWEETENED ORIGINAL ALMONDMILK",
                branded_food_category="Plant Based Milk",
                best_esha_code="14480",
                best_esha_description="Almond Milk, Almond Breeze, original, unsweetened",
                best_esha_head="Almond Milk",
                fixy_fndds_code="11350020",
                fixy_fndds_description="almond milk unsweetened",
            ),
            ESHA,
        )

        self.assertIsNone(out)

    def test_fixy_supported_cranberries_are_not_cod_fish(self) -> None:
        out = classify_row(
            row(
                product_description="CAPE COD SELECT, PREMIUM CRANBERRIES",
                branded_food_category="Pre-Packaged Fruit & Vegetables",
                best_esha_code="70223",
                best_esha_description="Fish, cod, fillet, premium, frozen",
                best_esha_head="Fish",
                fixy_fndds_description="cranberries",
                fndds_main_description="Cranberries, raw",
            ),
            ESHA,
        )

        self.assertIsNotNone(out)
        self.assertEqual(out["mismatch_bucket"], "cross_macro_conflict")
        self.assertEqual(out["candidate_esha_code"], "41953")
        self.assertIn("cranberry", out["missing_terms_from_current_esha"])

    def test_shrimp_is_not_cod(self) -> None:
        out = classify_row(
            row(
                product_description="SALAD SHRIMP",
                branded_food_category="Frozen Fish & Seafood",
                best_esha_code="52628",
                best_esha_description="Fish, cod, Pacific, untreated, cooked",
                best_esha_head="Fish",
                fixy_fndds_description="shrimp",
            ),
            ESHA,
        )

        self.assertIsNotNone(out)
        self.assertEqual(out["mismatch_bucket"], "species_or_base_conflict")
        self.assertEqual(out["candidate_esha_code"], "19141")
        self.assertIn("shrimp", out["missing_terms_from_current_esha"])
        self.assertIn("cod", out["conflicting_terms_in_current_esha"])

    def test_unassigned_fixy_backed_identity_gets_existing_leaf_candidate(self) -> None:
        out = classify_row(
            row(
                product_description="PREMIUM CRISP SAUERKRAUT",
                branded_food_category="Pickles, Olives, Peppers & Relishes",
                fixy_fndds_description="sauerkraut",
                fixy_match_source="title_category_bridge",
            ),
            ESHA,
        )

        self.assertIsNotNone(out)
        self.assertEqual(out["mismatch_bucket"], "missing_leaf_confirmed")
        self.assertEqual(out["recommended_action"], "remap_existing_leaf")
        self.assertEqual(out["candidate_esha_code"], "36986")

    def test_matching_cod_assignment_is_not_flagged(self) -> None:
        out = classify_row(
            row(
                product_description="ALASKA SKINLESS, BONELESS COD FILLETS",
                branded_food_category="Frozen Fish & Seafood",
                best_esha_code="70223",
                best_esha_description="Fish, cod, fillet, premium, frozen",
                best_esha_head="Fish",
                fixy_fndds_description="fish cod",
            ),
            ESHA,
        )

        self.assertIsNone(out)


if __name__ == "__main__":
    unittest.main()
