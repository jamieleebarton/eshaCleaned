"""Tests for phase16_drain_review_queues.py.

The drain script reads approved rows from the Task 12 review queues and
appends them to the canonical registries. Tests operate on copies of the
real CSVs in a temp directory so the committed registries are never mutated.
"""

from __future__ import annotations

import csv
import importlib.util
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SCRIPT_PATH = REPO_ROOT / "recipe_pricing" / "scripts" / "phase16_drain_review_queues.py"


def _load_drain_module():
    spec = importlib.util.spec_from_file_location("phase16_drain", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules["phase16_drain"] = module
    spec.loader.exec_module(module)
    return module


class DrainFixtureBase(unittest.TestCase):
    """Build a self-contained temp copy of the registries + queues per test."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="phase16_drain_"))

        self.canonical_items = self.tmp / "canonical_items.csv"
        self.canonical_aliases = self.tmp / "canonical_aliases.csv"
        self.canonical_pseudos = self.tmp / "canonical_pseudos.csv"
        self.canonical_unknown = self.tmp / "canonical_unknown.csv"
        self.pseudo_candidates = self.tmp / "pseudo_candidates.csv"
        self.cross_verify = self.tmp / "cross_verify_disputes.csv"
        self.sr28_food = self.tmp / "food.csv"

        self._write_csv(
            self.canonical_items,
            ["canonical_name", "sr28_fdc_id", "sr28_description"],
            [
                {"canonical_name": "all-purpose flour", "sr28_fdc_id": "169761", "sr28_description": "Wheat flour, white, all-purpose"},
                {"canonical_name": "saffron threads", "sr28_fdc_id": "172476", "sr28_description": "Spices, saffron"},
                {"canonical_name": "pre-existing canonical", "sr28_fdc_id": "111111", "sr28_description": "x"},
            ],
        )
        self._write_csv(
            self.canonical_aliases,
            ["surface", "canonical_name", "source"],
            [
                {"surface": "ap flour", "canonical_name": "all-purpose flour", "source": "seed"},
            ],
        )
        self._write_csv(
            self.canonical_pseudos,
            [
                "pseudo_code", "canonical_name", "nutrition_proxy_sr28_fdc_id",
                "portion_overrides_json", "product_file", "proxy_rationale",
                "macro_trivial", "review_status", "source", "notes",
            ],
            [
                {
                    "pseudo_code": "P-NEW-001",
                    "canonical_name": "already pseudo one",
                    "nutrition_proxy_sr28_fdc_id": "169761",
                    "portion_overrides_json": "",
                    "product_file": "",
                    "proxy_rationale": "seed",
                    "macro_trivial": "false",
                    "review_status": "approved",
                    "source": "seed",
                    "notes": "",
                }
            ],
        )
        self._write_csv(
            self.canonical_unknown,
            ["item", "occurrence_count", "recipes_using_it", "review_status", "approved_canonical"],
            [],
        )
        self._write_csv(
            self.pseudo_candidates,
            [
                "surface", "recipes_using_it", "suggested_canonical_from_normalizer",
                "review_status", "approved_canonical_name", "approved_proxy_sr28_fdc_id",
            ],
            [],
        )
        self._write_csv(
            self.cross_verify,
            ["item", "our_concept", "hestia_concept", "occurrence_count", "review_status"],
            [],
        )
        # SR28 food.csv stub — exactly the ids used by the canonical_items fixture
        self._write_csv(
            self.sr28_food,
            ["fdc_id", "data_type", "description"],
            [
                {"fdc_id": "169761", "data_type": "sr_legacy_food", "description": "Wheat flour"},
                {"fdc_id": "172476", "data_type": "sr_legacy_food", "description": "Saffron"},
                {"fdc_id": "111111", "data_type": "sr_legacy_food", "description": "x"},
            ],
        )

        self.module = _load_drain_module()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _write_csv(self, path: Path, fieldnames, rows):
        with open(path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for r in rows:
                writer.writerow(r)

    def _append_row(self, path: Path, row: dict):
        with open(path, newline="") as f:
            fieldnames = next(csv.reader(f))
        with open(path, "a", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writerow(row)

    def _read_rows(self, path: Path):
        with open(path, newline="") as f:
            return list(csv.DictReader(f))

    def _paths(self):
        return {
            "canonical_items": self.canonical_items,
            "canonical_aliases": self.canonical_aliases,
            "canonical_pseudos": self.canonical_pseudos,
            "canonical_unknown": self.canonical_unknown,
            "pseudo_candidates": self.pseudo_candidates,
            "cross_verify_disputes": self.cross_verify,
            "sr28_food": self.sr28_food,
        }


class DrainTests(DrainFixtureBase):
    def test_drain_empty_queues_is_noop(self):
        stats = self.module.drain(self._paths(), dry_run=False)
        self.assertEqual(stats["aliases_added"], 0)
        self.assertEqual(stats["pseudos_added"], 0)
        self.assertEqual(len(self._read_rows(self.canonical_aliases)), 1)
        self.assertEqual(len(self._read_rows(self.canonical_pseudos)), 1)

    def test_drain_approved_canonical_unknown_row_appends_alias(self):
        self._append_row(
            self.canonical_unknown,
            {
                "item": "all purpose flour",
                "occurrence_count": "83015",
                "recipes_using_it": "77812",
                "review_status": "approved",
                "approved_canonical": "all-purpose flour",
            },
        )
        stats = self.module.drain(self._paths(), dry_run=False)
        self.assertEqual(stats["aliases_added"], 1)
        rows = self._read_rows(self.canonical_aliases)
        self.assertEqual(len(rows), 2)
        match = [r for r in rows if r["surface"] == "all purpose flour"]
        self.assertEqual(len(match), 1)
        self.assertEqual(match[0]["canonical_name"], "all-purpose flour")
        self.assertEqual(match[0]["source"], "phase16_drain")

    def test_drain_invalid_sr28_fdc_id_rejects_pseudo(self):
        self._append_row(
            self.pseudo_candidates,
            {
                "surface": "fictitious spice blend",
                "recipes_using_it": "12",
                "suggested_canonical_from_normalizer": "",
                "review_status": "approved",
                "approved_canonical_name": "fictitious spice blend",
                "approved_proxy_sr28_fdc_id": "99999999",  # not in sr28 stub
            },
        )
        stats = self.module.drain(self._paths(), dry_run=False)
        self.assertEqual(stats["pseudos_added"], 0)
        self.assertGreaterEqual(stats["pseudos_rejected_bad_sr28"], 1)
        # No new pseudo row appended
        self.assertEqual(len(self._read_rows(self.canonical_pseudos)), 1)

    def test_drain_script_is_idempotent(self):
        self._append_row(
            self.canonical_unknown,
            {
                "item": "ap flour 2",
                "occurrence_count": "10",
                "recipes_using_it": "5",
                "review_status": "approved",
                "approved_canonical": "all-purpose flour",
            },
        )
        self._append_row(
            self.pseudo_candidates,
            {
                "surface": "saffron threads",
                "recipes_using_it": "772",
                "suggested_canonical_from_normalizer": "",
                "review_status": "approved",
                "approved_canonical_name": "saffron threads pseudo",
                "approved_proxy_sr28_fdc_id": "172476",
            },
        )
        first = self.module.drain(self._paths(), dry_run=False)
        self.assertEqual(first["aliases_added"], 1)
        self.assertEqual(first["pseudos_added"], 1)
        second = self.module.drain(self._paths(), dry_run=False)
        self.assertEqual(second["aliases_added"], 0)
        self.assertEqual(second["pseudos_added"], 0)

    def test_drain_does_not_modify_existing_rows(self):
        before_aliases = self._read_rows(self.canonical_aliases)
        before_pseudos = self._read_rows(self.canonical_pseudos)
        self._append_row(
            self.canonical_unknown,
            {
                "item": "new surface",
                "occurrence_count": "3",
                "recipes_using_it": "3",
                "review_status": "approved",
                "approved_canonical": "all-purpose flour",
            },
        )
        self.module.drain(self._paths(), dry_run=False)
        after_aliases = self._read_rows(self.canonical_aliases)
        after_pseudos = self._read_rows(self.canonical_pseudos)
        # All original rows survive byte-for-byte in the first N positions.
        self.assertEqual(after_aliases[: len(before_aliases)], before_aliases)
        self.assertEqual(after_pseudos[: len(before_pseudos)], before_pseudos)


if __name__ == "__main__":
    unittest.main()
