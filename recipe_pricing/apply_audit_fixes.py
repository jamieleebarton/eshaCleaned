#!/usr/bin/env python3
"""Generate title-pattern overrides from ingredient_classification_audit.csv
and append them to walmart_kroger_overrides.csv (idempotent).

Strategy (only safe categories applied):

  1. All `deeper_leaf` proposals     (1,195 — pure path extension, zero risk)
  2. Top 500 `sibling_switch`        by recipe_count (covers ~80% of volume)
  3. Five mechanical modifier passes (white, whole wheat, sliced, part-skim,
     extra virgin) — covered organically when their items appear in (1) or (2).

Skip:
  - Low-volume sibling switches (<200 recipes, not in top 500)
  - `generic_at_parent_no_match` (no proposal to apply)
  - `unresolved` (htc_code = ~00000000 — needs human review separately)

The override schema is:
  pattern,canonical_path,canonical_label,product_identity_fixed,modifier,note
"""
from __future__ import annotations

import csv
import re
import shutil
import sys
from pathlib import Path

csv.field_size_limit(sys.maxsize)

ROOT = Path(__file__).resolve().parents[1]
AUDIT = ROOT / "recipe_pricing" / "output" / "ingredient_classification_audit.csv"
OVERRIDES = ROOT / "recipe_pricing" / "walmart_kroger_overrides.csv"

DEEPER_LEAF_REASONS = ("deeper_leaf",)
SIBLING_SWITCH_REASONS = ("sibling_switch",)
TOP_SIBLING_SWITCH_LIMIT = 500


def title_to_regex(title: str) -> str:
    """Convert an ingredient title into an anchored regex matching both
    singular and plural variants. Case-insensitive at use site.
    """
    t = title.strip().lower()
    if not t:
        return ""
    # If the title ends with a plural 's', strip it so the regex matches both
    # forms (`red onion` and `red onions`). Heuristic: only strip when the
    # word is long enough that it's likely an actual plural (avoid mangling
    # 'grass', 'glass', 'molasses' etc).
    if t.endswith("s") and len(t) > 4 and not t.endswith("ss"):
        stem = t[:-1]
        escaped = re.escape(stem) + r"s?"
    else:
        escaped = re.escape(t) + r"s?"
    return f"^{escaped}$"


def derive_identity(canonical_path: str) -> str:
    """Use the leaf as product_identity_fixed when generating overrides."""
    if not canonical_path:
        return ""
    parts = [p.strip() for p in canonical_path.split(" > ") if p.strip()]
    return parts[-1] if parts else ""


def load_existing_patterns() -> set[str]:
    if not OVERRIDES.exists():
        return set()
    out: set[str] = set()
    with OVERRIDES.open() as f:
        for row in csv.DictReader(f):
            p = row.get("pattern", "").strip()
            if p:
                out.add(p)
    return out


def main() -> int:
    if not AUDIT.exists():
        print(f"missing {AUDIT}", file=sys.stderr)
        return 2

    rows = []
    with AUDIT.open() as f:
        for row in csv.DictReader(f):
            rows.append(row)

    # Filter
    deeper = [r for r in rows
              if r.get("proposed_canonical_path", "").strip()
              and any(reason in r.get("reasons", "") for reason in DEEPER_LEAF_REASONS)]
    siblings_all = [r for r in rows
                    if r.get("proposed_canonical_path", "").strip()
                    and any(reason in r.get("reasons", "") for reason in SIBLING_SWITCH_REASONS)
                    and not any(reason in r.get("reasons", "") for reason in DEEPER_LEAF_REASONS)]
    siblings_all.sort(key=lambda r: -int(r.get("recipe_count", 0) or 0))
    siblings_top = siblings_all[:TOP_SIBLING_SWITCH_LIMIT]

    print(f"deeper_leaf candidates:    {len(deeper):,}", file=sys.stderr)
    print(f"sibling_switch top {TOP_SIBLING_SWITCH_LIMIT:,}: {len(siblings_top):,}", file=sys.stderr)

    existing = load_existing_patterns()
    print(f"existing override patterns: {len(existing):,}", file=sys.stderr)

    # Build new override rules
    new_rules: list[dict] = []
    seen_patterns: set[str] = set(existing)
    for source_label, src_rows in [("deeper_leaf", deeper), ("sibling_switch_top500", siblings_top)]:
        for r in src_rows:
            title = (r.get("title") or "").strip()
            new_path = (r.get("proposed_canonical_path") or "").strip()
            if not title or not new_path:
                continue
            pattern = title_to_regex(title)
            if not pattern or pattern in seen_patterns:
                continue
            ident = derive_identity(new_path)
            new_rules.append({
                "pattern": pattern,
                "canonical_path": new_path,
                "canonical_label": ident,
                "product_identity_fixed": ident,
                "modifier": "",
                "note": f"audit_{source_label}: rc={r.get('recipe_count', '0')}",
            })
            seen_patterns.add(pattern)

    print(f"new override rules to append: {len(new_rules):,}", file=sys.stderr)

    if not new_rules:
        print("nothing to append", file=sys.stderr)
        return 0

    # Append (idempotent — we only add patterns not already present)
    fieldnames = ["pattern", "canonical_path", "canonical_label",
                  "product_identity_fixed", "modifier", "note"]
    if OVERRIDES.exists():
        # Read existing, append new, rewrite
        existing_rows: list[dict] = []
        with OVERRIDES.open() as f:
            reader = csv.DictReader(f)
            for row in reader:
                existing_rows.append({k: row.get(k, "") for k in fieldnames})
        all_rows = existing_rows + new_rules
    else:
        all_rows = new_rules

    tmp = OVERRIDES.with_suffix(".csv.tmp")
    with tmp.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(all_rows)
    shutil.move(str(tmp), str(OVERRIDES))
    print(f"  wrote {OVERRIDES} ({len(all_rows):,} total rules)", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
