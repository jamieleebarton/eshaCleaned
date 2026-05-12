import csv
import json
import tempfile
import unittest
from pathlib import Path

from implementation.orphan_parent_emitter import (
    SEED_FIELDS,
    _base_phrase,
    build_row,
    emit_orphan_parent_rows,
    load_orphan_parent_keys,
    load_source_a,
    load_source_b,
    write_rows_csv,
)


CONTRACT_FIELDS = [
    "contract_id",
    "concept_keys",
    "required_tokens",
    "forbidden_tokens",
    "allowed_categories",
    "min_matches",
    "review_status",
    "evidence_notes",
]


def _write_contracts(path: Path, rows):
    with open(path, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=CONTRACT_FIELDS)
        w.writeheader()
        w.writerows(rows)


def _write_seed(path: Path, canonical_concepts):
    with open(path, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=SEED_FIELDS)
        w.writeheader()
        for c in canonical_concepts:
            w.writerow({k: "" for k in SEED_FIELDS} | {"canonical_concept": c, "alias": c.split("|")[0]})


class TestBasePhrase(unittest.TestCase):
    def test_strips_trailing_pipes(self):
        self.assertEqual(_base_phrase("adobo|||"), "adobo")
        self.assertEqual(_base_phrase("baby back ribs|||"), "baby back ribs")
        self.assertEqual(_base_phrase("cottage cheese|curd||"), "cottage cheese")


class TestLoadOrphanParentKeys(unittest.TestCase):
    def test_returns_only_auto_parent_missing_from_seed(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            contracts = td / "contracts.csv"
            seed = td / "seed.csv"
            _write_contracts(
                contracts,
                [
                    {
                        "contract_id": "auto_parent_abc",
                        "concept_keys": json.dumps(["adobo|||"]),
                        "required_tokens": "[]",
                        "forbidden_tokens": "[]",
                        "allowed_categories": "[]",
                        "min_matches": "1",
                        "review_status": "proposed",
                        "evidence_notes": "",
                    },
                    {
                        "contract_id": "auto_parent_def",
                        "concept_keys": json.dumps(["berries|||"]),
                        "required_tokens": "[]",
                        "forbidden_tokens": "[]",
                        "allowed_categories": "[]",
                        "min_matches": "1",
                        "review_status": "proposed",
                        "evidence_notes": "",
                    },
                    {
                        "contract_id": "manual_xyz",
                        "concept_keys": json.dumps(["manual|||"]),
                        "required_tokens": "[]",
                        "forbidden_tokens": "[]",
                        "allowed_categories": "[]",
                        "min_matches": "1",
                        "review_status": "approved",
                        "evidence_notes": "",
                    },
                ],
            )
            _write_seed(seed, ["adobo|||"])  # adobo already exists

            orphans = load_orphan_parent_keys(contracts, seed)
            self.assertEqual(orphans, ["berries|||"])

    def test_skips_empty_concept_keys_and_bad_json(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            contracts = td / "contracts.csv"
            seed = td / "seed.csv"
            _write_contracts(
                contracts,
                [
                    {
                        "contract_id": "auto_parent_empty",
                        "concept_keys": "[]",
                        "required_tokens": "[]",
                        "forbidden_tokens": "[]",
                        "allowed_categories": "[]",
                        "min_matches": "1",
                        "review_status": "proposed",
                        "evidence_notes": "",
                    },
                    {
                        "contract_id": "auto_parent_bad",
                        "concept_keys": "not-json",
                        "required_tokens": "[]",
                        "forbidden_tokens": "[]",
                        "allowed_categories": "[]",
                        "min_matches": "1",
                        "review_status": "proposed",
                        "evidence_notes": "",
                    },
                ],
            )
            _write_seed(seed, [])
            self.assertEqual(load_orphan_parent_keys(contracts, seed), [])

    def test_deduplicates_repeated_parent_keys(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            contracts = td / "contracts.csv"
            seed = td / "seed.csv"
            _write_contracts(
                contracts,
                [
                    {
                        "contract_id": "auto_parent_a",
                        "concept_keys": json.dumps(["shared|||"]),
                        "required_tokens": "[]",
                        "forbidden_tokens": "[]",
                        "allowed_categories": "[]",
                        "min_matches": "1",
                        "review_status": "proposed",
                        "evidence_notes": "",
                    },
                    {
                        "contract_id": "auto_parent_b",
                        "concept_keys": json.dumps(["shared|||"]),
                        "required_tokens": "[]",
                        "forbidden_tokens": "[]",
                        "allowed_categories": "[]",
                        "min_matches": "1",
                        "review_status": "proposed",
                        "evidence_notes": "",
                    },
                ],
            )
            _write_seed(seed, [])
            self.assertEqual(load_orphan_parent_keys(contracts, seed), ["shared|||"])


class TestBuildRow(unittest.TestCase):
    def test_source_a_preferred_with_anchor(self):
        a = {
            "garam masala": {
                "phrase": "garam masala",
                "family": "spice_blend",
                "anchor_system": "SR28",
                "anchor_code": "171329",
                "anchor_description": "Spices, mixed spices",
                "notes": "",
            }
        }
        row, label = build_row("garam masala|||", a, {})
        self.assertEqual(label, "A")
        self.assertEqual(row["alias"], "garam masala")
        self.assertEqual(row["canonical_concept"], "garam masala|||")
        self.assertEqual(row["anchor_system"], "SR28")
        self.assertEqual(row["anchor_code"], "171329")
        self.assertEqual(row["family"], "spice_blend")
        self.assertEqual(row["trust_state"], "reviewed_usda_anchor")
        self.assertEqual(row["nutrition_state"], "reviewed_usda_anchor")
        self.assertEqual(row["shopping_state"], "shopping_candidates_strong")
        self.assertEqual(row["review_status"], "proposed")
        self.assertIn("Source: A", row["evidence_notes"])

    def test_source_b_when_a_missing(self):
        b = {
            "cottage cheese": {
                "parent_concept_phrase": "cottage cheese",
                "parent_anchor_system": "FNDDS",
                "parent_anchor_code": "14201200",
                "parent_description": "Cottage cheese, farmer's",
            }
        }
        row, label = build_row("cottage cheese|||", {}, b)
        self.assertEqual(label, "B")
        self.assertEqual(row["anchor_system"], "FNDDS")
        self.assertEqual(row["anchor_code"], "14201200")
        self.assertEqual(row["anchor_description"], "Cottage cheese, farmer's")
        self.assertEqual(row["trust_state"], "reviewed_usda_anchor")
        self.assertIn("Source: B", row["evidence_notes"])

    def test_source_c_fallback_uses_infer_family(self):
        row, label = build_row("adobo|||", {}, {})
        self.assertEqual(label, "C")
        self.assertEqual(row["anchor_code"], "")
        self.assertEqual(row["anchor_system"], "")
        self.assertEqual(row["trust_state"], "reviewed_local_label_anchor")
        self.assertEqual(row["nutrition_state"], "reviewed_proxy")
        self.assertTrue(row["family"])  # infer_family always returns something
        self.assertIn("Source: C", row["evidence_notes"])

    def test_source_a_without_anchor_code_falls_to_proxy_state(self):
        a = {
            "nothing": {
                "phrase": "nothing",
                "family": "other",
                "anchor_system": "",
                "anchor_code": "",
                "anchor_description": "",
                "notes": "",
            }
        }
        row, label = build_row("nothing|||", a, {})
        self.assertEqual(label, "A")
        self.assertEqual(row["trust_state"], "reviewed_local_label_anchor")
        self.assertEqual(row["nutrition_state"], "reviewed_proxy")
        self.assertEqual(row["family"], "other")


class TestEmitAndWrite(unittest.TestCase):
    def test_emit_and_write_round_trip(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            contracts = td / "contracts.csv"
            seed = td / "seed.csv"
            src_a = td / "proposed_seed_parents.csv"
            src_b = td / "proposed_local_label_concepts.csv"
            out = td / "out.csv"

            _write_contracts(
                contracts,
                [
                    {
                        "contract_id": "auto_parent_1",
                        "concept_keys": json.dumps(["garam masala|||"]),
                        "required_tokens": "[]",
                        "forbidden_tokens": "[]",
                        "allowed_categories": "[]",
                        "min_matches": "1",
                        "review_status": "proposed",
                        "evidence_notes": "",
                    },
                    {
                        "contract_id": "auto_parent_2",
                        "concept_keys": json.dumps(["cottage cheese|||"]),
                        "required_tokens": "[]",
                        "forbidden_tokens": "[]",
                        "allowed_categories": "[]",
                        "min_matches": "1",
                        "review_status": "proposed",
                        "evidence_notes": "",
                    },
                    {
                        "contract_id": "auto_parent_3",
                        "concept_keys": json.dumps(["adobo|||"]),
                        "required_tokens": "[]",
                        "forbidden_tokens": "[]",
                        "allowed_categories": "[]",
                        "min_matches": "1",
                        "review_status": "proposed",
                        "evidence_notes": "",
                    },
                ],
            )
            _write_seed(seed, [])
            with open(src_a, "w", newline="") as fh:
                w = csv.DictWriter(
                    fh,
                    fieldnames=["phrase", "family", "anchor_system", "anchor_code", "anchor_description", "notes"],
                )
                w.writeheader()
                w.writerow(
                    {
                        "phrase": "garam masala",
                        "family": "spice_blend",
                        "anchor_system": "SR28",
                        "anchor_code": "171329",
                        "anchor_description": "Spices, mixed spices",
                        "notes": "",
                    }
                )
            with open(src_b, "w", newline="") as fh:
                w = csv.DictWriter(
                    fh,
                    fieldnames=[
                        "concept_key",
                        "parent_concept_phrase",
                        "parent_anchor_system",
                        "parent_anchor_code",
                        "parent_description",
                    ],
                )
                w.writeheader()
                w.writerow(
                    {
                        "concept_key": "cottage cheese|curd||",
                        "parent_concept_phrase": "cottage cheese",
                        "parent_anchor_system": "FNDDS",
                        "parent_anchor_code": "14201200",
                        "parent_description": "Cottage cheese, farmer's",
                    }
                )

            rows, counts = emit_orphan_parent_rows(contracts, seed, src_a, src_b)
            self.assertEqual(counts, {"A": 1, "B": 1, "C": 1})
            self.assertEqual(len(rows), 3)
            write_rows_csv(rows, out)

            with open(out, newline="") as fh:
                read_rows = list(csv.DictReader(fh))
            self.assertEqual(len(read_rows), 3)
            self.assertEqual(list(read_rows[0].keys()), list(SEED_FIELDS))
            canonical = {r["canonical_concept"] for r in read_rows}
            self.assertEqual(canonical, {"garam masala|||", "cottage cheese|||", "adobo|||"})


class TestSourceLoaders(unittest.TestCase):
    def test_load_source_a_handles_missing(self):
        self.assertEqual(load_source_a(Path("/nonexistent/path_a.csv")), {})

    def test_load_source_b_handles_missing(self):
        self.assertEqual(load_source_b(Path("/nonexistent/path_b.csv")), {})


if __name__ == "__main__":
    unittest.main()
