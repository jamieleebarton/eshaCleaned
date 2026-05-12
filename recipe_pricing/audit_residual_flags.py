#!/usr/bin/env python3
"""Triage residual flags from recipe_line_comparison FULL output.

Reads the per-recipe summary + line-level CSV, groups failing patterns by
canonical_path (and FNDDS code where relevant), queries priced_products_v2.db
for alternative paths/SKUs, and emits a ranked candidate CSV with
suggested_action + confidence per pattern.

Also produces a 253-pick subset analysis (filtered to recipes the planner
actually picked over 12 weeks) for cost-weighted impact.

Read-only. Writes:
  recipe_pricing/audit_residual_flags.csv
  recipe_pricing/audit_residual_flags_picked.csv

Usage:
  python3 recipe_pricing/audit_residual_flags.py \
      --summary planner/data/recipe_line_comparison_FULL_v3_summary.csv \
      --lines   planner/data/recipe_line_comparison_FULL_v3.csv \
      --picked  /tmp/multi_week_ours_12w.json
"""
from __future__ import annotations
import argparse, csv, json, sqlite3, sys, re
from collections import defaultdict, Counter
from pathlib import Path

csv.field_size_limit(2**30)

ROOT = Path(__file__).resolve().parents[1]
DB   = ROOT / "recipe_pricing" / "data" / "priced_products_v2.db"

# Top-N patterns to surface per flag
TOPN = 25

# Flags we care about (others are noise / known-legit)
FLAGS_OF_INTEREST = ["OUR_NO_MATCH", "WE_UNDERPRICE", "WE_OVERPRICE",
                      "GRAMS_2X_HIGH", "GRAMS_2X_LOW", "LINE_COUNT_OFF",
                      "POOL_TINY", "OUR_NO_SPEND"]

STOPWORDS = {"the","a","an","of","and","or","with","fresh","raw","organic","plain",
              "whole","sliced","chopped","diced","minced","ground","cooked","frozen",
              "canned","dried","cut","shredded","grated","peeled","trimmed"}


def leaf_tokens(canonical_path: str) -> set[str]:
    if not canonical_path: return set()
    leaf = canonical_path.split(" > ")[-1].lower()
    toks = set(re.findall(r"[a-z]+", leaf))
    return {t for t in toks if len(t) > 2 and t not in STOPWORDS}


def load_summary(path: Path) -> list[dict]:
    rows = []
    with path.open() as f:
        for r in csv.DictReader(f):
            rows.append(r)
    return rows


def index_lines_by_rid(path: Path) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = defaultdict(list)
    with path.open() as f:
        for r in csv.DictReader(f):
            out[r["recipe_id"]].append(r)
    return out


def alt_path_for(con, our_path: str, our_htc_form: str | None = None) -> tuple[str, int, str]:
    """Find the canonical_path with most SKUs whose leaf-tokens overlap with `our_path`'s
    leaf, optionally filtered by htc_form_code. Returns (alt_path, n_skus, confidence)."""
    if not our_path: return ("", 0, "low")
    leaf = our_path.split(" > ")[-1]
    leaf_lc = leaf.lower()
    # Strict candidates: paths ending with the same leaf token
    q = """
        SELECT consensus_canonical, COUNT(*)
        FROM priced_products
        WHERE LOWER(consensus_canonical) LIKE ?
          AND available=1 AND non_food_path=0
        GROUP BY consensus_canonical
        ORDER BY COUNT(*) DESC LIMIT 4
    """
    rows = con.execute(q, (f"% > {leaf_lc}",)).fetchall()
    if rows:
        alt, n = rows[0]
        # If alt == our_path, it's not really an alternative
        if alt and alt != our_path:
            return (alt, n, "high")
        if len(rows) >= 2 and rows[1][0] != our_path:
            return (rows[1][0], rows[1][1], "high")

    # Looser: any path containing the leaf token
    rows = con.execute("""
        SELECT consensus_canonical, COUNT(*)
        FROM priced_products
        WHERE LOWER(consensus_canonical) LIKE ?
          AND available=1 AND non_food_path=0
          AND consensus_canonical != ?
        GROUP BY consensus_canonical
        ORDER BY COUNT(*) DESC LIMIT 4
    """, (f"%{leaf_lc}%", our_path)).fetchall()
    if rows:
        return (rows[0][0], rows[0][1], "medium")

    # Token-fallback
    toks = leaf_tokens(our_path)
    if toks:
        like_clauses = " OR ".join("LOWER(consensus_canonical) LIKE ?" for _ in toks)
        params = [f"%{t}%" for t in toks] + [our_path]
        rows = con.execute(f"""
            SELECT consensus_canonical, COUNT(*)
            FROM priced_products
            WHERE ({like_clauses})
              AND available=1 AND non_food_path=0
              AND consensus_canonical != ?
            GROUP BY consensus_canonical
            ORDER BY COUNT(*) DESC LIMIT 4
        """, params).fetchall()
        if rows:
            return (rows[0][0], rows[0][1], "low")
    return ("", 0, "low")


def cheaper_sku_at_path(con, path: str, exclude_sku: str = "") -> tuple[str, float, float]:
    """For WE_OVERPRICE: is there a cheaper SKU at the same canonical_path
    we should have picked? Returns (name, cents, grams) or ('', 0, 0)."""
    rows = con.execute("""
        SELECT name, cents, grams
        FROM priced_products
        WHERE consensus_canonical = ? AND available=1 AND non_food_path=0
          AND grams > 50 AND cents > 0
          AND name != ?
        ORDER BY (cents * 1.0 / grams) ASC LIMIT 1
    """, (path, exclude_sku)).fetchall()
    if rows:
        return (rows[0][0][:60], rows[0][1] / 100.0, rows[0][2])
    return ("", 0.0, 0.0)


def classify_alias_confidence(our_path: str, alt_path: str) -> str:
    """ASCII-fold + plural + redundant-adjective patterns are high-confidence."""
    if not (our_path and alt_path): return "low"
    our_leaf = our_path.split(" > ")[-1].lower()
    alt_leaf = alt_path.split(" > ")[-1].lower()
    # ASCII fold
    fold = str.maketrans("áàâäéèêëíìîïóòôöúùûüñç", "aaaaeeeeiiiioooouuuunc")
    if our_leaf.translate(fold) == alt_leaf.translate(fold):
        return "high"
    # Plural / -ies / -es
    if our_leaf.rstrip("s") == alt_leaf.rstrip("s"): return "high"
    if our_leaf.replace("ies","y") == alt_leaf.replace("ies","y"): return "high"
    # Same leaf word
    if our_leaf == alt_leaf: return "high"
    # Same leaf token after stopword strip
    ot = leaf_tokens(our_path); at = leaf_tokens(alt_path)
    if ot and at and ot.issubset(at | ot) and len(ot & at) >= max(1, min(len(ot), len(at)) // 2):
        return "medium"
    return "low"


def triage_no_match(con, summary: list[dict], lines_by_rid: dict[str, list[dict]],
                     subset_rids: set[str] | None = None) -> list[dict]:
    """Group OUR_NO_MATCH failures by our_canonical_path."""
    by_path: dict[str, dict] = defaultdict(lambda: {"n_recipes": 0, "n_lines": 0,
                                                       "sample_recipes": [], "spend_delta": 0.0})
    for s in summary:
        if "OUR_NO_MATCH" not in s.get("flags",""): continue
        rid = s["recipe_id"]
        if subset_rids is not None and rid not in subset_rids: continue
        for ln in lines_by_rid.get(rid, []):
            if ln["our_sku"] == "(none)":
                p = by_path[ln["our_canonical_path"]]
                p["n_lines"] += 1
                if rid not in p["sample_recipes"]:
                    p["sample_recipes"].append(rid)
                    p["n_recipes"] += 1
                # Spend delta = what we *would have spent* (Hestia's pick) we missed
                try:
                    p["spend_delta"] += float(ln["hes_spend"] or 0)
                except: pass

    out = []
    for path, d in sorted(by_path.items(), key=lambda kv: -kv[1]["n_lines"])[:TOPN]:
        alt, n_alt, alt_conf = alt_path_for(con, path)
        conf = classify_alias_confidence(path, alt)
        out.append({
            "flag": "OUR_NO_MATCH",
            "our_canonical_path": path,
            "hestia_fndds": "",
            "n_lines": d["n_lines"],
            "n_recipes": d["n_recipes"],
            "spend_delta_$": round(d["spend_delta"], 2),
            "alt_path": alt,
            "n_skus_at_alt": n_alt,
            "confidence": conf,
            "suggested_action": "alias" if conf in ("high","medium") and alt else "investigate",
            "sample_recipes": "|".join(d["sample_recipes"][:3]),
        })
    return out


def triage_underprice(con, summary: list[dict], lines_by_rid: dict[str, list[dict]],
                       subset_rids: set[str] | None = None) -> list[dict]:
    """Group WE_UNDERPRICE recipes (excluding NO_MATCH overlap) by our_canonical_path."""
    by_path: dict[str, dict] = defaultdict(lambda: {"n_recipes": 0, "spend_delta": 0.0,
                                                       "samples": []})
    for s in summary:
        flags = s.get("flags","")
        if "WE_UNDERPRICE" not in flags: continue
        if "OUR_NO_MATCH" in flags: continue  # already counted in no_match
        rid = s["recipe_id"]
        if subset_rids is not None and rid not in subset_rids: continue
        # Find the line(s) with biggest individual underprice within this recipe
        rid_lines = sorted(lines_by_rid.get(rid, []),
                            key=lambda ln: float(ln.get("spend_diff") or 0))
        for ln in rid_lines[:3]:
            if not ln["our_canonical_path"]: continue
            try: sd = float(ln.get("spend_diff") or 0)
            except: sd = 0
            if sd >= 0: continue  # only underprice
            p = by_path[ln["our_canonical_path"]]
            p["n_recipes"] += 1
            p["spend_delta"] += sd
            if len(p["samples"]) < 3:
                p["samples"].append(f"{rid}: ours={ln['our_sku'][:40]} (${ln['our_spend']}) vs hes={ln['hestia_sku'][:40]} (${ln['hes_spend']})")

    out = []
    for path, d in sorted(by_path.items(), key=lambda kv: kv[1]["spend_delta"])[:TOPN]:
        out.append({
            "flag": "WE_UNDERPRICE",
            "our_canonical_path": path,
            "hestia_fndds": "",
            "n_lines": "",
            "n_recipes": d["n_recipes"],
            "spend_delta_$": round(d["spend_delta"], 2),
            "alt_path": "",
            "n_skus_at_alt": "",
            "confidence": "investigate",
            "suggested_action": "manual_review",
            "sample_recipes": d["samples"][0] if d["samples"] else "",
        })
    return out


def triage_overprice(con, summary: list[dict], lines_by_rid: dict[str, list[dict]],
                      subset_rids: set[str] | None = None) -> list[dict]:
    """Group WE_OVERPRICE by our_canonical_path; for each, look for cheaper SKU
    at same path that we should have picked."""
    by_path: dict[str, dict] = defaultdict(lambda: {"n_recipes": 0, "spend_delta": 0.0,
                                                       "samples": []})
    for s in summary:
        flags = s.get("flags","")
        if "WE_OVERPRICE" not in flags: continue
        rid = s["recipe_id"]
        if subset_rids is not None and rid not in subset_rids: continue
        rid_lines = sorted(lines_by_rid.get(rid, []),
                            key=lambda ln: -float(ln.get("spend_diff") or 0))
        for ln in rid_lines[:3]:
            if not ln["our_canonical_path"]: continue
            try: sd = float(ln.get("spend_diff") or 0)
            except: sd = 0
            if sd <= 0: continue
            p = by_path[ln["our_canonical_path"]]
            p["n_recipes"] += 1
            p["spend_delta"] += sd
            if len(p["samples"]) < 3:
                p["samples"].append(f"{rid}: ours={ln['our_sku'][:40]} (${ln['our_spend']})")

    out = []
    for path, d in sorted(by_path.items(), key=lambda kv: -kv[1]["spend_delta"])[:TOPN]:
        cheaper_name, cheaper_cents, cheaper_g = cheaper_sku_at_path(con, path)
        out.append({
            "flag": "WE_OVERPRICE",
            "our_canonical_path": path,
            "hestia_fndds": "",
            "n_lines": "",
            "n_recipes": d["n_recipes"],
            "spend_delta_$": round(d["spend_delta"], 2),
            "alt_path": cheaper_name,
            "n_skus_at_alt": int(cheaper_g),
            "confidence": "high" if cheaper_name else "low",
            "suggested_action": "picker_review" if cheaper_name else "accept",
            "sample_recipes": d["samples"][0] if d["samples"] else "",
        })
    return out


def triage_grams_2x(summary: list[dict], lines_by_rid: dict[str, list[dict]],
                     subset_rids: set[str] | None = None,
                     direction: str = "HIGH") -> list[dict]:
    """Group GRAMS_2X by our_canonical_path. Common pattern: bone-in vs boneless yield."""
    flag = f"GRAMS_2X_{direction}"
    by_path: dict[str, dict] = defaultdict(lambda: {"n_recipes": 0, "g_ratio_avg": 0.0,
                                                       "samples": []})
    for s in summary:
        if flag not in s.get("flags",""): continue
        rid = s["recipe_id"]
        if subset_rids is not None and rid not in subset_rids: continue
        for ln in lines_by_rid.get(rid, []):
            if not ln["our_canonical_path"]: continue
            try: gr = float(ln.get("gram_ratio") or 0)
            except: gr = 0
            if direction == "HIGH" and gr <= 2.0: continue
            if direction == "LOW" and (gr >= 0.5 or gr <= 0): continue
            p = by_path[ln["our_canonical_path"]]
            p["n_recipes"] += 1
            p["g_ratio_avg"] += gr
            if len(p["samples"]) < 3:
                p["samples"].append(f"{rid}: ours={ln['our_grams']}g vs hes={ln['hestia_grams']}g (ratio={ln['gram_ratio']})")

    out = []
    for path, d in sorted(by_path.items(), key=lambda kv: -kv[1]["n_recipes"])[:TOPN]:
        out.append({
            "flag": flag,
            "our_canonical_path": path,
            "hestia_fndds": "",
            "n_lines": "",
            "n_recipes": d["n_recipes"],
            "spend_delta_$": "",
            "alt_path": f"avg_ratio={d['g_ratio_avg']/max(1,d['n_recipes']):.2f}",
            "n_skus_at_alt": "",
            "confidence": "investigate",
            "suggested_action": "data_fix",
            "sample_recipes": d["samples"][0] if d["samples"] else "",
        })
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--summary", required=True)
    ap.add_argument("--lines",   required=True)
    ap.add_argument("--picked",  default=None,
                     help="Path to multi_week_ours.json — limit to picked rids")
    ap.add_argument("--out",     default="recipe_pricing/audit_residual_flags.csv")
    ap.add_argument("--out-picked", default="recipe_pricing/audit_residual_flags_picked.csv")
    args = ap.parse_args()

    print(f"loading summary: {args.summary}", file=sys.stderr)
    summary = load_summary(Path(args.summary))
    print(f"  {len(summary):,} recipes", file=sys.stderr)

    # Flag distribution
    flag_counts: Counter = Counter()
    for s in summary:
        for fl in s.get("flags","").split("|"):
            if fl: flag_counts[fl] += 1
    print("\nFlag distribution (entire corpus):", file=sys.stderr)
    for fl in FLAGS_OF_INTEREST:
        n = flag_counts.get(fl, 0)
        print(f"  {fl:<18} {n:>7,}  ({n*100/max(1,len(summary)):>5.1f}%)", file=sys.stderr)

    print(f"\nloading lines: {args.lines}", file=sys.stderr)
    lines_by_rid = index_lines_by_rid(Path(args.lines))
    print(f"  {sum(len(v) for v in lines_by_rid.values()):,} lines across "
          f"{len(lines_by_rid):,} recipes", file=sys.stderr)

    con = sqlite3.connect(str(DB))
    con.execute("PRAGMA query_only=ON")

    def run_triage(subset: set[str] | None, out_path: str, label: str):
        rows = []
        rows += triage_no_match(con, summary, lines_by_rid, subset)
        rows += triage_underprice(con, summary, lines_by_rid, subset)
        rows += triage_overprice(con, summary, lines_by_rid, subset)
        rows += triage_grams_2x(summary, lines_by_rid, subset, "HIGH")
        rows += triage_grams_2x(summary, lines_by_rid, subset, "LOW")
        out = Path(out_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        if rows:
            with out.open("w", newline="") as f:
                w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
                w.writeheader()
                for r in rows: w.writerow(r)
        print(f"\n→ {out}  ({len(rows)} {label} triage rows)", file=sys.stderr)

    run_triage(None, args.out, "full corpus")

    if args.picked:
        d = json.loads(Path(args.picked).read_text())
        rids = set()
        for w in d["weeks"]: rids.update(str(x) for x in w["recipe_ids"])
        print(f"\nlimiting to {len(rids):,} picked recipe IDs from {args.picked}",
              file=sys.stderr)
        run_triage(rids, args.out_picked, "picked subset")


if __name__ == "__main__":
    main()
