#!/usr/bin/env python3
"""Send misrouted SKUs to DeepSeek and ask for the correct family>type.

Input:  deepseek_misroute_top5k.jsonl (one SKU group per line)
Output: deepseek_misroute_decisions.jsonl (one decision per fdc_id)

Resumable: skips fdc_ids already in the output. Concurrent (8 workers).
Validates DeepSeek's responses against the 11 valid families.

Usage:
    DEEPSEEK_API_KEY=sk-... python3 call_deepseek_misroute_review.py [--limit N]
"""
from __future__ import annotations

import argparse
import json
import os
import ssl
import sys
import time
import urllib.request
import urllib.error
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

try:
    import certifi
    _SSL = ssl.create_default_context(cafile=certifi.where())
except ImportError:
    _SSL = ssl.create_default_context()

V2 = Path(__file__).resolve().parent
SRC = V2 / "deepseek_misroute_top5k.jsonl"
OUT = V2 / "deepseek_misroute_decisions.jsonl"
LOG = V2 / "deepseek_misroute_log.txt"

API_URL = "https://api.deepseek.com/chat/completions"
MODEL = "deepseek-chat"

VALID_FAMILIES = {
    "Bakery", "Beverage", "Dairy", "Frozen", "Meal",
    "Meat & Seafood", "Pantry", "Produce", "Snack",
    "Baby & Toddler", "Sports & Wellness",
}

SYSTEM_PROMPT = f"""You categorize grocery SKUs into a retail taxonomy.

Output JSON ONLY. Schema:
  {{"family": "<one of {sorted(VALID_FAMILIES)}>", "type": "<short type name>", "confidence": "high|medium|low"}}

Rules:
- family MUST be exactly one of the 11 listed values
- type is the specific product type (e.g. "Applesauce", "Hamburger Buns", "Sandwich Cookies")
- confidence: "high" if title clearly matches; "low" if uncertain
- For ambiguous SKUs (e.g., title is just a brand name), return "low" confidence
- Pick the family that retail consumers would shop for the product
- Plant-based / vegan dairy alternatives go to Pantry, NOT Dairy
- Hot dog buns go to Bakery, hot dog meat goes to Meat & Seafood
- Cookies go to Bakery, NOT Snack (per project convention)
- Cracker products (Goldfish, Triscuits) go to Snack > Crackers

Examples:
  title="UNSWEETENED APPLESAUCE", bfc="Wholesome Snacks"
    → {{"family": "Pantry", "type": "Applesauce", "confidence": "high"}}
  title="HAMBURGER BUNS", bfc="Breads & Buns"
    → {{"family": "Bakery", "type": "Hamburger Buns", "confidence": "high"}}
  title="GOLDFISH CRACKERS", bfc="Cookies & Biscuits"
    → {{"family": "Snack", "type": "Crackers", "confidence": "high"}}
"""


def _load_done() -> set[str]:
    """Already-decided fdc_ids (resume support)."""
    if not OUT.exists():
        return set()
    done = set()
    with OUT.open() as fh:
        for line in fh:
            try:
                d = json.loads(line)
                if d.get("fdc_id"):
                    done.add(d["fdc_id"])
            except json.JSONDecodeError:
                continue
    return done


def _load_input() -> list[dict]:
    rows = []
    with SRC.open() as fh:
        for line in fh:
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return rows


def _make_request(api_key: str, sku: dict) -> dict:
    """Call DeepSeek for a single SKU. Returns the parsed decision dict."""
    user_prompt = (
        f"title={sku['title']!r}\n"
        f"branded_food_category={sku['bfc']!r}\n"
        f"fndds_desc={sku.get('fndds_desc', '')!r}\n"
        f"current_path={sku.get('current_path', '')!r}\n"
        f"\nReturn JSON only."
    )
    body = json.dumps({
        "model": MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0,
        "response_format": {"type": "json_object"},
    }).encode()
    req = urllib.request.Request(
        API_URL,
        data=body,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
    )
    with urllib.request.urlopen(req, context=_SSL, timeout=60) as resp:
        data = json.loads(resp.read())
    content = data["choices"][0]["message"]["content"]
    decision = json.loads(content)
    return decision


def _validate(decision: dict) -> dict | None:
    """Reject decisions with invalid family or missing fields."""
    if not isinstance(decision, dict):
        return None
    fam = decision.get("family")
    if fam not in VALID_FAMILIES:
        return None
    typ = decision.get("type", "").strip()
    if not typ:
        return None
    conf = decision.get("confidence", "medium")
    if conf not in {"high", "medium", "low"}:
        conf = "medium"
    return {"family": fam, "type": typ, "confidence": conf}


def process_sku(api_key: str, sku: dict, retries: int = 3) -> dict:
    last_err = None
    for attempt in range(retries):
        try:
            decision = _make_request(api_key, sku)
            valid = _validate(decision)
            if valid:
                return {
                    "fdc_id": sku["fdc_id"],
                    "title": sku["title"],
                    "bfc": sku["bfc"],
                    "current_path": sku.get("current_path", ""),
                    "decision": valid,
                    "_member_fdcs": sku.get("_member_fdcs", [sku["fdc_id"]]),
                }
            last_err = f"invalid response: {decision}"
        except urllib.error.HTTPError as e:
            last_err = f"HTTP {e.code}: {e.read()[:200]}"
            if e.code == 429:
                time.sleep(2 ** attempt)
                continue
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as e:
            last_err = str(e)
            time.sleep(2 ** attempt)
    return {"fdc_id": sku["fdc_id"], "error": last_err}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None, help="cap number of SKUs to process")
    ap.add_argument("--workers", type=int, default=8)
    args = ap.parse_args()

    api_key = os.environ.get("DEEPSEEK_API_KEY")
    if not api_key:
        print("ERROR: DEEPSEEK_API_KEY not set", file=sys.stderr)
        sys.exit(1)

    inputs = _load_input()
    done = _load_done()
    todo = [s for s in inputs if s["fdc_id"] not in done]
    if args.limit:
        todo = todo[:args.limit]
    print(f"Loaded {len(inputs):,} SKUs total, {len(done):,} done, {len(todo):,} todo")
    if not todo:
        print("Nothing to do.")
        return

    n_ok = 0
    n_err = 0
    t0 = time.time()
    with OUT.open("a") as out_fh, LOG.open("a") as log_fh:
        with ThreadPoolExecutor(max_workers=args.workers) as ex:
            futures = {ex.submit(process_sku, api_key, sku): sku for sku in todo}
            for i, fut in enumerate(as_completed(futures), 1):
                result = fut.result()
                out_fh.write(json.dumps(result) + "\n")
                out_fh.flush()
                if "error" in result:
                    n_err += 1
                    log_fh.write(f"ERR fdc={result['fdc_id']}: {result['error']}\n")
                else:
                    n_ok += 1
                if i % 50 == 0:
                    elapsed = time.time() - t0
                    rate = i / elapsed
                    eta = (len(todo) - i) / rate
                    print(f"  [{i:>5,}/{len(todo):,}]  ok={n_ok:,}  err={n_err:,}  rate={rate:.1f}/s  eta={eta:.0f}s")

    print(f"\nDone. ok={n_ok:,}  err={n_err:,}")
    print(f"Decisions written to {OUT}")


if __name__ == "__main__":
    main()
