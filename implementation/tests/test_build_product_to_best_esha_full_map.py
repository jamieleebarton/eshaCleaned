from __future__ import annotations

import csv
import json
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

IMPL = Path(__file__).resolve().parents[1]
if str(IMPL) not in sys.path:
    sys.path.insert(0, str(IMPL))

import build_product_to_best_esha_full_map as full_map


class BuildProductToBestEshaFullMapTests(unittest.TestCase):
    def test_preserves_legacy_and_falls_back(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            out_dir = root / "output"
            out_dir.mkdir(parents=True)
            products_db = root / "master_products.db"
            esha_csv = root / "esha.csv"
            aggregation_csv = root / "agg.csv"
            legacy_csv = root / "legacy.csv"
            out_csv = out_dir / "full.csv"
            out_summary = out_dir / "full.json"

            con = sqlite3.connect(products_db)
            try:
                con.execute(
                    "create table products (gtin_upc text, fdc_id text, description text, brand_owner text, brand_name text, branded_food_category text)"
                )
                con.execute(
                    "insert into products values "
                    "('111','1','GOAT CHEESE','Owner','Brand','Cheese'),"
                    "('222','2','PEACH SPARKLING WATER','Owner','Brand','Water')"
                )
                con.commit()
            finally:
                con.close()

            esha_csv.write_text(
                "\n".join(
                    [
                        "EshaCode,Description",
                        "1078,\"Cheese, goat, hard\"",
                        "37282,\"Drink, flavored water, spark\"",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            aggregation_csv.write_text(
                "\n".join(
                    [
                        "esha_code,description,family,query,distinct_category_count,category,category_count,signal,sample_row_count,sample_titles,sample_gtins,pack_path",
                        "1078,\"Cheese, goat, hard\",cheese,\"goat cheese\",1,Cheese,50,in_scope_category,1,,,x",
                        "37282,\"Drink, flavored water, spark\",beverage,\"sparkling water\",1,Water,50,in_scope_category,1,,,x",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            legacy_csv.write_text(
                "\n".join(
                    [
                        "gtin_upc,product_description,branded_food_category,brand_owner,best_esha_code,best_esha_description,score,n_candidates",
                        "111,GOAT CHEESE,Cheese,Owner,1078,\"Cheese, goat, hard\",1.0,4",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            with patch.object(full_map, "ROOT", root), patch.object(full_map, "PRODUCTS_DB", products_db), patch.object(full_map, "ESHA_CSV", esha_csv), patch.object(
                full_map, "AGGREGATION_CSV", aggregation_csv
            ), patch.object(full_map, "LEGACY_BEST_MAP_CSV", legacy_csv), patch.object(full_map, "OUT_CSV", out_csv), patch.object(
                full_map, "OUT_SUMMARY", out_summary
            ), patch.object(full_map, "OUT_DIR", out_dir):
                summary = full_map.build_full_map()

            self.assertEqual(summary["products"], 2)
            self.assertEqual(summary["assigned_from_legacy"], 1)
            self.assertEqual(summary["assigned_from_fallback"], 1)
            with out_csv.open(newline="", encoding="utf-8") as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual(rows[0]["best_esha_code"], "1078")
            self.assertEqual(rows[0]["assignment_source"], "legacy_best_map")
            self.assertEqual(rows[1]["best_esha_code"], "37282")
            self.assertTrue(rows[1]["assignment_source"].startswith("fallback_"))
            payload = json.loads(out_summary.read_text(encoding="utf-8"))
            self.assertEqual(payload["products"], 2)

    def test_rejects_legacy_generic_match_without_identity_overlap(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            out_dir = root / "output"
            out_dir.mkdir(parents=True)
            products_db = root / "master_products.db"
            esha_csv = root / "esha.csv"
            aggregation_csv = root / "agg.csv"
            legacy_csv = root / "legacy.csv"
            fix_queue_csv = root / "fix.csv"
            out_csv = out_dir / "full.csv"
            out_summary = out_dir / "full.json"

            con = sqlite3.connect(products_db)
            try:
                con.execute(
                    "create table products (gtin_upc text, fdc_id text, description text, brand_owner text, brand_name text, branded_food_category text)"
                )
                con.execute(
                    "insert into products values ('111','1','HABANERO PEPPER JELLY','Owner','Brand','Jam, Jelly & Fruit Spreads')"
                )
                con.commit()
            finally:
                con.close()

            esha_csv.write_text(
                "\n".join(
                    [
                        "EshaCode,Description",
                        "46801,\"Applesauce, original\"",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            aggregation_csv.write_text(
                "\n".join(
                    [
                        "esha_code,description,family,query,distinct_category_count,category,category_count,signal,sample_row_count,sample_titles,sample_gtins,pack_path",
                        "46801,\"Applesauce, original\",fruit,\"(original OR originals)\",30,Jam, Jelly & Fruit Spreads,50,in_scope_category,1,,,x",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            legacy_csv.write_text(
                "\n".join(
                    [
                        "gtin_upc,product_description,branded_food_category,brand_owner,best_esha_code,best_esha_description,score,n_candidates",
                        "111,HABANERO PEPPER JELLY,Jam, Jelly & Fruit Spreads,Owner,46801,\"Applesauce, original\",0.0,1",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            fix_queue_csv.write_text(
                "\n".join(
                    [
                        "esha_code,needs_fix,query,dominant_category,dominant_share",
                        "46801,1,\"(original OR originals)\",\"Jam, Jelly & Fruit Spreads\",0.10",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            with patch.object(full_map, "ROOT", root), patch.object(full_map, "PRODUCTS_DB", products_db), patch.object(full_map, "ESHA_CSV", esha_csv), patch.object(
                full_map, "AGGREGATION_CSV", aggregation_csv
            ), patch.object(full_map, "LEGACY_BEST_MAP_CSV", legacy_csv), patch.object(full_map, "FIX_QUEUE_CSV", fix_queue_csv), patch.object(
                full_map, "OUT_CSV", out_csv
            ), patch.object(full_map, "OUT_SUMMARY", out_summary), patch.object(full_map, "OUT_DIR", out_dir):
                summary = full_map.build_full_map()

            with out_csv.open(newline="", encoding="utf-8") as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual(summary["unassigned"], 1)
            self.assertEqual(rows[0]["best_esha_code"], "")
            self.assertTrue(rows[0]["assignment_source"].endswith("_no_match"))

    def test_rejects_weak_form_overlap_without_identity(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            out_dir = root / "output"
            out_dir.mkdir(parents=True)
            products_db = root / "master_products.db"
            esha_csv = root / "esha.csv"
            aggregation_csv = root / "agg.csv"
            legacy_csv = root / "legacy.csv"
            out_csv = out_dir / "full.csv"
            out_summary = out_dir / "full.json"

            con = sqlite3.connect(products_db)
            try:
                con.execute(
                    "create table products (gtin_upc text, fdc_id text, description text, brand_owner text, brand_name text, branded_food_category text)"
                )
                con.execute(
                    "insert into products values ('111','1','MUSHROOM PIECES & STEMS','Owner','Brand','Canned Vegetables')"
                )
                con.commit()
            finally:
                con.close()

            esha_csv.write_text(
                "\n".join(
                    [
                        "EshaCode,Description",
                        "7867,\"Artichoke, hearts, canned, pieces\"",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            aggregation_csv.write_text(
                "\n".join(
                    [
                        "esha_code,description,family,query,distinct_category_count,category,category_count,signal,sample_row_count,sample_titles,sample_gtins,pack_path",
                        "7867,\"Artichoke, hearts, canned, pieces\",vegetable,\"artichoke hearts\",1,Canned Vegetables,50,in_scope_category,1,,,x",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            legacy_csv.write_text("gtin_upc,product_description,branded_food_category,brand_owner,best_esha_code,best_esha_description,score,n_candidates\n", encoding="utf-8")

            with patch.object(full_map, "ROOT", root), patch.object(full_map, "PRODUCTS_DB", products_db), patch.object(full_map, "ESHA_CSV", esha_csv), patch.object(
                full_map, "AGGREGATION_CSV", aggregation_csv
            ), patch.object(full_map, "LEGACY_BEST_MAP_CSV", legacy_csv), patch.object(full_map, "OUT_CSV", out_csv), patch.object(
                full_map, "OUT_SUMMARY", out_summary
            ), patch.object(full_map, "OUT_DIR", out_dir):
                summary = full_map.build_full_map()

            with out_csv.open(newline="", encoding="utf-8") as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual(summary["unassigned"], 1)
            self.assertEqual(rows[0]["best_esha_code"], "")
            self.assertTrue(rows[0]["assignment_source"].endswith("_no_match"))

    def test_rejects_size_overlap_without_food_identity(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            out_dir = root / "output"
            out_dir.mkdir(parents=True)
            products_db = root / "master_products.db"
            esha_csv = root / "esha.csv"
            aggregation_csv = root / "agg.csv"
            legacy_csv = root / "legacy.csv"
            canonical_csv = root / "canonical.csv"
            fix_queue_csv = root / "fix.csv"
            out_csv = out_dir / "full.csv"
            out_summary = out_dir / "full.json"

            con = sqlite3.connect(products_db)
            try:
                con.execute(
                    "create table products (gtin_upc text, fdc_id text, description text, brand_owner text, brand_name text, branded_food_category text)"
                )
                con.execute(
                    "insert into products values ('111','1','LARGE APRICOTS','Owner','Brand','Wholesome Snacks')"
                )
                con.commit()
            finally:
                con.close()

            esha_csv.write_text(
                "\n".join(
                    [
                        "EshaCode,Description",
                        "900001,\"Biscuit, large\"",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            aggregation_csv.write_text(
                "\n".join(
                    [
                        "esha_code,description,family,query,distinct_category_count,category,category_count,signal,sample_row_count,sample_titles,sample_gtins,pack_path",
                        "900001,\"Biscuit, large\",dessert_snack,\"biscuit large\",1,Wholesome Snacks,50,in_scope_category,1,,,x",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            legacy_csv.write_text("gtin_upc,product_description,branded_food_category,brand_owner,best_esha_code,best_esha_description,score,n_candidates\n", encoding="utf-8")
            fix_queue_csv.write_text("esha_code,needs_fix\n", encoding="utf-8")

            with patch.object(full_map, "ROOT", root), patch.object(full_map, "PRODUCTS_DB", products_db), patch.object(full_map, "ESHA_CSV", esha_csv), patch.object(
                full_map, "AGGREGATION_CSV", aggregation_csv
            ), patch.object(full_map, "LEGACY_BEST_MAP_CSV", legacy_csv), patch.object(full_map, "CANONICAL_SURFACE_CSV", canonical_csv), patch.object(
                full_map, "FIX_QUEUE_CSV", fix_queue_csv
            ), patch.object(full_map, "OUT_CSV", out_csv), patch.object(full_map, "OUT_SUMMARY", out_summary), patch.object(full_map, "OUT_DIR", out_dir):
                summary = full_map.build_full_map()

            with out_csv.open(newline="", encoding="utf-8") as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual(summary["unassigned"], 1)
            self.assertEqual(rows[0]["best_esha_code"], "")
            self.assertTrue(rows[0]["assignment_source"].endswith("_no_match"))


if __name__ == "__main__":
    unittest.main()
