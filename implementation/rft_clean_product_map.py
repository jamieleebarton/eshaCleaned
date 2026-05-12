"""
Clean up the product_to_best_esha_full_map.vM.csv using the concept router
output. Same decision logic as the canonical cleanup:

  EXACT/STRONG + RFT has ESHA  → replace (or fill if old was empty)
  WEAK + RFT has ESHA          → keep old if present, fill if empty
  NEEDS_NEW_CONCEPT / NO_MATCH → keep old

Output preserves all original columns but updates best_esha_code,
best_esha_description, best_esha_head, score, assignment_source. Adds
audit columns plus the per-source codes from RFT (sr28_code, fndds_code).
"""

from __future__ import annotations

import csv
import re
import gzip
import sys
import time
from collections import Counter
from pathlib import Path

csv.field_size_limit(sys.maxsize)

ROOT = Path("/Users/jamiebarton/Desktop/esha_audit_bundle")
# Working file: re-clean the vIdentity product map in place each pass.
# Idempotent — _original_code columns are preserved through subsequent runs.
DEFAULT_IN = ROOT / "implementation/output/product_to_best_esha_full_map.vIdentity.csv"
DEFAULT_OUT = DEFAULT_IN
ROUTES = ROOT / "implementation/output/rft_v2/rft_concept/product_routes.csv.gz"

SPREAD_CATEGORY_MARKERS = (
    "jam, jelly",
    "fruit spreads",
    "fruit & vegetable spreads",
)
SPREAD_SURFACE_TERMS = (
    "jelly",
    "jam",
    "preserve",
    "preserves",
    "marmalade",
    "fruit spread",
)
SPREAD_TARGET_TERMS = (
    "fruit butter",
    "fruit spread",
    "jelly",
    "jam",
    "preserve",
    "preserves",
    "marmalade",
)

STRICT_DAIRY_SUBTYPES = (
    "buttermilk",
    "condensed",
    "creamer",
    "evaporated",
    "filled",
    "goat",
)
PLANT_MILK_SOURCES = (
    "almond",
    "cashew",
    "coconut",
    "hemp",
    "macadamia",
    "oat",
    "pea",
    "rice",
    "soy",
)
APPLESAUCE_CINNAMON_ALLOWED_MISSING = {
    "big",
    "fashioned",
    "go",
    "honey",
    "light",
    "lite",
    "old",
    "squeezable",
    "squeezables",
    "squeeze",
    "unsweetened",
}


def _norm(value: object) -> str:
    return str(value or "").lower()


def is_spread_lane(row: dict[str, str]) -> bool:
    category = _norm(row.get("branded_food_category"))
    desc = _norm(row.get("product_description"))
    return (
        any(marker in category for marker in SPREAD_CATEGORY_MARKERS)
        or any(term in desc for term in SPREAD_SURFACE_TERMS)
    )


def target_is_spread_family(description: str) -> bool:
    desc = _norm(description)
    return any(term in desc for term in SPREAD_TARGET_TERMS)


def should_quarantine_spread_gap(row: dict[str, str], current_desc: str) -> bool:
    """Quarantine non-spread incumbents when RFT cannot resolve a spread row."""
    verdict = str(row.get("rft_verdict") or "").strip()
    if verdict not in {"NEEDS_NEW_CONCEPT", "NO_MATCH", "NO_IDENTITY", "WEAK"}:
        return False
    if not is_spread_lane(row):
        return False
    if not str(row.get("best_esha_original_code") or row.get("best_esha_code") or "").strip():
        return False
    return not target_is_spread_family(current_desc)


def _has_milk_surface(row: dict[str, str]) -> bool:
    text = f"{_norm(row.get('product_description'))} {_norm(row.get('branded_food_category'))}"
    return "milk" in text or "creamer" in text or "cream substitute" in text


def unsafe_dairy_inherited_route(row: dict[str, str], rft_esha_desc: str, rft_esha_level: str) -> bool:
    """Reject inherited ESHA codes that drop strict dairy subtype/source."""
    if rft_esha_level != "inherited" or not _has_milk_surface(row):
        return False
    surface = f"{_norm(row.get('product_description'))} {_norm(row.get('branded_food_category'))}"
    target = _norm(rft_esha_desc)

    for subtype in STRICT_DAIRY_SUBTYPES:
        if subtype in surface and subtype not in target:
            return True

    if "cream substitute" in surface and "cream substitute" not in target and "creamer" not in target:
        return True

    for source in PLANT_MILK_SOURCES:
        compact = f"{source}milk"
        if (source in surface or compact in surface) and "milk" in surface and source not in target:
            return True

    return False


def should_promote_cinnamon_applesauce(row: dict[str, str], rft_esha: str) -> bool:
    if rft_esha != "46799":
        return False
    if row.get("rft_concept_tokens") != "applesauce|cinnamon":
        return False
    verdict = str(row.get("rft_verdict") or "").strip()
    if verdict not in {"WEAK", "NEEDS_NEW_CONCEPT"}:
        return False
    missing = {t for t in str(row.get("rft_missing") or "").split("|") if t}
    return missing.issubset(APPLESAUCE_CINNAMON_ALLOWED_MISSING)


def restore_original_assignment(row: dict[str, str], code: str, desc: str) -> None:
    if code:
        row["best_esha_code"] = code
        row["best_esha_description"] = desc
        row["best_esha_head"] = desc.split(",", 1)[0].strip() if desc else ""
    else:
        row["best_esha_code"] = ""
        row["best_esha_description"] = ""
        row["best_esha_head"] = ""
        row["best_esha_family"] = ""


_FAMILY_TOK = re.compile(r"[a-z][a-z0-9'%-]{2,}")
_FAMILY_NOISE = {
    "with", "and", "or", "of", "the", "for", "from", "in", "on",
    "fs", "nfs", "ns", "to", "as", "no", "not",
}


def _family_tokens(text: str) -> set[str]:
    if not text:
        return set()
    return {t for t in _FAMILY_TOK.findall(text.lower())
            if t not in _FAMILY_NOISE}


def orig_in_same_family_as_rft(orig_desc: str, rft_canonical: str,
                                 rft_esha_level: str) -> bool:
    """When RFT picks an INHERITED ESHA code (walked down to find any match
    in this source), the original code might already point to a more
    specific entry within the same concept family. In that case, prefer
    the original over the generic inherited fallback.

    Heuristic: tokenize both descriptions, drop tiny/noise tokens, and check
    whether they share at least 2 identity tokens AND coverage of the
    smaller-side ≥ 0.5. Same-family hits keep the more-specific original.
    """
    if rft_esha_level != "inherited":
        return False
    if not orig_desc or not rft_canonical:
        return False
    o = _family_tokens(orig_desc)
    r = _family_tokens(rft_canonical)
    if not o or not r:
        return False
    shared = o & r
    if len(shared) < 2:
        return False
    cov = len(shared) / min(len(o), len(r))
    return cov >= 0.5


def main():
    inp = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_IN
    out = Path(sys.argv[2]) if len(sys.argv) > 2 else DEFAULT_OUT
    if not inp.exists():
        sys.exit(f"input not found: {inp}")
    if not ROUTES.exists():
        sys.exit(f"routes not found: {ROUTES}\nrun rft_scale_concept.py first")

    print(f"Loading routes from {ROUTES.name}…", flush=True)
    t0 = time.time()
    # Build lookup: (gtin_upc, fdc_id) → route record
    route_idx: dict = {}
    with gzip.open(ROUTES, "rt") as f:
        for r in csv.DictReader(f):
            key = r.get("gtin_upc") or r.get("fdc_id") or ""
            if key:
                route_idx[key] = r
    print(f"  {len(route_idx):,} routes loaded in {time.time()-t0:.1f}s")

    print(f"\nReading: {inp}\nWriting: {out}\n", flush=True)
    audit = Counter()
    verdicts = Counter()
    n = 0
    n_replaced = 0
    n_filled = 0
    n_kept = 0

    NEW_COLS = [
        "rft_verdict", "rft_concept_tokens", "rft_canonical_name",
        "rft_missing", "rft_extra",
        "rft_composite_pieces", "rft_composite_secondary",
        "best_esha_original_code", "best_esha_original_description",
        "best_esha_change_reason", "best_esha_inherited_from",
        "rft_sr28_code", "rft_sr28_desc", "rft_sr28_level",
        "rft_fndds_code", "rft_fndds_desc", "rft_fndds_level",
    ]

    t1 = time.time()
    # Atomic-write via tempfile when input == output (in-place re-clean).
    tmp_out = out.with_suffix(out.suffix + ".tmp")
    with inp.open(encoding="utf-8", errors="replace") as fin, \
         tmp_out.open("w", newline="") as fout:
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
            route_r = route_idx.get(key, {})
            v = route_r.get("verdict", "")
            verdicts[v] += 1

            row_out = dict(r)
            row_out["rft_verdict"] = v
            row_out["rft_concept_tokens"] = route_r.get("matched_concept", "")
            row_out["rft_canonical_name"] = route_r.get("canonical_name", "")
            row_out["rft_missing"] = route_r.get("missing", "")
            row_out["rft_extra"] = route_r.get("extra", "")
            row_out["rft_composite_pieces"] = route_r.get("composite_pieces", "")
            row_out["rft_composite_secondary"] = route_r.get("composite_secondary", "")
            # SR28 / FNDDS audit info (passthrough)
            row_out["rft_sr28_code"] = route_r.get("sr28_code", "")
            row_out["rft_sr28_desc"] = route_r.get("sr28_desc", "")
            row_out["rft_sr28_level"] = route_r.get("sr28_level", "")
            row_out["rft_fndds_code"] = route_r.get("fndds_code", "")
            row_out["rft_fndds_desc"] = route_r.get("fndds_desc", "")
            row_out["rft_fndds_level"] = route_r.get("fndds_level", "")

            # Idempotency: keep the truly-original code from the first pass.
            preserved = (r.get("best_esha_original_code") or "").strip()
            preserved_desc = (r.get("best_esha_original_description") or "").strip()
            current = (r.get("best_esha_code") or "").strip()
            current_desc = (r.get("best_esha_description") or "").strip()
            orig_code = preserved if preserved else current
            orig_desc = preserved_desc if preserved_desc else current_desc
            row_out["best_esha_original_code"] = orig_code
            row_out["best_esha_original_description"] = orig_desc

            rft_esha = route_r.get("esha_code", "").strip()
            rft_esha_desc = route_r.get("esha_desc", "").strip()
            rft_esha_level = route_r.get("esha_level", "")
            rft_esha_inh = route_r.get("esha_inherited_from", "")
            row_out["best_esha_inherited_from"] = rft_esha_inh
            unsafe_rft_inheritance = unsafe_dairy_inherited_route(
                row_out, rft_esha_desc, rft_esha_level)

            # Decision logic — COMPOSITE products keep orig (recipes shouldn't
            # substitute composite-packaged products for single-ingredient calls).
            reason = ""
            if should_quarantine_spread_gap(row_out, orig_desc):
                row_out["best_esha_code"] = ""
                row_out["best_esha_description"] = ""
                row_out["best_esha_head"] = ""
                row_out["best_esha_family"] = ""
                row_out["assignment_source"] = "rft_spread_gap_quarantine"
                row_out["score"] = "0"
                row_out["score_num"] = "0"
                reason = "blanked_spread_head_mismatch"
                n_kept += 1
            elif should_promote_cinnamon_applesauce(row_out, rft_esha):
                row_out["best_esha_code"] = rft_esha
                row_out["best_esha_description"] = rft_esha_desc
                row_out["best_esha_head"] = rft_esha_desc.split(",", 1)[0].strip() if rft_esha_desc else ""
                row_out["assignment_source"] = "rft_concept_replaced"
                row_out["score"] = "0.85"
                row_out["score_num"] = "0.85"
                reason = "replaced_weak_applesauce_cinnamon"
                n_replaced += 1
            elif unsafe_rft_inheritance:
                restore_original_assignment(row_out, orig_code, orig_desc)
                reason = (
                    "kept_orig_unsafe_rft_inheritance"
                    if orig_code else "still_empty_unsafe_rft_inheritance"
                )
                n_kept += 1
            elif v in ("NEEDS_NEW_CONCEPT", "NO_MATCH", "NO_IDENTITY",
                     "COMPOSITE", ""):
                restore_original_assignment(row_out, orig_code, orig_desc)
                tag = ("composite" if v == "COMPOSITE" else "no_match")
                reason = (f"kept_orig_{tag}" if orig_code else "still_empty")
                n_kept += 1
            elif not rft_esha:
                restore_original_assignment(row_out, orig_code, orig_desc)
                reason = "kept_orig_no_rft_esha" if orig_code else "still_empty"
                n_kept += 1
            elif v in ("EXACT", "STRONG"):
                if orig_code == rft_esha:
                    row_out["best_esha_code"] = rft_esha
                    row_out["best_esha_description"] = rft_esha_desc
                    row_out["best_esha_head"] = rft_esha_desc.split(",", 1)[0].strip() if rft_esha_desc else ""
                    reason = f"kept_agree_{rft_esha_level}"
                    n_kept += 1
                elif not orig_code:
                    row_out["best_esha_code"] = rft_esha
                    row_out["best_esha_description"] = rft_esha_desc
                    row_out["assignment_source"] = "rft_concept_filled"
                    row_out["score"] = "1.0" if v == "EXACT" else "0.85"
                    row_out["score_num"] = "1.0" if v == "EXACT" else "0.85"
                    reason = f"filled_{rft_esha_level}"
                    n_filled += 1
                elif orig_in_same_family_as_rft(
                        orig_desc, route_r.get("canonical_name", ""),
                        rft_esha_level):
                    # RFT walked the tree to find SOMETHING in this source,
                    # but the original code is already a more specific entry
                    # in the same concept family. Keep the original.
                    restore_original_assignment(row_out, orig_code, orig_desc)
                    reason = "kept_orig_more_specific_than_inherited"
                    n_kept += 1
                else:
                    row_out["best_esha_code"] = rft_esha
                    row_out["best_esha_description"] = rft_esha_desc
                    row_out["assignment_source"] = "rft_concept_replaced"
                    row_out["score"] = "1.0" if v == "EXACT" else "0.85"
                    row_out["score_num"] = "1.0" if v == "EXACT" else "0.85"
                    reason = f"replaced_{rft_esha_level}"
                    n_replaced += 1
            else:  # WEAK
                if orig_code == rft_esha:
                    row_out["best_esha_code"] = rft_esha
                    row_out["best_esha_description"] = rft_esha_desc
                    row_out["best_esha_head"] = rft_esha_desc.split(",", 1)[0].strip() if rft_esha_desc else ""
                    reason = "kept_agree_weak"
                    n_kept += 1
                elif not orig_code:
                    row_out["best_esha_code"] = rft_esha
                    row_out["best_esha_description"] = rft_esha_desc
                    row_out["assignment_source"] = "rft_concept_filled_weak"
                    row_out["score"] = "0.5"
                    row_out["score_num"] = "0.5"
                    reason = f"filled_weak_{rft_esha_level}"
                    n_filled += 1
                else:
                    restore_original_assignment(row_out, orig_code, orig_desc)
                    reason = "kept_orig_weak"
                    n_kept += 1

            row_out["best_esha_change_reason"] = reason
            audit[reason] += 1
            writer.writerow(row_out)
            n += 1
            if n % 50000 == 0:
                print(f"  {n:,} rows  ({time.time()-t1:.1f}s)", flush=True)
    tmp_out.replace(out)

    print(f"\nCleaned {n:,} rows in {time.time()-t1:.1f}s\n")
    print("VERDICT DISTRIBUTION:")
    for v, c in verdicts.most_common():
        print(f"  {v:20s} {c:>7,}  ({100*c/n:5.1f}%)")
    print()
    print(f"OVERALL: replaced={n_replaced:,}  filled={n_filled:,}  kept={n_kept:,}")
    print()
    print("CHANGE REASONS:")
    for r, c in audit.most_common():
        print(f"  {r:30s} {c:>7,}  ({100*c/n:5.1f}%)")
    print(f"\nOutput: {out}")


if __name__ == "__main__":
    main()
