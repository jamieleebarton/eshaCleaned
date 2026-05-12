import sys
import unittest
from pathlib import Path


ROOT = Path("/Users/jamiebarton/Desktop/esha_audit_bundle")
V2 = ROOT / "retail_mapper" / "v2"
if str(V2) not in sys.path:
    sys.path.insert(0, str(V2))

import build_semantic_product_taxonomy as compiler  # noqa: E402


class SemanticProductTaxonomyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.head_entries = compiler.load_head_entries()
        cls.taxonomy_paths = compiler.load_taxonomy_paths(compiler.DEFAULT_TAXONOMY)

    def compile(self, title: str, parsed: dict[str, str] | None = None, **cleaned_extra):
        cleaned = {
            "fdc_id": "test",
            "gtin_upc": "",
            "title": title,
            "branded_food_category": "",
            "current_esha": "",
            "current_esha_desc": "",
            "clean_retail_leaf": "",
            "parser_needs_review": "[]",
        }
        cleaned.update(cleaned_extra)
        parsed_row = {
            "retail_type": "single",
            "claims": "{}",
            "flavor_blend": "[]",
            "needs_review": "[]",
        }
        if parsed:
            parsed_row.update(parsed)
        return compiler.compile_record(cleaned, parsed_row, self.head_entries, self.taxonomy_paths)

    def test_black_beans_repair_top_level_pantry_and_keep_claim(self) -> None:
        rec = self.compile(
            "NO SALT ADDED BLACK BEANS",
            parsed={
                "storage": "canned",
                "claims": '{"sodium":["salt","no salt added"]}',
            },
            current_esha_desc="Beans, black, whole, canned",
            clean_retail_leaf="Pantry",
        )

        self.assertEqual(rec.product_identity, "Black Beans")
        self.assertEqual(rec.category_path, "Pantry > Legume")
        self.assertIn("whole", rec.form_texture_cut)
        self.assertIn("canned", rec.processing_storage)
        self.assertEqual(rec.claims, ["no_salt_added"])
        self.assertIn("source_path_too_shallow_repaired", rec.notes)
        self.assertNotIn("head_dict_no_match", rec.review_flags)

    def test_almond_milk_keeps_flavor_and_claims_out_of_path(self) -> None:
        rec = self.compile(
            "UNSWEETENED CHOCOLATE ORGANIC ALMONDMILK, UNSWEETENED CHOCOLATE",
            parsed={
                "flavor": "chocolate",
                "claims": '{"diet":["organic"],"sweetener":["unsweetened"]}',
            },
            branded_food_category="Plant Based Milk",
            current_esha_desc="Almond Milk, Almond Breeze, chocolate, unsweetened",
        )

        self.assertEqual(rec.product_identity, "Almond Milk")
        self.assertEqual(rec.canonical_path, "Beverage > Plant Milk > Almond Milk")
        self.assertEqual(rec.flavor, ["chocolate"])
        self.assertEqual(rec.claims, ["unsweetened", "organic"])
        self.assertEqual(rec.canonical_label, "Almond Milk (Chocolate, Unsweetened, Organic)")

    def test_orange_juice_captures_pulp_and_concentrate_as_attributes(self) -> None:
        rec = self.compile(
            "NO PULP 100% ORANGE JUICE FROM CONCENTRATE, ORANGE",
            parsed={"claims": "{}"},
            current_esha_desc="Juice Drink, breakfast, orange, with pulp, prepared from concentrate with water",
        )

        self.assertEqual(rec.product_identity, "Orange Juice")
        self.assertEqual(rec.canonical_path, "Beverage > Juice > Orange Juice")
        self.assertEqual(rec.form_texture_cut, ["no_pulp"])
        self.assertEqual(rec.processing_storage, ["from_concentrate"])
        self.assertEqual(rec.canonical_label, "Orange Juice (No Pulp, From Concentrate)")

    def test_brown_sugar_barbecue_sauce_does_not_route_to_sugar(self) -> None:
        rec = self.compile("BROWN SUGAR BARBECUE SAUCE, BROWN SUGAR")

        self.assertEqual(rec.product_identity, "Barbecue Sauce")
        self.assertEqual(rec.taxonomy_head, "BBQ Sauce")
        self.assertEqual(rec.category_path, "Pantry > Sauces & Salsas")
        self.assertEqual(rec.flavor, ["brown_sugar"])
        self.assertEqual(rec.existing_taxonomy_path, "Pantry > Sauces & Salsas > Barbecue Sauce")
        self.assertFalse(rec.mint_required)

    def test_chipotle_mayo_keeps_chipotle_as_flavor(self) -> None:
        rec = self.compile("MAYO, CHIPOTLE", parsed={"flavor": "chipotle"})

        self.assertEqual(rec.product_identity, "Mayonnaise")
        self.assertEqual(rec.category_path, "Pantry > Condiments")
        self.assertEqual(rec.flavor, ["chipotle"])
        self.assertEqual(rec.canonical_label, "Mayonnaise (Chipotle)")


if __name__ == "__main__":
    unittest.main()
