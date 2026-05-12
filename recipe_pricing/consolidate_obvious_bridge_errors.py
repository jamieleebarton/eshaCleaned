#!/usr/bin/env python3
"""Consolidate clear bridge-error paths where the variant parent has
nothing to do with the leaf identity.

Examples that ARE bridge errors (merge):
  Pantry > Olives > Canned Tuna       → Meat & Seafood > Fish > Tuna
  Pantry > Flakes > Drink Mix          → Beverage > Flavored Drinks > Drink Mix
  Snack > Candy > Fruit Snacks         → Snack > Fruit Snacks
  Frozen > Frozen Fruit > Frozen Fruit → Frozen > Frozen Fruit (redundant)
  Pantry > Pie Fillings                → Pantry > Canned Fruit > Pie Filling

Examples that are NOT bridge errors (keep — real distinction):
  Frozen > Vegetables > Corn   vs   Pantry > Canned Vegetables > Corn
  Frozen > Vegetables > Broccoli vs Produce > Vegetables > Broccoli
  Dairy > Yogurt   vs   Frozen > Frozen Yogurt

Heuristic: read cross_parent_path_duplicates.csv. For each pair, compute
overlap between variant's PARENT-chain tokens and the leaf identity tokens
(extracted from the leaf segment). If parent tokens DON'T relate to the
leaf identity AND the canonical path's parent IS related, → bridge error.

Plus a manual deny-list of parent paths that historically produce bridge
errors (Olives, Flakes when leaf isn't olive/flake).
"""
from __future__ import annotations

import csv
import re
import shutil
import sqlite3
import sys
from pathlib import Path

csv.field_size_limit(sys.maxsize)

ROOT = Path(__file__).resolve().parents[1]
INPUT = ROOT / "recipe_pricing" / "cross_parent_path_duplicates.csv"
DB = ROOT / "recipe_pricing" / "data" / "priced_products_v2.db"
API = ROOT / "recipe_pricing" / "output" / "api_cache_taxonomy_v2.csv"
ING = ROOT / "recipe_mapper" / "v1" / "output" / "recipe_ingredient_taxonomy_v2.csv"
CONSENSUS = ROOT / "retail_mapper" / "v2" / "consensus_full_corpus_audit.csv"
LOG = ROOT / "recipe_pricing" / "bridge_error_consolidation_log.csv"

# Parent path patterns that are ALWAYS bridge errors when the leaf doesn't match
# (i.e. when leaf isn't about olives/flakes/pickles/sweeteners etc.)
BRIDGE_ERROR_PARENTS = [
    ("Pantry > Olives",           {"olive","pickle","relish","caper","gherkin","pepperoncini"}),
    ("Pantry > Flakes",           {"flake","oat","corn","wheat","bran","cereal","coconut"}),
    ("Pantry > Sweeteners",       {"sugar","sweetener","syrup","honey","stevia","molasses","agave"}),
    ("Pantry > Cereal",           {"cereal","oat","granola","bran","muesli","flake","grain"}),
    ("Snack > Candy",             {"candy","chocolate","gum","mint","gummy","toffee","fudge"}),
    ("Pantry > Pickles",          {"pickle","relish","gherkin"}),
    ("Snack > Trail Mix",         {"trail","mix","nut","almond","peanut","cashew"}),
    ("Snack > Chocolate Candy",   {"chocolate","candy","truffle","fudge"}),
    ("Snack > Bars",              {"bar","cookie","granola","protein"}),
    ("Pantry > Pasta",            {"pasta","noodle","macaroni","spaghetti","penne","linguine","gnocchi","ravioli"}),
]


def leaf_id_tokens(path: str) -> set[str]:
    """Identity tokens from leaf segment, normalized (singular, alpha)."""
    leaf = path.split(" > ")[-1].lower() if " > " in path else path.lower()
    leaf = re.sub(r"[^\w\s]", "", leaf)
    SOFT = {"the","a","an","of","and","or","with","for","fresh","dried","ground",
            "powdered","whole","crushed","chopped","frozen","raw","cooked","canned",
            "small","medium","large","extra","light","dark"}
    out = set()
    for w in leaf.split():
        if w in SOFT or len(w) <= 2:
            continue
        if w.endswith("s") and not w.endswith("ss") and len(w) > 3:
            w = w[:-1]
        out.add(w)
    return out


def is_bridge_error(variant_path: str) -> bool:
    """Return True if the variant_path's parent chain is unrelated to its leaf."""
    parent = " > ".join(variant_path.split(" > ")[:-1])
    leaf_toks = leaf_id_tokens(variant_path)
    for parent_pattern, valid_leaf_tokens in BRIDGE_ERROR_PARENTS:
        if parent.startswith(parent_pattern):
            # Parent matches a known bridge-error parent. If the leaf tokens
            # DON'T include any of the valid tokens → bridge error.
            if not (leaf_toks & valid_leaf_tokens):
                return True
    return False


def main() -> int:
    if not INPUT.exists():
        raise SystemExit(f"missing {INPUT} — run find_cross_parent_path_duplicates.py first")

    remap: dict[str, str] = {}
    with INPUT.open() as f:
        for row in csv.DictReader(f):
            variant = row["variant_path"]
            canonical = row["canonical_path"]
            if is_bridge_error(variant):
                remap[variant] = canonical

    # Also: explicit redundant-leaf collapses
    REDUNDANT_LEAF_REMAP = {
        "Frozen > Frozen Fruit > Frozen Fruit": "Frozen > Frozen Fruit",
        "Frozen > Vegetables > Frozen Vegetables": "Frozen > Vegetables",
    }
    remap.update(REDUNDANT_LEAF_REMAP)

    print(f"bridge-error remap rules: {len(remap):,}", file=sys.stderr)
    print("\nFirst 25 remap rules:", file=sys.stderr)
    for variant, canonical in list(remap.items())[:25]:
        print(f"  {variant}", file=sys.stderr)
        print(f"   → {canonical}", file=sys.stderr)

    # Apply to priced_products
    backup_db = DB.with_suffix(".db.before_bridge_error_consolidation")
    if not backup_db.exists():
        shutil.copy(str(DB), str(backup_db))
    con = sqlite3.connect(str(DB))
    cur = con.cursor()
    n_db = 0
    for variant, canonical in remap.items():
        cur.execute("UPDATE priced_products SET consensus_canonical = ? WHERE consensus_canonical = ?",
                    (canonical, variant))
        n_db += cur.rowcount
    con.commit()

    def update_csv(path: Path, cp_field: str = "canonical_path") -> int:
        if not path.exists():
            return 0
        backup = path.with_suffix(path.suffix + ".before_bridge_error_consolidation")
        if not backup.exists():
            shutil.copy(str(path), str(backup))
        tmp = path.with_suffix(".csv.tmp")
        n = 0
        with path.open(newline="") as fin, tmp.open("w", newline="") as fout:
            reader = csv.DictReader(fin)
            writer = csv.DictWriter(fout, fieldnames=reader.fieldnames)
            writer.writeheader()
            for row in reader:
                cp = (row.get(cp_field) or "").strip()
                if cp in remap:
                    row[cp_field] = remap[cp]
                    n += 1
                writer.writerow(row)
        shutil.move(str(tmp), str(path))
        return n

    n_api = update_csv(API)
    n_ing = update_csv(ING)
    n_consensus = update_csv(CONSENSUS)

    with LOG.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["variant_path", "canonical_path"])
        w.writeheader()
        for variant, canonical in remap.items():
            w.writerow({"variant_path": variant, "canonical_path": canonical})

    print(f"\n=== TOTAL UPDATES ===", file=sys.stderr)
    print(f"  priced_products:       {n_db:,}", file=sys.stderr)
    print(f"  api_cache:             {n_api:,}", file=sys.stderr)
    print(f"  recipe_ingredient:     {n_ing:,}", file=sys.stderr)
    print(f"  consensus_full:        {n_consensus:,}", file=sys.stderr)
    print(f"  total:                 {n_db+n_api+n_ing+n_consensus:,}", file=sys.stderr)
    print(f"  → {LOG}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
