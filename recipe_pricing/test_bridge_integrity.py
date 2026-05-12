#!/usr/bin/env python3
"""R12 integrity gate — ground-truth assertions for bridge correctness.

Reads recipe_pricing/bridge_truth.csv. For each truth row:
  1. Look up recipe-side concept_key in concept_resolution
  2. Find the cheapest priced SKU at the resolved concept
  3. Assert:
     a. Resolved priced_top_cat ∈ allowed (required_top_cat or NO_MATCH)
     b. Cheapest SKU name contains at least one must_contain_any token
     c. Cheapest SKU name contains NONE of the must_not_contain_any tokens

Exit code 0 only if ALL truth rows pass. Prints a numbered failure list with
per-row diagnostic so a human can fix the data without reading code.

Usage:
  python3 recipe_pricing/test_bridge_integrity.py [--quiet] [--first-n 50]
"""
from __future__ import annotations
import argparse, csv, json, math, re, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TRUTH = ROOT / "recipe_pricing" / "bridge_truth.csv"
CR = ROOT / "planner" / "data" / "concept_resolution.json"
CI = ROOT / "planner" / "data" / "concept_index.json"
OUT_FAIL = ROOT / "recipe_pricing" / "bridge_truth_failures.csv"


def _stem(t: str) -> str:
    if len(t) <= 3: return t
    if t.endswith("ies") and len(t) > 4: return t[:-3] + "y"
    if t.endswith("oes") and len(t) > 4: return t[:-2]
    if t.endswith("es")  and len(t) > 3 and not t.endswith("ses"): return t[:-2]
    if t.endswith("s")   and not t.endswith("ss"): return t[:-1]
    return t


def _normalize(s: str) -> str:
    """Lowercase, collapse spaces, drop hyphens/punct so 'bread crumbs'
    and 'breadcrumbs' compare equal."""
    s = s.lower()
    s = re.sub(r"[^a-z0-9 ]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    # Also produce a no-space variant for compound-word matching
    return s


def _contains(haystack: str, needle: str) -> bool:
    """Stem-aware, space-tolerant containment.
    'apples' matches 'apple' (and vice-versa); 'breadcrumbs' matches
    'bread crumbs'."""
    h = _normalize(haystack)
    n = _normalize(needle)
    if not n or not h: return False
    h_compact = h.replace(" ", "")
    n_compact = n.replace(" ", "")
    if n in h or n_compact in h_compact: return True
    # Stem each token and re-test
    h_stems = " ".join(_stem(t) for t in h.split())
    n_stems = " ".join(_stem(t) for t in n.split())
    if n_stems in h_stems: return True
    h_cs = h_stems.replace(" ", "")
    n_cs = n_stems.replace(" ", "")
    return n_cs in h_cs


def cheapest(packages: list, grams_needed: float = 100):
    if not packages: return None
    best = None; bs = 10**12
    for p in packages:
        g = p.get("grams", 0); c = p.get("cents", 0)
        if g <= 0: continue
        n = max(1, math.ceil(grams_needed / g))
        s = n * c
        if s < bs: bs = s; best = p
    return best


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--quiet", action="store_true")
    ap.add_argument("--first-n", type=int, default=0)
    args = ap.parse_args()

    cr = json.loads(CR.read_text())
    ci = json.loads(CI.read_text())

    failures = []
    n_pass = 0; n_total = 0
    with TRUTH.open() as f:
        rows = list(csv.DictReader(f))
    if args.first_n:
        rows = rows[:args.first_n]

    for tr in rows:
        n_total += 1
        cp = tr["recipe_cp"]; htc_form = tr["htc_form"]
        req_top = tr["required_top_cat"]
        mc_any = [t for t in (tr["must_contain_any"] or "").split("|") if t]
        mn_any = [t for t in (tr["must_not_contain_any"] or "").split("|") if t]
        ck = f"{cp}|{htc_form}"
        res = cr.get(ck, {})
        priced_key = res.get("priced_key") or ""
        tier = res.get("tier", "NO_MATCH")

        sku_name = ""; priced_cp = ""
        if priced_key and priced_key in ci:
            priced_cp = ci[priced_key]["canonical_path"]
            pkg = cheapest(ci[priced_key].get("packages", []))
            sku_name = (pkg.get("name","") or "") if pkg else ""

        priced_top = priced_cp.split(" > ")[0] if priced_cp else ""

        # Assertion 0: NO_MATCH must FAIL unless truth row explicitly allows
        # it (allow_no_match=true). Without this, the resolver pushing
        # everything to NO_MATCH would inflate the test pass rate.
        allow_no_match = (tr.get("allow_no_match","").lower() == "true")
        bad_no_match = (tier == "NO_MATCH" and not allow_no_match)
        # Assertion 1: top-cat (multi-cat req via "|")
        allowed_tops = {t.strip() for t in (req_top or "").split("|") if t.strip()}
        bad_top = bool(priced_top and allowed_tops and priced_top not in allowed_tops)
        # Assertion 2: must_contain (any of)
        bad_mc = bool(sku_name and mc_any and not any(_contains(sku_name, t) for t in mc_any))
        # Assertion 3: must_not_contain (none of)
        hit_neg = [t for t in mn_any if t and _contains(sku_name, t)]
        bad_mn = bool(sku_name and hit_neg)

        if not (bad_no_match or bad_top or bad_mc or bad_mn):
            n_pass += 1
            continue

        reasons = []
        if bad_no_match: reasons.append("NO_MATCH_NOT_ALLOWED")
        if bad_top: reasons.append(f"TOP_CAT[{priced_top}!={req_top}]")
        if bad_mc:  reasons.append(f"MISS_CONTAIN[need={'/'.join(mc_any)}]")
        if bad_mn:  reasons.append(f"NEG_HIT[{','.join(hit_neg)}]")
        failures.append({
            "recipe_cp": cp,
            "tier": tier,
            "priced_cp": priced_cp,
            "picked_sku": sku_name[:60],
            "n_recipes": tr.get("n_recipes_baseline",""),
            "reasons": "|".join(reasons),
        })

    if failures:
        with OUT_FAIL.open("w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(failures[0].keys()))
            w.writeheader()
            for r in failures: w.writerow(r)

    pct = (n_pass / n_total * 100.0) if n_total else 0
    print(f"\nBRIDGE INTEGRITY: {n_pass}/{n_total} pass ({pct:.1f}%)",
          file=sys.stderr)
    if failures:
        print(f"\nTop 30 failures (by recipe-impact):", file=sys.stderr)
        failures.sort(key=lambda r: -int(r.get("n_recipes") or 0))
        for fr in failures[:30]:
            print(f"  [{fr['n_recipes']:>5}] {fr['recipe_cp'][:38]:<38} → "
                  f"{fr['picked_sku'][:38]:<38} :: {fr['reasons']}",
                  file=sys.stderr)
        print(f"\n→ {OUT_FAIL}", file=sys.stderr)
    sys.exit(0 if not failures else 1)


if __name__ == "__main__":
    main()
