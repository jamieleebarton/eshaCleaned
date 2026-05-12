import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import rft_clean_canonical as cleaner  # noqa: E402


class RftCleanCanonicalMilkTests(unittest.TestCase):
    def test_milk_subtype_loss_detects_one_percent_to_generic_milk(self) -> None:
        desc_maps = {
            "esha": {
                "4": "Milk, 1%, with added vitamin A & D",
                "24340": "Milk",
            }
        }

        lost = cleaner._milk_subtype_loss(
            "esha",
            "1% milk",
            "4",
            "Milk, lowfat, fluid, 1% milkfat",
            "24340",
            "Milk",
            desc_maps,
        )

        self.assertEqual(lost, "one_percent")

    def test_milk_subtype_loss_allows_same_subtype(self) -> None:
        desc_maps = {
            "esha": {
                "6": "Milk, nonfat/skim, with added vitamin A & D",
                "20969": "Milk, skim, calcium fortified",
            }
        }

        lost = cleaner._milk_subtype_loss(
            "esha",
            "fat free milk",
            "6",
            "Milk, nonfat/skim, with added vitamin A & D",
            "20969",
            "Milk, skim, calcium fortified",
            desc_maps,
        )

        self.assertEqual(lost, "")

    def test_plain_oat_milk_rejects_puerto_rican_variant(self) -> None:
        extra = cleaner._milk_unasked_variant("oat milk", "Oat Milk, Puerto Rican")

        self.assertEqual(extra, "puerto,rican")

    def test_matching_oat_milk_variant_is_not_extra(self) -> None:
        extra = cleaner._milk_unasked_variant("oat milk puerto rican", "Oat Milk, Puerto Rican")

        self.assertEqual(extra, "")


if __name__ == "__main__":
    unittest.main()
