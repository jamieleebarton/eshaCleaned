import csv
import tempfile
import unittest
from pathlib import Path

from implementation.concept_candidate_miner import (
    build_miss_index,
    group_by_base,
    join_miss_counts,
    run_miner,
)

FIXTURE_DIR = Path(__file__).parent / "fixtures"


class TestGroupByBase(unittest.TestCase):
    def test_groups_chips_together(self):
        rows = [
            {"description": "Potato chips, plain", "wweia_code": "5002"},
            {"description": "Potato chips, barbecue flavored", "wweia_code": "5002"},
            {"description": "Ice creams, vanilla", "wweia_code": "5802"},
        ]
        groups = group_by_base(rows)
        self.assertIn("potato chips", groups)
        self.assertEqual(len(groups["potato chips"]), 2)
        self.assertIn("ice creams", groups)


class TestJoinMissCounts(unittest.TestCase):
    def test_recipe_count_attached(self):
        miss_rows = [
            {"normalized_line": "sour cream and onion potato chips", "recipe_count": "42"},
            {"normalized_line": "bbq potato chips", "recipe_count": "15"},
        ]
        idx = build_miss_index(miss_rows, {"potato chips"})
        count = join_miss_counts(
            base="potato chips",
            modifiers=["sour cream and onion"],
            miss_index=idx,
        )
        self.assertEqual(count, 42)

    def test_no_match_returns_zero(self):
        miss_rows = [{"normalized_line": "bbq potato chips", "recipe_count": "15"}]
        idx = build_miss_index(miss_rows, {"potato chips"})
        count = join_miss_counts(
            base="potato chips",
            modifiers=["salt and vinegar"],
            miss_index=idx,
        )
        self.assertEqual(count, 0)


class TestBuildMissIndex(unittest.TestCase):
    def test_substring_match_into_buckets(self):
        rows = [
            {"normalized_line": "plain potato chips"},
            {"normalized_line": "nacho cheese flavored tortilla chips"},
            {"normalized_line": "vanilla ice cream softened slightly"},
        ]
        idx = build_miss_index(rows, {"potato chips", "ice cream", "tortilla chips"})
        self.assertEqual(len(idx["potato chips"]), 1)
        self.assertEqual(len(idx["ice cream"]), 1)
        self.assertEqual(len(idx["tortilla chips"]), 1)


class TestVariantFromModifiers(unittest.TestCase):
    def test_joins_non_form_modifiers_sorted(self):
        from implementation.concept_candidate_miner import _variant_from_modifiers
        self.assertEqual(
            _variant_from_modifiers(["chocolate", "frozen", "nonfat milk"], None),
            "chocolate frozen nonfat milk",
        )

    def test_excludes_form_from_variant(self):
        from implementation.concept_candidate_miner import _variant_from_modifiers
        self.assertEqual(
            _variant_from_modifiers(["ground", "organic"], "ground"),
            "organic",
        )


class TestRunMiner(unittest.TestCase):
    def test_pipeline_emits_proposals_and_quarantines_brands(self):
        with tempfile.TemporaryDirectory() as td:
            outdir = Path(td)
            run_miner(
                fndds_csv=FIXTURE_DIR / "fndds_sample.csv",
                misses_csv=FIXTURE_DIR / "misses_sample.csv",
                out_dir=outdir,
                target_wweia={"5002", "5802"},
            )
            proposed = list(csv.DictReader(open(outdir / "proposed_concepts.csv")))
            chip_rows = [r for r in proposed if r["base"] == "potato chips"]
            self.assertGreaterEqual(len(chip_rows), 3)
            self.assertFalse(any("sandwich" in r["raw_description"].lower() for r in proposed))
            quar = list(csv.DictReader(open(outdir / "quarantined_rows.csv")))
            self.assertTrue(any("BREYERS" in r["raw_description"] for r in quar))
            sco = next(r for r in chip_rows if "sour cream and onion" in r["modifiers"])
            self.assertIn("barbecue", sco["forbidden_tokens"])
            self.assertIn("cheese", sco["forbidden_tokens"])
            self.assertEqual(int(sco["recipe_miss_count"]), 42)
            rules = list(csv.DictReader(open(outdir / "proposed_normalization_rules.csv")))
            self.assertTrue(any("sour cream and onion" in r["input_surface"] for r in rules))
            contracts = list(csv.DictReader(open(outdir / "proposed_product_contracts.csv")))
            sco_c = next(c for c in contracts if "sour cream and onion" in c["concept_keys"])
            self.assertIn("sour cream and onion", sco_c["required_all"])


class TestTargetWweiaCategories(unittest.TestCase):
    def test_beans_included(self):
        from implementation.concept_candidate_miner import TARGET_WWEIA_CATEGORIES
        self.assertIn("2802", TARGET_WWEIA_CATEGORIES)

    def test_string_beans_included(self):
        from implementation.concept_candidate_miner import TARGET_WWEIA_CATEGORIES
        self.assertIn("6412", TARGET_WWEIA_CATEGORIES)

    def test_dairy_drinks_included(self):
        # Note: user's handoff spec listed 1602 for "Milk shakes and other dairy
        # drinks", but FNDDS WWEIA 1602 is actually Cheese. The correct code for
        # milk shakes / dairy drinks in this FNDDS vintage is 1402. Using 1402
        # preserves the user's stated intent (include dairy drinks) rather than
        # pulling in 61 unrelated cheese rows.
        from implementation.concept_candidate_miner import TARGET_WWEIA_CATEGORIES
        self.assertIn("1402", TARGET_WWEIA_CATEGORIES)


if __name__ == "__main__":
    unittest.main()
