#!/usr/bin/env python3
"""P2 — Tag every unique recipe ingredient with an HTC code.

Goal is 100% coverage: every recipe ingredient resolves to an 8-char HTC.
If the deterministic encoder can't pick a group from the item string alone,
we tokenize and try each token; if STILL nothing matches, we mark group=0
and emit anyway so we can see the gap.

Input:  recipe_ingredient_items.csv (22k unique items)
Output: recipe_ingredient_htc_tagged.csv
"""
from __future__ import annotations

import argparse
import csv
import re
import sys
import time
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from htc.encoder import encode, GROUP_RULES, _match_first  # noqa: E402

HERE = Path(__file__).resolve().parent
DEFAULT_IN = HERE / "output" / "recipe_ingredient_items.csv"
DEFAULT_OUT = HERE / "output" / "recipe_ingredient_htc_tagged.csv"

WS = re.compile(r"\s+")
NONALPHA = re.compile(r"[^a-z0-9 ]+")


def normalize(s: str) -> str:
    return WS.sub(" ", NONALPHA.sub(" ", (s or "").lower())).strip()


def aggressive_token_fallback(item: str) -> str | None:
    """If primary encoder gives group=0, try each token of the item.

    Recipe ingredients are usually 1-4 tokens. Try the longest meaningful
    token first (typically the head noun at the end), then walk back."""
    tokens = [t for t in normalize(item).split() if len(t) > 1]
    # try right-to-left first (head noun usually trails)
    for tok in reversed(tokens):
        g = _match_first(GROUP_RULES, tok)
        if g != "0":
            return g
    # then try each substring (handles compound nouns like "garam masala")
    norm = normalize(item)
    for length in (3, 2):
        for i in range(len(tokens) - length + 1):
            phrase = " ".join(tokens[i:i + length])
            g = _match_first(GROUP_RULES, phrase)
            if g != "0":
                return g
    return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="inp", type=Path, default=DEFAULT_IN)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = ap.parse_args()

    args.out.parent.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    n = tagged = unresolved = 0
    fallback_used = 0
    by_group: Counter[str] = Counter()
    unresolved_items: list[str] = []

    with args.inp.open() as f, args.out.open("w", newline="") as g:
        r = csv.DictReader(f)
        w = csv.writer(g)
        w.writerow([
            "item", "recipe_count", "grams_total",
            "htc_code", "htc_group", "htc_family", "htc_food",
            "htc_form", "htc_processing", "htc_ptype", "htc_check",
            "htc_confidence", "htc_source",
        ])
        for row in r:
            n += 1
            item = row.get("item", "")
            sample_disp = row.get("sample_displays", "")
            # Primary encode uses ITEM ONLY for group/family decisions.
            # sample_displays is too noisy ("blueberries in fruit salad" leaks
            # 'salad' into Vegetables; "1 tbsp saffron, soaked in milk" leaks
            # 'milk' into Dairy). Form/processing/ptype are facet-extracted
            # separately by match_recipes_unified.py against per-HTC vocabs.
            h = encode(category="", description=item, extra="")
            source = h.source
            confidence = h.confidence
            group = h.group
            if group == "0":
                fb = aggressive_token_fallback(item)
                if fb:
                    h = encode(category="", description=item + " " + fb, extra="")
                    if h.group == "0":
                        # force the group via fallback by re-encoding with fallback hint
                        # (extra route: prepend a synthetic category-like token)
                        from htc.encoder import (FORM_RULES, FAMILY_RULES, PROC_RULES,
                                                 PTYPE_RULES, crockford_check)
                        combined = f"{item} {sample_disp}"
                        form = _match_first(FORM_RULES, combined)
                        family = "0"
                        for pat, code in FAMILY_RULES.get(fb, []):
                            if pat.search(combined):
                                family = code
                                break
                        proc = _match_first(PROC_RULES, combined)
                        ptype = _match_first(PTYPE_RULES, combined)
                        code_7 = f"{fb}{family}00{form}{proc}{ptype}"
                        check = crockford_check(code_7)
                        from htc.encoder import HTC
                        h = HTC(code=code_7 + check, group=fb, family=family, food="00",
                                form=form, processing=proc, ptype=ptype, check=check,
                                confidence=0.5, source="token_fallback")
                    fallback_used += 1
                    source = "token_fallback"
                    confidence = 0.5
                    group = h.group

            if group != "0":
                tagged += 1
                by_group[group] += 1
            else:
                unresolved += 1
                if len(unresolved_items) < 200:
                    unresolved_items.append(item)

            w.writerow([
                item, row.get("recipe_count", ""), row.get("grams_total", ""),
                h.code, h.group, h.family, h.food,
                h.form, h.processing, h.ptype, h.check,
                f"{confidence:.2f}", source,
            ])

    print(f"[{time.time()-t0:6.1f}s] {n:,} unique items processed")
    print(f"  tagged:        {tagged:,}  ({tagged/n:.1%})")
    print(f"  fallback used: {fallback_used:,}")
    print(f"  unresolved:    {unresolved:,}  ({unresolved/n:.1%})")
    print(f"  by group:")
    for g_, c in by_group.most_common():
        print(f"    {g_}: {c:>5,}")
    if unresolved_items:
        print(f"  sample unresolved (first 25):")
        for u in unresolved_items[:25]:
            print(f"    {u!r}")
    print(f"  -> {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
