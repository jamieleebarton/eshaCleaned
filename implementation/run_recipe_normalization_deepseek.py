#!/usr/bin/env python3
"""Recipe-normalization runner against the official DeepSeek API.

Three input modes:
- jsonl-testpack    : reads the curated 47-recipe test pack
- recipenlg         : reads full_dataset.csv (RecipeNLG), strips food.com links by default
- foodcom-parquet   : reads archive/recipes.parquet (Food.com canonical, better-parsed columns)

Resume-safe: appends to --out, dedupes on recipe_id. Async with concurrency
semaphore. Reports DeepSeek prompt cache hit ratio + running cost.
"""
from __future__ import annotations

import argparse
import asyncio
import csv
import json
import os
import random
import re
import sys
import time
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PROMPT = ROOT / "implementation" / "RECIPE_NORMALIZATION_NEBIUS_PROMPT_DRAFT.md"
DEFAULT_TESTPACK = ROOT / "implementation" / "output" / "recipe_normalization_prompt_test_pack.jsonl"
DEFAULT_BASE_URL = "https://api.deepseek.com/v1/"
DEFAULT_MODEL = "deepseek-chat"  # = deepseek-v4-flash, non-thinking
DEFAULT_API_KEY_ENV = "DEEPSEEK_API_KEY"

# DeepSeek-Flash pricing as of 2026/04 (per 1M tokens)
COST_CACHE_HIT_PER_M = 0.0028
COST_CACHE_MISS_PER_M = 0.14
COST_OUTPUT_PER_M = 0.28

csv.field_size_limit(sys.maxsize)


# ---------------------------------------------------------------------------
# Input adapters: each yields {"recipe_id", "title", "ingredients": [{"line_index", "display", "item", "grams"}, ...]}
# ---------------------------------------------------------------------------

def iter_testpack(path: Path) -> Iterable[dict[str, Any]]:
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            ings = []
            for idx, ing in enumerate(row.get("ingredients") or []):
                if not isinstance(ing, dict):
                    continue
                ings.append({
                    "line_index": idx,
                    "display": ing.get("display"),
                    "item": ing.get("item"),
                    "grams": ing.get("grams"),
                })
            yield {"recipe_id": row.get("recipe_id"), "title": row.get("title"), "ingredients": ings}


def _parse_json_list(value: str | None) -> list[str]:
    if not value:
        return []
    value = value.strip()
    if not value:
        return []
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return [value]
    if isinstance(parsed, list):
        return [str(x) for x in parsed]
    return [str(parsed)]


def iter_recipenlg(path: Path, exclude_foodcom: bool, limit: int | None, sample: int | None, seed: int) -> Iterable[dict[str, Any]]:
    """Iterate recipes from full_dataset.csv. Stripping food.com is the default."""
    if sample is not None:
        # Reservoir sample for fairness — seek by sampled row indexes.
        rng = random.Random(seed)
        with path.open(encoding="utf-8") as f:
            total = sum(1 for _ in csv.DictReader(f))
        target_count = min(sample, total)
        # Oversample 2x to compensate for food.com filter so we still get N
        oversample = target_count * (3 if exclude_foodcom else 1)
        wanted = set(rng.sample(range(total), min(oversample, total)))
        emitted = 0
        with path.open(encoding="utf-8") as f:
            for idx, row in enumerate(csv.DictReader(f)):
                if idx not in wanted:
                    continue
                link = (row.get("link") or "").lower()
                if exclude_foodcom and "food.com" in link:
                    continue
                ings = _parse_json_list(row.get("ingredients"))
                if not ings:
                    continue
                yield {
                    "recipe_id": f"recipenlg_{idx}",
                    "title": row.get("title") or "",
                    "ingredients": [
                        {"line_index": i, "display": s, "item": None, "grams": None}
                        for i, s in enumerate(ings)
                    ],
                }
                emitted += 1
                if emitted >= target_count:
                    return
        return

    with path.open(encoding="utf-8") as f:
        n = 0
        for idx, row in enumerate(csv.DictReader(f)):
            link = (row.get("link") or "").lower()
            if exclude_foodcom and "food.com" in link:
                continue
            ings = _parse_json_list(row.get("ingredients"))
            if not ings:
                continue
            yield {
                "recipe_id": f"recipenlg_{idx}",
                "title": row.get("title") or "",
                "ingredients": [
                    {"line_index": i, "display": s, "item": None, "grams": None}
                    for i, s in enumerate(ings)
                ],
            }
            n += 1
            if limit and n >= limit:
                return


def iter_foodcom_parquet(path: Path, limit: int | None) -> Iterable[dict[str, Any]]:
    import pyarrow.parquet as pq
    pf = pq.ParquetFile(path)
    n = 0
    for batch in pf.iter_batches(batch_size=2000):
        rows = batch.to_pylist()
        for row in rows:
            qtys = row.get("RecipeIngredientQuantities") or []
            parts = row.get("RecipeIngredientParts") or []
            ings = []
            for i in range(max(len(qtys), len(parts))):
                qty = qtys[i] if i < len(qtys) else ""
                part = parts[i] if i < len(parts) else ""
                display = f"{qty} {part}".strip() if qty else (part or "")
                if not display:
                    continue
                ings.append({"line_index": i, "display": display, "item": part, "grams": None})
            if not ings:
                continue
            yield {
                "recipe_id": f"foodcom_{int(row.get('RecipeId') or 0)}",
                "title": row.get("Name") or "",
                "ingredients": ings,
            }
            n += 1
            if limit and n >= limit:
                return


# ---------------------------------------------------------------------------
# DeepSeek call
# ---------------------------------------------------------------------------

def _parse_response(raw: str) -> dict:
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.strip("`")
        if raw.lower().startswith("json"):
            raw = raw[4:].strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        if not match:
            return {"_parse_error": "no JSON object", "_raw_preview": raw[:200]}
        try:
            return json.loads(match.group(0))
        except Exception as exc:
            return {"_parse_error": str(exc), "_raw_preview": raw[:200]}


async def call_deepseek(client, model: str, prompt: str, recipe: dict, retries: int = 4) -> tuple[dict, dict]:
    msgs = [
        {"role": "system", "content": prompt},
        {"role": "user", "content": json.dumps(recipe, ensure_ascii=False, sort_keys=True)},
    ]
    last_exc: Exception | None = None
    for attempt in range(retries + 1):
        try:
            resp = await client.chat.completions.create(
                model=model,
                messages=msgs,
                temperature=0,
                response_format={"type": "json_object"},
                max_tokens=12000,
            )
            content = resp.choices[0].message.content or ""
            usage = {}
            if resp.usage:
                u = resp.usage
                usage = {
                    "prompt_tokens": getattr(u, "prompt_tokens", None),
                    "completion_tokens": getattr(u, "completion_tokens", None),
                    "prompt_cache_hit_tokens": getattr(u, "prompt_cache_hit_tokens", None),
                    "prompt_cache_miss_tokens": getattr(u, "prompt_cache_miss_tokens", None),
                }
            return _parse_response(content), usage
        except Exception as exc:
            last_exc = exc
            if attempt >= retries:
                break
            await asyncio.sleep(2.0 * (2 ** attempt))
    return {"_api_error": f"{type(last_exc).__name__}: {last_exc}"}, {}


# ---------------------------------------------------------------------------
# Worker pool
# ---------------------------------------------------------------------------

async def worker(q: asyncio.Queue, client, model: str, prompt: str, out_lock, out_path: Path, counter: dict):
    while True:
        item = await q.get()
        if item is None:
            q.task_done()
            return
        recipe = item
        try:
            result, usage = await call_deepseek(client, model, prompt, recipe)
        except Exception as exc:
            result = {"_runner_error": str(exc)}
            usage = {}
        if str(result.get("recipe_id")) != str(recipe["recipe_id"]):
            result["recipe_id"] = recipe["recipe_id"]
            result.setdefault("runner_warnings", []).append("model recipe_id != source; overwritten")
        result.setdefault("title", recipe.get("title"))
        async with out_lock:
            out_path.open("a", encoding="utf-8").write(json.dumps(result, ensure_ascii=False) + "\n")
            counter["done"] += 1
            counter["cache_hit"] += int(usage.get("prompt_cache_hit_tokens") or 0)
            counter["cache_miss"] += int(usage.get("prompt_cache_miss_tokens") or 0)
            counter["completion"] += int(usage.get("completion_tokens") or 0)
            if counter["done"] % 5 == 0 or counter["done"] == counter["total"]:
                _print_progress(counter)
        q.task_done()


def _print_progress(c: dict) -> None:
    elapsed = max(time.time() - c["start"], 0.001)
    rate = c["done"] / elapsed
    tot_in = c["cache_hit"] + c["cache_miss"]
    hit_pct = 100 * c["cache_hit"] / tot_in if tot_in else 0
    cost = (c["cache_hit"] * COST_CACHE_HIT_PER_M + c["cache_miss"] * COST_CACHE_MISS_PER_M + c["completion"] * COST_OUTPUT_PER_M) / 1e6
    eta_min = (c["total"] - c["done"]) / max(rate, 0.001) / 60
    print(f"  [{c['done']:>5d}/{c['total']}]  {rate:.1f} req/s  cache={hit_pct:.0f}%  in={tot_in:,} out={c['completion']:,}  ${cost:.3f}  eta {eta_min:.1f}m", flush=True)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def gather_recipes(args) -> list[dict]:
    if args.input_mode == "jsonl-testpack":
        return list(iter_testpack(args.testpack))[: args.limit] if args.limit else list(iter_testpack(args.testpack))
    if args.input_mode == "recipenlg":
        return list(iter_recipenlg(args.csv, exclude_foodcom=not args.include_foodcom, limit=args.limit, sample=args.sample, seed=args.seed))
    if args.input_mode == "foodcom-parquet":
        return list(iter_foodcom_parquet(args.parquet, limit=args.limit))
    raise SystemExit(f"unknown input-mode: {args.input_mode}")


async def amain(args) -> None:
    prompt = args.prompt.read_text(encoding="utf-8")
    recipes = gather_recipes(args)
    print(f"queued {len(recipes)} recipes from mode={args.input_mode}", flush=True)

    if args.dry_run:
        first = recipes[0] if recipes else {}
        print(json.dumps({
            "model": args.model,
            "base_url": args.base_url,
            "prompt_chars": len(prompt),
            "recipe": first,
        }, indent=2, ensure_ascii=False))
        return

    api_key = os.environ.get(args.api_key_env, "").strip()
    if not api_key:
        raise SystemExit(f"{args.api_key_env} not set")

    # Resume support
    completed: set[str] = set()
    if args.out.exists():
        for line in args.out.open(encoding="utf-8"):
            line = line.strip()
            if not line:
                continue
            try:
                completed.add(str(json.loads(line).get("recipe_id", "")))
            except Exception:
                pass
        if completed:
            print(f"resuming — {len(completed)} already in {args.out}", flush=True)

    todo = [r for r in recipes if str(r["recipe_id"]) not in completed]
    skipped = len(recipes) - len(todo)
    print(f"todo: {len(todo)}  skipped (already done): {skipped}", flush=True)
    if not todo:
        return

    args.out.parent.mkdir(parents=True, exist_ok=True)

    from openai import AsyncOpenAI
    client = AsyncOpenAI(api_key=api_key, base_url=args.base_url)

    q: asyncio.Queue = asyncio.Queue()
    for r in todo:
        await q.put(r)
    for _ in range(args.concurrency):
        await q.put(None)

    out_lock = asyncio.Lock()
    counter = {"done": 0, "total": len(todo), "start": time.time(), "cache_hit": 0, "cache_miss": 0, "completion": 0}
    workers = [asyncio.create_task(worker(q, client, args.model, prompt, out_lock, args.out, counter))
               for _ in range(args.concurrency)]
    await q.join()
    for w in workers:
        w.cancel()
    print(f"\ndone. {counter['done']} recipes.", flush=True)
    _print_progress(counter)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--input-mode", choices=["jsonl-testpack", "recipenlg", "foodcom-parquet"], required=True)
    p.add_argument("--testpack", type=Path, default=DEFAULT_TESTPACK)
    p.add_argument("--csv", type=Path, default=Path("/Users/jamiebarton/Downloads/dataset/full_dataset.csv"))
    p.add_argument("--parquet", type=Path, default=Path("/Users/jamiebarton/Downloads/archive/recipes.parquet"))
    p.add_argument("--include-foodcom", action="store_true", help="recipenlg mode: keep food.com links instead of stripping them")
    p.add_argument("--prompt", type=Path, default=DEFAULT_PROMPT)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--limit", type=int, default=None, help="cap rows for smoke runs")
    p.add_argument("--sample", type=int, default=None, help="recipenlg: random sample N rows (with --seed)")
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--model", default=DEFAULT_MODEL)
    p.add_argument("--base-url", default=DEFAULT_BASE_URL)
    p.add_argument("--api-key-env", default=DEFAULT_API_KEY_ENV)
    p.add_argument("--concurrency", type=int, default=10)
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()
    asyncio.run(amain(args))


if __name__ == "__main__":
    main()
