"""
Full-corpus superset patch — single-pass scan + patch of the entire product map.

For every product, checks if the current ESHA assignment is a generic subset
of a better ESHA code, and if the product description contains the extra
distinguishing tokens.  Patches are applied directly; no JSON reports.
"""

from __future__ import annotations

import csv
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from swarm_worker import load_esha_index, tokens

csv.field_size_limit(sys.maxsize)

ROOT = Path("/Users/jamiebarton/Desktop/esha_audit_bundle")
PRODUCT_MAP = ROOT / "implementation/output/product_to_best_esha_full_map.vIdentity.csv"
TMP_OUT = PRODUCT_MAP.with_suffix(".vFullSuperset.tmp")


def main():
    print("Loading ESHA index...")
    esha_index, esha_desc_index = load_esha_index()
    print(f"  {len(esha_index):,} ESHA codes")

    # Build reverse token index
    token_to_codes: dict[str, set[str]] = defaultdict(set)
    for code, toks in esha_index.items():
        for t in toks:
            token_to_codes[t].add(code)

    # Phase 1: scan all products and collect patches
    print("\nPhase 1: scanning all products for superset upgrades...")
    patches: dict[str, dict] = {}
    category_counts: Counter = Counter()
    skipped_exact = 0
    n = 0

    with open(PRODUCT_MAP, encoding="utf-8", errors="replace") as f:
        for r in csv.DictReader(f):
            n += 1
            if n % 50000 == 0:
                print(f"  {n:,} scanned", flush=True)

            desc = r.get("product_description", "").strip()
            if not desc:
                continue

            current_code = r.get("best_esha_code", "").strip()
            current_desc = r.get("best_esha_description", "").strip()
            current_reason = r.get("best_esha_change_reason", "").strip()

            # Skip already exact/strong assignments
            if current_reason in ("kept_agree_exact", "replaced_exact",
                                   "filled_exact", "kept_agree_strong",
                                   "superset_patch"):
                skipped_exact += 1
                continue

            prod_toks = set(tokens(desc))
            if not prod_toks:
                continue

            current_toks = set(tokens(current_desc)) if current_desc else esha_index.get(current_code, set())

            # Find candidate ESHA codes that share tokens
            code_scores: Counter = Counter()
            for t in prod_toks:
                for code in token_to_codes.get(t, []):
                    code_scores[code] += 1

            if not code_scores:
                continue

            ranked = []
            for code, shared in code_scores.most_common(100):
                esha_toks = esha_index.get(code, set())
                if not esha_toks:
                    continue
                cov = len(prod_toks & esha_toks) / max(1, len(prod_toks))
                if cov < 0.5:
                    continue
                is_superset = bool(current_toks) and current_toks < esha_toks
                if not is_superset:
                    continue
                extra_vs_current = esha_toks - current_toks
                if not extra_vs_current.issubset(prod_toks):
                    continue
                # Filter marketing words
                marketing_words = {"original", "naturally", "natural", "classic",
                                   "premium", "select", "gourmet", "homestyle",
                                   "traditional", "family", "favorite", "style",
                                   "chunky", "smooth", "creamy", "crunchy"}
                real_extras = extra_vs_current - marketing_words
                if not real_extras:
                    continue

                # Skip dangerous numeric-variant upgrades (milk fat %)
                if current_code in ("18759", "18760", "55040", "35402") \
                        and code in ("18759", "18760", "55040", "35402"):
                    continue

                ranked.append((code, cov, len(extra_vs_current), shared, esha_toks, extra_vs_current))

            if not ranked:
                continue

            # Sort: highest coverage, then fewest extras
            ranked.sort(key=lambda x: (-x[1], x[2], -x[3]))
            best_code, best_cov, _, _, _, _ = ranked[0]

            if best_code == current_code:
                continue

            key = f"{r.get('gtin_upc', '')}::{r.get('fdc_id', '')}"
            patches[key] = {
                "gtin_upc": r.get("gtin_upc", ""),
                "fdc_id": r.get("fdc_id", ""),
                "product_description": desc,
                "current_code": current_code,
                "current_desc": current_desc,
                "proposed_code": best_code,
                "proposed_desc": esha_desc_index.get(best_code, ""),
                "coverage": best_cov,
                "category": r.get("branded_food_category", "").strip(),
            }
            category_counts[r.get("branded_food_category", "").strip()] += 1

    print(f"\n  {n:,} products scanned")
    print(f"  {skipped_exact:,} skipped (already exact/strong/superset)")
    print(f"  {len(patches)} patches identified")

    if not patches:
        print("\nNo patches to apply.")
        return

    print("\nTop categories with patches:")
    for cat, c in category_counts.most_common(20):
        print(f"  {c:>4}  {cat}")

    # Phase 2: apply patches
    print("\nPhase 2: applying patches...")
    n_patched = 0
    n_unchanged = 0
    pattern_counts: Counter = Counter()

    with open(PRODUCT_MAP, encoding="utf-8", errors="replace") as fin, \
         open(TMP_OUT, "w", newline="") as fout:
        reader = csv.DictReader(fin)
        fields = list(reader.fieldnames or [])
        writer = csv.DictWriter(fout, fieldnames=fields)
        writer.writeheader()

        for r in reader:
            key = f"{r.get('gtin_upc', '')}::{r.get('fdc_id', '')}"
            patch = patches.get(key)

            if not patch:
                writer.writerow(r)
                n_unchanged += 1
                continue

            row_out = dict(r)
            row_out["best_esha_code"] = patch["proposed_code"]
            row_out["best_esha_description"] = patch["proposed_desc"]
            row_out["best_esha_change_reason"] = f"superset_patch_from_{patch['current_code']}"
            row_out["assignment_source"] = "superset_patch"
            row_out["score"] = str(round(patch["coverage"], 3))
            row_out["score_num"] = str(round(patch["coverage"], 3))
            writer.writerow(row_out)
            n_patched += 1
            pattern_counts[(patch["current_code"], patch["proposed_code"])] += 1

    TMP_OUT.replace(PRODUCT_MAP)

    print(f"\nApplied {n_patched} patches, {n_unchanged} unchanged")
    print("\nTop patch patterns:")
    for (cc, pc), count in pattern_counts.most_common(15):
        cd = esha_desc_index.get(cc, "")[:30]
        pd = esha_desc_index.get(pc, "")[:30]
        print(f"  {count:>4}  [{cc:>8s}] {cd:30s} -> [{pc:>8s}] {pd:30s}")


if __name__ == "__main__":
    main()
