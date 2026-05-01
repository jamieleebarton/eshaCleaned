#!/usr/bin/env python3
"""Pass 1 of the two-pass design: DeepSeek emits canonical_path per SKU.

Input: path_describe_input.jsonl (one SKU per line, with full evidence).
Output: path_describe_decisions.jsonl (one decision per SKU with proposed
canonical_path in our top-down convention).

The prompt teaches DeepSeek the convention via examples and rules.
DeepSeek emits a canonical_path string. Pass 2 (separate script) maps
the proposed path against our existing tree.

Concurrent + resumable, same pattern as call_deepseek_fndds_resolve.py.

Requires: export DEEPSEEK_API_KEY=sk-...
"""
from __future__ import annotations

import argparse
import json
import os
import ssl
import sys
import threading
import time
import urllib.request
import urllib.error
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

try:
    import certifi
    _SSL_CONTEXT = ssl.create_default_context(cafile=certifi.where())
except ImportError:
    _SSL_CONTEXT = ssl.create_default_context()

REPO = Path(__file__).resolve().parents[2]
V2 = REPO / "retail_mapper" / "v2"
SRC = V2 / "path_describe_input.jsonl"
OUT = V2 / "path_describe_decisions.jsonl"
LOG = V2 / "path_describe_log.txt"

API_URL = "https://api.deepseek.com/chat/completions"
MODEL = "deepseek-chat"

SYSTEM_PROMPT = """You are placing a grocery SKU into a retail taxonomy. \
Given the title, ingredients, brand, and branded category, produce the \
correct canonical_path in our STRICT TOP-DOWN format.

CONVENTION:
- Path uses ' > ' separators
- Top-Level is one of: Bakery, Beverage, Dairy, Frozen, Meal, Meat & Seafood, \
  Pantry, Produce, Snack, Sports & Wellness, Baby & Toddler
- Path order: Top-Level > Sub-Family > Type > Tier-1 > Tier-2 > Form > Claims (alphabetical)
- TYPE comes before its modifiers (top-down). NEVER bottom-up.
- Each segment is Title Case, no commas, no slashes.
- Keep proper compound names ("Monterey Jack", "Half & Half", "Mahi Mahi").
- Drop generic intermediate parents that duplicate the leaf.

EXAMPLES:
- Mozzarella Cheese, Low Moisture Part Skim, Shredded, Organic
  → Dairy > Cheese > Mozzarella > Low Moisture > Part Skim > Shredded > Organic
- Extra Sharp Aged Cheddar Block
  → Dairy > Cheese > Cheddar > Extra Sharp > Aged
- Sourdough Bread, Sliced
  → Bakery > Bread > Sourdough Bread > Sliced
- Hard Pretzels, Organic
  → Snack > Pretzels > Hard > Organic
- Italian Sausage, Smoked, Boneless
  → Meat & Seafood > Sausage > Italian Sausage > Smoked > Boneless
- Crunchy Italian Biscuits, Amaretti
  → Snack > Cookies > Italian Biscuits > Amaretti
- Tomato Sauce with Garlic and Onion
  → Pantry > Sauces & Salsas > Pasta Sauce > Garlic > Onion
- Chicken Phyllo Bites, Frozen Appetizer
  → Frozen > Appetizers > Chicken Bites
- Yellow Onions (PLU)
  → Produce > Vegetables > Onions > Yellow

CRITICAL RULES:
- Use the INGREDIENTS to disambiguate. "Cookies & cream ice cream" desc + \
  ingredients "wheat flour, sugar, butter" + title "BISCUITS" → cookie, not ice cream.
- The branded category is a strong hint but not authoritative. Title + \
  ingredients win when they conflict.
- For frozen finished products (entrees, appetizers), use Frozen as top-level.
- For canned products, use Pantry > Canned Vegetables/Fruit/etc.
- Storage modifiers (Frozen, Refrigerated, Shelf Stable) are NOT path levels \
  unless they distinguish a product family (Frozen Pizza vs Pizza dough).

OUTPUT STRICT JSON, no markdown:
{
  "canonical_path": "<the path>",
  "rationale": "<1 sentence on why>",
  "confidence": <0.0-1.0>
}"""


def call_deepseek(api_key: str, messages: list[dict], timeout: int = 120) -> str:
    body = {
        "model": MODEL,
        "messages": messages,
        "temperature": 0,
        "max_tokens": 500,
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
    with urllib.request.urlopen(req, timeout=timeout, context=_SSL_CONTEXT) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    return payload["choices"][0]["message"]["content"]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--resume", action="store_true")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--workers", type=int, default=20)
    args = ap.parse_args()

    api_key = os.environ.get("DEEPSEEK_API_KEY")
    if not api_key:
        raise SystemExit("DEEPSEEK_API_KEY not set in env.")
    if not SRC.exists():
        raise SystemExit(f"missing {SRC}; run build_path_describe_input.py first")

    skus: list[dict] = []
    with SRC.open() as fh:
        for line in fh:
            if line.strip():
                skus.append(json.loads(line))
    if args.limit:
        skus = skus[: args.limit]

    done_fdc: set[str] = set()
    if args.resume and OUT.exists():
        with OUT.open() as fh:
            for line in fh:
                try:
                    d = json.loads(line)
                    done_fdc.add(d.get("fdc_id", ""))
                except Exception:
                    pass
        print(f"  resume: {len(done_fdc):,} SKUs already done")

    pending = [s for s in skus if s["fdc_id"] not in done_fdc]
    print(f"  pending: {len(pending):,} SKUs")

    out_mode = "a" if args.resume else "w"
    log_mode = "a" if args.resume else "w"
    fh_out = OUT.open(out_mode, encoding="utf-8")
    fh_log = LOG.open(log_mode, encoding="utf-8")
    write_lock = threading.Lock()

    def process_one(sku: dict) -> bool:
        fdc = sku["fdc_id"]
        # Compose user message — keep tight to control tokens
        user_msg = json.dumps({
            "fdc_id": fdc,
            "title": sku.get("title", ""),
            "branded_food_category": sku.get("branded_food_category", ""),
            "brand_name": sku.get("brand_name", ""),
            "ingredients": sku.get("ingredients", "")[:300],
            "current_fndds_desc": sku.get("current_fndds_desc", ""),
        }, ensure_ascii=False)
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_msg},
        ]
        try:
            resp = call_deepseek(api_key, messages)
            decision = json.loads(resp)
            decision["fdc_id"] = fdc
            line_out = json.dumps(decision, ensure_ascii=False) + "\n"
            with write_lock:
                fh_out.write(line_out)
                fh_out.flush()
                fh_log.write(f"OK {fdc} → {decision.get('canonical_path','')[:80]}\n")
                fh_log.flush()
            return True
        except (urllib.error.HTTPError, urllib.error.URLError,
                json.JSONDecodeError, KeyError, TimeoutError, ValueError) as e:
            with write_lock:
                fh_log.write(f"ERR {fdc}: {e}\n")
                fh_log.flush()
            return False

    n_ok = 0; n_err = 0
    t0 = time.time()
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futures = {ex.submit(process_one, s): s for s in pending}
        done = 0
        for fut in as_completed(futures):
            done += 1
            if fut.result(): n_ok += 1
            else: n_err += 1
            if done % 100 == 0 or done == len(pending):
                elapsed = time.time() - t0
                rate = done / elapsed if elapsed else 0
                eta = (len(pending) - done) / rate if rate else 0
                print(f"  [{done}/{len(pending)}] ok={n_ok} err={n_err} "
                      f"rate={rate:.1f}/s eta={eta/60:.1f}min", flush=True)

    fh_out.close()
    fh_log.close()
    print(f"  done: {n_ok} ok, {n_err} errors")


if __name__ == "__main__":
    main()
