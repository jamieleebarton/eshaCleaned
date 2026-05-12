import json
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent


class RunReleaseBlockerBatchTest(unittest.TestCase):
    def test_dry_run_emits_plan_without_mutating_registries(self):
        result = subprocess.run(
            [sys.executable, "implementation/run_release_blocker_batch.py",
             "--limit", "1", "--dry-run"],
            cwd=str(ROOT),
            capture_output=True,
            timeout=120,
        )
        self.assertEqual(result.returncode, 0, msg=result.stderr.decode())
        plan = json.loads(result.stdout.decode())
        self.assertIn("blockers", plan)
        self.assertEqual(len(plan["blockers"]), 1)
        self.assertIn("normalized_item", plan["blockers"][0])
        self.assertEqual(plan["mode"], "dry-run")
        self.assertIn("fixture_entry_state", plan)


if __name__ == "__main__":
    unittest.main()
