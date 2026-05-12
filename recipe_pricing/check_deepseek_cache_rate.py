#!/usr/bin/env python3
"""Quick cache-rate diagnostic. DeepSeek caches system prompts so the
big SYSTEM block we send isn't billed at full rate after the first call.

Runs N calls against the SAME prompt template (different recipes) and
reports per-call:
  - total prompt tokens
  - cache_hit_tokens (charged at the cheaper cache-hit rate)
  - cache_miss_tokens (charged at full rate)
  - completion tokens

Then projects total $ for the full 491k run at this hit ratio.

Usage:
  DEEPSEEK_API_KEY=sk-... python3 recipe_pricing/check_deepseek_cache_rate.py
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

from openai import AsyncOpenAI

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "recipe_pricing"))
from classify_buyability_via_deepseek import (  # type: ignore
    SYSTEM, build_user_message, MODEL, BASE_URL,
)

INPUT = ROOT / "recipe_pricing" / "buyability_input_full.jsonl"
N = 10  # calls to make

# Pricing per https://api-docs.deepseek.com/quick_start/pricing/
# deepseek-chat = deepseek-v4-flash non-thinking mode:
#   prompt cache hit  : $0.0028 / M tokens   (1/10 launch price as of 2026-04-26)
#   prompt cache miss : $0.14   / M tokens
#   completion        : $0.28   / M tokens
PRICE_HIT = 0.0028 / 1_000_000
PRICE_MISS = 0.14 / 1_000_000
PRICE_OUT = 0.28 / 1_000_000


async def main():
    key = os.environ.get("DEEPSEEK_API_KEY", "").strip()
    if not key:
        raise SystemExit("DEEPSEEK_API_KEY not set")

    client = AsyncOpenAI(api_key=key, base_url=BASE_URL)

    # Pull N recipes from the input
    recipes = []
    with INPUT.open() as f:
        for line in f:
            recipes.append(json.loads(line))
            if len(recipes) >= N:
                break

    print(f"benchmarking {N} calls; same SYSTEM prompt, different recipes\n")
    total_prompt = 0
    total_hit = 0
    total_miss = 0
    total_out = 0

    for i, recipe in enumerate(recipes):
        resp = await client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": SYSTEM},
                {"role": "user", "content": build_user_message(recipe)},
            ],
            response_format={"type": "json_object"},
            temperature=0.0,
            max_tokens=4000,
        )
        u = resp.usage.model_dump() if hasattr(resp.usage, "model_dump") else dict(resp.usage)
        prompt = u.get("prompt_tokens", 0)
        # DeepSeek-specific cache fields
        hit = u.get("prompt_cache_hit_tokens", 0) or 0
        miss = u.get("prompt_cache_miss_tokens", prompt - hit) or 0
        out = u.get("completion_tokens", 0)
        total_prompt += prompt
        total_hit += hit
        total_miss += miss
        total_out += out
        print(f"  call {i+1:>2}: prompt={prompt:>5}  hit={hit:>5}  miss={miss:>5}  out={out:>4}")

    print()
    avg_prompt = total_prompt / N
    avg_hit = total_hit / N
    avg_miss = total_miss / N
    avg_out = total_out / N
    hit_rate = total_hit / max(total_prompt, 1)
    print(f"AVG per call:  prompt={avg_prompt:.0f}  hit={avg_hit:.0f}  miss={avg_miss:.0f}  out={avg_out:.0f}")
    print(f"cache hit rate: {hit_rate:.1%}")
    print()

    # Cost per call at this hit rate
    cost_call = (avg_hit * PRICE_HIT) + (avg_miss * PRICE_MISS) + (avg_out * PRICE_OUT)
    cost_block_a = (avg_prompt * PRICE_MISS) + (avg_out * PRICE_OUT)  # if no caching
    print(f"per-call cost WITH cache: ${cost_call:.6f}  (= ¢{cost_call*100:.4f})")
    print(f"per-call cost NO cache:   ${cost_block_a:.6f}  (= ¢{cost_block_a*100:.4f})")
    print(f"savings from caching: {(1 - cost_call/cost_block_a):.1%}")
    print()

    # Project for full corpus
    n_total = sum(1 for _ in INPUT.open())
    print(f"projected for {n_total:,} recipe corpus:")
    print(f"  with cache:    ${cost_call * n_total:.2f}")
    print(f"  without cache: ${cost_block_a * n_total:.2f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
