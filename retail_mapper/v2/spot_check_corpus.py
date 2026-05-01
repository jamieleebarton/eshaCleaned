#!/usr/bin/env python3
"""Spot-check the full corpus output as it streams in.

Usage:
    python3 retail_mapper/v2/spot_check_corpus.py
        # default: latest 10 rows + summary

    python3 retail_mapper/v2/spot_check_corpus.py --random 20
        # show 20 random rows from what's been written so far

    python3 retail_mapper/v2/spot_check_corpus.py --identity "Almond Milk"
        # show all rows that landed on a specific identity

    python3 retail_mapper/v2/spot_check_corpus.py --suspect
        # show only rows with: bare-generic identity, invalid retail_type,
        # parse_error, or empty product_identity. The ones to fix.

    python3 retail_mapper/v2/spot_check_corpus.py --summary
        # just numbers: rows so far, distinct identities, top 25, invalid_rt,
        # parse_errors, cost-to-date
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import random
import sys
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
V2 = REPO / "retail_mapper" / "v2"
DEFAULT_LIVE = V2 / "full_corpus.live.jsonl"


def load_module():
    sp = importlib.util.spec_from_file_location("ltc", V2 / "llm_taxonomy_cleanup.py")
    m = importlib.util.module_from_spec(sp); sys.modules["ltc"] = m
    sp.loader.exec_module(m)
    return m


def stream_rows(path: Path):
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except Exception:
                continue


def print_row(o, m=None):
    rec = o.get("record", {}) or {}
    err = rec.get("_parse_error") or rec.get("_api_error")
    if m and not err:
        rec = m.normalize_record(rec, {"title": o.get("title", ""), "branded_food_category": o.get("branded_food_category", "")})
    print(f"  fdc:        {o.get('fdc_id', '')}")
    print(f"  title:      {o.get('title', '')[:90]}")
    print(f"  bfc:        {o.get('branded_food_category', '')}")
    if err:
        print(f"  ERROR:      {err}")
        return
    print(f"  identity:   {rec.get('product_identity', '?')}")
    print(f"  cat_path:   {rec.get('category_path', '?')}")
    print(f"  retail_type:{rec.get('retail_type', '?')}")
    fac = []
    for f in ("variant", "flavor", "form_texture_cut", "processing_storage", "claims"):
        v = rec.get(f, [])
        if v: fac.append(f"{f}={v}")
    if fac:
        print(f"  facets:     {'  '.join(fac)}")
    comp = rec.get("components", []) or []
    if comp:
        ids = [c.get("identity", "?") for c in comp]
        print(f"  components: {ids}")


def cmd_summary(args, m, rows):
    pids = Counter(); cats = Counter()
    invalid_rt = 0; parse_err = 0; api_err = 0
    bare_generic = 0
    bare_set = {"Bar", "Candy", "Cheese" if False else None, "Snack", "Beverage"}  # not Cheese, that's legitimate
    bare_set = {"Bar", "Bars", "Candy", "Snack", "Beverage", "Drink", "Food"}
    hit = miss = comp_tok = 0
    for o in rows:
        u = o.get("usage", {}) or {}
        if u.get("prompt_cache_hit_tokens") is not None:
            hit += u["prompt_cache_hit_tokens"]
        if u.get("prompt_cache_miss_tokens") is not None:
            miss += u["prompt_cache_miss_tokens"]
        if u.get("completion_tokens") is not None:
            comp_tok += u["completion_tokens"]
        rec = o.get("record", {}) or {}
        if "_parse_error" in rec:
            parse_err += 1; continue
        if "_api_error" in rec:
            api_err += 1; continue
        norm = m.normalize_record(rec, {"title": o.get("title", ""), "branded_food_category": o.get("branded_food_category", "")})
        pid = norm.get("product_identity", "")
        if not pid: pid = "(empty)"
        pids[pid] += 1
        cats[norm.get("category_path", "")] += 1
        if norm.get("retail_type") not in m.RETAIL_TYPES:
            invalid_rt += 1
        if pid in bare_set:
            bare_generic += 1
    n = len(rows)
    cost = (hit * 0.0028 + miss * 0.14 + comp_tok * 0.28) / 1e6
    print(f"  rows so far:           {n:,}")
    print(f"  distinct identities:   {len(pids):,}")
    print(f"  distinct categories:   {len(cats):,}")
    print(f"  invalid retail_types:  {invalid_rt:,}  ({100*invalid_rt/max(n,1):.2f}%)")
    print(f"  parse errors:          {parse_err}")
    print(f"  api errors:            {api_err}")
    print(f"  bare-generic identity: {bare_generic}  ({100*bare_generic/max(n,1):.2f}%)")
    print(f"  cache hit tokens:      {hit:,}")
    print(f"  cache miss tokens:     {miss:,}")
    print(f"  completion tokens:     {comp_tok:,}")
    if hit + miss:
        print(f"  cache hit rate:        {100*hit/(hit+miss):.1f}%")
    print(f"  cost so far:           ${cost:.2f}")
    print()
    print(f"  Top {args.top} identities (after normalizer):")
    for p, c in pids.most_common(args.top):
        in_hint = "★" if p in m.CANONICAL_CATEGORY_HINTS else "✗"
        print(f"    {c:>6,}  {p:40s}  {in_hint}")


def cmd_random(args, m, rows):
    if not rows:
        print("(no rows yet)")
        return
    sample = random.sample(rows, min(args.random, len(rows)))
    for i, o in enumerate(sample, 1):
        print("=" * 100)
        print(f"  Random sample {i}/{len(sample)}")
        print_row(o, m)
    print()


def cmd_latest(args, m, rows):
    if not rows:
        print("(no rows yet)")
        return
    sample = rows[-args.latest:]
    for i, o in enumerate(sample, 1):
        print("=" * 100)
        print(f"  Latest {i}/{len(sample)}")
        print_row(o, m)


def cmd_identity(args, m, rows):
    target = args.identity.lower()
    matches = []
    for o in rows:
        rec = o.get("record", {}) or {}
        if "_parse_error" in rec or "_api_error" in rec:
            continue
        norm = m.normalize_record(rec, {"title": o.get("title", ""), "branded_food_category": o.get("branded_food_category", "")})
        if str(norm.get("product_identity", "")).lower() == target:
            matches.append(o)
    print(f"found {len(matches)} rows with identity={args.identity!r}")
    for o in matches[:args.limit]:
        print("=" * 100)
        print_row(o, m)


def cmd_suspect(args, m, rows):
    bare = {"Bar", "Bars", "Candy", "Snack", "Beverage", "Drink", "Food", "Other", "Item", ""}
    sus = []
    for o in rows:
        rec = o.get("record", {}) or {}
        if "_parse_error" in rec or "_api_error" in rec:
            sus.append(("error", o)); continue
        norm = m.normalize_record(rec, {"title": o.get("title", ""), "branded_food_category": o.get("branded_food_category", "")})
        rt = norm.get("retail_type", "")
        if rt not in m.RETAIL_TYPES:
            sus.append((f"invalid_rt={rt}", o)); continue
        pid = norm.get("product_identity", "")
        if pid in bare or not pid:
            sus.append((f"bare_id={pid!r}", o)); continue
    print(f"found {len(sus)} suspect rows of {len(rows):,}")
    for tag, o in sus[:args.limit]:
        print("=" * 100)
        print(f"  TAG: {tag}")
        print_row(o, m)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--live", type=Path, default=DEFAULT_LIVE)
    parser.add_argument("--random", type=int, default=0,
                        help="Show N random rows.")
    parser.add_argument("--latest", type=int, default=10,
                        help="Show the N most recently written rows (default).")
    parser.add_argument("--identity", type=str, default=None,
                        help="Filter to rows where product_identity exactly matches this.")
    parser.add_argument("--suspect", action="store_true",
                        help="Show only rows with errors, invalid retail_type, or bare-generic identity.")
    parser.add_argument("--summary", action="store_true",
                        help="Print summary stats only.")
    parser.add_argument("--top", type=int, default=25,
                        help="In summary, how many top identities to show.")
    parser.add_argument("--limit", type=int, default=20,
                        help="Cap on detail rows shown.")
    args = parser.parse_args()

    if not args.live.exists():
        print(f"no live file at {args.live}"); raise SystemExit(1)

    m = load_module()
    rows = list(stream_rows(args.live))
    print(f"  >> {len(rows):,} rows in {args.live.name}")
    print()

    if args.summary or (not args.random and not args.identity and not args.suspect):
        cmd_summary(args, m, rows)
        if args.summary:
            return
    if args.random:
        print("\n" + "#" * 100); print("  RANDOM SAMPLE")
        print("#" * 100 + "\n")
        cmd_random(args, m, rows)
    if args.identity:
        print("\n" + "#" * 100); print(f"  IDENTITY={args.identity!r}")
        print("#" * 100 + "\n")
        cmd_identity(args, m, rows)
    if args.suspect:
        print("\n" + "#" * 100); print("  SUSPECT ROWS")
        print("#" * 100 + "\n")
        cmd_suspect(args, m, rows)
    if not (args.summary or args.random or args.identity or args.suspect):
        print("\n" + "#" * 100); print(f"  LATEST {args.latest}")
        print("#" * 100 + "\n")
        cmd_latest(args, m, rows)


if __name__ == "__main__":
    main()
