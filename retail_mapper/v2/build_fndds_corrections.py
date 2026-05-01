#!/usr/bin/env python3
"""Build fndds_corrections.csv from DeepSeek decisions.

Reads:
  - fndds_cluster_decisions.jsonl  (cluster-level decisions from DeepSeek)
  - fndds_disagreements.csv         (the original disagreement list)

For each disagreement row, looks up its cluster decision and chooses the
corrected FNDDS code:
  - rule = "prefer_ours"   → no correction (ours_code stands)
  - rule = "prefer_master" → corrected to master_code
  - rule = "prefer_other"  → corrected to rule_fndds
  - rule = "per_row_required" → use per_row_decisions[fdc_id].chosen_code

Writes:
  retail_mapper/v2/fndds_corrections.csv

Columns: fdc_id, title, old_code, old_desc, new_code, new_desc,
         source (cluster|per_row), rule, rationale, confidence

Idempotent: re-running rebuilds the CSV from current decisions.
"""
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
V2 = REPO / "retail_mapper" / "v2"
DISAGREEMENTS = V2 / "fndds_disagreements.csv"
CLUSTER_DECISIONS = V2 / "fndds_cluster_decisions.jsonl"
PERROW_DECISIONS = V2 / "fndds_perrow_decisions.jsonl"
OUT = V2 / "fndds_corrections.csv"

csv.field_size_limit(sys.maxsize)


def load_fndds_descs() -> dict[str, str]:
    """Load FNDDS code -> description from MainFoodDesc16.csv."""
    out: dict[str, str] = {}
    for path in [
        REPO / "data" / "fndds" / "MainFoodDesc16.csv",
        Path("/Users/jamiebarton/Desktop/Hestia/Hestia/Resources/MainFoodDesc.csv"),
    ]:
        if not path.exists():
            continue
        with path.open(encoding="utf-8", errors="replace") as fh:
            for r in csv.DictReader(fh):
                code = (r.get("Food code") or "").strip()
                desc = (r.get("Main food description") or "").strip()
                if code and desc and code not in out:
                    out[code] = desc
    return out


def build_desc_index(fndds_desc: dict[str, str]) -> dict[str, set[str]]:
    """Build a token-set index over FNDDS descriptions for fuzzy lookup.
    Maps each lowercase token to the set of FNDDS codes whose desc contains
    that token. Used to find the closest real FNDDS code for a free-form
    description from DeepSeek."""
    import re
    rx = re.compile(r"[A-Za-z0-9]+")
    index: dict[str, set[str]] = {}
    for code, desc in fndds_desc.items():
        for tok in rx.findall(desc.lower()):
            if len(tok) > 2:
                index.setdefault(tok, set()).add(code)
    return index


def _token_overlap(a: str, b: str) -> float:
    """Jaccard token overlap between two desc strings."""
    import re
    rx = re.compile(r"[A-Za-z0-9]+")
    ta = {t for t in rx.findall((a or "").lower()) if len(t) > 2}
    tb = {t for t in rx.findall((b or "").lower()) if len(t) > 2}
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def lookup_fndds_by_desc(desc: str, index: dict[str, set[str]],
                         fndds_desc: dict[str, str]) -> tuple[str, float]:
    """Given a free-form description, find the best-matching real FNDDS
    code. Returns (code, score). Score = Jaccard overlap of tokens between
    the input desc and the FNDDS desc, weighted by word match.
    Returns ("", 0) if nothing scores above 0.2.
    """
    import re
    rx = re.compile(r"[A-Za-z0-9]+")
    desc_tokens = {t for t in rx.findall(desc.lower()) if len(t) > 2}
    if not desc_tokens:
        return ("", 0.0)
    # Candidate codes: every code that shares at least one token
    candidates: set[str] = set()
    for tok in desc_tokens:
        candidates.update(index.get(tok, set()))
    if not candidates:
        return ("", 0.0)
    best_code = ""
    best_score = 0.0
    for code in candidates:
        cdesc = fndds_desc.get(code, "")
        ctokens = {t for t in rx.findall(cdesc.lower()) if len(t) > 2}
        if not ctokens:
            continue
        # Jaccard overlap
        inter = len(desc_tokens & ctokens)
        union = len(desc_tokens | ctokens)
        score = inter / union if union else 0.0
        if score > best_score:
            best_score = score
            best_code = code
    if best_score < 0.2:
        return ("", best_score)
    return (best_code, best_score)


def main() -> None:
    if not DISAGREEMENTS.exists():
        raise SystemExit(f"missing {DISAGREEMENTS}")
    if not CLUSTER_DECISIONS.exists():
        raise SystemExit(f"missing {CLUSTER_DECISIONS}; run call_deepseek_fndds_resolve.py first")

    fndds_desc = load_fndds_descs()
    print(f"  FNDDS desc lookup: {len(fndds_desc):,} codes")
    desc_index = build_desc_index(fndds_desc)
    print(f"  FNDDS desc token index: {len(desc_index):,} tokens")

    # Load cluster decisions, keyed by (ours_code, master_code)
    cluster_decisions: dict[tuple[str, str], dict] = {}
    with CLUSTER_DECISIONS.open() as fh:
        for line in fh:
            if not line.strip():
                continue
            try:
                d = json.loads(line)
                cluster_decisions[(d["ours_code"], d["master_code"])] = d
            except Exception:
                pass
    print(f"  cluster decisions: {len(cluster_decisions):,}")

    # Build per-row override map from cluster decisions' per_row_decisions.
    # For decisions where DeepSeek chose "other", it returned a free-form
    # food description; we resolve that to a real FNDDS code via fuzzy
    # token-overlap against the 17K-code lookup table.
    perrow_from_cluster: dict[str, dict] = {}
    n_other_resolved = 0
    n_other_unresolved = 0
    for d in cluster_decisions.values():
        ours = d.get("ours_code", "")
        master = d.get("master_code", "")
        for entry in d.get("per_row_decisions") or []:
            fdc = str(entry.get("fdc_id", ""))
            if not fdc:
                continue
            decision = entry.get("decision", "")
            chosen_code = entry.get("chosen_code", "")  # legacy field, may be empty
            chosen_desc = entry.get("chosen_desc", "")
            if decision == "ours":
                resolved_code = ours
            elif decision == "master":
                resolved_code = master
            elif decision == "other" and chosen_desc:
                resolved_code, _ = lookup_fndds_by_desc(chosen_desc, desc_index, fndds_desc)
                if resolved_code:
                    n_other_resolved += 1
                else:
                    n_other_unresolved += 1
                    resolved_code = ""
            else:
                # Legacy chosen_code from older runs (validate exists)
                resolved_code = chosen_code if chosen_code in fndds_desc else ""
            perrow_from_cluster[fdc] = {
                "chosen_code": resolved_code,
                "chosen_desc": chosen_desc,
                "decision": decision,
                "reason": entry.get("reason", ""),
                "cluster_rule": d.get("rule", ""),
                "cluster_rationale": d.get("rationale", ""),
                "cluster_confidence": d.get("confidence", 0),
            }
    print(f"  resolved 'other' descriptions to real FNDDS codes: "
          f"{n_other_resolved:,} resolved, {n_other_unresolved:,} unresolved")

    # Optional: load standalone per-row decisions (if we ran a per-row pass)
    perrow_standalone: dict[str, dict] = {}
    if PERROW_DECISIONS.exists():
        with PERROW_DECISIONS.open() as fh:
            for line in fh:
                if not line.strip():
                    continue
                try:
                    d = json.loads(line)
                    fdc = str(d.get("fdc_id", ""))
                    if fdc:
                        perrow_standalone[fdc] = d
                except Exception:
                    pass
        print(f"  per-row standalone decisions: {len(perrow_standalone):,}")

    # Walk disagreements, emit corrections
    n_total = 0
    n_corrected = 0
    n_no_change = 0
    n_no_decision = 0
    n_perrow = 0
    out_rows: list[dict] = []
    with DISAGREEMENTS.open(encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            n_total += 1
            fdc = row["fdc_id"]
            ours = row["ours_code"]
            master = row["master_code"]
            cluster = cluster_decisions.get((ours, master))
            new_code = ""
            source = ""
            rule = ""
            rationale = ""
            conf = 0.0
            # Prefer standalone per-row if available, else cluster's per_row_decisions,
            # else cluster-level rule
            if fdc in perrow_standalone:
                pr = perrow_standalone[fdc]
                new_code = str(pr.get("chosen_code", ""))
                source = "per_row"
                rule = "per_row"
                rationale = pr.get("reason", "")
                conf = float(pr.get("confidence", 0))
                n_perrow += 1
            elif cluster:
                rule = cluster.get("rule", "")
                conf = float(cluster.get("confidence", 0))
                rationale = cluster.get("rationale", "")
                if rule == "prefer_ours":
                    new_code = ours  # no actual change
                elif rule == "prefer_master":
                    new_code = master
                elif rule == "prefer_other":
                    # DeepSeek returns rule_desc; we resolve to a real code.
                    rule_desc = cluster.get("rule_desc", "") or cluster.get("rule_fndds", "")
                    # 1. Already a real 8-digit code? use it.
                    if rule_desc.isdigit() and rule_desc in fndds_desc:
                        new_code = rule_desc
                    elif rule_desc:
                        # 2. If desc strongly overlaps ours_desc or master_desc,
                        #    redirect to that side (DeepSeek's 'other' was a mis-call).
                        ours_desc_str = row.get("ours_desc", "")
                        master_desc_str = row.get("master_desc", "")
                        master_overlap = _token_overlap(rule_desc, master_desc_str)
                        ours_overlap = _token_overlap(rule_desc, ours_desc_str)
                        if master_overlap >= 0.5 and master_overlap >= ours_overlap:
                            new_code = master
                        elif ours_overlap >= 0.5:
                            new_code = ours
                        else:
                            # 3. Genuine third category — fuzzy lookup against full FNDDS.
                            new_code, _score = lookup_fndds_by_desc(rule_desc, desc_index, fndds_desc)
                    else:
                        new_code = ""
                elif rule == "per_row_required":
                    pr = perrow_from_cluster.get(fdc)
                    if pr:
                        new_code = str(pr.get("chosen_code", ""))
                        rationale = pr.get("reason", "") or rationale
                        n_perrow += 1
                    else:
                        new_code = ""
                source = "cluster_per_row" if rule == "per_row_required" else "cluster_rule"
            else:
                n_no_decision += 1
                continue
            if not new_code:
                n_no_decision += 1
                continue
            if new_code == ours:
                n_no_change += 1
                continue
            n_corrected += 1
            out_rows.append({
                "fdc_id": fdc,
                "title": row["title"],
                "old_code": ours,
                "old_desc": row["ours_desc"],
                "new_code": new_code,
                "new_desc": fndds_desc.get(new_code, ""),
                "source": source,
                "rule": rule,
                "rationale": rationale,
                "confidence": f"{conf:.2f}",
            })

    cols = ["fdc_id", "title", "old_code", "old_desc", "new_code", "new_desc",
            "source", "rule", "rationale", "confidence"]
    with OUT.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        # Sort by confidence ascending so iffy ones are easy to spot
        out_rows.sort(key=lambda r: float(r["confidence"]))
        w.writerows(out_rows)

    print(f"  total disagreement rows:  {n_total:,}")
    print(f"    corrections to apply:   {n_corrected:,}")
    print(f"    no change needed:       {n_no_change:,} (DeepSeek says ours was right)")
    print(f"    per-row decisions used: {n_perrow:,}")
    print(f"    no decision yet:        {n_no_decision:,}")
    print(f"  wrote {OUT.name}")


if __name__ == "__main__":
    main()
