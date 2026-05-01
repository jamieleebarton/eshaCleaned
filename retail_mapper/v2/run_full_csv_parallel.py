#!/usr/bin/env python3
"""Run the full enriched CSV through DeepSeek in parallel.

Reads retail_leaf_v2_enriched_v2.csv, sends each row to the LLM with the
same lean prompt used in production, persists every output. Uses asyncio +
a concurrency semaphore to fan out N concurrent requests. Resume-safe.

Usage:
    NEBIUS_API_KEY=... python3 retail_mapper/v2/run_full_csv_parallel.py \
        --concurrency 50 \
        --out retail_mapper/v2/full_csv_run.live.jsonl \
        --limit 1000   # optional cap for dry runs

Persistence:
  - Every successful API call is appended to --out atomically (one line per row).
  - On restart, we read --out, skip every fdc_id that's already there, and
    continue with the rest. So you can ctrl-C and resume.

Cost guardrail:
  - --estimate flag prints projected token+cost without making any calls.
  - --limit N caps to N rows for dry runs.
"""
from __future__ import annotations

import argparse
import asyncio
import csv
import importlib.util
import json
import os
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
V2 = REPO / "retail_mapper" / "v2"
DEFAULT_CSV = V2 / "retail_leaf_v2_enriched_v2.csv"
DEFAULT_MODEL = "deepseek-chat"  # = deepseek-v4-flash, non-thinking
DEFAULT_BASE_URL = "https://api.deepseek.com/v1/"
DEFAULT_API_KEY_ENV = "DEEPSEEK_API_KEY"

csv.field_size_limit(sys.maxsize)


def load_module():
    sp = importlib.util.spec_from_file_location("ltc", V2 / "llm_taxonomy_cleanup.py")
    m = importlib.util.module_from_spec(sp); sys.modules["ltc"] = m
    sp.loader.exec_module(m)
    return m


def iter_csv_rows(csv_path: Path, bfc_filter: str | None, limit: int | None):
    n = 0
    with csv_path.open(encoding="utf-8", errors="replace", newline="") as fh:
        for row in csv.DictReader(fh):
            if not row.get("title") or not row.get("fdc_id"):
                continue
            if bfc_filter and bfc_filter.lower() not in (row.get("branded_food_category") or "").lower():
                continue
            yield row
            n += 1
            if limit and n >= limit:
                return


async def call_llm(client, model: str, msgs: list[dict], retries: int = 4) -> tuple[str, dict, dict]:
    """Returns (raw, parsed_record, usage_dict). usage_dict captures cache stats."""
    last_exc: Exception | None = None
    for attempt in range(retries + 1):
        try:
            resp = await client.chat.completions.create(
                model=model, messages=msgs, temperature=0.0,
                max_tokens=1200, response_format={"type": "json_object"},
            )
            raw = resp.choices[0].message.content or ""
            usage = {}
            if resp.usage:
                u = resp.usage
                usage = {
                    "prompt_tokens": getattr(u, "prompt_tokens", None),
                    "completion_tokens": getattr(u, "completion_tokens", None),
                    "total_tokens": getattr(u, "total_tokens", None),
                    "prompt_cache_hit_tokens": getattr(u, "prompt_cache_hit_tokens", None),
                    "prompt_cache_miss_tokens": getattr(u, "prompt_cache_miss_tokens", None),
                }
            return raw, _parse(raw), usage
        except Exception as exc:
            last_exc = exc
            if attempt >= retries:
                break
            await asyncio.sleep(2.0 * (2 ** attempt))
    return "", {"_api_error": f"{type(last_exc).__name__}: {last_exc}"}, {}


def _parse(raw: str) -> dict:
    import re, json as _j
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    if not match:
        return {"_parse_error": "no JSON object found", "_raw_preview": raw[:200]}
    try:
        return _j.loads(match.group(0))
    except Exception as exc:
        return {"_parse_error": str(exc), "_raw_preview": raw[:200]}


async def worker(name: int, q: asyncio.Queue, client, model: str, m,
                 out_lock: asyncio.Lock, out_path: Path, counter: dict):
    while True:
        item = await q.get()
        if item is None:
            q.task_done(); return
        row = item
        msgs = [
            {"role": "system", "content": m.SYSTEM_PROMPT},
            {"role": "user", "content": json.dumps({"source_row": m.compact_source_row(row)},
                                                   indent=2, sort_keys=True)},
        ]
        raw, parsed, usage = await call_llm(client, model, msgs)
        record = {
            "fdc_id": row.get("fdc_id", ""),
            "title": row.get("title", ""),
            "branded_food_category": row.get("branded_food_category", ""),
            "raw": raw,
            "record": parsed,
            "usage": usage,
        }
        line = json.dumps(record, sort_keys=True)
        async with out_lock:
            with out_path.open("a", encoding="utf-8") as fh:
                fh.write(line + "\n")
            counter["done"] += 1
            # Roll up cache stats
            if usage:
                if usage.get("prompt_cache_hit_tokens") is not None:
                    counter["cache_hit_tokens"] += usage["prompt_cache_hit_tokens"]
                if usage.get("prompt_cache_miss_tokens") is not None:
                    counter["cache_miss_tokens"] += usage["prompt_cache_miss_tokens"]
                if usage.get("completion_tokens") is not None:
                    counter["completion_tokens"] += usage["completion_tokens"]
            if counter["done"] % 50 == 0 or counter["done"] == counter["total"]:
                elapsed = time.time() - counter["start"]
                rate = counter["done"] / max(elapsed, 0.001)
                hit = counter.get("cache_hit_tokens", 0)
                miss = counter.get("cache_miss_tokens", 0)
                comp = counter.get("completion_tokens", 0)
                tot_in = hit + miss
                hit_pct = (100.0 * hit / max(tot_in, 1)) if tot_in else 0.0
                # Cost (DeepSeek v4-flash pricing)
                cost = (hit * 0.0028 + miss * 0.14 + comp * 0.28) / 1e6
                print(f"  [{counter['done']:>6d}/{counter['total']}]  {rate:.1f} req/s  "
                      f"cache={hit_pct:.0f}% hit  in={tot_in:,}  out={comp:,}  cost=${cost:.2f}  "
                      f"eta {(counter['total']-counter['done'])/max(rate,0.001)/60:.1f}m",
                      flush=True)
        q.task_done()


async def amain(args) -> None:
    api_key = os.environ.get(args.api_key_env, "").strip()
    if not api_key:
        raise SystemExit(f"{args.api_key_env} not set")

    m = load_module()

    # Estimate mode: count rows, project cost, exit.
    if args.estimate:
        n = 0
        for _ in iter_csv_rows(args.csv, args.bfc_filter, args.limit):
            n += 1
        # Use measured average from earlier runs
        in_tok = 3000
        out_tok = 600
        in_cost_per_m = 0.27
        out_cost_per_m = 1.10
        total = n * (in_tok * in_cost_per_m + out_tok * out_cost_per_m) / 1e6
        print(f"rows: {n:,}")
        print(f"avg input tokens: ~{in_tok}")
        print(f"avg output tokens: ~{out_tok}")
        print(f"projected total: ${total:.2f}")
        print(f"  input cost:  ${n * in_tok * in_cost_per_m / 1e6:.2f}")
        print(f"  output cost: ${n * out_tok * out_cost_per_m / 1e6:.2f}")
        return

    # Resume support: read existing output, skip those fdc_ids
    completed: set[str] = set()
    if args.out.exists():
        with args.out.open(encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    completed.add(str(json.loads(line).get("fdc_id", "")))
                except Exception:
                    pass
        print(f"resuming — {len(completed)} fdc_ids already in {args.out}", flush=True)

    # Collect work
    todo: list[dict] = []
    skipped = 0
    for row in iter_csv_rows(args.csv, args.bfc_filter, args.limit):
        if str(row.get("fdc_id", "")) in completed:
            skipped += 1; continue
        todo.append(row)
    print(f"queued: {len(todo)} rows  (skipped already-done: {skipped})", flush=True)
    if not todo:
        print("nothing to do."); return

    args.out.parent.mkdir(parents=True, exist_ok=True)

    from openai import AsyncOpenAI
    client = AsyncOpenAI(api_key=api_key, base_url=args.base_url)

    q: asyncio.Queue = asyncio.Queue()
    for row in todo:
        await q.put(row)
    for _ in range(args.concurrency):
        await q.put(None)

    out_lock = asyncio.Lock()
    counter = {"done": 0, "total": len(todo), "start": time.time(),
               "cache_hit_tokens": 0, "cache_miss_tokens": 0, "completion_tokens": 0}
    workers = [asyncio.create_task(worker(i, q, client, args.model, m, out_lock, args.out, counter))
               for i in range(args.concurrency)]
    await q.join()
    for w in workers:
        w.cancel()
    elapsed = time.time() - counter["start"]
    print(f"\ndone. {counter['done']} rows in {elapsed/60:.1f} min "
          f"({counter['done']/max(elapsed,0.001):.1f} req/s)")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--csv", type=Path, default=DEFAULT_CSV)
    parser.add_argument("--bfc-filter", type=str, default=None)
    parser.add_argument("--limit", type=int, default=None,
                        help="Cap rows for dry runs (e.g. --limit 1000)")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--api-key-env", default=DEFAULT_API_KEY_ENV)
    parser.add_argument("--concurrency", type=int, default=50,
                        help="Max simultaneous in-flight API calls")
    parser.add_argument("--estimate", action="store_true",
                        help="Estimate cost+rows, no API calls")
    args = parser.parse_args()
    asyncio.run(amain(args))


if __name__ == "__main__":
    main()
