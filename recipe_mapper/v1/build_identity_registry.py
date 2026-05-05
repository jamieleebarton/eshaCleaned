#!/usr/bin/env python3
"""Build the Hestia Identity Coding System registry.

Per IDENTITY_CODING_SYSTEM_DESIGN.md and TAXONOMY_LLM_GUIDE.md:
  - Compact code: Domain.Class.Type[.Modifier]
  - Domain = first segment of canonical_path (D/P/S/B/K/F/M/L/R/W/Y)
  - Rules A/B/C governing whether modifiers are part of the code

Inputs:
  retail_mapper/v2/consensus_full_corpus_audit.csv  (462k SKUs)

Outputs:
  recipe_mapper/v1/output/identity_registry.json
  recipe_mapper/v1/output/identity_registry.csv     (one row per identity code)
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

csv.field_size_limit(sys.maxsize)

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_AUDIT = ROOT / "retail_mapper" / "v2" / "consensus_full_corpus_audit.csv"
HERE = Path(__file__).resolve().parent
DEFAULT_JSON = HERE / "output" / "identity_registry.json"
DEFAULT_CSV = HERE / "output" / "identity_registry.csv"

DOMAIN_TO_CODE = {
    "Dairy": "D", "Pantry": "P", "Snack": "S", "Beverage": "B",
    "Bakery": "K", "Frozen": "F", "Meat & Seafood": "M", "Meal": "L",
    "Produce": "R", "Sports & Wellness": "W", "Baby & Toddler": "Y",
}

# Rule B canonical-path patterns: modifier IS identity (becomes part of code).
# Sourced from IDENTITY_CODING_SYSTEM_DESIGN.md §3 Rule B + §5.7 / §5.9.
RULE_B_PREFIXES = (
    "Frozen > Single Entrees",
    "Frozen > Family Entrees",
    "Frozen > Appetizers",
    "Frozen > Pizza",
    "Meal > Sandwiches",
    "Meal > Salads",
    "Meal > Pasta Dishes",
    "Meal > Composite Dishes",
    "Meal > Sushi",
    "Pantry > Spices & Seasonings > Seasoning",
    "Pantry > Sauces & Salsas > Pasta Sauce",
    "Pantry > Sauces & Salsas > BBQ Sauce",
    "Pantry > Soup",
    "Pantry > Dips",
    "Pantry > Salsa",
)

# Rule C canonical paths: default-unmarked (plain is default, flavored variants exist).
RULE_C_PATHS = {
    "Dairy > Cheese > Cream Cheese",
    "Dairy > Cheese > Cottage Cheese",
    "Dairy > Yogurt",
    "Dairy > Yogurt > Greek Yogurt",
    "Bakery > Bagels",
    "Bakery > Bread",
    "Bakery > English Muffins",
    "Bakery > Tortillas",
}

# Rule B product_identity_fixed values: explicit "the modifier IS the food" PIDs.
# Discovered in the corpus: Spice Blend (973 rows), Seasoning (3,891 rows), and
# similar generic catch-alls. When PID is one of these, the registry must key
# on the modifier or every spice/sauce/entree collapses into one bucket.
RULE_B_PIDS = {
    "Spice Blend", "Seasoning", "Single Entree", "Family Entree",
    "Pasta Sauce", "BBQ Sauce", "Hot Sauce", "Marinade",
    "Pizza", "Sandwich", "Salad", "Composite Dish", "Pasta Dish",
    "Sauce", "Soup", "Salsa", "Dip",
}

# tokens that signal "plain" / unmarked variant
PLAIN_TOKENS = {"plain", "regular", "original", "classic", "natural"}

CAMEL_NONALPHA = re.compile(r"[^A-Za-z0-9]+")


def to_camel(s: str) -> str:
    parts = [p for p in CAMEL_NONALPHA.split(s) if p]
    return "".join(p[:1].upper() + p[1:] for p in parts)


def classify_rule(canonical_path: str, product_identity: str = "") -> str:
    if canonical_path in RULE_C_PATHS:
        return "C"
    if product_identity in RULE_B_PIDS:
        return "B"
    for pref in RULE_B_PREFIXES:
        if canonical_path.startswith(pref):
            return "B"
    return "A"


def primary_modifier(modifier: str) -> str:
    """Take only the first segment (before '>'), drop trailing '> Organic' etc."""
    if not modifier:
        return ""
    return modifier.split(" > ")[0].strip()


def compact_code(canonical_path: str, product_identity: str, rule: str,
                 modifier: str = "") -> str:
    segs = [s.strip() for s in canonical_path.split(" > ") if s.strip()]
    if not segs:
        return "?"
    domain = DOMAIN_TO_CODE.get(segs[0], segs[0][:1].upper())
    klass = to_camel(segs[1]) if len(segs) >= 2 else ""
    typ = to_camel(product_identity) if product_identity else (
        to_camel(segs[-1]) if len(segs) >= 3 else "")
    parts = [p for p in [domain, klass, typ] if p]
    code = ".".join(parts)
    if rule in ("B", "C") and modifier:
        code += "." + to_camel(modifier)
    return code


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--audit", type=Path, default=DEFAULT_AUDIT)
    ap.add_argument("--out-json", type=Path, default=DEFAULT_JSON)
    ap.add_argument("--out-csv", type=Path, default=DEFAULT_CSV)
    args = ap.parse_args()

    args.out_json.parent.mkdir(parents=True, exist_ok=True)

    # Key is now (canonical_path, product_identity_fixed, primary_modifier_or_empty).
    # For Rule A/C the primary_modifier slot is "" (not in the key); for Rule B
    # nodes the primary modifier IS the type, so it goes in the key.
    sku_n: Counter[tuple[str, str, str]] = Counter()
    rule_for: dict[tuple, str] = {}
    modifiers: dict[tuple, Counter] = defaultdict(Counter)
    flavors: dict[tuple, Counter] = defaultdict(Counter)
    forms: dict[tuple, Counter] = defaultdict(Counter)
    fndds: dict[tuple, Counter] = defaultdict(Counter)
    fndds_descs: dict[tuple, dict] = defaultdict(dict)
    sr28: dict[tuple, Counter] = defaultdict(Counter)
    sr28_descs: dict[tuple, dict] = defaultdict(dict)
    bfcs: dict[tuple, Counter] = defaultdict(Counter)
    leaf_paths: dict[tuple, Counter] = defaultdict(Counter)
    has_portions: dict[tuple, bool] = defaultdict(bool)
    sample_titles: dict[tuple, list[str]] = defaultdict(list)

    n = 0
    with args.audit.open() as f:
        r = csv.DictReader(f)
        for row in r:
            n += 1
            cp = (row.get("canonical_path") or "").strip()
            pid = (row.get("product_identity_fixed") or "").strip()
            if not cp or not pid:
                continue
            mod = (row.get("modifier") or "").strip()
            rule = classify_rule(cp, pid)
            pmod = primary_modifier(mod) if rule == "B" else ""
            key = (cp, pid, pmod)
            sku_n[key] += 1
            rule_for[key] = rule

            if mod:
                modifiers[key][mod] += 1
            fv = (row.get("flavor") or "").strip()
            if fv:
                flavors[key][fv] += 1
            fm = (row.get("form_texture_cut") or "").strip()
            if fm:
                forms[key][fm] += 1

            fc = (row.get("fndds_code") or "").strip()
            if fc:
                fndds[key][fc] += 1
                fndds_descs[key].setdefault(fc, (row.get("fndds_desc") or "").strip())
            sc = (row.get("sr28_code") or "").strip()
            if sc:
                sr28[key][sc] += 1
                sr28_descs[key].setdefault(sc, (row.get("sr28_desc") or "").strip())
            bfc = (row.get("branded_food_category") or "").strip()
            if bfc:
                bfcs[key][bfc] += 1
            lp = (row.get("retail_leaf_path") or "").strip()
            if lp:
                leaf_paths[key][lp] += 1
            if (row.get("portions_json") or "").strip():
                has_portions[key] = True
            tit = (row.get("title") or "").strip()
            if tit and len(sample_titles[key]) < 5 and tit not in sample_titles[key]:
                sample_titles[key].append(tit)

    print(f"scanned {n:,} SKUs  unique nodes={len(sku_n):,}")

    def top1(c: Counter) -> str:
        return c.most_common(1)[0][0] if c else ""

    registry: list[dict] = []
    for key, nsku in sku_n.most_common():
        cp, pid, pmod = key
        rule = rule_for[key]
        # For Rule B, the primary modifier IS the type — bake it into the code.
        code = compact_code(cp, pid, rule, modifier=pmod if rule == "B" else "")
        kmods = [(m, c) for m, c in modifiers[key].most_common(30) if c >= 2]
        flavor_vocab = [f for f, c in flavors[key].most_common(20) if c >= 2]
        form_vocab = [f for f, c in forms[key].most_common(10) if c >= 2]
        registry.append({
            "code": code,
            "canonical_path": cp,
            "product_identity_fixed": pid,
            "primary_modifier": pmod,
            "rule": rule,
            "domain_code": code.split(".")[0],
            "sku_count": nsku,
            "modal_branded_food_category": top1(bfcs[key]),
            "modal_fndds_code": top1(fndds[key]),
            "modal_fndds_desc": fndds_descs[key].get(top1(fndds[key]), ""),
            "modal_sr28_code": top1(sr28[key]),
            "modal_sr28_desc": sr28_descs[key].get(top1(sr28[key]), ""),
            "modal_retail_leaf_path": top1(leaf_paths[key]),
            "has_portions": has_portions[key],
            "known_modifiers": kmods,
            "flavor_vocab": flavor_vocab,
            "form_vocab": form_vocab,
            "sample_titles": sample_titles[key],
        })

    # JSON: full registry (list)
    with args.out_json.open("w") as f:
        json.dump(registry, f, indent=2)

    # CSV: flat one-row-per-code summary for inspection
    cols = ["code", "rule", "domain_code", "canonical_path",
            "product_identity_fixed", "sku_count",
            "modal_fndds_code", "modal_fndds_desc",
            "modal_sr28_code", "modal_sr28_desc",
            "modal_retail_leaf_path", "has_portions",
            "n_known_modifiers", "top_modifiers"]
    with args.out_csv.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(cols)
        for e in registry:
            top_mods = " | ".join(f"{m}:{c}" for m, c in e["known_modifiers"][:5])
            w.writerow([e["code"], e["rule"], e["domain_code"],
                        e["canonical_path"], e["product_identity_fixed"],
                        e["sku_count"],
                        e["modal_fndds_code"], e["modal_fndds_desc"],
                        e["modal_sr28_code"], e["modal_sr28_desc"],
                        e["modal_retail_leaf_path"], e["has_portions"],
                        len(e["known_modifiers"]), top_mods])

    # quick stats
    by_rule = Counter(e["rule"] for e in registry)
    by_domain = Counter(e["domain_code"] for e in registry)
    print(f"  by rule: {dict(by_rule)}")
    print(f"  by domain: {dict(by_domain)}")
    print(f"  wrote {args.out_json} and {args.out_csv}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
