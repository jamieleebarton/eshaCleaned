from __future__ import annotations

import csv
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent.parent


class EshaPackGuardrailTests(unittest.TestCase):
    def build_pack(self, code: str) -> dict[str, str]:
        with tempfile.TemporaryDirectory() as temp_dir:
            out_root = Path(temp_dir) / "packs"
            index_path = Path(temp_dir) / "index.csv"
            proc = subprocess.run(
                [
                    sys.executable,
                    "implementation/build_esha_code_query_packs.py",
                    "--code",
                    code,
                    "--out-root",
                    str(out_root),
                    "--index-out",
                    str(index_path),
                ],
                cwd=str(ROOT),
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(proc.returncode, 0, msg=proc.stderr)
            with index_path.open(newline="", encoding="utf-8-sig") as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual(len(rows), 1)
            row = rows[0]
            row["pack_markdown"] = Path(row["pack_path"]).read_text(encoding="utf-8")
            return row

    def test_macaroni_and_cheese_guardrail_keeps_macaroni(self) -> None:
        row = self.build_pack("448")
        self.assertIn("macaroni", row["query"].lower())
        self.assertIn("selected_query_attempt: strict", row["pack_markdown"])
        self.assertNotIn("drop_one_core_term:macaroni", row["pack_markdown"])

    def test_swiss_cheese_guardrail_keeps_swiss(self) -> None:
        row = self.build_pack("1027")
        self.assertIn("swiss", row["query"].lower())
        self.assertIn("selected_query_attempt: strict", row["pack_markdown"])
        self.assertNotIn("`(cheese OR cheeses)`", row["pack_markdown"].splitlines()[5])


if __name__ == "__main__":
    unittest.main()
