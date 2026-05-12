"""Acceptance suite — runs against real produced artifact.

Skipped if the artifact is missing (e.g. on a fresh checkout before Task 11 has run).
"""
from __future__ import annotations
import csv
import unittest
from pathlib import Path

ARTIFACT = Path(
    "/Users/jamiebarton/Desktop/esha_audit_bundle/implementation/output/"
    "product_to_canonical_signature.csv"
)


def _load_rows():
    with ARTIFACT.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


@unittest.skipUnless(ARTIFACT.exists(),
                     f"acceptance suite skipped: {ARTIFACT} not built yet")
class AcceptanceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rows = _load_rows()

    def test_artifact_has_full_corpus(self):
        # Spec: 462,647 rows in vM. Allow some slack.
        self.assertGreater(len(self.rows), 462000)

    def test_coverage_threshold(self):
        # >=90% of non-composite products reach an anchor with confidence>=0.5
        non_comp = [r for r in self.rows if r["composite"] == "false"]
        ok = sum(1 for r in non_comp
                 if r["canonical_anchor_id"] and float(r["match_confidence"]) >= 0.5)
        ratio = ok / len(non_comp) if non_comp else 0
        self.assertGreaterEqual(ratio, 0.90, f"non-composite coverage at {ratio:.2%}")

    def test_composite_recall(self):
        # Products containing 'with', 'filled', 'stuffed', or '&' should be flagged composite >=80%
        triggered = [r for r in self.rows
                     if any(t in (r["product_description"] or "").lower().split()
                            for t in ("with", "filled", "stuffed"))
                     or "&" in (r["product_description"] or "")]
        flagged = sum(1 for r in triggered if r["composite"] == "true")
        if triggered:
            self.assertGreaterEqual(flagged / len(triggered), 0.80,
                                    f"composite recall {flagged}/{len(triggered)}")

    def test_assignment_changed_rate_is_substantial_but_not_chaotic(self):
        changed = sum(1 for r in self.rows if r["assignment_changed"] == "true")
        ratio = changed / len(self.rows)
        self.assertGreater(ratio, 0.05, "expected some changes vs vM")
        self.assertLess(ratio, 0.95, "near-total reshuffle suggests pipeline broken")

    def test_hand_picked_examples(self):
        """The examples the user pasted into the brainstorming session."""
        wanted_substrings = [
            "NATURE'S PLACE, ORGANIC APPLES",
            "FRESH SELECTIONS, VEGGIE TRAY WITH APPLES",
            "FRESH-PICKED APPLES",
            "GOLDENS FRESH SLICED APPLES",
            "CHAR-SIU MANAPUA STEAMED BUN WITH ROAST SWEET PORK FILLING",
            "PERI PERI SPICY TOMATO & PEPPER STEAMED RICE",
            "ORGANIC BLUE AGAVE NECTAR PACKETS",
            "ORGANIC RAW BLUE AGAVE NECTAR",
            "AGAVE NECTAR LIQUID SWEETENER",
            "AGAVE NECTAR",
            "MADHAVA, RAW ORGANIC AGAVE NECTAR",
        ]
        by_desc = {(r["product_description"] or "").upper(): r for r in self.rows}
        found = [w for w in wanted_substrings if w in by_desc]
        for desc in found:
            r = by_desc[desc]
            self.assertIn(r["match_layer"],
                          {"L4_lexical", "L5_embedding", "L6_disambiguated",
                           "L7_category", "L7_unresolved"},
                          f"unexpected match_layer for {desc}: {r['match_layer']}")
