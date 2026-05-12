from __future__ import annotations

import sys
import unittest
from pathlib import Path


IMPLEMENTATION = Path(__file__).resolve().parents[1]
if str(IMPLEMENTATION) not in sys.path:
    sys.path.insert(0, str(IMPLEMENTATION))

from sparse_cascade_planner.pricing_guard import (  # noqa: E402
    assert_no_default_priced_ingredients,
    unpriced_ingredient_keys,
)


class FakeIngredientIndex:
    num_ingredients = 3
    idx_to_fpid = {0: "ESHA:1", 1: "SR28:2", 2: "ESHA:3"}


class FakePackageIndex:
    packages_by_fndds = {"ESHA:1": [(1.0, 100.0)], "ESHA:3": [(2.0, 200.0)]}


class PricingGuardTests(unittest.TestCase):
    def test_finds_tensor_keys_missing_store_packages(self) -> None:
        self.assertEqual(unpriced_ingredient_keys(FakeIngredientIndex(), FakePackageIndex()), ["SR28:2"])

    def test_refuses_default_priced_tensor_keys(self) -> None:
        with self.assertRaisesRegex(RuntimeError, r"Refusing to use PackageIndex's \$3/kg default"):
            assert_no_default_priced_ingredients(
                FakeIngredientIndex(),
                FakePackageIndex(),
                context="test",
            )


if __name__ == "__main__":
    unittest.main()
