"""
Targeted patch: re-route ONLY products whose descriptions contain one of the
new PHRASE_ALIASES keys.  This avoids a full 462k re-run of rft_scale_concept.py.

Updates product_to_best_esha_full_map.vIdentity.csv in place for affected rows.
Preserves all other rows exactly.
"""

from __future__ import annotations

import csv
import gzip
import sys
import time
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from rft import PHRASE_ALIASES
from rft_concept import build_concept_index, build_token_to_concepts, route
from rft_scale_concept import (
    strip_known_brand_columns, strip_brand_registry,
    apply_brand_food_aliases,
)

csv.field_size_limit(sys.maxsize)

ROOT = Path("/Users/jamiebarton/Desktop/esha_audit_bundle")
PRODUCT_MAP = ROOT / "implementation/output/product_to_best_esha_full_map.vIdentity.csv"
TMP_OUT = PRODUCT_MAP.with_suffix(".vPhraseAlias.tmp")


def main():
    print("Building concept index with phrase aliases...")
    concepts = build_concept_index()
    token_idx = build_token_to_concepts(concepts)
    print(f"  {len(concepts):,} concepts")

    phrase_set = set(PHRASE_ALIASES.keys())
    print(f"Phrase aliases: {phrase_set}")

    # Pre-discover which products are affected
    print("\nScanning for affected products...")
    affected_keys: set[str] = set()
    with open(PRODUCT_MAP, encoding="utf-8", errors="replace") as f:
        for r in csv.DictReader(f):
            desc = (r.get("product_description") or "").lower()
            if any(ph in desc for ph in phrase_set):
                key = r.get("gtin_upc") or r.get("fdc_id") or ""
                if key:
                    affected_keys.add(key)
    print(f"  {len(affected_keys):,} affected products")

    # Build route cache for unique cleaned surfaces
    cache: dict = {}

    def route_cached(desc: str, owner: str, name: str) -> dict:
        augmented, aliases = apply_brand_food_aliases(desc, owner, name)
        cleaned = strip_known_brand_columns(augmented, owner, name)
        # Brand registry not needed for phrase-only patch; use empty set
        stripped = cleaned
        if stripped in cache:
            return cache[stripped]
        res = route(stripped, concepts, token_idx, brand_registry=set())
        cache[stripped] = res
        return res

    print("\nPatching product map...")
    t0 = time.time()
    audit = Counter()
    n = 0
    n_patched = 0
    n_unchanged = 0

    NEW_COLS = [
        "rft_verdict", "rft_concept_tokens", "rft_canonical_name",
        "rft_missing", "rft_extra",
        "rft_composite_pieces", "rft_composite_secondary",
        "best_esha_original_code", "best_esha_original_description",
        "best_esha_change_reason", "best_esha_inherited_from",
        "rft_sr28_code", "rft_sr28_desc", "rft_sr28_level",
        "rft_fndds_code", "rft_fndds_desc", "rft_fndds_level",
    ]

    with open(PRODUCT_MAP, encoding="utf-8", errors="replace") as fin, \
         open(TMP_OUT, "w", newline="") as fout:
        reader = csv.DictReader(fin)
        existing = list(reader.fieldnames or [])
        out_fields = list(existing)
        for col in NEW_COLS:
            if col not in out_fields:
                out_fields.append(col)
        writer = csv.DictWriter(fout, fieldnames=out_fields)
        writer.writeheader()

        for r in reader:
            key = r.get("gtin_upc") or r.get("fdc_id") or ""
            n += 1
            if n % 50000 == 0:
                print(f"  {n:,} rows  ({time.time()-t0:.1f}s)", flush=True)

            if key not in affected_keys:
                # Passthrough unchanged
                writer.writerow({k: r.get(k, "") for k in out_fields})
                n_unchanged += 1
                continue

            # Re-route this product
            desc = (r.get("product_description") or "").strip()
            owner = r.get("brand_owner") or ""
            name = r.get("brand_name") or ""
            res = route_cached(desc, owner, name)
            v = res["verdict"]

            c = res.get("concept")
            bt = res.get("backtracked") or {}
            sr = bt.get("sr28") or {}
            fn = bt.get("fndds") or {}
            es = bt.get("esha") or {}

            comp = res.get("composite") or None
            comp_pieces = (" | ".join(comp.get("pieces", [])) if comp else "")
            comp_secondary = (
                " | ".join(s.get("canonical", "") for s in comp.get("secondary", []))
                if comp else ""
            )

            # Build output row
            row_out = dict(r)
            row_out["rft_verdict"] = v
            row_out["rft_concept_tokens"] = "|".join(sorted(res.get("surface_concept") or []))
            row_out["rft_canonical_name"] = c.canonical_name if c else ""
            row_out["rft_missing"] = "|".join(sorted(res.get("missing") or []))
            row_out["rft_extra"] = "|".join(sorted(res.get("extra") or []))
            row_out["rft_composite_pieces"] = comp_pieces
            row_out["rft_composite_secondary"] = comp_secondary
            row_out["rft_sr28_code"] = sr.get("code", "")
            row_out["rft_sr28_desc"] = sr.get("desc", "")
            row_out["rft_sr28_level"] = sr.get("level", "")
            row_out["rft_fndds_code"] = fn.get("code", "")
            row_out["rft_fndds_desc"] = fn.get("desc", "")
            row_out["rft_fndds_level"] = fn.get("level", "")

            # Preserve original code if not already preserved
            preserved = (r.get("best_esha_original_code") or "").strip()
            preserved_desc = (r.get("best_esha_original_description") or "").strip()
            current = (r.get("best_esha_code") or "").strip()
            current_desc = (r.get("best_esha_description") or "").strip()
            orig_code = preserved if preserved else current
            orig_desc = preserved_desc if preserved_desc else current_desc
            row_out["best_esha_original_code"] = orig_code
            row_out["best_esha_original_description"] = orig_desc

            rft_esha = es.get("code", "").strip()
            rft_esha_desc = es.get("desc", "").strip()
            rft_esha_level = es.get("level", "")
            rft_esha_inh = "|".join(es.get("inherited_from") or []) if es.get("inherited_from") else ""
            row_out["best_esha_inherited_from"] = rft_esha_inh

            # Decision logic — same as rft_clean_product_map.py
            reason = ""
            if v in ("NEEDS_NEW_CONCEPT", "NO_MATCH", "NO_IDENTITY",
                     "COMPOSITE", ""):
                tag = ("composite" if v == "COMPOSITE" else "no_match")
                reason = (f"kept_orig_{tag}" if orig_code else "still_empty")
            elif not rft_esha:
                reason = "kept_orig_no_rft_esha" if orig_code else "still_empty"
            elif v in ("EXACT", "STRONG"):
                if orig_code == rft_esha:
                    reason = f"kept_agree_{rft_esha_level}"
                elif not orig_code:
                    row_out["best_esha_code"] = rft_esha
                    row_out["best_esha_description"] = rft_esha_desc
                    row_out["assignment_source"] = "rft_concept_filled"
                    row_out["score"] = "1.0" if v == "EXACT" else "0.85"
                    row_out["score_num"] = "1.0" if v == "EXACT" else "0.85"
                    reason = f"filled_{rft_esha_level}"
                else:
                    row_out["best_esha_code"] = rft_esha
                    row_out["best_esha_description"] = rft_esha_desc
                    row_out["assignment_source"] = "rft_concept_replaced"
                    row_out["score"] = "1.0" if v == "EXACT" else "0.85"
                    row_out["score_num"] = "1.0" if v == "EXACT" else "0.85"
                    reason = f"replaced_{rft_esha_level}"
            else:  # WEAK
                if orig_code == rft_esha:
                    reason = "kept_agree_weak"
                elif not orig_code:
                    row_out["best_esha_code"] = rft_esha
                    row_out["best_esha_description"] = rft_esha_desc
                    row_out["assignment_source"] = "rft_concept_filled_weak"
                    row_out["score"] = "0.5"
                    row_out["score_num"] = "0.5"
                    reason = f"filled_weak_{rft_esha_level}"
                else:
                    reason = "kept_orig_weak"

            row_out["best_esha_change_reason"] = reason
            audit[reason] += 1
            writer.writerow(row_out)
            n_patched += 1

    TMP_OUT.replace(PRODUCT_MAP)

    print(f"\nPatched {n_patched:,} rows, unchanged {n_unchanged:,} in {time.time()-t0:.1f}s")
    print("\nChange reasons:")
    for reason, count in audit.most_common():
        print(f"  {reason:40s} {count:>6,}")


if __name__ == "__main__":
    main()
