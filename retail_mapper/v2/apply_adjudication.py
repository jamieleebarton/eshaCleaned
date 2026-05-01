#!/usr/bin/env python3
"""Apply adjudication decisions, with me as final judge.

Reads:
  - retail_mapper/v2/adjudication_decisions.jsonl (DeepSeek's verdicts)

Filters and applies:
  - decision="current": no change (reject the centroid move)
  - decision="proposed": adopt centroid's proposed_path IF DeepSeek confidence ≥ 0.85
  - decision="other": resolve chosen_desc via Jaccard against existing tree;
    apply only if Jaccard ≥ 0.55 AND DeepSeek confidence ≥ 0.85

Anything below confidence 0.85 is logged but NOT applied.

Output: retail_mapper/v2/adjudication_corrections.csv
        retail_mapper/v2/adjudication_skipped.csv (low-confidence + unresolvable)
"""
from __future__ import annotations

import csv
import json
import re
import sys
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
V2 = REPO / "retail_mapper" / "v2"
DECISIONS = V2 / "adjudication_decisions.jsonl"
AUDIT = V2 / "full_corpus_audit.csv"
OUT_APPLY = V2 / "adjudication_corrections.csv"
OUT_SKIP = V2 / "adjudication_skipped.csv"

CONF_MIN = 0.85
JACCARD_MIN_OTHER = 0.55

csv.field_size_limit(sys.maxsize)

WORD_RX = re.compile(r"[A-Za-z0-9]+")


def tokens(s: str) -> set[str]:
    return {t.lower() for t in WORD_RX.findall(s) if len(t) > 2}


def main() -> None:
    if not DECISIONS.exists():
        raise SystemExit(f"missing {DECISIONS}")

    # Build set of existing canonical paths from current audit
    print("  reading audit to build known-paths set...")
    known_paths: set[str] = set()
    with AUDIT.open(encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            cp = r.get("canonical_path", "").strip()
            if cp:
                known_paths.add(cp)
    print(f"    known canonical_paths: {len(known_paths):,}")

    # Pre-tokenize known paths for Jaccard lookup
    paths_tokenized = [(p, tokens(p)) for p in known_paths]

    apply_rows: list[dict] = []
    skip_rows: list[dict] = []
    decision_counts: Counter = Counter()
    apply_breakdown: Counter = Counter()

    with DECISIONS.open() as fh:
        for line in fh:
            if not line.strip():
                continue
            try:
                d = json.loads(line)
            except Exception:
                continue
            decision = d.get("decision", "")
            confidence = float(d.get("confidence", 0))
            decision_counts[decision] += 1
            fdc = d.get("fdc_id", "")
            cur = d.get("current_path", "")
            prop = d.get("centroid_proposed_path", "")
            title = d.get("title", "")[:80]
            rationale = d.get("rationale", "")[:160]

            if decision == "current":
                # Reject centroid; no change. Don't write a correction.
                apply_breakdown["rejected_centroid"] += 1
                continue
            if confidence < CONF_MIN:
                skip_rows.append({
                    "fdc_id": fdc, "title": title, "current_path": cur,
                    "centroid_path": prop, "decision": decision,
                    "chosen_desc": d.get("chosen_desc", ""),
                    "confidence": f"{confidence:.2f}",
                    "skip_reason": "low_confidence",
                    "rationale": rationale,
                })
                continue
            if decision == "proposed":
                if prop in known_paths:
                    apply_rows.append({
                        "fdc_id": fdc, "title": title,
                        "old_path": cur, "new_path": prop,
                        "rationale": f"adjudicated proposed: {rationale}",
                        "confidence": f"{confidence:.2f}",
                    })
                    apply_breakdown["accepted_proposed"] += 1
                else:
                    skip_rows.append({
                        "fdc_id": fdc, "title": title, "current_path": cur,
                        "centroid_path": prop, "decision": decision,
                        "chosen_desc": "", "confidence": f"{confidence:.2f}",
                        "skip_reason": "proposed_not_in_tree",
                        "rationale": rationale,
                    })
            elif decision == "other":
                desc = (d.get("chosen_desc") or "").strip()
                if not desc:
                    skip_rows.append({
                        "fdc_id": fdc, "title": title, "current_path": cur,
                        "centroid_path": prop, "decision": decision,
                        "chosen_desc": "", "confidence": f"{confidence:.2f}",
                        "skip_reason": "other_no_desc",
                        "rationale": rationale,
                    })
                    continue
                desc_tokens = tokens(desc)
                if not desc_tokens:
                    continue
                # Best-Jaccard over existing tree
                best_score = 0.0
                best_path = ""
                for p, p_toks in paths_tokenized:
                    if not p_toks:
                        continue
                    j = len(desc_tokens & p_toks) / len(desc_tokens | p_toks)
                    if j > best_score:
                        best_score = j
                        best_path = p
                if best_score >= JACCARD_MIN_OTHER and best_path != cur:
                    apply_rows.append({
                        "fdc_id": fdc, "title": title,
                        "old_path": cur, "new_path": best_path,
                        "rationale": f"adjudicated other [{desc}] j={best_score:.2f}: {rationale}",
                        "confidence": f"{confidence:.2f}",
                    })
                    apply_breakdown["accepted_other_resolved"] += 1
                else:
                    skip_rows.append({
                        "fdc_id": fdc, "title": title, "current_path": cur,
                        "centroid_path": prop, "decision": decision,
                        "chosen_desc": desc, "confidence": f"{confidence:.2f}",
                        "skip_reason": f"other_jaccard_low_{best_score:.2f}",
                        "rationale": rationale,
                    })

    cols_apply = ["fdc_id", "title", "old_path", "new_path", "rationale", "confidence"]
    with OUT_APPLY.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=cols_apply)
        w.writeheader()
        w.writerows(apply_rows)

    cols_skip = ["fdc_id", "title", "current_path", "centroid_path", "decision",
                 "chosen_desc", "confidence", "skip_reason", "rationale"]
    with OUT_SKIP.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=cols_skip)
        w.writeheader()
        w.writerows(skip_rows)

    print(f"\n  decisions seen:")
    for k, v in decision_counts.most_common():
        print(f"    {k:>10}: {v:,}")
    print(f"\n  apply breakdown:")
    for k, v in apply_breakdown.most_common():
        print(f"    {k}: {v:,}")
    print(f"\n  TO APPLY: {len(apply_rows):,}")
    print(f"  SKIPPED:  {len(skip_rows):,}")
    print(f"\n  wrote {OUT_APPLY.name}")
    print(f"  wrote {OUT_SKIP.name}")


if __name__ == "__main__":
    main()
