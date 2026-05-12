import csv
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from build_retail_canonical_surface_bridge import build_bridge  # noqa: E402


class RetailCanonicalSurfaceBridgeTests(unittest.TestCase):
    def test_api_cache_search_terms_resolve_to_canonical_surface_rows(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            surface_csv = tmp / "surface.csv"
            api_cache_csv = tmp / "api.csv"
            out_csv = tmp / "bridge.csv"
            out_summary = tmp / "summary.json"

            with surface_csv.open("w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(
                    handle,
                    fieldnames=[
                        "canonical_surface",
                        "canonical_normalized",
                        "canonical_shopping_item",
                        "record_type",
                        "product_query",
                        "sr28_code",
                        "esha_code",
                        "hestia_product_proxy_code",
                    ],
                )
                writer.writeheader()
                writer.writerow(
                    {
                        "canonical_surface": "test sauce",
                        "canonical_normalized": "test sauce",
                        "canonical_shopping_item": "test sauce",
                        "record_type": "ingredient",
                        "product_query": "test sauce",
                        "sr28_code": "123",
                        "esha_code": "999",
                        "hestia_product_proxy_code": "HXP-PRODUCT-TEST-SAUCE",
                    }
                )

            with api_cache_csv.open("w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(handle, fieldnames=["source", "upc", "name", "grams", "cents", "search_term"])
                writer.writeheader()
                writer.writerow(
                    {
                        "source": "walmart",
                        "upc": "111",
                        "name": "Test Sauce",
                        "grams": "100",
                        "cents": "299",
                        "search_term": "test sauce",
                    }
                )
                writer.writerow(
                    {
                        "source": "walmart",
                        "upc": "222",
                        "name": "Missing Food",
                        "grams": "100",
                        "cents": "199",
                        "search_term": "missing food",
                    }
                )

            summary = build_bridge(
                surface_csv=surface_csv,
                api_cache_csv=api_cache_csv,
                out_csv=out_csv,
                out_summary=out_summary,
            )
            self.assertEqual(summary["rows"], 2)
            self.assertEqual(summary["assigned"], 1)

            with out_csv.open(newline="", encoding="utf-8") as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual(rows[0]["canonical_match_status"], "assigned")
            self.assertEqual(rows[0]["canonical_surface"], "test sauce")
            self.assertEqual(rows[0]["esha_code"], "999")
            self.assertEqual(rows[0]["hestia_product_proxy_code"], "HXP-PRODUCT-TEST-SAUCE")
            self.assertEqual(rows[1]["canonical_match_status"], "unmatched")


if __name__ == "__main__":
    unittest.main()
