#!/usr/bin/env python3
"""Apply DeepSeek proposals to the corpus and emit a before/after diff CSV.

Reads:
  - deepseek_proposals.jsonl  (one proposal per leaf path, from DeepSeek)
  - full_corpus_audit.csv     (current state)

Writes:
  - deepseek_subroute_rules.py        — Python module: keyword→child path map
  - deepseek_path_diff.csv            — before/after, one row per (old_path,
                                        new_path) pair with SKU count and 5
                                        sample titles. Sortable by impact.
  - full_corpus_audit_DEEPSEEK.csv    — proposed audit CSV (NOT replacing
                                        the current one until you approve)

The flow:
  1. Read proposals — each proposal has action ∈ {split, keep, reroute_all}.
  2. For "split" actions, build a keyword→new-path map keyed on the OLD
     leaf path. The matcher fires only when canonical_path == old_path AND
     title contains the keyword.
  3. For "reroute_all" actions, rewrite every SKU at that path.
  4. Walk the audit CSV; for each row apply the matching proposal and record
     (old, new, fdc_id, title) for the diff.
  5. Write the proposed audit CSV and the diff CSV.

You then eyeball deepseek_path_diff.csv. If you approve, swap
full_corpus_audit_DEEPSEEK.csv → full_corpus_audit.csv.
"""
from __future__ import annotations

import csv
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
V2 = REPO / "retail_mapper" / "v2"
PROPOSALS = V2 / "deepseek_proposals.jsonl"
SRC = V2 / "full_corpus_audit.csv"
OUT_AUDIT = V2 / "full_corpus_audit_DEEPSEEK.csv"
OUT_DIFF = V2 / "deepseek_path_diff.csv"
OUT_RULES = V2 / "deepseek_subroute_rules.py"

csv.field_size_limit(sys.maxsize)


def main() -> None:
    if not PROPOSALS.exists():
        raise SystemExit(f"missing {PROPOSALS}")
    if not SRC.exists():
        raise SystemExit(f"missing {SRC}")

    # Index proposals by old path
    splits: dict[str, dict[str, str]] = {}     # old_path -> {keyword -> new_path}
    reroutes: dict[str, str] = {}               # old_path -> new_path
    keeps: set[str] = set()
    n_proposals = 0
    with PROPOSALS.open() as fh:
        for line in fh:
            if not line.strip():
                continue
            r = json.loads(line)
            n_proposals += 1
            old = r["path"]
            action = r.get("action", "keep")
            if action == "split":
                subs = r.get("subroutes") or {}
                if subs:
                    splits[old] = {kw.lower(): new for kw, new in subs.items()}
            elif action == "reroute_all":
                new = r.get("new_path")
                if new:
                    reroutes[old] = new
            else:
                keeps.add(old)

    print(f"  loaded {n_proposals:,} proposals")
    print(f"    split:        {len(splits):,}")
    print(f"    reroute_all:  {len(reroutes):,}")
    print(f"    keep:         {len(keeps):,}")

    # Apply to the corpus and collect diff
    diff_counts: Counter[tuple[str, str]] = Counter()
    diff_samples: dict[tuple[str, str], list[str]] = defaultdict(list)
    n_changed = 0
    n_total = 0

    with SRC.open(encoding="utf-8") as src, \
         OUT_AUDIT.open("w", encoding="utf-8", newline="") as dst:
        rdr = csv.DictReader(src)
        wtr = csv.DictWriter(dst, fieldnames=rdr.fieldnames)
        wtr.writeheader()
        for row in rdr:
            n_total += 1
            cp = row.get("canonical_path") or ""
            title = (row.get("title") or "").lower()
            new_cp = cp
            if cp in reroutes:
                new_cp = reroutes[cp]
            elif cp in splits:
                # Pick the FIRST keyword that matches title (longer keywords
                # checked first to prefer most-specific match).
                rules = splits[cp]
                for kw in sorted(rules, key=len, reverse=True):
                    if kw in title:
                        new_cp = rules[kw]
                        break
            if new_cp != cp:
                row["canonical_path"] = new_cp
                n_changed += 1
                key = (cp, new_cp)
                diff_counts[key] += 1
                if len(diff_samples[key]) < 5:
                    diff_samples[key].append(row.get("title", "")[:80])
            wtr.writerow(row)

    print(f"  wrote {OUT_AUDIT.name} ({n_total:,} rows, {n_changed:,} changed)")

    # Emit diff CSV
    with OUT_DIFF.open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["old_path", "new_path", "n_skus", "sample_titles"])
        for (old, new), n in sorted(diff_counts.items(), key=lambda x: -x[1]):
            samples = " || ".join(diff_samples[(old, new)])
            w.writerow([old, new, n, samples])
    print(f"  wrote {OUT_DIFF.name} ({len(diff_counts):,} (old,new) pairs)")

    # Emit subroute rules as a Python module so we can wire them into
    # build_audit_csv.py later (after you approve).
    lines = [
        '"""DeepSeek-proposed sub-route rules for build_audit_csv.py.',
        "",
        "Generated by apply_deepseek_proposals.py.",
        "Wire into build_audit_csv.py with: from deepseek_subroute_rules import",
        "DEEPSEEK_SUBROUTES, DEEPSEEK_REROUTES — apply after FNDDS overrides.",
        '"""',
        "",
        "DEEPSEEK_SUBROUTES: dict[str, dict[str, str]] = {",
    ]
    for old in sorted(splits):
        lines.append(f'    "{old}": {{')
        for kw, new in sorted(splits[old].items()):
            lines.append(f'        "{kw}": "{new}",')
        lines.append("    },")
    lines.append("}")
    lines.append("")
    lines.append("DEEPSEEK_REROUTES: dict[str, str] = {")
    for old in sorted(reroutes):
        lines.append(f'    "{old}": "{reroutes[old]}",')
    lines.append("}")
    lines.append("")
    OUT_RULES.write_text("\n".join(lines))
    print(f"  wrote {OUT_RULES.name}")


if __name__ == "__main__":
    main()
