from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
RECIPE_MAPPER = ROOT / "recipe_mapper" / "v1"
if str(RECIPE_MAPPER) not in sys.path:
    sys.path.insert(0, str(RECIPE_MAPPER))

from htc.qty_units import extract_qty_unit  # noqa: E402


class QtyUnitsTests(unittest.TestCase):
    def test_unicode_fraction_slash_extracts_quantity_and_unit(self) -> None:
        cases = [
            ("1⁄2 head lettuce", 0.5, "head"),
            ("3⁄4 cup sugar", 0.75, "cup"),
            ("1 1⁄2 teaspoons salt", 1.5, "tsp"),
            ("1∕4 head cabbage", 0.25, "head"),
        ]
        for display, expected_qty, expected_unit in cases:
            with self.subTest(display=display):
                qty, unit, _ = extract_qty_unit(display)
                self.assertIsNotNone(qty)
                self.assertAlmostEqual(qty or 0, expected_qty)
                self.assertEqual(unit, expected_unit)


if __name__ == "__main__":
    unittest.main()
