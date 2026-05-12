#!/usr/bin/env python3
"""Fix products where the LLM routed a single-variant item to a generic
"blend" identity. Walmart product "Spice Islands Ground Cumin Seed" has
LLM canonical_path = `Pantry > Spices & Seasonings > Spice Blend`,
product_identity_fixed = `Spice Blend`, variant = `cumin`. The variant
column already tells us the specific identity — and the FDC universe
has `Pantry > Spices & Seasonings > Cumin`. Move it.

Targets generic-bucket identities at any path where:
  - product_identity_fixed ∈ GENERIC_BUCKETS (Spice Blend, Vegetable Blend,
    Cheese Blend, Salad Mix, ...)
  - variant or canonical_label has a single specific food token
  - the SPECIFIC leaf exists in FDC universe

Rewrites canonical_path on api_cache_taxonomy_v2.csv (Walmart/Kroger) AND
recipe_ingredient_taxonomy_v2.csv (recipe ingredients), then propagates to
htc_code via re-derivation.

Idempotent. Run after cleanup_llm_output. Followed by the standard chain
(enrich, build_full_audit, tag_consensus).
"""
from __future__ import annotations

import csv
import shutil
import sys
from collections import Counter
from pathlib import Path

csv.field_size_limit(sys.maxsize)

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "recipe_pricing"))
from cleanup_llm_output import derive_htc  # type: ignore
sys.path.insert(0, str(ROOT))
from recipe_mapper.v1.htc.food_slots import default_registry  # type: ignore
from recipe_mapper.v1.htc.full_code import compose_full_code  # type: ignore

API = ROOT / "recipe_pricing" / "output" / "api_cache_taxonomy_v2.csv"
ING = ROOT / "recipe_mapper" / "v1" / "output" / "recipe_ingredient_taxonomy_v2.csv"
UNIVERSE = ROOT / "retail_mapper" / "v2" / "consensus_full_corpus_audit.csv"

# product_identity_fixed values that mean "generic blend container, look at variant"
GENERIC_BUCKETS = {
    "Spice Blend", "Spice Mix", "Seasoning Blend", "Seasoning Mix",
    "Vegetable Blend", "Salad Mix", "Mixed Vegetables",
    "Cheese Blend", "Shredded Cheese Blend",
    "Fruit Blend", "Berry Blend",
    "Herb Blend",
}

# Map specific variant strings → preferred leaf name in FDC tree.
# When the universe leaf name differs from the variant token (e.g. "Coriander"
# variant → "Coriander Seed" leaf), put the alias here.
VARIANT_TO_LEAF_ALIAS = {
    "red pepper flakes": "Crushed Red Pepper",
    "dry mustard": "Mustard Powder",
    "coriander": "Coriander Seed",
}


def load_universe() -> set[str]:
    universe: set[str] = set()
    with UNIVERSE.open() as f:
        for row in csv.DictReader(f):
            cp = (row.get("canonical_path") or "").strip()
            if cp:
                universe.add(cp)
    return universe


def fix_csv(path: Path, universe: set[str], registry, pif_field: str = "product_identity_fixed") -> tuple[int, Counter]:
    """Walk a tagged file, rewrite canonical_path where applicable.
    Returns (rewrite_count, by_target_path_counter)."""
    if not path.exists():
        print(f"missing {path}", file=sys.stderr)
        return 0, Counter()

    tmp = path.with_suffix(".csv.tmp")
    rewrite_count = 0
    by_target = Counter()

    with path.open(newline="") as fin, tmp.open("w", newline="") as fout:
        reader = csv.DictReader(fin)
        fns = list(reader.fieldnames or [])
        writer = csv.DictWriter(fout, fieldnames=fns)
        writer.writeheader()
        for row in reader:
            cp = (row.get("canonical_path") or "").strip()
            pif = (row.get(pif_field) or "").strip()
            variant = (row.get("variant") or "").strip().lower()

            if pif in GENERIC_BUCKETS and variant and cp.startswith("Pantry > Spices"):
                # Normalize variant: replace underscores with spaces
                v_clean = variant.replace("_", " ").strip()

                # Try BOTH "as-is" and "with leading form-word stripped"
                # so "ground_cumin" → ["ground cumin", "cumin"] and we
                # try the more specific form first, then the bare leaf.
                FORM_PREFIXES = {"ground", "whole", "dried", "powdered",
                                 "crushed", "minced", "flaked", "fresh",
                                 "raw", "smoked"}
                tokens = v_clean.split()
                candidates: list[str] = []
                if v_clean in VARIANT_TO_LEAF_ALIAS:
                    candidates.append(VARIANT_TO_LEAF_ALIAS[v_clean])
                # Form-prefixed first (more specific): "Cumin Seed", "Ground Cumin"
                candidates.append(v_clean)
                # Strip leading form word: "ground cumin" → "cumin"
                if len(tokens) > 1 and tokens[0] in FORM_PREFIXES:
                    bare = " ".join(tokens[1:])
                    candidates.append(bare)
                    if bare in VARIANT_TO_LEAF_ALIAS:
                        candidates.append(VARIANT_TO_LEAF_ALIAS[bare])
                # Singular fallback: "cumin seeds" → "cumin seed"
                if v_clean.endswith("s") and not v_clean.endswith("ss"):
                    candidates.append(v_clean[:-1])

                # Try the actual title-case path; pick first that exists in universe
                top = "Pantry > Spices & Seasonings"
                seen_cand: set[str] = set()
                for cand in candidates:
                    cand = cand.strip()
                    if not cand or cand in seen_cand:
                        continue
                    seen_cand.add(cand)
                    proposed = f"{top} > {cand.title()}"
                    if proposed in universe and proposed != cp:
                        row["canonical_path"] = proposed
                        # Re-derive htc_code with the new path so downstream
                        # joins (build_full_audit) find Walmart products.
                        # The new specific identity (Cumin, Paprika, ...) is
                        # also the new canonical_label / product_identity_fixed.
                        leaf = proposed.split(" > ")[-1]
                        new_htc = derive_htc(
                            canonical_path=proposed,
                            canonical_label=leaf,
                            modifier=row.get("modifier", "") or "",
                            product_identity=leaf,
                            registry=registry,
                            form=row.get("form_texture_cut", "") or "",
                            processing=row.get("processing_storage", "") or "",
                            ptype=row.get("form_texture_cut", "") or "",
                            flavor=row.get("flavor", "") or "",
                            variant=row.get("variant", "") or "",
                        )
                        if isinstance(new_htc, dict):
                            row["htc_code"] = new_htc.get("htc_code", row.get("htc_code", ""))
                            row["htc_sku_code"] = new_htc.get("htc_sku_code", row.get("htc_sku_code", ""))
                            row["htc_group"] = new_htc.get("htc_group", row.get("htc_group", ""))
                            row["htc_family"] = new_htc.get("htc_family", row.get("htc_family", ""))
                            row["htc_food"] = new_htc.get("htc_food", row.get("htc_food", ""))
                            row["htc_form"] = new_htc.get("htc_form", row.get("htc_form", ""))
                            row["htc_processing"] = new_htc.get("htc_processing", row.get("htc_processing", ""))
                            row["htc_ptype"] = new_htc.get("htc_ptype", row.get("htc_ptype", ""))
                            row["htc_check"] = new_htc.get("htc_check", row.get("htc_check", ""))
                            # Recompose full code
                            row["htc_full_code"] = compose_full_code(
                                row["htc_code"],
                                proposed,
                                row.get("retail_leaf_path", "") or "",
                                row.get("claims", "") or "",
                            )
                        # Update PIF and canonical_label to reflect new identity
                        row["product_identity_fixed"] = leaf
                        row["canonical_label"] = leaf
                        rewrite_count += 1
                        by_target[proposed] += 1
                        break
            writer.writerow(row)
    shutil.move(str(tmp), str(path))
    return rewrite_count, by_target


def main() -> int:
    universe = load_universe()
    registry = default_registry()
    print(f"FDC universe: {len(universe):,} paths", file=sys.stderr)

    print(f"\n--- {API.name} ---", file=sys.stderr)
    n, by = fix_csv(API, universe, registry)
    print(f"  rewrote {n} rows", file=sys.stderr)
    for p, c in by.most_common(15):
        print(f"    {c:>4}  → {p}", file=sys.stderr)

    print(f"\n--- {ING.name} ---", file=sys.stderr)
    n, by = fix_csv(ING, universe, registry)
    print(f"  rewrote {n} rows", file=sys.stderr)
    for p, c in by.most_common(15):
        print(f"    {c:>4}  → {p}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
