#!/usr/bin/env python3
"""Call DeepSeek to propose top-down structural rewrites for canonical paths.

Reads `deepseek_input.jsonl` (one batch per top-level family, path-only).
For each batch, prompts DeepSeek-V3 to return a strict {old_path: new_path}
mapping. Pure string transformation; no SKU evidence needed.

Output:
  - deepseek_proposals.jsonl  — one line per batch with the old→new map
  - deepseek_call_log.txt     — raw responses for debugging

Requires:
    export DEEPSEEK_API_KEY=sk-...

Usage:
    python3 retail_mapper/v2/call_deepseek_pathnorm.py
    python3 retail_mapper/v2/call_deepseek_pathnorm.py --resume
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.request
import urllib.error
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
V2 = REPO / "retail_mapper" / "v2"
SRC = V2 / "deepseek_input.jsonl"
OUT = V2 / "deepseek_proposals.jsonl"
LOG = V2 / "deepseek_call_log.txt"

API_URL = "https://api.deepseek.com/chat/completions"
MODEL = "deepseek-chat"

SYSTEM_PROMPT = """You are normalizing a grocery retail taxonomy. Your input \
is a list of canonical category paths from one top-level family (e.g. all \
"Dairy > ..." paths). Your job is to rewrite each path into its top-down \
canonical form.

CORE PRINCIPLE — PATH LEVELS vs FACETS:

Path levels describe what the product IS (type, sub-type, age/sharpness).
Facets describe properties that apply across many types (claims like Organic,
forms like Shredded, package size like 12 oz). Facets are NOT path levels.

So when you see a path like "Dairy > Aged Organic Shredded Cheddar":
  - "Cheddar"       → path noun
  - "Aged"          → path child (sub-type of Cheddar)
  - "Organic"       → DROP from path (it's a claim facet, lives in a separate
                     "claims" column)
  - "Shredded"      → DROP from path (it's a form facet)
Result: "Dairy > Cheese > Cheddar > Aged"

Why: "Organic" is independent of Cheese. The same Organic claim applies to
Bread, Pasta, Apples — putting it as a path level creates tree-explosion and
splits one product into multiple paths. Keep claims and forms OUT of paths.

DROP-FROM-PATH WORDS (claims and forms — facets, not path levels):
  Claims: organic, non-gmo, kosher, halal, vegan, vegetarian, gluten-free,
          dairy-free, lactose-free, sugar-free, fat-free, low-fat, reduced-fat,
          fair-trade, grass-fed, pasture-raised, free-range, cage-free, antibiotic-free,
          hormone-free, no added sugar, unsweetened, low-sodium, no salt added,
          natural, all-natural, pure, premium, select, deluxe, classic, original
  Forms:  shredded, shaved, sliced, block, crumbled, grated, cubed, diced,
          chunk, chunks, ball, balls, stick, sticks, log, wedge, round,
          spread, dip, whipped, soft, hard, frozen, refrigerated, fresh

KEEP-IN-PATH WORDS (genuine sub-types — these belong as path levels):
  Cheese age:    aged, sharp, mild, medium, extra sharp, extra mild, vintage, smoked
  Mozzarella:    fresh, low moisture, part skim, whole milk
  Cheddar color: white, yellow
  (and analogous type-defining sub-categories in other families)

RULES:

1. NOUN-FIRST (top-down): the type/noun comes before any sub-type modifier.
   Bad:  "Dairy > Cheese > Aged Cheddar"
   Good: "Dairy > Cheese > Cheddar > Aged"

2. INSERT MISSING TYPE PARENT: if a path skips an obvious type parent, add it.
   "Dairy > Aged Cheddar" → "Dairy > Cheese > Cheddar > Aged"
   "Snack > Hard Pretzels" → "Snack > Pretzels > Hard"

3. STRIP CLAIMS AND FORMS from the path (they're facets):
   "Dairy > Cheese > Organic Aged Cheddar Shredded"
       → "Dairy > Cheese > Cheddar > Aged"
   "Snack > Chips > Organic Tortilla Chips Bag"
       → "Snack > Chips > Tortilla Chips"

4. KEEP PROPER COMPOUND NAMES: "Monterey Jack", "Pepper Jack", "Half & Half",
   "Mahi Mahi", "Cream Cheese", "Cottage Cheese" are single-name products or
   cheese types. Don't decompose them.

5. STRIP REDUNDANT LEAVES: if leaf duplicates the parent ("Pasta > Macaroni
   > Macaroni"), drop the leaf.

6. FLATTEN COMMA-BLOB PARENTS: replace category-blob middle segments
   ("Pancakes, Waffles, French Toast & Crepes") with the leaf's natural home.

7. FIX BOTTOM-UP LEAVES: any path where the noun is at the END of a multi-word
   leaf with style words in front gets restructured top-down.

8. AT MOST 4 LEVELS deep below the top-level family. If your rewrite would
   create level 5+, collapse to 4.

WORKED EXAMPLES:

Input:  "Dairy > Aged Cheddar"
Output: "Dairy > Cheese > Cheddar > Aged"

Input:  "Dairy > Cheese > Organic Sharp Cheddar Block"
Output: "Dairy > Cheese > Cheddar > Sharp"
        (Organic + Block are facets, dropped)

Input:  "Dairy > Cheese > Mozzarella > Low Moisture Part Skim"
Output: "Dairy > Cheese > Mozzarella > Part Skim"
        (level cap at 4; Low Moisture goes to facet via separate process)

Input:  "Snack > Hard Pretzels"
Output: "Snack > Pretzels > Hard"

Input:  "Bakery > English Muffins"
Output: "Bakery > English Muffins"
        (already canonical)

Input:  "Pantry > Sweeteners > Sugar > Cream > Coconut Cream"
Output: "Pantry > Coconut > Coconut Cream"
        (wholesale wrong-family → reroute)

OUTPUT SCHEMA (STRICT JSON, no markdown, no prose):
{
  "rewrites": {
    "<old_path>": "<new_path>",
    ...
  }
}

Include EVERY input path as a key. If unchanged, set value equal to key.
This keeps the output auditable — every decision explicit.
"""


def call_deepseek(api_key: str, messages: list[dict], timeout: int = 240) -> str:
    body = {
        "model": MODEL,
        "messages": messages,
        "temperature": 0,
        "max_tokens": 8000,
        "response_format": {"type": "json_object"},
    }
    req = urllib.request.Request(
        API_URL,
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    return payload["choices"][0]["message"]["content"]


def chunk_paths(paths: list[str], max_per_chunk: int) -> list[list[str]]:
    """Split a family's paths into chunks if it's too big for a single call."""
    if len(paths) <= max_per_chunk:
        return [paths]
    out: list[list[str]] = []
    for i in range(0, len(paths), max_per_chunk):
        out.append(paths[i:i + max_per_chunk])
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-per-batch", type=int, default=200,
                    help="max paths per LLM call (token budget; small = safer)")
    ap.add_argument("--limit-families", type=int, default=0,
                    help="0 = all families; otherwise process only this many")
    ap.add_argument("--resume", action="store_true",
                    help="skip family chunks already in deepseek_proposals.jsonl")
    args = ap.parse_args()

    api_key = os.environ.get("DEEPSEEK_API_KEY")
    if not api_key:
        raise SystemExit("DEEPSEEK_API_KEY not set in env. "
                         "export DEEPSEEK_API_KEY=sk-... and re-run.")

    if not SRC.exists():
        raise SystemExit(f"missing {SRC}; run build_deepseek_input.py first")

    families = [json.loads(l) for l in SRC.open() if l.strip()]
    if args.limit_families:
        families = families[: args.limit_families]

    # Build all (family, chunk_idx, paths) units of work
    units: list[tuple[str, int, list[str]]] = []
    for fam in families:
        chunks = chunk_paths(fam["paths"], args.max_per_batch)
        for i, ch in enumerate(chunks):
            units.append((fam["family"], i, ch))

    done_keys: set[tuple[str, int]] = set()
    if args.resume and OUT.exists():
        for line in OUT.open():
            try:
                rec = json.loads(line)
                done_keys.add((rec["family"], rec["chunk"]))
            except Exception:
                pass
        print(f"  resume: {len(done_keys):,} chunks already done")

    pending = [u for u in units if (u[0], u[1]) not in done_keys]
    print(f"  pending: {len(pending):,} chunks (across {len(families)} families)")

    out_mode = "a" if args.resume else "w"
    log_mode = "a" if args.resume else "w"
    n_ok = n_err = 0
    t0 = time.time()

    with OUT.open(out_mode, encoding="utf-8") as out_fh, \
         LOG.open(log_mode, encoding="utf-8") as log_fh:
        for i, (family, chunk_idx, paths) in enumerate(pending, 1):
            user_msg = json.dumps({"family": family, "paths": paths},
                                   ensure_ascii=False)
            messages = [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_msg},
            ]
            try:
                resp = call_deepseek(api_key, messages)
                proposal = json.loads(resp)
                rewrites = proposal.get("rewrites") or {}
                rec = {
                    "family": family,
                    "chunk": chunk_idx,
                    "n_paths_in": len(paths),
                    "n_rewrites": len(rewrites),
                    "rewrites": rewrites,
                }
                out_fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
                out_fh.flush()
                n_ok += 1
                log_fh.write(f"[{i}/{len(pending)}] OK {family} chunk={chunk_idx} "
                             f"in={len(paths)} out={len(rewrites)}\n")
            except (urllib.error.HTTPError, urllib.error.URLError,
                    json.JSONDecodeError, KeyError) as e:
                n_err += 1
                log_fh.write(f"[{i}/{len(pending)}] ERR {family} chunk={chunk_idx}: {e}\n")
                time.sleep(2)
            log_fh.flush()
            elapsed = time.time() - t0
            rate = i / elapsed if elapsed else 0
            eta = (len(pending) - i) / rate if rate else 0
            print(f"  [{i}/{len(pending)}] {family} chunk={chunk_idx} "
                  f"ok={n_ok} err={n_err} eta={eta/60:.1f}min", flush=True)

    print(f"  done: {n_ok} ok, {n_err} errors")
    print(f"  proposals -> {OUT}")
    print(f"  log       -> {LOG}")


if __name__ == "__main__":
    main()
