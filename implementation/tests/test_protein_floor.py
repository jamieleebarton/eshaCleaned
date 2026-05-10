from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
PLANNER = ROOT / "planner"
if str(PLANNER) not in sys.path:
    sys.path.insert(0, str(PLANNER))

from protein_floor import daily_protein_floor_g


class ProteinFloorTests(unittest.TestCase):
    def test_flat50_keeps_macro_target_out_of_hard_floor(self) -> None:
        self.assertEqual(daily_protein_floor_g(2000.0, 35.0, "flat50"), 50.0)

    def test_pct_mode_is_explicit_audit_switch(self) -> None:
        self.assertEqual(daily_protein_floor_g(2000.0, 35.0, "pct"), 175.0)


if __name__ == "__main__":
    unittest.main()
