"""Regression test for the wrong-class pick patterns surfaced in the
2026-05-11 recipe-price audit.

For each (recipe_concept_fragment, banned_sku_fragment) pair, assert no
recipe-side concept_key whose path matches the fragment resolves to a
priced concept whose package pool contains the banned fragment.

Reads planner/data/concept_resolution.json and concept_index.json — the
authoritative artifacts emitted by the contract-ordered pipeline
(rebuild_pricing_pipeline.py). No planner run required.
"""

import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CR = ROOT / "planner" / "data" / "concept_resolution.json"
CI = ROOT / "planner" / "data" / "concept_index.json"

BANNED_PAIRS = [
    ("Produce > Vegetables > Avocado",          "Grape Leaves"),
    ("Produce > Vegetables > Baby Carrots",     "Peas"),
    ("Dairy > Cheese > Cheddar",                "Snack Stick"),
    ("Dairy > Cheese > Cheddar",                "String Cheese"),
    ("Pantry > Oil > Vegetable Oil",            "Vegetable Oil Stick"),
    ("Pantry > Oil > Vegetable Oil",            "Margarine"),
    ("Pantry > Sweeteners > Sugar > Brown",     "Agave"),
    ("Pantry > Spices & Seasonings > Oregano",  "Bay Leaves"),
    ("Pantry > Spices & Seasonings > Cumin",    "Bay Leaves"),
    ("Dairy > Cream",                           "Finishing Sugar"),
    ("Meat & Seafood > Bacon",                  "Veggie"),
    ("Meat & Seafood > Bacon",                  "MorningStar"),
    ("Meat & Seafood > Bacon",                  "Meatless"),
    ("Produce > Fruit > Limes",                 "Citrus Splash"),
    ("Frozen > Vegetables > Pierogies",         "Mashed Potatoes"),
    ("Pantry > Sauces & Salsas > Hot Pepper",   "Hollandaise"),
]


class KnownMisroutesStayFixedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        if not CR.exists() or not CI.exists():
            raise unittest.SkipTest(
                f"Required artifacts missing — run "
                f"planner/scripts/rebuild_pricing_pipeline.py"
            )
        cls.cr = json.loads(CR.read_text())
        cls.ci = json.loads(CI.read_text())

    def test_no_banned_resolution(self) -> None:
        violations: list[str] = []
        for concept_frag, sku_frag in BANNED_PAIRS:
            cf = concept_frag.lower()
            sf = sku_frag.lower()
            for rk, res in self.cr.items():
                if cf not in rk.lower():
                    continue
                pk = res.get("priced_key")
                if not pk:
                    continue
                priced = self.ci.get(pk)
                if not priced:
                    continue
                cp_priced = (priced.get("canonical_path") or "").lower()
                pkg_blob = " || ".join(
                    p.get("name", "") for p in priced.get("packages", [])
                ).lower()
                if sf in cp_priced or sf in pkg_blob:
                    violations.append(
                        f"  '{concept_frag}' → '{sku_frag}' "
                        f"recipe_ck='{rk}' "
                        f"priced_ck='{pk}' tier={res.get('tier')}"
                    )
                    break
        if violations:
            self.fail(
                "Banned wrong-class resolutions are back in concept_resolution.json:\n"
                + "\n".join(violations)
            )


if __name__ == "__main__":
    unittest.main()
