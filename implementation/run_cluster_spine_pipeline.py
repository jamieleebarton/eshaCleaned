from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


STEPS = [
    "implementation/build_esha_spine.py",
    "implementation/build_product_evidence_clusters_v2.py",
    "implementation/assign_clusters_to_esha.py",
    "implementation/project_cluster_assignments_to_products.py",
    "implementation/validate_cluster_assignments.py",
    "implementation/build_cluster_graph.py",
]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-graph", action="store_true")
    args = parser.parse_args()

    steps = STEPS[:-1] if args.skip_graph else STEPS
    for step in steps:
        print(f"\n=== {step} ===", flush=True)
        subprocess.run([sys.executable, step], cwd=ROOT, check=True)


if __name__ == "__main__":
    main()
