from __future__ import annotations

import sys
import unittest
from pathlib import Path

import pandas as pd

IMPL = Path(__file__).resolve().parents[1]
if str(IMPL) not in sys.path:
    sys.path.insert(0, str(IMPL))

import apply_vm_cluster_structural_quarantine as quarantine
import build_evidence_first_cluster_proposals as evidence


class ApplyVmClusterStructuralQuarantineTests(unittest.TestCase):
    def test_identity_contract_rejects_fruit_to_biscuit_even_without_dried_word(self) -> None:
        candidate = evidence.EshaCandidate(
            code="16980",
            description="Biscuit, large",
            head="Biscuit",
            head_norm="biscuit",
            desc_terms=frozenset({"biscuit", "large"}),
            terms=frozenset({"biscuit", "large"}),
            canonical_terms=frozenset(),
        )
        row = pd.Series(
            {
                "best_esha_code": "16980",
                "product_description": "ROUNDY'S, LARGE APRICOTS",
                "branded_food_category": "Wholesome Snacks",
            }
        )

        reason = quarantine.row_structural_reject_reason(row, by_code={"16980": candidate}, ingredient_signature="")

        self.assertTrue(reason.startswith("identity_contract:"))
        self.assertIn("apricot", reason)
        self.assertIn("biscuit", reason)


if __name__ == "__main__":
    unittest.main()
