import sqlite3
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
DB = ROOT / "data" / "master_products.db"


class ProductCodeTagsHygiene(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.con = sqlite3.connect(DB)

    @classmethod
    def tearDownClass(cls):
        cls.con.close()

    def test_table_exists(self):
        r = self.con.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='product_code_tags'"
        ).fetchone()
        self.assertIsNotNone(r, "run phase13_tag_products_four_sources.py first")

    def test_source_column_constrained(self):
        rows = self.con.execute(
            "SELECT DISTINCT source FROM product_code_tags"
        ).fetchall()
        sources = {r[0] for r in rows}
        allowed = {"A_fndds_crosswalk", "B_category_map", "C_normalizer", "D_cleaned_overlay"}
        self.assertTrue(sources.issubset(allowed),
                        f"unknown sources: {sources - allowed}")

    def test_tag_type_constrained(self):
        rows = self.con.execute("SELECT DISTINCT tag_type FROM product_code_tags").fetchall()
        types = {r[0] for r in rows}
        self.assertTrue(types.issubset({"sr28", "fndds", "pseudo"}),
                        f"unknown tag types: {types}")

    def test_sr28_codes_validate_against_food_csv(self):
        import csv as csvmod
        sr28 = set()
        with (ROOT / "data" / "sr28_csv" / "food.csv").open() as f:
            for r in csvmod.DictReader(f):
                sr28.add(r["fdc_id"].strip())
        rows = self.con.execute(
            "SELECT DISTINCT code FROM product_code_tags WHERE tag_type='sr28'"
        ).fetchall()
        bad = [r[0] for r in rows if r[0] not in sr28]
        self.assertEqual(bad[:5], [], f"SR28 tags not in food.csv (first 5 of {len(bad)})")

    def test_coverage_at_least_90pct(self):
        total = self.con.execute("SELECT COUNT(*) FROM products").fetchone()[0]
        tagged = self.con.execute(
            "SELECT COUNT(DISTINCT gtin_upc) FROM product_code_tags"
        ).fetchone()[0]
        pct = 100 * tagged / total if total else 0
        self.assertGreaterEqual(pct, 90, f"product tagging coverage {pct:.1f}% < 90%")


if __name__ == "__main__":
    unittest.main()
