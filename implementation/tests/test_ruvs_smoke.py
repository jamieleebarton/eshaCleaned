import os
import json
import subprocess
from pathlib import Path
import pytest


SMOKE = Path(__file__).resolve().parents[1] / "run_ruvs_smoke.py"


def test_ruvs_package_importable():
    import ruvs
    assert hasattr(ruvs, "__version__")


@pytest.mark.skipif(not os.environ.get("NEBIUS_API_KEY"), reason="NEBIUS_API_KEY not set")
def test_smoke_506745_completes_under_budget():
    result = subprocess.run(
        ["python3", str(SMOKE), "--budget-usd", "0.50"],
        capture_output=True, text=True, timeout=360,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    summary = json.loads(result.stdout.strip().split("}\n")[-1] if "}\n" in result.stdout else result.stdout)
    assert summary["spent_usd"] <= 0.50
    assert summary["elapsed_s"] <= 300
    assert summary["lines"] >= 5
