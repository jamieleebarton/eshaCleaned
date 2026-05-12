#!/usr/bin/env python3
"""V2 of the bridge-error consolidator. Uses semantic check:
  - Extract the variant_path's PARENT TOKEN (last parent segment).
  - Compare to the LEAF identity tokens.
  - If parent tokens are completely UNRELATED to leaf tokens AND the canonical
    path's parent IS related, → bridge error.

PRESERVES Frozen/Canned/Fresh distinctions: any path starting with 'Frozen',
'Pantry > Canned', 'Pantry > Pickled', 'Snack > Dried' is treated as a
state-of-food and never merged with a non-state path having the same leaf.

Operates only on pairs where variant_n < 30% of canonical_n.
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
LOG = ROOT / "recipe_pricing" / "bridge_v2_log.csv"

# Paths starting with these prefixes mean a state-of-food (frozen/canned/etc.)
# We NEVER merge a state-prefixed path with a non-state-prefixed path of the
# same leaf — they're different products by storage method.
STATE_PREFIXES = (
    "Frozen", "Pantry > Canned", "Pantry > Pickled", "Pantry > Pickles",
    "Pantry > Dried", "Snack > Dried", "Pantry > Frozen",
    "Pantry > Sun Dried", "Snack > Trail Mix",
)


def is_state_path(path: str) -> bool:
    return any(path.startswith(p) for p in STATE_PREFIXES)


# Leaf tokens that suggest a category — when parent chain doesn't include
# anything compatible, parent is probably wrong.
SOFT_TOKENS = {"the","a","an","of","and","or","with","for","fresh","whole","raw"}


def leaf_tokens(path: str) -> set[str]:
    leaf = path.split(" > ")[-1].lower() if " > " in path else path.lower()
    leaf = re.sub(r"[^\w\s]", "", leaf)
    out = set()
    for w in leaf.split():
        if w in SOFT_TOKENS or len(w) <= 2:
            continue
        if w.endswith("s") and not w.endswith("ss") and len(w) > 3:
            w = w[:-1]
        out.add(w)
    return out


def parent_chain_tokens(path: str) -> set[str]:
    """Tokens in the parent chain (everything except the leaf)."""
    if " > " not in path:
        return set()
    parents = path.split(" > ")[:-1]
    out = set()
    for seg in parents:
        seg = re.sub(r"[^\w\s]", "", seg.lower())
        for w in seg.split():
            if w in SOFT_TOKENS or len(w) <= 2:
                continue
            if w.endswith("s") and not w.endswith("ss") and len(w) > 3:
                w = w[:-1]
            out.add(w)
    return out


# Concept-cluster tokens: tokens that are semantically RELATED enough to
# belong under each other's parent chain. So "tuna" is part of {fish, seafood,
# meat}; "mushroom" is part of {vegetable, produce, mushroom}; etc.
RELATED_PARENTS = {
    # leaf token → set of parent tokens that are reasonable to find it under
    "tuna":      {"fish","seafood","meat","tuna"},
    "salmon":    {"fish","seafood","meat","salmon"},
    "shrimp":    {"shellfish","seafood","fish","meat","shrimp"},
    "chicken":   {"poultry","meat","seafood","chicken"},
    "turkey":    {"poultry","meat","seafood","turkey"},
    "beef":      {"meat","seafood","beef"},
    "pork":      {"meat","seafood","pork"},
    "ham":       {"meat","seafood","pork","ham","deli"},
    "lamb":      {"meat","seafood","lamb"},
    # produce
    "potato":    {"produce","vegetable","frozen","canned","pantry","potato"},
    "onion":     {"produce","vegetable","frozen","canned","pantry","onion"},
    "garlic":    {"produce","vegetable","spice","seasoning","pickle","garlic","pantry"},
    "mushroom":  {"produce","vegetable","frozen","canned","pantry","mushroom"},
    "pepper":    {"produce","vegetable","frozen","canned","pantry","pepper","pickle","spice","seasoning"},
    "broccoli":  {"produce","vegetable","frozen","canned","pantry","broccoli"},
    "spinach":   {"produce","vegetable","frozen","canned","pantry","spinach"},
    "carrot":    {"produce","vegetable","frozen","canned","pantry","carrot"},
    "lettuce":   {"produce","vegetable","salad","lettuce"},
    "tomato":    {"produce","vegetable","fruit","frozen","canned","pantry","tomato","sauce","pasta"},
    "corn":      {"produce","vegetable","frozen","canned","pantry","grain","corn"},
    # bakery
    "bread":     {"bakery","grain","pantry","bread"},
    "roll":      {"bakery","sushi","meal","roll","grain"},
    "cookie":    {"bakery","snack","dessert","cookie"},
    "cake":      {"bakery","snack","dessert","cake"},
    "pie":       {"bakery","dessert","pantry","pie"},
    "muffin":    {"bakery","breakfast","muffin"},
    "biscuit":   {"bakery","biscuit"},
    "donut":     {"bakery","dessert","donut"},
    "pancake":   {"bakery","breakfast","frozen","pancake"},
    # dairy
    "milk":      {"dairy","beverage","milk","frozen"},
    "cheese":    {"dairy","cheese","snack"},
    "yogurt":    {"dairy","yogurt","beverage","frozen"},
    "butter":    {"dairy","spread","butter"},
    "cream":     {"dairy","cream","sweetener"},
    # snack
    "candy":     {"snack","candy","chocolate","sugar","sweetener"},
    "chocolate": {"snack","candy","chocolate","baking","dessert"},
    "chip":      {"snack","chip","produce"},
    "cracker":   {"snack","cracker","bakery"},
    # beverage
    "drink":     {"beverage","drink","mix"},
    "juice":     {"beverage","juice","fruit","produce"},
    "soda":      {"beverage","soda","carbonated"},
    "coffee":    {"beverage","coffee"},
    "tea":       {"beverage","tea"},
    "wine":      {"beverage","wine","cooking","spirit","liquor","alcohol","sake","mirin","sauce","salsa"},
    "shake":     {"beverage","drink","protein","dairy","milk","shake","sport","wellness"},
    # pantry
    "sauce":     {"pantry","sauce","salsa","condiment"},
    "dressing":  {"pantry","dressing","salad","condiment","sauce"},
    "soup":      {"pantry","soup","meal"},
    "spice":     {"pantry","spice","seasoning"},
    "flour":     {"pantry","flour","baking","grain"},
    "sugar":     {"pantry","sugar","sweetener","baking"},
    "oil":       {"pantry","oil","cooking"},
    "vinegar":   {"pantry","vinegar","sauce","salsa","cooking","wine"},
    "pasta":     {"pantry","pasta","grain"},
    "rice":      {"pantry","rice","grain"},
    "noodle":    {"pantry","pasta","noodle","grain"},
    "bean":      {"pantry","bean","canned","grain","legume"},
    "fruit":     {"produce","frozen","snack","dried","fruit","pantry","canned","candy","chocolate"},
    "vegetable": {"produce","frozen","canned","vegetable","pantry"},
    "blend":     {"pantry","blend","spice","seasoning","frozen","produce","vegetable","beverage","drink","mix","baking","oil"},
    # snack categories
    "bar":       {"snack","bakery","cookie","cake","bar","granola","protein","fruit","candy","chocolate"},
    "snack":     {"snack","bar","candy","cookie","cracker"},
    "mix":       {"pantry","beverage","drink","mix","baking","snack","seasoning","flake","cereal"},
    "topping":   {"dairy","cream","sweetener","sauce","topping"},
    "frosting":  {"baking","dessert","sweetener","frosting","cake"},
    "filling":   {"baking","dessert","pie","fruit","canned","filling","pantry"},
}


def is_unrelated(variant_parent_tokens: set[str], leaf_tokens_set: set[str]) -> bool:
    """True if NONE of the leaf tokens have a related parent that's in the variant_parent_tokens."""
    for lt in leaf_tokens_set:
        related = RELATED_PARENTS.get(lt)
        if related and (variant_parent_tokens & related):
            return False
    return True


def main() -> int:
    if not INPUT.exists():
        raise SystemExit(f"missing {INPUT}")

    remap: dict[str, str] = {}
    pair_count = 0
    skipped_state = 0
    skipped_minority = 0
    skipped_related = 0

    with INPUT.open() as f:
        for row in csv.DictReader(f):
            cn = row["canonical_path"]
            vn = row["variant_path"]
            cn_n = int(row["canonical_n"])
            vn_n = int(row["variant_n"])
            pair_count += 1

            # Rule 1: variant must be true minority
            if cn_n == 0 or vn_n / cn_n >= 0.30:
                skipped_minority += 1
                continue

            # Rule 2: skip if either path is a state-of-food (frozen/canned/etc.)
            #         vs the other being non-state — those are real distinctions
            cn_state = is_state_path(cn)
            vn_state = is_state_path(vn)
            if cn_state != vn_state:
                skipped_state += 1
                continue

            # Rule 3: skip parent-vs-leaf nesting
            if vn.startswith(cn + " > ") or cn.startswith(vn + " > "):
                skipped_minority += 1
                continue

            # Rule 4: same-leaf check
            cn_leaf = cn.split(" > ")[-1].lower().rstrip("s")
            vn_leaf = vn.split(" > ")[-1].lower().rstrip("s")
            if cn_leaf != vn_leaf:
                skipped_minority += 1
                continue

            # Rule 5: variant's parent chain must be UNRELATED to leaf
            v_parents = parent_chain_tokens(vn)
            l_toks = leaf_tokens(vn)
            if not is_unrelated(v_parents, l_toks):
                # The variant's parent IS plausible for this leaf — keep distinct
                skipped_related += 1
                continue

            remap[vn] = cn

    print(f"pairs scanned: {pair_count:,}", file=sys.stderr)
    print(f"  skipped minority (variant ≥30% of canonical): {skipped_minority:,}", file=sys.stderr)
    print(f"  skipped state-of-food distinction:             {skipped_state:,}", file=sys.stderr)
    print(f"  skipped parent-related-to-leaf:                {skipped_related:,}", file=sys.stderr)
    print(f"  TO MERGE:                                      {len(remap):,}", file=sys.stderr)

    if not remap:
        return 0

    print(f"\nFirst 25 merges:", file=sys.stderr)
    for variant, canonical in list(remap.items())[:25]:
        print(f"  {variant}  →  {canonical}", file=sys.stderr)

    # Apply
    backup = DB.with_suffix(".db.before_bridge_v2")
    if not backup.exists():
        shutil.copy(str(DB), str(backup))
    con = sqlite3.connect(str(DB))
    cur = con.cursor()
    n_db = 0
    for variant, canonical in remap.items():
        cur.execute("UPDATE priced_products SET consensus_canonical = ? WHERE consensus_canonical = ?",
                    (canonical, variant))
        n_db += cur.rowcount
    con.commit()

    def update_csv(path: Path) -> int:
        if not path.exists():
            return 0
        backup = path.with_suffix(path.suffix + ".before_bridge_v2")
        if not backup.exists():
            shutil.copy(str(path), str(backup))
        tmp = path.with_suffix(".csv.tmp")
        n = 0
        with path.open(newline="") as fin, tmp.open("w", newline="") as fout:
            reader = csv.DictReader(fin)
            writer = csv.DictWriter(fout, fieldnames=reader.fieldnames)
            writer.writeheader()
            for row in reader:
                cp = (row.get("canonical_path") or "").strip()
                if cp in remap:
                    row["canonical_path"] = remap[cp]
                    n += 1
                writer.writerow(row)
        shutil.move(str(tmp), str(path))
        return n

    n_api = update_csv(API)
    n_ing = update_csv(ING)
    n_cons = update_csv(CONSENSUS)

    with LOG.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["variant_path", "canonical_path"])
        w.writeheader()
        for v, c in remap.items():
            w.writerow({"variant_path": v, "canonical_path": c})

    print(f"\nUPDATES: db={n_db}, api={n_api}, ing={n_ing}, cons={n_cons}, total={n_db+n_api+n_ing+n_cons}",
          file=sys.stderr)
    print(f"  → {LOG}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
