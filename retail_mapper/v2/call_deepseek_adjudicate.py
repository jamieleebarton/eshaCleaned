#!/usr/bin/env python3
"""DeepSeek adjudicates borderline centroid reroutes.

For each case, DeepSeek sees: full evidence + current path + centroid's
proposed path. It picks one of:
  - "current"   — current path is correct, reject the centroid move
  - "proposed"  — centroid's proposal is correct, apply
  - "other"     — both are wrong; describes the right home in plain English

Output: retail_mapper/v2/adjudication_decisions.jsonl

Resumable, concurrent, same pattern as call_deepseek_path_describe.py.
Requires DEEPSEEK_API_KEY.
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
    _SSL = ssl.create_default_context(cafile=certifi.where())
except ImportError:
    _SSL = ssl.create_default_context()

REPO = Path(__file__).resolve().parents[2]
V2 = REPO / "retail_mapper" / "v2"
SRC = V2 / "adjudication_input.jsonl"
OUT = V2 / "adjudication_decisions.jsonl"
LOG = V2 / "adjudication_log.txt"

API_URL = "https://api.deepseek.com/chat/completions"
MODEL = "deepseek-chat"

SYSTEM_PROMPT = """You arbitrate borderline grocery taxonomy placements. \
A SKU is currently at one path. An embedding model proposed moving it to \
a different path. You decide: which path is correct, given title + \
ingredients + branded category?

Three choices per SKU:
- "current": current_path is correct, reject the proposed move
- "proposed": centroid_proposed_path is correct, accept the move
- "other": both are wrong; describe the right food category in plain \
  English (e.g., "kale chip seasoned", "raw chicken breast", "frozen \
  fruit smoothie"). Don't invent FNDDS codes — the host system will \
  resolve descriptions to the closest existing tree path.

The current path may be a generic fallback (e.g., "Pantry > Spices & \
Seasonings > Seasoning") — embedding moves can be right or wrong from \
there. Use INGREDIENTS as the strongest signal. Don't be afraid to \
reject the proposed move if it's clearly wrong (e.g., sesame seeds being \
moved to sesame oil — they're seeds, not oil).

Output STRICT JSON, no markdown:
{
  "decision": "current" | "proposed" | "other",
  "chosen_desc": "<plain food description, only if decision=other>",
  "rationale": "<1 sentence>",
  "confidence": <0.0-1.0>
}"""


def call(api_key: str, messages, timeout=120):
    body = {"model": MODEL, "messages": messages, "temperature": 0,
            "max_tokens": 400, "response_format": {"type": "json_object"}}
    req = urllib.request.Request(API_URL,
        data=json.dumps(body).encode("utf-8"),
        headers={"Authorization": f"Bearer {api_key}",
                 "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout, context=_SSL) as resp:
        return json.loads(resp.read())["choices"][0]["message"]["content"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=20)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--resume", action="store_true")
    args = ap.parse_args()

    api_key = os.environ.get("DEEPSEEK_API_KEY")
    if not api_key:
        raise SystemExit("DEEPSEEK_API_KEY not set")

    cases = [json.loads(l) for l in SRC.open() if l.strip()]
    if args.limit: cases = cases[:args.limit]

    done = set()
    if args.resume and OUT.exists():
        for l in OUT.open():
            try: done.add(json.loads(l).get("fdc_id"))
            except: pass
        print(f"  resume: {len(done):,} already done")

    pending = [c for c in cases if c["fdc_id"] not in done]
    print(f"  pending: {len(pending):,}")

    fh_out = OUT.open("a" if args.resume else "w", encoding="utf-8")
    fh_log = LOG.open("a" if args.resume else "w", encoding="utf-8")
    lock = threading.Lock()

    def process(case):
        fdc = case["fdc_id"]
        user = json.dumps({k: case[k] for k in
            ["fdc_id", "title", "branded_food_category", "brand_name",
             "ingredients", "current_path", "centroid_proposed_path"]},
            ensure_ascii=False)
        try:
            resp = call(api_key, [{"role": "system", "content": SYSTEM_PROMPT},
                                   {"role": "user", "content": user}])
            d = json.loads(resp)
            d["fdc_id"] = fdc
            d["title"] = case["title"]
            d["current_path"] = case["current_path"]
            d["centroid_proposed_path"] = case["centroid_proposed_path"]
            with lock:
                fh_out.write(json.dumps(d, ensure_ascii=False) + "\n")
                fh_out.flush()
                fh_log.write(f"OK {fdc} dec={d.get('decision','?')} conf={d.get('confidence',0)}\n")
                fh_log.flush()
            return True
        except Exception as e:
            with lock:
                fh_log.write(f"ERR {fdc}: {e}\n"); fh_log.flush()
            return False

    n_ok = n_err = 0
    t0 = time.time()
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = {ex.submit(process, c): c for c in pending}
        done_count = 0
        for f in as_completed(futs):
            done_count += 1
            if f.result(): n_ok += 1
            else: n_err += 1
            if done_count % 100 == 0 or done_count == len(pending):
                el = time.time() - t0
                rate = done_count / el if el else 0
                eta = (len(pending) - done_count) / rate / 60 if rate else 0
                print(f"  [{done_count}/{len(pending)}] ok={n_ok} err={n_err} rate={rate:.1f}/s eta={eta:.1f}m", flush=True)

    fh_out.close(); fh_log.close()
    print(f"  done: {n_ok} ok, {n_err} err")


if __name__ == "__main__":
    main()
