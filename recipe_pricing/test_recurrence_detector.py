#!/usr/bin/env python3
"""R12.5 — Recurrence detector (Groundhog-Day lock).

Failure mode we're trying to prevent: in round N we add a rule to
reclassify SKU X to path P. In round N+1 some upstream change re-classifies
X back to its old path, and we add the SAME rule again. After enough
rounds, reclassify_log.csv grows but bugs keep recurring.

This script:
  1. Reads reclassify_log_round*.csv (per-round snapshots) — if they exist
  2. ALSO reads canonical_path_aliases.csv.before_round* snapshots
  3. Detects any (sku_name, target_path) tuple that appears in ≥2 different
     rounds — that's a sign the fix isn't sticking
  4. Detects any alias that gets ADDED then REMOVED then RE-ADDED across
     rounds — same recurrence pattern

Exit code 0 if no recurrence; 1 otherwise. Run as a CI gate.
"""
from __future__ import annotations
import csv, sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PRICING = ROOT / "recipe_pricing"


def collect_reclass_snapshots() -> list[tuple[str, list[dict]]]:
    """Return [(round_label, rows), ...] for each archived reclass log we
    can find. Today we only have the live log; future rounds should snapshot
    via `cp reclassify_log.csv reclassify_log_round12.csv` after apply."""
    snaps: list[tuple[str, list[dict]]] = []
    candidates = sorted(PRICING.glob("reclassify_log_round*.csv"))
    for p in candidates:
        with p.open() as f:
            snaps.append((p.stem, list(csv.DictReader(f))))
    # Always include the live log as the latest snapshot
    live = PRICING / "reclassify_log.csv"
    if live.exists():
        with live.open() as f:
            snaps.append(("reclassify_log_live", list(csv.DictReader(f))))
    return snaps


def collect_alias_snapshots() -> list[tuple[str, list[dict]]]:
    snaps = []
    for p in sorted(PRICING.glob("canonical_path_aliases.csv.before_round*")):
        with p.open() as f:
            snaps.append((p.name, list(csv.DictReader(f))))
    live = PRICING / "canonical_path_aliases.csv"
    if live.exists():
        with live.open() as f:
            snaps.append(("aliases_live", list(csv.DictReader(f))))
    return snaps


def main():
    reclass_snaps = collect_reclass_snapshots()
    alias_snaps = collect_alias_snapshots()

    print(f"Reclass log snapshots: {len(reclass_snaps)}", file=sys.stderr)
    for n, rows in reclass_snaps:
        print(f"  {n}: {len(rows)} rows", file=sys.stderr)
    print(f"Alias snapshots: {len(alias_snaps)}", file=sys.stderr)
    for n, rows in alias_snaps:
        print(f"  {n}: {len(rows)} rows", file=sys.stderr)

    # Recurrence: same (name-prefix, target_path) appears in ≥2 reclass snapshots
    recurrence: dict[tuple, set] = defaultdict(set)
    for label, rows in reclass_snaps:
        for r in rows:
            n = (r.get("name") or "")[:35].lower().strip()
            tp = (r.get("new_path") or "").strip()
            if n and tp:
                recurrence[(n, tp)].add(label)

    repeats = [(k, sorted(v)) for k, v in recurrence.items() if len(v) >= 2]

    # Alias flip-flop detection: same old_path → new_path appears, disappears,
    # re-appears
    alias_history: dict[tuple, list[str]] = defaultdict(list)
    for label, rows in alias_snaps:
        for r in rows:
            o = (r.get("old_path") or "").strip()
            n = (r.get("new_path") or "").strip()
            if o and n: alias_history[(o, n)].append(label)
    flip_flops = []
    for (o, n), seq in alias_history.items():
        if len(seq) >= 2 and seq != sorted(set(seq), key=seq.index):
            flip_flops.append((o, n, seq))

    print(f"\nReclass recurrences (same (sku-prefix, target) in ≥2 rounds): "
          f"{len(repeats):,}", file=sys.stderr)
    if repeats:
        print(f"Top 20:", file=sys.stderr)
        for (n, tp), labs in sorted(repeats, key=lambda x: -len(x[1]))[:20]:
            print(f"  [{len(labs)}× rounds] '{n}' → '{tp}' :: {labs}",
                  file=sys.stderr)

    print(f"\nAlias flip-flops: {len(flip_flops):,}", file=sys.stderr)
    for o, n, seq in flip_flops[:10]:
        print(f"  '{o}' → '{n}' :: {seq}", file=sys.stderr)

    if repeats or flip_flops:
        print(f"\nRECURRENCE DETECTED — see snapshots above. "
              f"Fix root cause, do not re-add the same rule.", file=sys.stderr)
        sys.exit(1)
    print(f"\nNo recurrence detected.", file=sys.stderr)
    sys.exit(0)


if __name__ == "__main__":
    main()
