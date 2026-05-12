import csv
import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent.parent
SCRIPT = ROOT / "implementation" / "build_comprehensive_fix_plan.py"
PLAN = ROOT / "implementation" / "output" / "comprehensive_fix_plan.md"
INVENTORY = ROOT / "implementation" / "output" / "comprehensive_fix_inventory.csv"


class BuildComprehensiveFixPlanTest(unittest.TestCase):
    def test_plan_and_inventory_are_generated(self) -> None:
        subprocess.run([sys.executable, str(SCRIPT)], check=True, cwd=str(ROOT))

        self.assertTrue(PLAN.exists())
        self.assertTrue(INVENTORY.exists())

        plan_text = PLAN.read_text(encoding="utf-8")
        self.assertIn("## Fix Waves", plan_text)
        self.assertIn("Wave 0: Truth And Observability", plan_text)
        self.assertIn("product_covered_needs_contract_audit", plan_text)

        with INVENTORY.open(newline="", encoding="utf-8-sig") as fh:
            rows = list(csv.DictReader(fh))

        class_ids = {row["class_id"] for row in rows}
        self.assertIn("observability_top2500_coverage_invalid", class_ids)
        self.assertIn("product_contract_failed_candidates", class_ids)
        self.assertIn("whole_map_missing_leaf_quarantine", class_ids)
        self.assertTrue(
            {
                "observability_missing_wrong_product_recipe_audit",
                "observability_wrong_product_queue_bootstrapped",
            }
            & class_ids
        )


if __name__ == "__main__":
    unittest.main()
