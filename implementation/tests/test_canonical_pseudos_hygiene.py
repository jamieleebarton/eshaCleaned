import csv
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent


class CanonicalPseudosHygiene(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.p = ROOT / "implementation" / "canonical_pseudos.csv"
        cls.sr28_fdc = set()
        with (ROOT / "data" / "sr28_csv" / "food.csv").open() as f:
            for r in csv.DictReader(f):
                cls.sr28_fdc.add(r["fdc_id"].strip())

    def test_file_exists(self):
        self.assertTrue(self.p.exists(), "run phase12_seed_pseudos_from_cleaned.py first")

    def test_required_columns_present(self):
        with self.p.open() as f:
            reader = csv.DictReader(f)
            required = {"pseudo_code", "canonical_name", "nutrition_proxy_sr28_fdc_id",
                        "portion_overrides_json", "product_file", "proxy_rationale",
                        "macro_trivial", "review_status", "source", "notes"}
            self.assertTrue(required.issubset(set(reader.fieldnames or [])),
                            f"missing columns: {required - set(reader.fieldnames or [])}")

    def test_every_pseudo_has_sr28_grounding(self):
        bad = []
        with self.p.open() as f:
            for i, r in enumerate(csv.DictReader(f), start=2):
                if (r.get("review_status") or "").strip() in ("catch_all_split", "ungrounded"):
                    continue  # legitimate unresolved tail
                proxy = (r.get("nutrition_proxy_sr28_fdc_id") or "").strip()
                if not proxy:
                    bad.append((i, r.get("pseudo_code"), "no proxy"))
                elif proxy not in self.sr28_fdc:
                    bad.append((i, r.get("pseudo_code"), f"proxy {proxy} not in SR28"))
        self.assertEqual(bad, [], f"pseudos without valid SR28 grounding: {bad[:5]}")

    def test_product_file_exists_for_adopted(self):
        bad = []
        with self.p.open() as f:
            for i, r in enumerate(csv.DictReader(f), start=2):
                if (r.get("review_status") or "").strip() != "approved":
                    continue
                pf = (r.get("product_file") or "").strip()
                if pf and not Path(pf).exists():
                    bad.append((i, pf))
        self.assertEqual(bad, [], f"approved pseudos with missing product_file: {bad[:5]}")

    def test_pseudo_code_namespaces_clean(self):
        """Hestia codes are numeric; ours are P-*. No overlap, no mixed IDs."""
        seen_numeric = set()
        seen_p = set()
        with self.p.open() as f:
            for r in csv.DictReader(f):
                code = (r.get("pseudo_code") or "").strip()
                if not code:
                    continue
                if code.startswith("P-"):
                    seen_p.add(code)
                elif code.isdigit():
                    seen_numeric.add(code)
                else:
                    self.fail(f"pseudo_code {code!r} is neither numeric nor P-*")


if __name__ == "__main__":
    unittest.main()
