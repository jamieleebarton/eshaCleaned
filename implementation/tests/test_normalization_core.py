from __future__ import annotations

import csv
import json
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path


IMPLEMENTATION_ROOT = Path(__file__).resolve().parents[1]
if str(IMPLEMENTATION_ROOT) not in sys.path:
    sys.path.insert(0, str(IMPLEMENTATION_ROOT))

from build_full_line_item_candidate_cache import build_cache  # noqa: E402
from build_normalized_item_line_rollup import build_rollup  # noqa: E402
from hf_v3_collapse_core import collapse_candidate_to_v3  # noqa: E402
from normalization_core import CanonicalIngredientNormalizer, normalize_candidate_surface  # noqa: E402
from resolver_context import DEFAULT_ARTIFACTS  # noqa: E402


class Namespace:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


class NormalizationCoreTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.normalizer = CanonicalIngredientNormalizer()

    def write_ingredient_lines_db(self, path: Path, rows: list[tuple[str, int, str]]) -> None:
        conn = sqlite3.connect(path)
        try:
            conn.execute(
                """
                CREATE TABLE ingredient_lines (
                    normalized_line TEXT NOT NULL,
                    recipe_count INTEGER NOT NULL,
                    example_raw_line TEXT NOT NULL
                )
                """
            )
            conn.executemany("INSERT INTO ingredient_lines VALUES (?,?,?)", rows)
            conn.commit()
        finally:
            conn.close()

    def test_every_line_uses_same_bridge_resolver_sequence(self) -> None:
        cases = {
            "1 cup unsalted butter": "unsalted butter|||",
            "1 cup orange juice, freshly squeezed": "orange juice|||fresh",
            "1 cup orange juice, chilled": "orange juice|||",
            "1 cup green beans, drained": "green bean|||",
        }
        for line, concept_key in cases.items():
            with self.subTest(line=line):
                resolution = self.normalizer.normalize_line(line)
                self.assertEqual("concept_ready", resolution.bridge_status)
                self.assertEqual(concept_key, resolution.canonical_concept_key)

    def test_compound_food_is_not_reduced_to_head_food(self) -> None:
        resolution = self.normalizer.normalize_line("1 can green bean casserole")
        self.assertNotEqual("green bean|||", resolution.canonical_concept_key)

    def test_item_hint_wins_before_fragile_line_fallback(self) -> None:
        resolution = self.normalizer.normalize_line("1", item_hint="butter")
        self.assertEqual("concept_ready", resolution.bridge_status)
        self.assertEqual("butter|||", resolution.canonical_concept_key)
        self.assertTrue(resolution.candidate_method.startswith("item_hint_"))

    def test_candidate_cleanup_runs_after_hf_extraction(self) -> None:
        self.assertEqual("gallon orange juice", normalize_candidate_surface("gallon orange juice"))
        resolution = self.normalizer.normalize_item_candidate("crushed tomatoes")
        self.assertEqual("concept_ready", resolution["bridge_status"])
        self.assertEqual("tomato||crushed|canned", resolution["canonical_concept_key"])

    def test_historical_hf_v3_base_collapse_layer(self) -> None:
        self.assertEqual(("orange juice", "orange juice", "orange juice"), collapse_candidate_to_v3("gallon orange juice"))
        self.assertEqual(("tomatoes", "tomatoes", "tomatoes"), collapse_candidate_to_v3("crushed tomatoes"))
        self.assertEqual(
            ("green bean casserole", "green bean casserole", "green bean casserole"),
            collapse_candidate_to_v3("green bean casserole"),
        )

    def test_hf_ner_candidate_rescues_parser_miss_without_overriding_bridge_hit(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ner_path = Path(tmp) / "ner.jsonl"
            rows = [
                {
                    "normalized_line": "1 cup wrapper text not food",
                    "candidate_food_phrase": "orange juice",
                },
                {
                    "normalized_line": "1 cup milk",
                    "candidate_food_phrase": "butter",
                },
            ]
            ner_path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")

            normalizer = CanonicalIngredientNormalizer(ner_jsonl=ner_path)
            rescued = normalizer.normalize_line("1 cup wrapper text not food")
            self.assertEqual("concept_ready", rescued.bridge_status)
            self.assertEqual("orange juice|||", rescued.canonical_concept_key)
            self.assertTrue(rescued.candidate_method.startswith("hf_ner_candidate_"))

            bridge_hit = normalizer.normalize_line("1 cup milk")
            self.assertEqual("concept_ready", bridge_hit.bridge_status)
            self.assertEqual("milk|||", bridge_hit.canonical_concept_key)
            self.assertTrue(bridge_hit.candidate_method.startswith("parsed_surface_"))

    def test_approved_regex_rule_extracts_canonical_food(self) -> None:
        resolved = self.normalizer.normalize_line("sunflower oil to shallow fry fish")
        self.assertEqual("concept_ready", resolved.bridge_status)
        self.assertEqual("sunflower oil|||", resolved.canonical_concept_key)
        self.assertEqual("parsed_surface_approved_regex_rule", resolved.candidate_method)

    def test_approved_reject_stops_bridge_fallback(self) -> None:
        resolved = self.normalizer.normalize_line("1 hot glue")
        self.assertEqual("rejected", resolved.bridge_status)
        self.assertEqual("|||", resolved.canonical_concept_key)
        self.assertEqual("approved_normalization_reject", resolved.bridge_source)

    def test_full_line_cache_streams_rows_through_normalizer(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            recipe_funnel_db = tmp_path / "recipe_funnel.db"
            self.write_ingredient_lines_db(
                recipe_funnel_db,
                [(f"{index} teaspoon salt", 200 - index, f"{index} teaspoon salt") for index in range(1, 101)],
            )
            args = Namespace(
                recipe_funnel_db=recipe_funnel_db,
                bridge_csv=DEFAULT_ARTIFACTS.normalized_item_bridge_csv,
                output_csv=tmp_path / "line_cache.csv",
                output_db=tmp_path / "line_cache.db",
                summary_json=tmp_path / "line_cache.summary.json",
                limit=100,
                insert_chunk_size=25,
                progress_every=0,
                skip_csv=False,
            )
            summary = build_cache(args)
            self.assertEqual(100, summary["rows"])
            self.assertIn("concept_ready", summary["status_rows"])

            with args.output_csv.open(newline="", encoding="utf-8") as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual(100, len(rows))
            self.assertIn("parsed_food_phrase", rows[0])
            self.assertIn("product_contract_status", rows[0])

            conn = sqlite3.connect(args.output_db)
            try:
                count = conn.execute("SELECT COUNT(*) FROM full_line_item_candidate_cache").fetchone()[0]
            finally:
                conn.close()
            self.assertEqual(100, count)

    def test_rollup_preserves_pointer_from_item_to_line_variants(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            recipe_funnel_db = tmp_path / "recipe_funnel.db"
            self.write_ingredient_lines_db(
                recipe_funnel_db,
                [(f"{index} teaspoon salt", 300 - index, f"{index} teaspoon salt") for index in range(1, 31)]
                + [(f"{index} cup milk", 200 - index, f"{index} cup milk") for index in range(1, 11)]
                + [(f"{index} tablespoon sugar", 100 - index, f"{index} tablespoon sugar") for index in range(1, 11)],
            )
            cache_args = Namespace(
                recipe_funnel_db=recipe_funnel_db,
                bridge_csv=DEFAULT_ARTIFACTS.normalized_item_bridge_csv,
                output_csv=tmp_path / "line_cache.csv",
                output_db=tmp_path / "line_cache.db",
                summary_json=tmp_path / "line_cache.summary.json",
                limit=1000,
                insert_chunk_size=100,
                progress_every=0,
                skip_csv=False,
            )
            build_cache(cache_args)
            rollup_args = Namespace(
                input_db=cache_args.output_db,
                output_csv=tmp_path / "rollup.csv",
                summary_json=tmp_path / "rollup.summary.json",
                top_n=5,
            )
            summary = build_rollup(rollup_args)
            self.assertLess(summary["rollup_rows"], summary["source_line_rows"])

            with rollup_args.output_csv.open(newline="", encoding="utf-8") as handle:
                rows = {row["item_candidate"]: row for row in csv.DictReader(handle)}
            self.assertIn("salt", rows)
            salt = rows["salt"]
            self.assertGreater(int(salt["unique_line_count"]), 1)
            self.assertIn("top_normalized_lines", salt)
            self.assertIn("quantity_unit_examples", salt)


if __name__ == "__main__":
    unittest.main()
