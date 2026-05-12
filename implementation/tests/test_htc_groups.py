from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
PLANNER = ROOT / "planner"
if str(PLANNER) not in sys.path:
    sys.path.insert(0, str(PLANNER))

from htc_groups import htc_from_concept_key, protein_source, shelf_days


class HtcGroupsTests(unittest.TestCase):
    def test_two_part_concept_key_extracts_htc(self) -> None:
        self.assertEqual(
            htc_from_concept_key("Meat & Seafood > Poultry > Chicken Breast|3001000K"),
            "3001000K",
        )

    def test_protein_source_accepts_concept_key(self) -> None:
        self.assertEqual(
            protein_source("Meat & Seafood > Poultry > Chicken|3000000A"),
            2,
        )
        self.assertEqual(protein_source("Meat & Seafood > Beef > Ground Beef|2001002A"), 0)
        self.assertEqual(protein_source("Meat & Seafood > Pork > Pork Shoulder|2106100M"), 1)
        self.assertEqual(protein_source("Meat & Seafood > Bacon|24020000"), 1)
        self.assertEqual(protein_source("Meat & Seafood > Lamb|2201000B"), 0)
        self.assertEqual(
            protein_source("Dairy > Eggs|5000000A"),
            4,
        )
        self.assertEqual(
            protein_source("Pantry > Beans > Black Beans|9000000A"),
            5,
        )

    def test_perishability_accepts_concept_key(self) -> None:
        self.assertEqual(shelf_days("Meat & Seafood > Poultry > Chicken|3000000A"), 4)
        self.assertEqual(shelf_days("Produce > Vegetables > Lettuce|6000000A"), 10)


if __name__ == "__main__":
    unittest.main()
