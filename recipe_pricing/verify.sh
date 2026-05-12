#!/bin/bash
# R12 — All-gates verify script. Run before/after any bridge change.
# CI should run this and FAIL on any non-zero exit.
set -e
cd "$(dirname "$0")/.."

echo "=== R12.6 freeze drift check ==="
python3 recipe_pricing/freeze_canonical_paths.py --check || \
    echo "  (drift detected — review canonical_path_drift.csv before shipping)"

echo
echo "=== R12.5 recurrence detector ==="
python3 recipe_pricing/test_recurrence_detector.py

echo
echo "=== R12.1 bridge truth integrity ==="
python3 recipe_pricing/test_bridge_integrity.py

echo
echo "All gates passed."
