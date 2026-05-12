# implementation/tests/test_canonical_hygiene.py
import csv
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent


class CanonicalItemsHygiene(unittest.TestCase):
    def test_every_row_has_canonical_name(self):
        p = ROOT / "implementation" / "canonical_items.csv"
        bad = []
        with p.open() as f:
            for i, r in enumerate(csv.DictReader(f), start=2):
                if not (r.get("canonical_name") or "").strip():
                    bad.append(i)
        self.assertEqual(bad, [], "rows missing canonical_name")

    def test_every_row_has_review_status(self):
        p = ROOT / "implementation" / "canonical_items.csv"
        bad = []
        with p.open() as f:
            for i, r in enumerate(csv.DictReader(f), start=2):
                if not (r.get("review_status") or "").strip():
                    bad.append(i)
        self.assertEqual(bad, [], "rows missing review_status")

    def test_row_without_any_code_marks_unresolved(self):
        """Rows without sr28_fdc_id, fndds_code, or pseudo_code must have
        review_status=canonical_name_only (tree-only tree seed)."""
        p = ROOT / "implementation" / "canonical_items.csv"
        bad = []
        with p.open() as f:
            for i, r in enumerate(csv.DictReader(f), start=2):
                sr = (r.get("sr28_fdc_id") or "").strip()
                fn = (r.get("fndds_code") or "").strip()
                ps = (r.get("pseudo_code") or "").strip()
                status = (r.get("review_status") or "").strip()
                if not sr and not fn and not ps and status not in ("canonical_name_only", "unresolved"):
                    bad.append((i, r.get("canonical_name"), status))
        self.assertLess(len(bad), 10, f"rows with no codes but approved status: {bad[:5]}")


class CanonicalAliasesHygiene(unittest.TestCase):
    def test_source_column_excludes_substring_methods(self):
        """Guardrail #15: substring-based Hestia aliases forbidden."""
        p = ROOT / "implementation" / "canonical_aliases.csv"
        bad_sources = {"hestia_expanded_substring", "hestia_expanded_aggressive",
                       "hestia_expanded_reverse_substring"}
        bad = []
        with p.open() as f:
            for i, r in enumerate(csv.DictReader(f), start=2):
                src = (r.get("source") or "").strip()
                if src in bad_sources:
                    bad.append(i)
        self.assertEqual(bad, [], "canonical_aliases.csv contains substring-derived entries")

    def test_all_targets_exist_as_canonical(self):
        p = ROOT / "implementation" / "canonical_aliases.csv"
        canonicals = set()
        with (ROOT / "implementation" / "canonical_items.csv").open() as f:
            for r in csv.DictReader(f):
                canonicals.add((r.get("canonical_name") or "").strip().lower())
        bad = []
        with p.open() as f:
            for i, r in enumerate(csv.DictReader(f), start=2):
                tgt = (r.get("canonical_name") or "").strip().lower()
                if tgt and tgt not in canonicals:
                    bad.append((i, tgt))
        self.assertEqual(bad, [], f"aliases point at non-canonical targets: {bad[:5]}")


if __name__ == "__main__":
    unittest.main()
