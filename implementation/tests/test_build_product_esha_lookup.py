from __future__ import annotations

import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


IMPLEMENTATION_ROOT = Path(__file__).resolve().parents[1]
if str(IMPLEMENTATION_ROOT) not in sys.path:
    sys.path.insert(0, str(IMPLEMENTATION_ROOT))

import build_product_esha_lookup as lookup  # noqa: E402
import match_esha_to_products as matcher  # noqa: E402


def profile(code: str = "4791") -> matcher.EshaProfile:
    return matcher.EshaProfile(
        code=code,
        description="Water, seltzer",
        norm="water seltzer",
        tokens=("water", "seltzer"),
        family="beverage",
        hard_terms=("water", "seltzer"),
        attrs=(),
        fts_terms=("water", "seltzer"),
        skip_reason="",
    )


class BuildProductEshaLookupTests(unittest.TestCase):
    def test_collect_assignment_rows_uses_direct_retrieval_for_requested_codes(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "products.db"
            sqlite3.connect(db_path).close()

            products = [
                {
                    "gtin_upc": "050428591376",
                    "fdc_id": "1",
                    "description": "ORANGE SELTZER WATER, ORANGE",
                    "brand_owner": "CVS Pharmacy, Inc.",
                    "brand_name": "GOLD EMBLEM",
                    "category": "Water",
                    "ingredients": "Carbonated Water, Natural Flavor",
                    "rank": "1.0",
                },
                {
                    "gtin_upc": "023627362153",
                    "fdc_id": "2",
                    "description": "ORANGE SELTZER, ORANGE",
                    "brand_owner": "Festive Finer Foods",
                    "brand_name": "AVENUE",
                    "category": "Water",
                    "ingredients": "Carbonated Water, Natural Flavor",
                    "rank": "2.0",
                },
                {
                    "gtin_upc": "999",
                    "fdc_id": "3",
                    "description": "ORANGE TONIC WATER",
                    "brand_owner": "Acme",
                    "brand_name": "ACME",
                    "category": "Water",
                    "ingredients": "Carbonated Water, Quinine",
                    "rank": "3.0",
                },
            ]

            def classify(_profile: matcher.EshaProfile, product_row: dict[str, str], _filters: tuple[str, ...] = ()) -> tuple[str, list[str]]:
                if "SELTZER" in product_row["description"]:
                    return "contract_accept", []
                return "contract_reject", ["not_seltzer"]

            with patch.object(lookup, "PRODUCTS_DB", db_path), \
                patch.object(lookup, "load_profiles_by_code", return_value={"4791": profile()}), \
                patch.object(lookup.pack_builder, "query_attempts_for", return_value=[("strict", ("water", "seltzer"))]), \
                patch.object(lookup.pack_builder, "fts_query", return_value="water AND seltzer"), \
                patch.object(lookup.pack_builder, "category_terms_for_profile", return_value=()), \
                patch.object(lookup.pack_builder, "semantic_filters_for_profile", return_value=()), \
                patch.object(lookup.pack_builder, "query_products", return_value=products), \
                patch.object(lookup.pack_builder, "classify_product", side_effect=classify), \
                patch.object(lookup, "pack_files", return_value=[]):
                rows = lookup.collect_assignment_rows(codes={"4791"}, limit_per_code=10, source="auto")

            self.assertEqual(len(rows), 2)
            self.assertEqual(rows[0]["gtin_upc"], "050428591376")
            self.assertEqual(rows[0]["match_reason"], "direct_contract_accept:strict")
            self.assertEqual({row["gtin_upc"] for row in rows}, {"050428591376", "023627362153"})

    def test_collect_assignment_rows_dedupes_across_attempts_before_limit(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "products.db"
            sqlite3.connect(db_path).close()

            duplicate = {
                "gtin_upc": "050428591376",
                "fdc_id": "1",
                "description": "ORANGE SELTZER WATER, ORANGE",
                "brand_owner": "CVS Pharmacy, Inc.",
                "brand_name": "GOLD EMBLEM",
                "category": "Water",
                "ingredients": "Carbonated Water, Natural Flavor",
                "rank": "5.0",
            }
            second = {
                "gtin_upc": "041190067718",
                "fdc_id": "4",
                "description": "ORANGE SELTZER, ORANGE",
                "brand_owner": "Wakefern",
                "brand_name": "SHOPRITE",
                "category": "Water",
                "ingredients": "Carbonated Water, Natural Flavor",
                "rank": "6.0",
            }

            with patch.object(lookup, "PRODUCTS_DB", db_path), \
                patch.object(lookup, "load_profiles_by_code", return_value={"4791": profile()}), \
                patch.object(lookup.pack_builder, "query_attempts_for", return_value=[("strict", ("water", "seltzer")), ("fallback", ("seltzer",))]), \
                patch.object(lookup.pack_builder, "fts_query", side_effect=["water AND seltzer", "seltzer"]), \
                patch.object(lookup.pack_builder, "category_terms_for_profile", return_value=()), \
                patch.object(lookup.pack_builder, "semantic_filters_for_profile", return_value=()), \
                patch.object(lookup.pack_builder, "query_products", side_effect=[[duplicate, second], [duplicate]]), \
                patch.object(lookup.pack_builder, "classify_product", return_value=("contract_accept", [])), \
                patch.object(lookup, "pack_files", return_value=[]):
                rows = lookup.collect_assignment_rows(codes={"4791"}, limit_per_code=5, source="direct")

            self.assertEqual(len(rows), 2)
            self.assertEqual([row["gtin_upc"] for row in rows], ["050428591376", "041190067718"])

    def test_auto_mode_falls_back_to_pack_when_direct_finds_nothing(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "products.db"
            sqlite3.connect(db_path).close()
            pack_path = Path(temp_dir) / "004791_water_seltzer.md"
            pack_path.write_text("# ESHA 4791: Water, seltzer\n", encoding="utf-8")
            parsed_pack = {
                "pack_path": pack_path,
                "esha_code": "4791",
                "esha_description": "Water, seltzer",
                "esha_family": "beverage",
                "required_terms": "water|seltzer",
                "attributes": "",
                "rows": [
                    {
                        "rank": "1",
                        "gtin_upc": "050428591376",
                        "fdc_id": "1",
                        "product_description": "ORANGE SELTZER WATER, ORANGE",
                        "branded_food_category": "Water",
                        "ingredients": "Carbonated Water, Natural Flavor",
                        "signal": "contract_accept",
                        "noise_terms": "",
                    }
                ],
            }

            with patch.object(lookup, "PRODUCTS_DB", db_path), \
                patch.object(lookup, "load_profiles_by_code", return_value={"4791": profile()}), \
                patch.object(lookup.pack_builder, "query_attempts_for", return_value=[("strict", ("water", "seltzer"))]), \
                patch.object(lookup.pack_builder, "fts_query", return_value="water AND seltzer"), \
                patch.object(lookup.pack_builder, "category_terms_for_profile", return_value=()), \
                patch.object(lookup.pack_builder, "semantic_filters_for_profile", return_value=()), \
                patch.object(lookup.pack_builder, "query_products", return_value=[]), \
                patch.object(lookup, "pack_files", return_value=[pack_path]), \
                patch.object(lookup, "parse_pack", return_value=parsed_pack), \
                patch.object(
                    lookup,
                    "fetch_product_details",
                    return_value={
                        "brand_owner": "CVS Pharmacy, Inc.",
                        "brand_name": "GOLD EMBLEM",
                        "branded_food_category": "Water",
                        "product_description": "ORANGE SELTZER WATER, ORANGE",
                    },
                ):
                rows = lookup.collect_assignment_rows(codes={"4791"}, limit_per_code=10, source="auto")

            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["match_reason"], "pack_contract_accept")
            self.assertEqual(rows[0]["gtin_upc"], "050428591376")


if __name__ == "__main__":
    unittest.main()
