"""Export high-lift exclude candidates per retail category as JSON.

Re-runs the analysis in ``category_walk_excludes.walk_category`` for every
branded food category with ``>= MIN_LEAKY_PACKS`` leaky packs, then selects
description + ingredient tokens that pass both bars:

- ``packs_leaked >= MIN_PACKS_LEAKED`` (signal is not a one-off)
- ``lift >= MIN_LIFT`` or ``candidate_freq == 0`` (token is rare in candidates)

The result lands at ``implementation/output/category_excludes.json`` as:

    {"<category>": {"description_excludes": [...], "ingredient_excludes": [...]}, ...}

The sweep synthesizer will merge these into per-pack excludes, gated by the
per-pack safety check (token appears in this pack's cleanup rows AND does not
appear in this pack's candidate rows).
"""

from __future__ import annotations

import csv
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
IMPL = ROOT / "implementation"
if str(IMPL) not in sys.path:
    sys.path.insert(0, str(IMPL))

from category_walk_excludes import STOP_DESC, STOP_ING, parse_md_tables, tokens_of  # noqa: E402
from run_pack_builder_sweep import INDEX_CSV  # noqa: E402

SWEEP_CSV = ROOT / "implementation" / "output" / "pack_builder_sweep.csv"
OUT_JSON = ROOT / "implementation" / "output" / "category_excludes.json"

MIN_LEAKY_PACKS_PER_CATEGORY = 5
MIN_PACKS_LEAKED = 3
MIN_LIFT = 10.0


def score_category(category: str, leaky_rows: list[dict[str, str]], index: dict[str, dict[str, str]]) -> dict[str, list[str]]:
    desc_leak: Counter[str] = Counter()
    ing_leak: Counter[str] = Counter()
    desc_cand: Counter[str] = Counter()
    ing_cand: Counter[str] = Counter()
    pack_count = 0
    for row in leaky_rows:
        idx = index.get(row["esha_code"])
        if not idx:
            continue
        pack_path = Path(idx["pack_path"])
        if not pack_path.exists():
            continue
        tables = parse_md_tables(pack_path.read_text(encoding="utf-8", errors="replace"))
        failing = {g for g in (row.get("failing_gtins") or "").split(",") if g}
        pack_count += 1
        for crow in tables["candidate"]:
            desc_cand.update(tokens_of(crow.get("description", ""), STOP_DESC))
            ing_cand.update(tokens_of(crow.get("ingredients", ""), STOP_ING))
        pd_tokens: set[str] = set()
        pi_tokens: set[str] = set()
        for crow in tables["cleanup"]:
            if crow.get("gtin_upc", "") not in failing:
                continue
            pd_tokens |= tokens_of(crow.get("description", ""), STOP_DESC)
            pi_tokens |= tokens_of(crow.get("ingredients", ""), STOP_ING)
        desc_leak.update(pd_tokens)
        ing_leak.update(pi_tokens)

    def pick(leak: Counter[str], cand: Counter[str]) -> list[str]:
        cand_total = sum(cand.values()) or 1
        keep: list[str] = []
        for tok, n in leak.most_common():
            if n < MIN_PACKS_LEAKED:
                break
            cand_n = cand.get(tok, 0)
            leak_rate = n / max(pack_count, 1)
            cand_rate = cand_n / cand_total
            if cand_n == 0 or (cand_rate > 0 and leak_rate / cand_rate >= MIN_LIFT):
                keep.append(tok)
        return keep

    return {
        "pack_count": pack_count,
        "description_excludes": pick(desc_leak, desc_cand),
        "ingredient_excludes": pick(ing_leak, ing_cand),
    }


def main() -> None:
    sweep = list(csv.DictReader(SWEEP_CSV.open(encoding="utf-8")))
    index = {r["esha_code"]: r for r in csv.DictReader(INDEX_CSV.open(encoding="utf-8"))}

    leaky_by_cat: dict[str, list[dict[str, str]]] = {}
    for r in sweep:
        if r["status"] != "semantic_validation_failed" or r["failure_mode"] != "excludes_too_loose":
            continue
        cat = r["top_category"] or ""
        leaky_by_cat.setdefault(cat, []).append(r)

    out: dict[str, dict] = {}
    for cat in sorted(leaky_by_cat, key=lambda c: -len(leaky_by_cat[c])):
        rows = leaky_by_cat[cat]
        if len(rows) < MIN_LEAKY_PACKS_PER_CATEGORY:
            continue
        scored = score_category(cat, rows, index)
        if scored["description_excludes"] or scored["ingredient_excludes"]:
            out[cat] = scored

    OUT_JSON.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    total_cats = len(out)
    total_desc = sum(len(v["description_excludes"]) for v in out.values())
    total_ing = sum(len(v["ingredient_excludes"]) for v in out.values())
    print(f"wrote {OUT_JSON.relative_to(ROOT)}")
    print(f"  categories: {total_cats}")
    print(f"  description excludes total: {total_desc}")
    print(f"  ingredient excludes total:  {total_ing}")


if __name__ == "__main__":
    main()
