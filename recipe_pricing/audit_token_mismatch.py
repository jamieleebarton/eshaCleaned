#!/usr/bin/env python3
"""R9e — Token-mismatch detector for per-recipe lines.

For each picked-recipe line, compare token overlap:
  ingredient_text tokens  ↔  sr_description tokens   (bridge)
  ingredient_text tokens  ↔  picked_sku tokens       (pick)
  picked_sku tokens       ↔  expected-form tokens    (form sanity)

Emits flags:
  BRIDGE_TOKEN_MISS  — recipe text and SR28 desc share no meaningful tokens
                        (e.g., "corn tortillas" → SR28 "Toaster pastries")
  SKU_TOKEN_MISS     — recipe text and SKU name share no meaningful tokens
                        (e.g., "longhorn cheese" → "Velveeta Slices")
  WRONG_FORM         — SKU name has a form/state word (sticks, mush, spray,
                        mix, packet) that recipe didn't say
  IMITATION_PICKED   — SKU has "imitation"/"pasteurized recipe"/"product"
                        but recipe wanted real food

Aggregates by (ingredient_item, picked_sku) → count, ranks bug categories.

Outputs:
  recipe_pricing/audit_token_mismatch_lines.csv  — per-line flagged lines
  recipe_pricing/audit_token_mismatch_rollup.csv — top bug patterns
"""
from __future__ import annotations
import csv, re, sys
from collections import Counter, defaultdict
from pathlib import Path

csv.field_size_limit(2**30)
ROOT = Path(__file__).resolve().parents[1]
IN_LINES = ROOT / "recipe_pricing" / "per_recipe_audit_lines.csv"
OUT_LINES = ROOT / "recipe_pricing" / "audit_token_mismatch_lines.csv"
OUT_ROLLUP = ROOT / "recipe_pricing" / "audit_token_mismatch_rollup.csv"

# Words to exclude from token comparison
STOP = {
    "the","a","an","of","and","or","with","fresh","whole","raw","organic",
    "plain","ground","dried","cooked","mix","flavor","style","grade","product",
    "food","unit","oz","pkg","each","fl","lb","ct","count","kosher","drained",
    "natural","added","without","unsalted","salted","reduced","light","large",
    "medium","small","jumbo","piece","slice","slices","cup","cups","head",
    "leaf","leaves","clove","cloves","stalk","tsp","tbsp","brand","brands",
    # Brand-ish noise that frequently appears in SKU titles
    "great","value","kroger","marketside","sargento","heritage","farm","farms",
    "happy","tot","oz","total","fluid","ounce","ounces","tablespoon","teaspoon",
    "ready","serve","fully","easy","simple","truth","selection","private",
    "morningstar","beyond","yummy","yummier","yummiest","wesson","new","york",
}

# SKU form/state words that should never be picked unless the recipe asks for them
FORM_STATE_WORDS = {
    "sticks", "stick",            # margarine sticks for "vegetable oil"
    "spray", "cooking spray",     # spray for liquid oil
    "mix", "powder", "packet",    # dry mix for liquid
    "mush", "mushy", "mashed",    # prepared form for raw
    "imitation", "imitation cheese",
    "pasteurized prepared", "pasteurized recipe", "cheese product",
    "cheese food",                # plastic cheese for real cheese
    "bouillon", "stock cube",     # condensed for liquid
    "panko",                      # seasoned breadcrumb for plain
    "frozen", "instant",
    "marshmallow",
}


def _stem(t: str) -> str:
    """Cheap singular/plural stemming to align tokens like 'eggs'/'egg',
    'onions'/'onion', 'tomatoes'/'tomato', 'sugars'/'sugar'."""
    if len(t) <= 3: return t
    if t.endswith("ies") and len(t) > 4: return t[:-3] + "y"  # tomatoes→tomato? no, tomatoes ends 'oes'
    if t.endswith("oes") and len(t) > 4: return t[:-2]        # tomatoes→tomato, potatoes→potato
    if t.endswith("es")  and len(t) > 3: return t[:-2]        # cherries? but cherries ends 'ies' caught earlier
    if t.endswith("s")   and not t.endswith("ss"): return t[:-1]
    return t


def tokens(s: str) -> set[str]:
    if not s: return set()
    return {_stem(t) for t in re.findall(r"[a-z]+", s.lower())
            if len(t) > 2 and t not in STOP}


def main():
    if not IN_LINES.exists():
        print(f"missing {IN_LINES}", file=sys.stderr); sys.exit(1)

    flag_counts: Counter = Counter()
    issue_counts: Counter = defaultdict(lambda: Counter())  # flag → (item, sku) → count
    out_rows = []
    rows_seen = 0

    with IN_LINES.open() as f:
        for row in csv.DictReader(f):
            rows_seen += 1
            ing_text = row.get("ingredient_text", "")
            ing_item = row.get("ingredient_item", "")
            sr_desc  = row.get("sr_description", "")
            sku      = row.get("picked_sku", "")
            if not sku: continue

            ing_toks = tokens(ing_text) | tokens(ing_item)
            sr_toks  = tokens(sr_desc)
            sku_toks = tokens(sku)

            flags = []
            # Bridge mismatch
            if ing_toks and sr_toks and not (ing_toks & sr_toks):
                flags.append("BRIDGE_TOKEN_MISS")
            # SKU mismatch
            if ing_toks and sku_toks and not (ing_toks & sku_toks):
                flags.append("SKU_TOKEN_MISS")
            # Wrong form
            sku_lc = sku.lower()
            ing_lc = (ing_text + " " + ing_item).lower()
            for fw in FORM_STATE_WORDS:
                if fw in sku_lc and fw not in ing_lc:
                    flags.append(f"WRONG_FORM:{fw[:14]}")
                    break
            # Imitation picked
            if any(t in sku_lc for t in ("imitation", "cheese product", "cheese food", "pasteurized recipe", "pasteurized prepared")) \
               and "imitation" not in ing_lc:
                flags.append("IMITATION_PICKED")

            if not flags: continue
            for f in flags:
                flag_counts[f] += 1
                issue_counts[f][(ing_item, sku[:50])] += 1

            out_rows.append({
                "recipe_id": row.get("recipe_id",""),
                "recipe_name": row.get("recipe_name",""),
                "line_idx": row.get("line_idx",""),
                "ingredient_text": ing_text[:60],
                "ingredient_item": ing_item[:25],
                "fdc_id": row.get("fdc_id",""),
                "sr_description": sr_desc[:35],
                "picked_sku": sku[:55],
                "total_spend_$": row.get("total_spend_$",""),
                "flags": "|".join(flags),
            })

    # Write per-line output
    OUT_LINES.parent.mkdir(parents=True, exist_ok=True)
    if out_rows:
        with OUT_LINES.open("w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(out_rows[0].keys()))
            w.writeheader()
            for r in out_rows: w.writerow(r)

    # Rollup by (flag, item) pattern
    rollup = []
    for flag, pairs in issue_counts.items():
        for (item, sku), n in pairs.most_common(15):
            rollup.append({
                "flag": flag,
                "ingredient_item": item,
                "picked_sku": sku,
                "n_lines": n,
            })
    rollup.sort(key=lambda r: -r["n_lines"])
    if rollup:
        with OUT_ROLLUP.open("w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(rollup[0].keys()))
            w.writeheader()
            for r in rollup: w.writerow(r)

    print(f"\nrows scanned: {rows_seen:,}", file=sys.stderr)
    print(f"flagged lines: {len(out_rows):,}", file=sys.stderr)
    print(f"\nFlag distribution:", file=sys.stderr)
    for f, n in flag_counts.most_common():
        print(f"  {f:<28}  {n:>4}", file=sys.stderr)
    print(f"\nTop 20 (flag, ingredient → picked SKU) patterns:", file=sys.stderr)
    for r in rollup[:20]:
        print(f"  [{r['flag'][:18]:<18}] {r['n_lines']:>3}× '{r['ingredient_item']:<22}' → "
              f"'{r['picked_sku']}'", file=sys.stderr)
    print(f"\n→ {OUT_LINES}\n→ {OUT_ROLLUP}", file=sys.stderr)


if __name__ == "__main__":
    main()
