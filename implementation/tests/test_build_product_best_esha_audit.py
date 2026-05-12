from __future__ import annotations

import csv
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

IMPL = Path(__file__).resolve().parents[1]
if str(IMPL) not in sys.path:
    sys.path.insert(0, str(IMPL))

import build_product_best_esha_audit as audit


class BuildProductBestEshaAuditTests(unittest.TestCase):
    def test_build_best_esha_audit_writes_full_corpus_view(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)
            rollup = output_dir / "product_esha_code_rollup.csv"
            rollup.write_text(
                "\n".join(
                    [
                        "gtin_upc,fdc_id,product_description,brand_owner,brand_name,branded_food_category,esha_code_count,esha_codes,esha_descriptions,primary_esha_code,primary_esha_description,primary_esha_canonical_title,collision_status,match_reasons",
                        "1,10,WHOLE MILK,Owner,Brand,Milk,1,1,Milk whole,1,Milk whole,Milk whole,single,1:direct",
                        "2,20,UNKNOWN,Owner,Brand,Water,0,,,,,,unassigned,",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            out_csv = output_dir / "product_to_best_esha_audit.csv"
            out_summary = output_dir / "product_to_best_esha_audit_summary.json"

            with patch.object(audit, "ROLLUP_CSV", rollup), patch.object(audit, "OUT_CSV", out_csv), patch.object(
                audit, "OUT_SUMMARY", out_summary
            ), patch.object(audit, "OUT_DIR", output_dir):
                summary = audit.build_best_esha_audit()

            self.assertEqual(summary["products"], 2)
            self.assertEqual(summary["assigned_single"], 1)
            self.assertEqual(summary["unassigned"], 1)

            with out_csv.open(newline="", encoding="utf-8") as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual(len(rows), 2)
            self.assertEqual(rows[0]["best_esha_code"], "1")
            self.assertEqual(rows[1]["best_esha_code"], "")
            self.assertEqual(rows[1]["collision_status"], "unassigned")

            payload = json.loads(out_summary.read_text(encoding="utf-8"))
            self.assertEqual(payload["products"], 2)
            self.assertEqual(payload["audit_csv"], str(out_csv))

    def test_build_best_esha_audit_from_legacy_best_map(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)
            products_db = output_dir / "master_products.db"
            legacy = output_dir / "product_to_best_esha_map.csv"
            out_csv = output_dir / "product_to_best_esha_audit.csv"
            out_summary = output_dir / "product_to_best_esha_audit_summary.json"

            import sqlite3

            con = sqlite3.connect(products_db)
            try:
                con.execute(
                    "create table products (gtin_upc text, fdc_id text, description text, brand_owner text, brand_name text, branded_food_category text)"
                )
                con.execute(
                    "insert into products values ('0-1','10','WHOLE MILK','Owner','Brand','Milk'), ('2','20','UNKNOWN','Owner','Brand','Water')"
                )
                con.commit()
            finally:
                con.close()

            legacy.write_text(
                "\n".join(
                    [
                        "gtin_upc,product_description,branded_food_category,brand_owner,best_esha_code,best_esha_description,score,n_candidates",
                        "0 1,WHOLE MILK,Milk,Owner,1,Milk whole,1.0,3",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            with patch.object(audit, "LEGACY_BEST_MAP_CSV", legacy), patch.object(audit, "PRODUCTS_DB", products_db), patch.object(
                audit, "OUT_CSV", out_csv
            ), patch.object(audit, "OUT_SUMMARY", out_summary), patch.object(audit, "OUT_DIR", output_dir):
                summary = audit.build_best_esha_audit(source="legacy-best-map")

            self.assertEqual(summary["products"], 2)
            self.assertEqual(summary["assigned_single"], 1)
            self.assertEqual(summary["unassigned"], 1)
            with out_csv.open(newline="", encoding="utf-8") as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual(rows[0]["best_esha_code"], "1")
            self.assertEqual(rows[1]["best_esha_code"], "")


if __name__ == "__main__":
    unittest.main()
