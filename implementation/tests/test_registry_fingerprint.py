from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path


IMPLEMENTATION_ROOT = Path(__file__).resolve().parents[1]
if str(IMPLEMENTATION_ROOT) not in sys.path:
    sys.path.insert(0, str(IMPLEMENTATION_ROOT))

from registry_fingerprint import (  # noqa: E402
    assert_fingerprint_current,
    registry_fingerprint_id,
    sidecar_path,
    write_fingerprint_sidecar,
)


class RegistryFingerprintTests(unittest.TestCase):
    def test_fingerprint_changes_when_registry_file_changes(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "rules.csv"
            path.write_text("rule_id,status\nr1,approved\n", encoding="utf-8")
            first = registry_fingerprint_id([path])
            path.write_text("rule_id,status\nr1,approved\nr2,approved\n", encoding="utf-8")
            second = registry_fingerprint_id([path])
            self.assertNotEqual(first, second)

    def test_sidecar_validates_current_and_rejects_stale(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            registry = Path(temp_dir) / "rules.csv"
            output = Path(temp_dir) / "queue.csv"
            registry.write_text("rule_id,status\nr1,approved\n", encoding="utf-8")
            output.write_text("x\n1\n", encoding="utf-8")
            sidecar = write_fingerprint_sidecar(output, [registry])
            self.assertEqual(sidecar_path(output), sidecar)
            assert_fingerprint_current(sidecar, [registry])

            registry.write_text("rule_id,status\nr1,approved\nr2,approved\n", encoding="utf-8")
            with self.assertRaises(RuntimeError):
                assert_fingerprint_current(sidecar, [registry])


if __name__ == "__main__":
    unittest.main()
