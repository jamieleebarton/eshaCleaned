from __future__ import annotations

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[2]
IMPLEMENTATION_ROOT = ROOT / "implementation"
if str(IMPLEMENTATION_ROOT) not in sys.path:
    sys.path.insert(0, str(IMPLEMENTATION_ROOT))

import build_esha_code_query_packs as packs
import build_retail_query_rewrite_plan as rewrite_plan


class RetailQueryRewritePlanTests(unittest.TestCase):
    def test_term_roles_for_beverage_aspartame_terms(self) -> None:
        original_cache = packs._QUERY_TERM_DROP_CANDIDATES_CACHE
        try:
            packs._QUERY_TERM_DROP_CANDIDATES_CACHE = {}
            profile = SimpleNamespace(code="151", family="beverage", attrs=("dry",))
            roles = packs.term_roles_for(profile, ("chocolate", "reduced", "calorie", "aspartame", "wtr"))
            self.assertEqual(roles["aspartame"], "ingredient_only")
            self.assertEqual(roles["wtr"], "process_only")
            self.assertEqual(roles["reduced"], "query_optional_or_claim_translation")
            self.assertEqual(roles["calorie"], "query_optional_or_claim_translation")
        finally:
            packs._QUERY_TERM_DROP_CANDIDATES_CACHE = original_cache

    def test_recommended_category_terms_for_fresh_strawberries(self) -> None:
        profile = SimpleNamespace(code="25760", family="fruit", attrs=("fresh",))
        category_terms = packs.recommended_category_terms_for(profile, ("fresh", "strawberries"))
        self.assertEqual(category_terms, ("pre-packaged", "produce"))

    def test_semantic_filter_failures_rejects_frozen_for_fresh_fruit(self) -> None:
        profile = SimpleNamespace(family="fruit", attrs=("fresh",), hard_terms=("strawberry",))
        product = {
            "description": "FRESH FROZEN WHOLE STRAWBERRIES",
            "category": "Frozen Fruit & Fruit Juice Concentrates",
            "ingredients": "Strawberries.",
        }
        failures = packs.semantic_filter_failures(profile, product, ("fresh",))
        self.assertIn("fresh", failures)

    def test_semantic_filter_single_commodity_rejects_mixed_fruit(self) -> None:
        profile = SimpleNamespace(family="fruit", attrs=("fresh",), hard_terms=("strawberry",))
        product = {
            "description": "STRAWBERRIES & BLUEBERRIES",
            "category": "Pre-Packaged Fruit & Vegetables",
            "ingredients": "Strawberries, Blueberries",
        }
        failures = packs.semantic_filter_failures(profile, product, ("single_commodity",))
        self.assertIn("single_commodity", failures)

    def test_semantic_filter_produce_proxy_peel_rejects_salad_kit(self) -> None:
        profile = SimpleNamespace(family="fruit", attrs=("fresh",), hard_terms=("lemon", "peel"))
        product = {
            "description": "LEMON PARMESAN CHOPPED SALAD KIT",
            "category": "Pre-Packaged Fruit & Vegetables",
            "ingredients": "Lettuce, Lemon Juice Concentrate, Lemon Peel",
        }
        failures = packs.semantic_filter_failures(profile, product, ("produce_proxy_peel",))
        self.assertIn("produce_proxy_peel", failures)

    def test_planned_query_attempt_only_uses_strong_rows(self) -> None:
        original_cache = packs._RETAIL_QUERY_REWRITE_PLAN_CACHE
        try:
            profile = SimpleNamespace(code="25760")
            packs._RETAIL_QUERY_REWRITE_PLAN_CACHE = {
                "25760": {
                    "exactness_status": "strong",
                    "query_terms_after": "strawberries",
                }
            }
            self.assertEqual(packs.planned_query_attempt_for(profile), ("rewrite_plan", ("strawberries",)))
            packs._RETAIL_QUERY_REWRITE_PLAN_CACHE = {
                "25760": {
                    "exactness_status": "uncertain",
                    "query_terms_after": "strawberries",
                }
            }
            self.assertIsNone(packs.planned_query_attempt_for(profile))
        finally:
            packs._RETAIL_QUERY_REWRITE_PLAN_CACHE = original_cache

    def test_category_terms_for_profile_uses_strong_plan_and_falls_back_for_other_statuses(self) -> None:
        original_cache = packs._RETAIL_QUERY_REWRITE_PLAN_CACHE
        try:
            profile = SimpleNamespace(code="25760")
            packs._RETAIL_QUERY_REWRITE_PLAN_CACHE = {
                "25760": {
                    "exactness_status": "strong",
                    "category_terms_after": "pre-packaged | produce",
                }
            }
            self.assertEqual(packs.category_terms_for_profile(profile), ("pre-packaged", "produce"))
            packs._RETAIL_QUERY_REWRITE_PLAN_CACHE = {
                "25760": {
                    "exactness_status": "uncertain",
                    "category_terms_after": "pre-packaged | produce",
                }
            }
            self.assertEqual(packs.category_terms_for_profile(profile), packs.PRODUCT_CATEGORY_FILTERS_BY_CODE.get("25760", ()))
            profile = SimpleNamespace(code="9558")
            packs._RETAIL_QUERY_REWRITE_PLAN_CACHE = {
                "9558": {
                    "exactness_status": "unresolved",
                    "category_terms_after": "frozen prepared | prepared side",
                }
            }
            self.assertEqual(packs.category_terms_for_profile(profile), ("sauce", "condiment", "dip"))
        finally:
            packs._RETAIL_QUERY_REWRITE_PLAN_CACHE = original_cache

    def test_unresolved_metrics_emits_clean_zero_row(self) -> None:
        profile = SimpleNamespace(code="22", description="Milk, human breast", family="nonfood")
        row = rewrite_plan.select_row(
            profile,
            {"selected_attempt_before": "strict", "query_before": ""},
            rewrite_plan.unresolved_metrics(),
            (),
            (),
            (),
            {},
            {},
        )
        self.assertEqual(row["recommended_attempt"], "no_viable_query")
        self.assertEqual(row["exactness_status"], "unresolved")
        self.assertEqual(row["reason"], "clean_zero_preferred")
        self.assertEqual(row["query_after"], "")


if __name__ == "__main__":
    unittest.main()
