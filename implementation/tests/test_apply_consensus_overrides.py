import csv
import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path


REPO = Path(__file__).resolve().parents[2]
V2 = REPO / "retail_mapper" / "v2"
SCRIPT = V2 / "apply_consensus_overrides.py"

sys.path.insert(0, str(V2))
spec = importlib.util.spec_from_file_location("apply_consensus_overrides", SCRIPT)
overrides = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(overrides)


SOURCE_FIELDS = [
    "fdc_id",
    "title",
    "branded_food_category",
    "retail_type",
    "category_path_fixed",
    "product_identity_fixed",
    "canonical_path",
    "canonical_label",
    "modifier",
    "retail_leaf_path",
    "fndds_code",
    "fndds_desc",
    "sr28_code",
    "sr28_desc",
    "esha_code",
    "esha_desc",
    "match_source",
    "match_score",
    "matched_key",
    "portions_json",
]


def write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


class ApplyConsensusOverridesTests(unittest.TestCase):
    def test_candidate_rows_are_inert_by_default(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            source = base / "source.csv"
            taxonomy = base / "taxonomy.csv"
            reference = base / "reference.csv"
            conflicts = base / "conflicts.csv"
            out = base / "out.csv"
            decisions = base / "decisions.csv"
            report = base / "report.json"
            md = base / "out.md"
            write_csv(source, SOURCE_FIELDS, [{
                "fdc_id": "1",
                "title": "ALMOND MILK",
                "branded_food_category": "Plant Based Milk",
                "category_path_fixed": "Beverage > Plant Milk",
                "product_identity_fixed": "Almond Milk",
                "canonical_path": "Beverage > Plant Milk > Almond Milk",
                "modifier": "Unsweetened",
                "retail_leaf_path": "Beverage > Plant Milk > Almond Milk > Unsweetened",
                "sr28_desc": "Milk, lowfat",
            }])
            write_csv(reference, ["fdc_id", "status", "owner", "issue_family", "sr28_desc"], [{
                "fdc_id": "1",
                "status": "todo",
                "owner": "codex",
                "issue_family": "plant_milk_has_dairy_milk_reference",
                "sr28_desc": "Almond milk, unsweetened",
            }])
            write_csv(taxonomy, ["fdc_id", "status"], [])
            write_csv(conflicts, ["fdc_id", "status"], [])

            overrides.apply_overrides(
                source=source,
                taxonomy_overrides=taxonomy,
                reference_overrides=reference,
                source_conflicts=conflicts,
                out=out,
                decisions_out=decisions,
                report_out=report,
                markdown_out=md,
            )

            rows = read_rows(out)
            self.assertEqual("Milk, lowfat", rows[0]["sr28_desc"])
            self.assertEqual([], read_rows(decisions))

    def test_reference_override_updates_only_provided_fields(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            source = base / "source.csv"
            taxonomy = base / "taxonomy.csv"
            reference = base / "reference.csv"
            conflicts = base / "conflicts.csv"
            out = base / "out.csv"
            decisions = base / "decisions.csv"
            report = base / "report.json"
            md = base / "out.md"
            write_csv(source, SOURCE_FIELDS, [{
                "fdc_id": "2",
                "title": "CINNAMON CHURRO COFFEE CREAMER",
                "branded_food_category": "Milk Additives",
                "category_path_fixed": "Beverage > Coffee Creamers",
                "product_identity_fixed": "Coffee Creamer",
                "canonical_path": "Beverage > Coffee Creamers > Coffee Creamer",
                "modifier": "Cinnamon Churro",
                "retail_leaf_path": "Beverage > Coffee Creamers > Coffee Creamer > Cinnamon Churro",
                "sr28_code": "20081",
                "sr28_desc": "Wheat flour, white",
                "esha_code": "49565",
                "esha_desc": "Churro, cinnamon & sugar",
            }])
            write_csv(reference, ["fdc_id", "status", "owner", "issue_family", "sr28_code", "sr28_desc"], [{
                "fdc_id": "2",
                "status": "approved",
                "owner": "codex",
                "issue_family": "beverage_or_creamer_has_bakery_flour_reference",
                "sr28_code": "43210",
                "sr28_desc": "Coffee creamer, liquid",
            }])
            write_csv(taxonomy, ["fdc_id", "status"], [])
            write_csv(conflicts, ["fdc_id", "status"], [])

            overrides.apply_overrides(
                source=source,
                taxonomy_overrides=taxonomy,
                reference_overrides=reference,
                source_conflicts=conflicts,
                out=out,
                decisions_out=decisions,
                report_out=report,
                markdown_out=md,
            )

            row = read_rows(out)[0]
            self.assertEqual("43210", row["sr28_code"])
            self.assertEqual("Coffee creamer, liquid", row["sr28_desc"])
            self.assertEqual("49565", row["esha_code"])
            self.assertEqual("Churro, cinnamon & sugar", row["esha_desc"])
            self.assertEqual("reference:beverage_or_creamer_has_bakery_flour_reference", row["override_source"])

    def test_partial_taxonomy_override_repairs_path_contract(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            source = base / "source.csv"
            taxonomy = base / "taxonomy.csv"
            reference = base / "reference.csv"
            conflicts = base / "conflicts.csv"
            out = base / "out.csv"
            decisions = base / "decisions.csv"
            report = base / "report.json"
            md = base / "out.md"
            write_csv(source, SOURCE_FIELDS, [{
                "fdc_id": "3",
                "title": "CHEESE SANDWICH CRACKERS",
                "branded_food_category": "Biscuits/Cookies",
                "category_path_fixed": "Meal > Sandwiches",
                "product_identity_fixed": "Crackers",
                "canonical_path": "Meal > Sandwiches > Crackers",
                "modifier": "Cheese Sandwich",
                "retail_leaf_path": "Meal > Sandwiches > Crackers > Cheese Sandwich",
            }])
            write_csv(taxonomy, ["fdc_id", "status", "owner", "issue_family", "category_path_fixed", "product_identity_fixed"], [{
                "fdc_id": "3",
                "status": "approved",
                "owner": "claude",
                "issue_family": "sandwich_cookie_or_cracker_routed_as_meal_sandwich",
                "category_path_fixed": "Snack > Crackers",
                "product_identity_fixed": "Sandwich Crackers",
            }])
            write_csv(reference, ["fdc_id", "status"], [])
            write_csv(conflicts, ["fdc_id", "status"], [])

            overrides.apply_overrides(
                source=source,
                taxonomy_overrides=taxonomy,
                reference_overrides=reference,
                source_conflicts=conflicts,
                out=out,
                decisions_out=decisions,
                report_out=report,
                markdown_out=md,
            )

            row = read_rows(out)[0]
            self.assertEqual("Snack > Crackers", row["category_path_fixed"])
            self.assertEqual("Snack > Crackers > Sandwich Crackers", row["canonical_path"])
            self.assertEqual("Snack > Crackers > Sandwich Crackers > Cheese Sandwich", row["retail_leaf_path"])
            self.assertEqual([], overrides.path_defects(row))

    def test_approved_legacy_taxonomy_override_schema_is_mapped(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            source = base / "source.csv"
            taxonomy = base / "taxonomy.csv"
            reference = base / "reference.csv"
            conflicts = base / "conflicts.csv"
            out = base / "out.csv"
            decisions = base / "decisions.csv"
            report = base / "report.json"
            md = base / "out.md"
            write_csv(source, SOURCE_FIELDS, [{
                "fdc_id": "30",
                "title": "COOKIE SANDWICH",
                "branded_food_category": "Biscuits/Cookies",
                "category_path_fixed": "Meal > Sandwiches",
                "product_identity_fixed": "Cookies",
                "canonical_path": "Meal > Sandwiches > Cookies",
                "modifier": "Chocolate",
                "retail_leaf_path": "Meal > Sandwiches > Cookies > Chocolate",
            }])
            write_csv(taxonomy, ["fdc_id", "status", "new_canonical_path", "new_product_identity", "issue_family", "reason"], [{
                "fdc_id": "30",
                "status": "approved",
                "new_canonical_path": "Bakery > Cookies",
                "new_product_identity": "Sandwich Cookies",
                "issue_family": "sandwich_cookie_or_cracker_routed_as_meal_sandwich",
                "reason": "legacy reviewed row",
            }])
            write_csv(reference, ["fdc_id", "status"], [])
            write_csv(conflicts, ["fdc_id", "status"], [])

            overrides.apply_overrides(
                source=source,
                taxonomy_overrides=taxonomy,
                reference_overrides=reference,
                source_conflicts=conflicts,
                out=out,
                decisions_out=decisions,
                report_out=report,
                markdown_out=md,
            )

            row = read_rows(out)[0]
            self.assertEqual("Bakery > Cookies", row["category_path_fixed"])
            self.assertEqual("Bakery > Cookies > Sandwich Cookies", row["canonical_path"])
            self.assertEqual("Bakery > Cookies > Sandwich Cookies > Chocolate", row["retail_leaf_path"])

    def test_active_taxonomy_override_alias_does_not_replace_derived_canonical_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            source = base / "source.csv"
            taxonomy = base / "taxonomy.csv"
            reference = base / "reference.csv"
            conflicts = base / "conflicts.csv"
            out = base / "out.csv"
            decisions = base / "decisions.csv"
            report = base / "report.json"
            md = base / "out.md"
            write_csv(source, SOURCE_FIELDS, [{
                "fdc_id": "31",
                "title": "COOKIE SANDWICH",
                "branded_food_category": "Biscuits/Cookies",
                "category_path_fixed": "Meal > Sandwiches",
                "product_identity_fixed": "Cookies",
                "canonical_path": "Meal > Sandwiches > Cookies",
                "modifier": "Chocolate",
                "retail_leaf_path": "Meal > Sandwiches > Cookies > Chocolate",
            }])
            write_csv(
                taxonomy,
                [
                    "fdc_id",
                    "status",
                    "category_path_fixed",
                    "product_identity_fixed",
                    "new_canonical_path",
                    "new_product_identity",
                    "issue_family",
                ],
                [{
                    "fdc_id": "31",
                    "status": "approved",
                    "category_path_fixed": "Bakery > Cookies",
                    "product_identity_fixed": "Sandwich Cookies",
                    "new_canonical_path": "Bakery > Cookies",
                    "new_product_identity": "Sandwich Cookies",
                    "issue_family": "sandwich_cookie_or_cracker_routed_as_meal_sandwich",
                }],
            )
            write_csv(reference, ["fdc_id", "status"], [])
            write_csv(conflicts, ["fdc_id", "status"], [])

            overrides.apply_overrides(
                source=source,
                taxonomy_overrides=taxonomy,
                reference_overrides=reference,
                source_conflicts=conflicts,
                out=out,
                decisions_out=decisions,
                report_out=report,
                markdown_out=md,
            )

            row = read_rows(out)[0]
            self.assertEqual("Bakery > Cookies", row["category_path_fixed"])
            self.assertEqual("Sandwich Cookies", row["product_identity_fixed"])
            self.assertEqual("Bakery > Cookies > Sandwich Cookies", row["canonical_path"])
            self.assertEqual("Bakery > Cookies > Sandwich Cookies > Chocolate", row["retail_leaf_path"])

    def test_blank_modifier_override_does_not_reuse_old_leaf_tail(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            source = base / "source.csv"
            taxonomy = base / "taxonomy.csv"
            reference = base / "reference.csv"
            conflicts = base / "conflicts.csv"
            out = base / "out.csv"
            decisions = base / "decisions.csv"
            report = base / "report.json"
            md = base / "out.md"
            write_csv(source, SOURCE_FIELDS, [{
                "fdc_id": "32",
                "title": "MACARONI PRODUCT",
                "branded_food_category": "Pasta by Shape & Type",
                "category_path_fixed": "Pantry > Pasta > Macaroni > Shells",
                "product_identity_fixed": "Macaroni",
                "canonical_path": "Pantry > Pasta > Macaroni > Shells > Macaroni",
                "modifier": "Plain",
                "retail_leaf_path": "Pantry > Pasta > Macaroni > Shells > Macaroni > Plain",
            }])
            write_csv(taxonomy, ["fdc_id", "status", "owner", "issue_family", "category_path_fixed", "product_identity_fixed", "modifier"], [{
                "fdc_id": "32",
                "status": "approved",
                "owner": "codex",
                "issue_family": "pasta_shape_sibling_stack",
                "category_path_fixed": "Pantry > Pasta",
                "product_identity_fixed": "Macaroni",
                "modifier": "<blank>",
            }])
            write_csv(reference, ["fdc_id", "status"], [])
            write_csv(conflicts, ["fdc_id", "status"], [])

            overrides.apply_overrides(
                source=source,
                taxonomy_overrides=taxonomy,
                reference_overrides=reference,
                source_conflicts=conflicts,
                out=out,
                decisions_out=decisions,
                report_out=report,
                markdown_out=md,
            )

            row = read_rows(out)[0]
            self.assertEqual("", row["modifier"])
            self.assertEqual("Pantry > Pasta > Macaroni", row["retail_leaf_path"])

    def test_source_conflict_can_record_corrected_category_without_replacing_original(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            source = base / "source.csv"
            taxonomy = base / "taxonomy.csv"
            reference = base / "reference.csv"
            conflicts = base / "conflicts.csv"
            out = base / "out.csv"
            decisions = base / "decisions.csv"
            report = base / "report.json"
            md = base / "out.md"
            write_csv(source, SOURCE_FIELDS, [{
                "fdc_id": "4",
                "title": "CHICKEN CAESAR SALAD",
                "branded_food_category": "Pickles, Olives, Peppers & Relishes",
                "category_path_fixed": "Meal > Salads",
                "product_identity_fixed": "Chicken Caesar Salad",
                "canonical_path": "Meal > Salads > Chicken Caesar Salad",
                "modifier": "",
                "retail_leaf_path": "Meal > Salads > Chicken Caesar Salad",
            }])
            write_csv(conflicts, ["fdc_id", "status", "owner", "issue_family", "branded_food_category_corrected", "source_conflict_note"], [{
                "fdc_id": "4",
                "status": "approved",
                "owner": "shared",
                "issue_family": "pickle_bfc_salad_source_conflict",
                "branded_food_category_corrected": "Prepared Salads",
                "source_conflict_note": "Title and path are salad; source BFC is dirty.",
            }])
            write_csv(taxonomy, ["fdc_id", "status"], [])
            write_csv(reference, ["fdc_id", "status"], [])

            overrides.apply_overrides(
                source=source,
                taxonomy_overrides=taxonomy,
                reference_overrides=reference,
                source_conflicts=conflicts,
                out=out,
                decisions_out=decisions,
                report_out=report,
                markdown_out=md,
            )

            row = read_rows(out)[0]
            self.assertEqual("Pickles, Olives, Peppers & Relishes", row["branded_food_category"])
            self.assertEqual("Prepared Salads", row["branded_food_category_corrected"])
            self.assertIn("source BFC is dirty", row["source_conflict_note"])


if __name__ == "__main__":
    unittest.main()
