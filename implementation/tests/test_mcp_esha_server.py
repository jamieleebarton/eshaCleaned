import json
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent


class McpEshaServerTest(unittest.TestCase):
    def test_list_tools_returns_thirteen(self):
        proc = subprocess.Popen(
            [sys.executable, "implementation/mcp_esha_server.py", "--self-test"],
            cwd=str(ROOT),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        out, err = proc.communicate(timeout=15)
        self.assertEqual(proc.returncode, 0, msg=err.decode())
        result = json.loads(out.decode())
        self.assertEqual(len(result["tools"]), 13)
        names = {t["name"] for t in result["tools"]}
        for expected in ["get_card", "search_products", "compare_nutrient_fingerprint",
                         "recipe_context", "prior_decisions", "trace_entity"]:
            self.assertIn(expected, names)


if __name__ == "__main__":
    unittest.main()
