#!/usr/bin/env python3
"""Apply path rewrites + FDC-constraint enforcement to a taxonomy CSV in place.

Used for files that don't go through cleanup_llm_output.py (notably
sr28_fndds_taxonomy_v2.csv). Same logic as cleanup's stage 1.5/2.5/2.75:

  1. If canonical_path matches a rewrite key, replace with target.
  2. If still out of FDC, parent-strip until in FDC or fall through.
  3. If still out of FDC, route to Non-Food > Other.

Snapshots the input to <name>.before-fdc-align-rewrite.csv only on first run.
"""
from __future__ import annotations

import argparse
import csv
import shutil
import sys
from collections import Counter
from pathlib import Path

csv.field_size_limit(sys.maxsize)

ROOT = Path(__file__).resolve().parents[1]
NON_FOOD_OTHER = "Non-Food > Other"


def load_universe(audit: Path) -> set[str]:
    universe: set[str] = set()
    with audit.open() as f:
        for row in csv.DictReader(f):
            cp = (row.get("canonical_path") or "").strip()
            if cp:
                universe.add(cp)
    return universe


def load_rewrites(*paths: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    for p in paths:
        if not p.exists():
            continue
        with p.open() as f:
            for row in csv.DictReader(f):
                old = (row.get("old_canonical_path") or row.get("old_path") or "").strip()
                new = (row.get("new_canonical_path") or row.get("new_path") or "").strip()
                if old and new:
                    out[old] = new
    return out


def resolve(cp: str, rewrites: dict[str, str], universe: set[str]) -> tuple[str, str]:
    """Return (new_path, source) where source ∈ {unchanged, rewrite, parent_strip, catchall}."""
    rew = rewrites.get(cp)
    if rew:
        cp = rew
        if cp in universe:
            return cp, "rewrite"
    if cp in universe:
        return cp, "unchanged"
    # Parent-strip retry
    parts = [s.strip() for s in cp.split(" > ") if s.strip()]
    while len(parts) > 1:
        parts.pop()
        candidate = " > ".join(parts)
        if candidate in universe:
            return candidate, "parent_strip"
    return NON_FOOD_OTHER, "catchall"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", type=Path, required=True)
    ap.add_argument("--audit", type=Path,
                    default=ROOT / "retail_mapper" / "v2" / "consensus_full_corpus_audit.csv")
    ap.add_argument("--rewrites", type=Path, nargs="+", default=[
        ROOT / "recipe_pricing" / "walmart_kroger_path_rewrites.csv",
        ROOT / "recipe_pricing" / "expand_fdc_rewrites.csv",
    ])
    args = ap.parse_args()

    if not args.input.exists():
        print(f"missing input: {args.input}", file=sys.stderr)
        return 2

    # Reuse cleanup's identity map + retail_leaf composer so SR28/FNDDS rows
    # get routed and leaf-composed the same way as Walmart/recipes.
    sys.path.insert(0, str(ROOT / "retail_mapper" / "v2"))
    sys.path.insert(0, str(ROOT / "recipe_pricing"))
    try:
        from product_identity_canonical_map import PRODUCT_IDENTITY_CANONICAL_PATH_MAP
    except ImportError:
        PRODUCT_IDENTITY_CANONICAL_PATH_MAP = {}
    from cleanup_llm_output import (
        load_retail_leaf_index,
        compose_retail_leaf_path,
        _normalize_facet_tokens,
        lookup_identity_path,
        resolve_deep_identity,
        derive_htc,
    )
    sys.path.insert(0, str(ROOT / "recipe_mapper" / "v1"))
    from htc.full_code import compose_full_code
    from htc.food_slots import default_registry, primary_modifier
    registry = default_registry()

    universe = load_universe(args.audit)
    rewrites = load_rewrites(*args.rewrites)
    leaf_index = load_retail_leaf_index(args.audit)
    print(f"FDC universe: {len(universe):,} paths", file=sys.stderr)
    print(f"rewrite rules: {len(rewrites):,}", file=sys.stderr)
    print(f"identity map entries: {len(PRODUCT_IDENTITY_CANONICAL_PATH_MAP):,}", file=sys.stderr)
    n_leaves = sum(len(v) for v in leaf_index.values())
    print(f"retail_leaf candidates: {n_leaves:,}", file=sys.stderr)

    tmp = args.input.with_suffix(".csv.tmp")
    sources = Counter()
    leaf_sources = Counter()
    identity_routed = 0
    n = 0
    with args.input.open(newline="") as fin, tmp.open("w", newline="") as fout:
        reader = csv.DictReader(fin)
        fieldnames = list(reader.fieldnames or [])
        if "retail_leaf_path" not in fieldnames:
            # Insert right after canonical_path for parity with cleanup output
            try:
                idx = fieldnames.index("canonical_path") + 1
            except ValueError:
                idx = len(fieldnames)
            fieldnames.insert(idx, "retail_leaf_path")
            fieldnames.insert(idx + 1, "retail_leaf_source")
        if "htc_full_code" not in fieldnames:
            anchor = "htc_sku_code" if "htc_sku_code" in fieldnames else (
                "htc_code" if "htc_code" in fieldnames else None
            )
            if anchor:
                fieldnames.insert(fieldnames.index(anchor) + 1, "htc_full_code")
        writer = csv.DictWriter(fout, fieldnames=fieldnames)
        writer.writeheader()
        for row in reader:
            n += 1
            cp = (row.get("canonical_path") or "").strip()
            pid = (row.get("product_identity_fixed") or "").strip()

            # Identity-driven path override (mirror cleanup stage 1.7)
            mapped = lookup_identity_path(pid)
            if mapped and mapped in universe:
                if mapped != cp:
                    cp = mapped
                    identity_routed += 1
                source = "identity_map"
            else:
                cp, source = resolve(cp, rewrites, universe)

            # Title-driven deepening (mirror cleanup stage 1.8)
            title = (row.get("title") or "").strip()
            if cp in universe and title:
                deeper = resolve_deep_identity(title, cp)
                if deeper and deeper in universe:
                    cp = deeper
                    source = "identity_deepened"

            row["canonical_path"] = cp
            sources[source] += 1

            # Compose retail_leaf_path from the row's facets
            facet_tokens = _normalize_facet_tokens(
                row.get("variant", ""), row.get("flavor", ""),
                row.get("form_texture_cut", ""), row.get("processing_storage", ""),
                row.get("claims", ""), row.get("modifier", ""),
            )
            rlp, leaf_source = compose_retail_leaf_path(cp, facet_tokens, leaf_index)
            row["retail_leaf_path"] = rlp
            row["retail_leaf_source"] = leaf_source
            leaf_sources[leaf_source] += 1

            # Re-encode htc_code/htc_sku_code/htc_food/etc using the CURRENT
            # encoder. The cp may have been rewritten and the encoder rules
            # may have changed (encoder-fix round). This keeps SR28's codes
            # consistent with the freshly-encoded recipe + walmart corpora.
            mod_raw = (row.get("modifier") or "").strip()
            modifier = primary_modifier(mod_raw) if mod_raw else ""
            try:
                htc_dict = derive_htc(
                    canonical_path=cp,
                    canonical_label=(row.get("canonical_label") or "").strip(),
                    modifier=modifier or mod_raw,
                    product_identity=pid,
                    registry=registry,
                    form=(row.get("form_texture_cut") or "").strip(),
                    processing=(row.get("processing_storage") or "").strip(),
                    ptype=(row.get("form_texture_cut") or "").strip(),
                    flavor=(row.get("flavor") or "").strip(),
                    variant=(row.get("variant") or "").strip(),
                )
                for k, v in htc_dict.items():
                    if k in fieldnames:
                        row[k] = v
            except Exception:
                pass  # Keep existing values on encoder failure

            # Compose htc_full_code from the (possibly updated) htc_code
            htc = (row.get("htc_code") or "").strip()
            if htc and "htc_full_code" in fieldnames:
                claims = (row.get("claims") or row.get("modifier") or "").strip()
                row["htc_full_code"] = compose_full_code(htc, cp, rlp, claims)

            writer.writerow(row)

    shutil.move(str(tmp), str(args.input))
    print(f"  rows: {n:,}", file=sys.stderr)
    print(f"  identity-routed: {identity_routed:,}", file=sys.stderr)
    for k, v in sources.most_common():
        print(f"    path:{k:<14} {v:>7,}", file=sys.stderr)
    for k, v in leaf_sources.most_common():
        print(f"    leaf:{k:<14} {v:>7,}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
