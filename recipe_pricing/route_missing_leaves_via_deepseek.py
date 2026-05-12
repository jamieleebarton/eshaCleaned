#!/usr/bin/env python3
"""For each `spice_blend_too_generic_no_fdc_leaf` ingredient (the 437 cases
where my proposed leaf doesn't exist in the FDC universe), ask DeepSeek
to pick the BEST EXISTING FDC leaf under `Pantry > Spices & Seasonings`.

No fabrication: the model picks from a fixed list. If nothing fits, it
returns "NONE" and we skip.

Output:  recipe_pricing/data_layer_misroute_overrides_deepseek.csv
"""
from __future__ import annotations

import asyncio
import csv
import json
import os
import re
import sys
from pathlib import Path

from openai import AsyncOpenAI

ROOT = Path(__file__).resolve().parents[1]
AUDIT = ROOT / "recipe_pricing" / "data_layer_misroute_audit.csv"
UNIVERSE = ROOT / "retail_mapper" / "v2" / "consensus_full_corpus_audit.csv"
OUT = ROOT / "recipe_pricing" / "data_layer_misroute_overrides_deepseek.csv"

MODEL = "deepseek-chat"
BASE_URL = "https://api.deepseek.com/v1/"
CONCURRENCY = 16


def title_to_regex(title: str) -> str:
    t = title.strip().lower()
    if not t:
        return ""
    return f"^{re.escape(t)}s?$"


SYSTEM = """You are a food taxonomy router. Given an ingredient title from a recipe,
pick the SINGLE BEST canonical_path from the provided list of FDC retail leaves.

Hard rules:
  - You MUST return exactly one canonical_path from the LIST, OR the literal string "NONE".
  - Do NOT invent paths. Do NOT modify the chosen path's text.
  - Prefer specific spice/herb leaves over generic blends or seasonings.
  - If the ingredient is clearly a specific spice/herb but the list has no
    matching leaf, return "NONE" — do NOT route to "Spice Blend" or
    "Seasoning Blend" as a fallback.
  - Output JSON ONLY: {"canonical_path": "<one of the list>" | "NONE"}
"""

USER_TMPL = """Ingredient title: {title}

Choose the best canonical_path from this list:
{paths}

Return JSON only."""


async def route_one(client: AsyncOpenAI, sem: asyncio.Semaphore,
                    title: str, paths: list[str]) -> tuple[str, str]:
    async with sem:
        try:
            resp = await client.chat.completions.create(
                model=MODEL,
                messages=[
                    {"role": "system", "content": SYSTEM},
                    {"role": "user", "content": USER_TMPL.format(
                        title=title, paths="\n".join(f"  - {p}" for p in paths)
                    )},
                ],
                response_format={"type": "json_object"},
                temperature=0.0,
                max_tokens=200,
            )
            raw = resp.choices[0].message.content or ""
            data = json.loads(raw)
            choice = (data.get("canonical_path") or "").strip()
            if choice == "NONE" or choice in paths:
                return (title, choice)
            return (title, "NONE")
        except Exception as exc:
            print(f"  err {title!r}: {exc}", file=sys.stderr)
            return (title, "NONE")


async def main_async() -> int:
    api_key = os.environ.get("DEEPSEEK_API_KEY", "").strip()
    if not api_key:
        raise SystemExit("DEEPSEEK_API_KEY not set")

    # Pull the FDC universe — full retail leaves + just the Pantry > Spices subset
    universe: set[str] = set()
    with UNIVERSE.open() as f:
        for row in csv.DictReader(f):
            cp = (row.get("canonical_path") or "").strip()
            if cp:
                universe.add(cp)
    spice_paths = sorted(p for p in universe if p.startswith("Pantry > Spices"))
    print(f"FDC spice leaves: {len(spice_paths)}", file=sys.stderr)

    # Load the no_fdc_leaf rows from the audit
    cases: list[dict] = []
    with AUDIT.open() as f:
        for row in csv.DictReader(f):
            if row.get("category") == "spice_blend_too_generic_no_fdc_leaf":
                cases.append({
                    "title": row["title"],
                    "rc": int(row.get("recipe_count", "0") or 0),
                })
    # Dedupe by title (regex), keep highest rc
    seen: dict[str, dict] = {}
    for c in cases:
        if c["title"] not in seen or c["rc"] > seen[c["title"]]["rc"]:
            seen[c["title"]] = c
    cases = sorted(seen.values(), key=lambda r: -r["rc"])
    print(f"unique titles to route: {len(cases)}", file=sys.stderr)

    client = AsyncOpenAI(api_key=api_key, base_url=BASE_URL)
    sem = asyncio.Semaphore(CONCURRENCY)
    tasks = [route_one(client, sem, c["title"], spice_paths) for c in cases]
    results = await asyncio.gather(*tasks)

    # Build override rules for the rows where DeepSeek picked a real leaf
    rules = []
    none_count = 0
    title_to_choice = dict(results)
    for c in cases:
        choice = title_to_choice.get(c["title"], "NONE")
        if choice == "NONE" or choice not in universe:
            none_count += 1
            continue
        leaf = choice.split(" > ")[-1]
        rules.append({
            "pattern": title_to_regex(c["title"]),
            "canonical_path": choice,
            "canonical_label": leaf,
            "product_identity_fixed": leaf,
            "modifier": "",
            "note": f"deepseek-routed (was no_fdc_leaf, rc={c['rc']})",
        })

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=[
            "pattern", "canonical_path", "canonical_label",
            "product_identity_fixed", "modifier", "note",
        ])
        w.writeheader()
        w.writerows(rules)

    print(f"\nrouted: {len(rules):,}", file=sys.stderr)
    print(f"NONE (skipped): {none_count:,}", file=sys.stderr)
    print(f"  → {OUT}", file=sys.stderr)
    print(f"\nTop 25 routes:", file=sys.stderr)
    for r in rules[:25]:
        title = r["pattern"][1:].replace("\\", "").replace("s?$", "")
        print(f"  {title:<36} → {r['canonical_path']}", file=sys.stderr)
    return 0


def main() -> int:
    return asyncio.run(main_async())


if __name__ == "__main__":
    raise SystemExit(main())
