from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

IMPL = Path(__file__).resolve().parents[1]
if str(IMPL) not in sys.path:
    sys.path.insert(0, str(IMPL))

import build_typed_identity_match as typed_match


def write_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row) + "\n")


class BuildTypedIdentityMatchTests(unittest.TestCase):
    def test_typed_gate_does_not_score_apricot_against_biscuit(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            product_path = root / "products.jsonl"
            esha_path = root / "esha.jsonl"
            out_path = root / "map.csv"

            write_jsonl(
                product_path,
                [
                    {
                        "entity_type": "product",
                        "entity_id": "2289461",
                        "text": "ROUNDY'S, LARGE APRICOTS",
                        "category": "Wholesome Snacks",
                        "brand": "ROUNDY'S",
                        "head_noun": "apricot",
                        "form": "dried_fruit",
                        "modifiers": ["large"],
                        "prep_state": "dried",
                        "sweetness": "",
                        "fat_level": "",
                        "foodex2_code": "",
                        "foodex2_name": "",
                        "confidence": 0.9,
                        "extractor": "test",
                        "notes": "",
                    }
                ],
            )
            write_jsonl(
                esha_path,
                [
                    {
                        "entity_type": "esha",
                        "entity_id": "16980",
                        "text": "Biscuit, large",
                        "category": "",
                        "brand": "",
                        "head_noun": "biscuit",
                        "form": "biscuit",
                        "modifiers": ["large"],
                        "prep_state": "",
                        "sweetness": "",
                        "fat_level": "",
                        "foodex2_code": "",
                        "foodex2_name": "",
                        "confidence": 0.9,
                        "extractor": "test",
                        "notes": "",
                    }
                ],
            )

            products = typed_match.load_identity_jsonl(product_path, "product")
            eshas = typed_match.load_identity_jsonl(esha_path, "esha")
            summary = typed_match.build_map(products, eshas, out_path)

            self.assertEqual(summary["assigned"], 0)
            self.assertEqual(summary["unassigned"], 1)


if __name__ == "__main__":
    unittest.main()
