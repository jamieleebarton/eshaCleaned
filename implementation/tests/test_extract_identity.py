from __future__ import annotations

import sys
import unittest
from pathlib import Path

IMPL = Path(__file__).resolve().parents[1]
if str(IMPL) not in sys.path:
    sys.path.insert(0, str(IMPL))

import extract_identity


class ExtractIdentityTests(unittest.TestCase):
    def test_heuristic_keeps_apricot_as_head_not_large(self) -> None:
        record = extract_identity.heuristic_identity(
            entity_type="product",
            entity_id="1",
            text="ROUNDY'S, LARGE APRICOTS",
            category="Wholesome Snacks",
            brand="ROUNDY'S",
            ingredients="Apricots, sulfur dioxide",
        )

        self.assertEqual(record.head_noun, "apricot")
        self.assertNotEqual(record.head_noun, "large")
        self.assertIn(record.form, {"dried_fruit", "dried fruit"})

    def test_heuristic_keeps_biscuit_head_for_biscuit_large(self) -> None:
        record = extract_identity.heuristic_identity(
            entity_type="esha",
            entity_id="16980",
            text="Biscuit, large",
        )

        self.assertEqual(record.head_noun, "biscuit")
        self.assertNotEqual(record.head_noun, "large")


if __name__ == "__main__":
    unittest.main()
