#!/usr/bin/env python3
"""Audit priced_products_v2.db for products mis-filed at the wrong
consensus_canonical / consensus_pid. Build an exclusion list the calculator
can use to skip these at query time.

Strategy: for each consensus_pid, the product NAME should contain the
head noun of that pid (or a close variant). Products that don't are
either bridge errors or specialty edge cases. We surface them, apply
deny-list rules to catch the obvious bridge errors, and write the
exclusion list.

Two outputs:
  recipe_pricing/priced_products_excluded.csv   — upc + reason for each
                                                   product to skip
  recipe_pricing/priced_products_audit.csv      — full audit listing
                                                   suspicious rows for
                                                   manual review

The calculator (`calculate_recipe_cost_v7.py`) loads the exclusion list
on startup and filters those upcs from candidate SKUs.
"""
from __future__ import annotations

import csv
import re
import sqlite3
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "recipe_pricing" / "data" / "priced_products_v2.db"
OUT_EXCL = ROOT / "recipe_pricing" / "priced_products_excluded.csv"
OUT_AUDIT = ROOT / "recipe_pricing" / "priced_products_audit.csv"


# ---------------------------------------------------------------------------
# Hard-coded exclusion rules — known bridge errors we want to suppress.
# Each rule = (pid_lower, must_not_match_in_name_lower, reason)
# A product matches a rule if consensus_pid (lower) == pid_lower AND any
# of the must_not_match tokens appears in name (lower).
# ---------------------------------------------------------------------------
HARD_RULES: list[tuple[str, list[str], str]] = [
    # Salt bridge errors
    ("salt", ["water softener", "softener", "ice melt", "melt salt",
              "salt pellets", "rock salt", "epsom", "bath salt",
              "scrub", "for water", "fish tank", "pool"],
     "non-food salt at salt pid"),

    # Butter bridge errors
    ("butter", ["pecan ice cream", "butter pecan", "ice cream", "frozen yogurt",
                "popcorn", "popcorn topper", "butter flavor",
                "almond butter", "peanut butter", "cashew butter",
                "sunflower butter", "bread & butter", "butter & oil",
                "butter spray", "butter lite"],
     "non-butter product at butter pid"),

    # Black pepper / pepper bridge errors
    ("black pepper", ["sauerkraut", "kimchi", "salsa", "marinade",
                       "dressing", "sauce", "rub", "seasoning blend",
                       "rice mix", "marinated", "pickle"],
     "non-pepper product at black pepper pid"),
    ("pepper", ["sauerkraut", "kimchi", "marinade", "rub", "seasoning blend"],
     "non-pepper product at pepper pid"),

    # Lemon / lime juice bridge errors
    ("lemon juice", ["punch", "berry flavor", "drink mix",
                      "punch flavor", "fruit drink", "lemonade powder",
                      "fruit punch", "berry juice"],
     "non-lemon-juice drink at lemon juice pid"),
    ("lime juice", ["punch", "berry flavor", "drink mix", "fruit drink",
                     "fruit punch"],
     "non-lime-juice drink at lime juice pid"),
    ("juice", ["hawaiian punch", "fruit punch", "fruit drink",
                "berry flavor", "punch flavor", "lemonade powder",
                "drink mix"],
     "non-juice drink at juice pid"),

    # Vinegar bridge errors
    ("vinegar", ["cleaning vinegar", "for cleaning", "all-purpose cleaner"],
     "cleaning vinegar at vinegar pid"),

    # Olive bridge errors — Mt. Olive is a brand of pickles/relish, not olives
    ("olive", ["mt. olive bread", "mt. olive sweet", "mt. olive sandwich",
               "mt. olive pickle", "olive garden", "bread & butter chips",
               "pickle", "relish", "gherkin"],
     "non-olive product at olive pid"),
    ("olives", ["mt. olive bread", "mt. olive sweet", "mt. olive sandwich",
                "mt. olive pickle", "olive garden", "bread & butter chips",
                "pickle", "relish", "gherkin"],
     "non-olives product at olives pid"),
    ("green olives", ["mt. olive bread", "mt. olive sweet", "mt. olive sandwich",
                       "bread & butter chips", "pickle", "relish", "gherkin"],
     "non-olive product at green olives pid"),
    # Pickles/Relish at olive consensus_canonical (Pantry > Olives > Pickles)
    ("pickles", ["mt. olive sweet", "mt. olive bread", "bread & butter chips"],
     "pickles in olives canonical_path"),
    ("relish", ["mt. olive sweet relish", "mt. olive bread"],
     "relish in olives canonical_path"),

    # Cream bridge errors
    ("cream", ["ice cream", "shaving cream", "lotion", "moisturizer"],
     "non-cream product at cream pid"),
    ("heavy cream", ["ice cream", "lotion"],
     "non-heavy-cream product at heavy cream pid"),

    # Milk bridge errors
    ("milk", ["milk chocolate bar", "milk chocolate candy"],
     "milk chocolate at milk pid"),

    # Egg bridge errors
    ("egg", ["egg roll", "egg roll wrap", "egg substitute", "egg replacer"],
     "non-egg product at egg pid"),
    ("eggs", ["egg substitute", "egg replacer"],
     "non-eggs product at eggs pid"),

    # Sugar
    ("sugar", ["sugar substitute", "sugar free", "sugar cookie", "sugar wafer",
               "for baking decorating"],
     "non-sugar product at sugar pid"),

    # Spice/herb bridge errors (oregano/basil/parsley filed at sauce/tomato pids)
    ("oregano", ["diced tomatoes", "tomato sauce", "spaghetti sauce",
                  "marinara"],
     "non-oregano product at oregano pid"),
    ("basil", ["diced tomatoes", "tomato sauce", "marinara",
                "spaghetti sauce"],
     "non-basil product at basil pid"),

    # Generic non-food flag (any pid)
    ("*", ["soap", "shampoo", "conditioner", "deodorant", "lotion",
           "candle", "candle wick", "fragrance oil", "essential oil bath",
           "scrub", "fertilizer", "ice melt", "fishing line",
           "livestock", "poultry feed", "chicken feed", "feeding livestock",
           "for feeding", "bird seed", "wild bird", "deer feed",
           "horse feed", "fish food", "cat food", "dog food", "pet food",
           "dewormer", "supplement powder for pet"],
     "non-food item"),

    # Baby/infant food at adult-food pids — do NOT pick baby food when
    # the recipe asks for adult-food broth/cereal/etc.
    ("*", ["baby food", "infant food", "stage 1", "stage 2", "stage 3",
            "for toddlers", "for infants", "beech-nut", "gerber baby",
            "earth's best organic baby"],
     "baby food at adult pid"),

    # Shrimp/Seafood seasoning bridge errors — these bouillon/boil/seasoning
    # products keep getting shelved next to meat at seafood pids
    ("shrimp", ["crab boil", "shrimp boil", "crawfish boil", "seasoning",
                "bouillon", "stock cube", "broth cube", "rub", "spice",
                "marinade", "boil bag", "seafood seasoning", "old bay"],
     "seasoning at shrimp pid"),
    ("crab", ["crab boil", "shrimp boil", "crawfish boil", "seasoning",
              "bouillon", "rub", "spice"],
     "seasoning at crab pid"),
    ("lobster", ["seasoning", "spice", "bouillon", "broth"],
     "seasoning at lobster pid"),
    ("scallop", ["seasoning", "rub"],
     "seasoning at scallop pid"),
    ("clam", ["clam chowder", "broth", "boil", "seasoning"],
     "non-clam at clam pid"),
    ("fish", ["fish food", "aquarium", "fish sauce", "tamari", "fish bouillon",
              "fish stock cube"],
     "non-fish-meat at fish pid"),

    # Beef/poultry seasoning bridge errors
    ("beef", ["seasoning", "rub", "marinade only", "bouillon", "stock cube",
              "gravy mix", "ramen", "instant noodles", "jerky cure"],
     "seasoning at beef pid"),
    ("chicken", ["seasoning", "rub", "marinade only", "bouillon", "stock cube",
                 "gravy mix", "ramen", "instant noodles"],
     "seasoning at chicken pid"),
]


def name_matches_rule(name: str, must_not_match: list[str]) -> str | None:
    nl = name.lower()
    for token in must_not_match:
        if token in nl:
            return token
    return None


def main() -> int:
    if not DB.exists():
        raise SystemExit(f"missing {DB}")
    con = sqlite3.connect(str(DB))
    con.row_factory = sqlite3.Row
    cur = con.cursor()

    # 1. Apply hard rules
    print("scanning priced_products against hard rules...", file=sys.stderr)
    excluded: list[dict] = []
    seen_upcs: set[str] = set()
    by_reason: Counter = Counter()

    for pid, must_not, reason in HARD_RULES:
        if pid == "*":
            cur.execute(
                "SELECT upc, name, consensus_pid, consensus_canonical FROM priced_products "
                "WHERE available = 1"
            )
        else:
            cur.execute(
                "SELECT upc, name, consensus_pid, consensus_canonical FROM priced_products "
                "WHERE LOWER(consensus_pid) = ? AND available = 1",
                (pid,),
            )
        for row in cur.fetchall():
            upc = row["upc"]
            name = row["name"] or ""
            if upc in seen_upcs:
                continue
            matched = name_matches_rule(name, must_not)
            if matched:
                excluded.append({
                    "upc": upc,
                    "name": name,
                    "consensus_pid": row["consensus_pid"] or "",
                    "consensus_canonical": row["consensus_canonical"] or "",
                    "matched_token": matched,
                    "reason": reason,
                })
                seen_upcs.add(upc)
                by_reason[reason] += 1

    # 2. Audit (broader): for each consensus_pid, find products whose name
    #    doesn't contain the pid head noun. Output to audit CSV but DON'T
    #    auto-exclude (too noisy without manual review).
    print("building suspicious-name audit (non-blocking)...", file=sys.stderr)
    pid_head_token: dict[str, str] = {}
    cur.execute(
        "SELECT consensus_pid, COUNT(*) FROM priced_products "
        "WHERE consensus_pid != '' AND available = 1 "
        "GROUP BY consensus_pid HAVING COUNT(*) >= 5"
    )
    pids_to_audit = [row[0] for row in cur.fetchall()]

    audit_rows: list[dict] = []
    for pid in pids_to_audit:
        # head noun = last word
        words = pid.lower().split()
        if not words:
            continue
        head = words[-1].rstrip("s")
        # check if products at this pid all contain the head
        cur.execute(
            "SELECT upc, name, consensus_canonical FROM priced_products "
            "WHERE consensus_pid = ? AND available = 1 LIMIT 200",
            (pid,),
        )
        for row in cur.fetchall():
            nl = (row["name"] or "").lower()
            if head and head not in nl and (head + "s") not in nl:
                # missing head — suspicious
                audit_rows.append({
                    "upc": row["upc"],
                    "name": row["name"] or "",
                    "consensus_pid": pid,
                    "consensus_canonical": row["consensus_canonical"] or "",
                    "missing_token": head,
                })

    # 3. Write outputs
    OUT_EXCL.parent.mkdir(parents=True, exist_ok=True)
    with OUT_EXCL.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=[
            "upc", "name", "consensus_pid", "consensus_canonical",
            "matched_token", "reason",
        ])
        w.writeheader()
        w.writerows(excluded)
    with OUT_AUDIT.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=[
            "upc", "name", "consensus_pid", "consensus_canonical",
            "missing_token",
        ])
        w.writeheader()
        w.writerows(audit_rows)

    # Sample some excluded for the operator to verify
    print(f"\nhard-excluded products: {len(excluded):,}", file=sys.stderr)
    print(f"\nby reason:", file=sys.stderr)
    for reason, n in by_reason.most_common():
        print(f"  {n:>5}  {reason}", file=sys.stderr)
    print(f"\nsample excluded (first 12):", file=sys.stderr)
    for r in excluded[:12]:
        print(f"  pid={r['consensus_pid']!r:<22} name={r['name'][:62]!r}", file=sys.stderr)

    print(f"\nsuspicious (head-noun missing, audit only): {len(audit_rows):,}", file=sys.stderr)
    print(f"  {OUT_EXCL}", file=sys.stderr)
    print(f"  {OUT_AUDIT}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
