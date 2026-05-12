"""
Per-category audit of vIdentity.csv.

Groups all 462k products by `branded_food_category`. For each category,
identifies "fix candidates" — rows where the current RFT route is
suspect (WEAK/NEEDS_NEW/NO_MATCH, or where the canonical drifts from the
product description). Deduplicates by (concept, verdict) so an agent
sees ~10-100 unique route patterns per category instead of thousands of
duplicate rows.

For each unique pattern, finds the top-3 alternative concepts using a
relaxed match (max shared identity tokens, ignoring position filter)
so the audit surfaces concepts the strict router rejected.

Output: implementation/category_audits/{slug}.csv — one file per category.
       implementation/category_audits/_summary.csv — category-level rollup.

Usage: python rft_category_audit.py [N_TOP_CATEGORIES]
"""

from __future__ import annotations

import csv
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from rft_concept import (
    build_concept_index, build_token_to_concepts, route,
    concept_tokens_from_text, FIRST_FRAG_DESCRIPTORS, IDENTITY_IMPLICATIONS,
)
import rft_concept as rftc

csv.field_size_limit(sys.maxsize)

ROOT = Path("/Users/jamiebarton/Desktop/esha_audit_bundle")
DEFAULT_IN = ROOT / "implementation/output/product_to_best_esha_full_map.vIdentity.csv"
OUT_DIR = ROOT / "implementation/category_audits"
OUT_DIR.mkdir(exist_ok=True)

CANDIDATE_VERDICTS = {"WEAK", "NEEDS_NEW_CONCEPT", "NO_MATCH", "NO_IDENTITY"}
SLUG_RE = re.compile(r"[^a-z0-9]+")


def slug(text: str) -> str:
    s = SLUG_RE.sub("_", (text or "").lower()).strip("_")
    return s or "uncategorized"


def find_alternatives(surface: str, concepts: dict, token_idx: dict,
                       current_concept_id: frozenset, k: int = 3) -> list:
    """Find up to k concept alternatives that are STRONGER candidates than
    the current matched concept, ignoring the strict position filter."""
    surf = concept_tokens_from_text(surface)
    if not surf:
        return []
    counter: Counter = Counter()
    for t in surf:
        for cid in token_idx.get(t, ()):
            counter[cid] += 1
    candidates = []
    for cid, n_shared in counter.most_common(50):
        if cid == current_concept_id:
            continue
        c = concepts[cid]
        shared = surf & cid
        missing = surf - cid
        extra = cid - surf
        if len(shared) < 2 and len(surf) >= 2:
            continue
        # Identity-coverage score: surface coverage minus extras penalty
        cov_surf = len(shared) / max(len(surf), 1)
        cov_concept = len(shared) / max(len(cid), 1)
        score = cov_surf + 0.3 * cov_concept - 0.05 * len(extra)
        candidates.append((score, c, shared, missing, extra))
    candidates.sort(key=lambda x: -x[0])
    out = []
    for score, c, shared, missing, extra in candidates[:k]:
        out.append({
            "concept": "|".join(sorted(c.concept_id)),
            "canonical": c.canonical_name,
            "score": f"{score:.2f}",
            "shared": "|".join(sorted(shared)),
            "missing": "|".join(sorted(missing)),
            "extra": "|".join(sorted(extra)),
        })
    return out


def main():
    n_top = int(sys.argv[1]) if len(sys.argv) > 1 else 0  # 0 = all

    print(f"Reading {DEFAULT_IN}")
    print("Building concept index…", flush=True)
    concepts = build_concept_index()
    token_idx = build_token_to_concepts(concepts)
    print(f"  {len(concepts):,} concepts")

    # Group by category. Within each category, group by (rft_verdict,
    # rft_concept_tokens) — these are the unique route patterns we'll
    # attack as units.
    cat_patterns: dict[str, dict] = defaultdict(
        lambda: defaultdict(lambda: {"count": 0, "examples": []})
    )
    cat_totals: Counter = Counter()

    with DEFAULT_IN.open(encoding="utf-8", errors="replace") as f:
        for r in csv.DictReader(f):
            cat = (r.get("branded_food_category") or "").strip()
            cat = cat or "(uncategorized)"
            cat_totals[cat] += 1

            v = (r.get("rft_verdict") or "").strip()
            if v not in CANDIDATE_VERDICTS:
                continue

            ctoks = (r.get("rft_concept_tokens") or "").strip()
            cname = (r.get("rft_canonical_name") or "").strip()
            key = (v, ctoks, cname)
            slot = cat_patterns[cat][key]
            slot["count"] += 1
            if len(slot["examples"]) < 5:
                desc = (r.get("product_description") or "").strip()
                slot["examples"].append({
                    "desc": desc,
                    "missing": r.get("rft_missing", ""),
                    "extra": r.get("rft_extra", ""),
                    "best_esha_code": r.get("best_esha_code", ""),
                    "best_esha_description": r.get("best_esha_description", ""),
                })

    # Rank categories by candidate volume
    cat_candidate_total = {cat: sum(p["count"] for p in pats.values())
                           for cat, pats in cat_patterns.items()}
    sorted_cats = sorted(cat_patterns.keys(),
                         key=lambda c: -cat_candidate_total[c])
    if n_top:
        sorted_cats = sorted_cats[:n_top]

    # Write summary
    summary_path = OUT_DIR / "_summary.csv"
    with summary_path.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["category", "total_in_category",
                    "candidates", "candidate_pct",
                    "n_unique_patterns", "audit_file"])
        for cat in sorted_cats:
            total = cat_totals[cat]
            cand = cat_candidate_total[cat]
            pct = 100 * cand / max(total, 1)
            n_pat = len(cat_patterns[cat])
            w.writerow([cat, total, cand, f"{pct:.1f}%", n_pat,
                        f"{slug(cat)}.csv"])
    print(f"\nSummary: {summary_path}")
    print(f"Top 15 categories by candidate volume:")
    for cat in sorted_cats[:15]:
        cand = cat_candidate_total[cat]
        total = cat_totals[cat]
        n_pat = len(cat_patterns[cat])
        print(f"  {cat[:55]:55s}  cand={cand:>6,}/{total:<7,}  patterns={n_pat:>4}")

    # Per-category audit files
    print("\nWriting per-category audits…", flush=True)
    for cat in sorted_cats:
        patterns = cat_patterns[cat]
        out_path = OUT_DIR / f"{slug(cat)}.csv"
        rows = []
        # Sort patterns by count desc — biggest opportunities first
        sorted_patterns = sorted(patterns.items(), key=lambda kv: -kv[1]["count"])
        for (v, ctoks, cname), info in sorted_patterns:
            ex = info["examples"][0] if info["examples"] else {}
            # Find top alternatives for the first example surface
            current_cid = frozenset(t for t in ctoks.split("|") if t) if ctoks else frozenset()
            alts = find_alternatives(ex.get("desc", ""), concepts, token_idx,
                                     current_cid, k=3)
            rows.append({
                "category": cat,
                "count": info["count"],
                "verdict": v,
                "current_concept": ctoks,
                "current_canonical": cname,
                "example_1": ex.get("desc", ""),
                "example_1_missing": ex.get("missing", ""),
                "example_1_extra": ex.get("extra", ""),
                "example_1_best_esha_code": ex.get("best_esha_code", ""),
                "example_1_best_esha_desc": ex.get("best_esha_description", ""),
                "examples_more": " | ".join(
                    e["desc"] for e in info["examples"][1:5]
                ),
                "alt1_concept": alts[0]["concept"] if len(alts) >= 1 else "",
                "alt1_canonical": alts[0]["canonical"] if len(alts) >= 1 else "",
                "alt1_score": alts[0]["score"] if len(alts) >= 1 else "",
                "alt1_shared": alts[0]["shared"] if len(alts) >= 1 else "",
                "alt1_missing": alts[0]["missing"] if len(alts) >= 1 else "",
                "alt1_extra": alts[0]["extra"] if len(alts) >= 1 else "",
                "alt2_concept": alts[1]["concept"] if len(alts) >= 2 else "",
                "alt2_canonical": alts[1]["canonical"] if len(alts) >= 2 else "",
                "alt2_score": alts[1]["score"] if len(alts) >= 2 else "",
                "alt3_concept": alts[2]["concept"] if len(alts) >= 3 else "",
                "alt3_canonical": alts[2]["canonical"] if len(alts) >= 3 else "",
            })
        with out_path.open("w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys()) if rows else
                               ["category", "count"])
            w.writeheader()
            w.writerows(rows)
    print(f"  wrote {len(sorted_cats)} category files to {OUT_DIR}/")


if __name__ == "__main__":
    main()
