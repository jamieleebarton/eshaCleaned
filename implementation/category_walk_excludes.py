"""Phase-2 category walk: mine shared exclude signal for a retail aisle.

For each ``excludes_too_loose`` pack in a given ``top_category``, collect the
GTINs that slipped through the contract. Extract their description + ingredient
tokens and rank the ones that appear across many leaks but are rare in the
per-pack candidates. These are the best-leverage category-level exclude
candidates: adding them to the pack-builder synthesis would close many leaks at
once without needing Nebius.

Outputs per-category:
- ``category_walk_<slug>.csv`` — one row per leaked GTIN with pack context
- ``category_walk_<slug>_suggestions.md`` — ranked exclude-token suggestions
"""

from __future__ import annotations

import argparse
import csv
import re
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "implementation" / "output"
SWEEP_CSV = OUT / "pack_builder_sweep.csv"
INDEX_CSV = OUT / "esha_code_query_pack_index.csv"
OUT_DIR = OUT / "category_walks"


def slug(text: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "_", text).strip("_").lower() or "category"


def parse_md_rows(text: str) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    header: list[str] | None = None
    in_section = False
    for raw in text.splitlines():
        line = raw.rstrip()
        if line.startswith("## "):
            in_section = line in {"## Candidate Clean Products", "## Rows To Clean Up"}
            header = None
            continue
        if not in_section or not line.startswith("|"):
            header = None
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if all(set(c) <= {"-", ":"} for c in cells if c):
            continue
        if header is None:
            header = [c.strip() for c in cells]
            continue
        if len(cells) != len(header):
            continue
        row = dict(zip(header, cells))
        row["__in_section"] = "candidate" if line.startswith("|") else ""
        rows.append(row)
    return rows


def parse_md_tables(text: str) -> dict[str, list[dict[str, str]]]:
    out: dict[str, list[dict[str, str]]] = {"candidate": [], "cleanup": []}
    section: str | None = None
    header: list[str] | None = None
    for raw in text.splitlines():
        line = raw.rstrip()
        if line.startswith("## "):
            if line == "## Candidate Clean Products":
                section = "candidate"
            elif line == "## Rows To Clean Up":
                section = "cleanup"
            else:
                section = None
            header = None
            continue
        if section is None or not line.startswith("|"):
            header = None
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if all(set(c) <= {"-", ":"} for c in cells if c):
            continue
        if header is None:
            header = [c.strip() for c in cells]
            continue
        if len(cells) != len(header):
            continue
        out[section].append(dict(zip(header, cells)))
    return out


def tokens_of(text: str, stop: set[str]) -> set[str]:
    import sys
    sys.path.insert(0, str(ROOT / "implementation"))
    from match_esha_to_products import tokens_for  # noqa: E402
    return {t for t in tokens_for(text or "") if t and t not in stop and not t.isdigit()}


STOP_DESC = {"and", "or", "the", "with", "for", "of", "a", "an", "to", "in", "on", "plus", "size"}
STOP_ING = STOP_DESC | {"water", "salt", "natural", "flavor", "flavors", "flavoring", "citric", "acid", "ascorbic"}


def walk_category(category: str, out_dir: Path) -> None:
    sweep = list(csv.DictReader(SWEEP_CSV.open(encoding="utf-8")))
    index = {r["esha_code"]: r for r in csv.DictReader(INDEX_CSV.open(encoding="utf-8"))}

    leaky = [
        r for r in sweep
        if r["status"] == "semantic_validation_failed"
        and r["failure_mode"] == "excludes_too_loose"
        and r["top_category"] == category
    ]
    if not leaky:
        print(f"no leaky packs for {category!r}")
        return

    # Per-pack: what were the failing GTINs (cleanup rows that got accepted)?
    leak_rows: list[dict[str, str]] = []
    desc_token_cross_pack: Counter[str] = Counter()  # token -> number of packs where it appeared in a leaked GTIN
    ing_token_cross_pack: Counter[str] = Counter()
    candidate_desc_tokens: Counter[str] = Counter()  # across all candidates in this category
    candidate_ing_tokens: Counter[str] = Counter()
    pack_count = 0

    for row in leaky:
        idx = index.get(row["esha_code"])
        if not idx:
            continue
        pack_path = Path(idx["pack_path"])
        if not pack_path.exists():
            continue
        tables = parse_md_tables(pack_path.read_text(encoding="utf-8", errors="replace"))
        failing_gtins = {g for g in (row.get("failing_gtins") or "").split(",") if g}
        pack_count += 1
        # Aggregate candidate tokens (so we can avoid recommending excludes that also hit candidates)
        for crow in tables["candidate"]:
            candidate_desc_tokens.update(tokens_of(crow.get("description", ""), STOP_DESC))
            candidate_ing_tokens.update(tokens_of(crow.get("ingredients", ""), STOP_ING))
        # Per-pack leaked GTIN tokens (each leak GTIN contributes once per pack, not once per row)
        pack_desc_tokens: set[str] = set()
        pack_ing_tokens: set[str] = set()
        for crow in tables["cleanup"]:
            gtin = crow.get("gtin_upc", "")
            if gtin not in failing_gtins:
                continue
            dtoks = tokens_of(crow.get("description", ""), STOP_DESC)
            itoks = tokens_of(crow.get("ingredients", ""), STOP_ING)
            pack_desc_tokens |= dtoks
            pack_ing_tokens |= itoks
            leak_rows.append({
                "esha_code": row["esha_code"],
                "esha_description": row["description"],
                "gtin_upc": gtin,
                "leaked_description": crow.get("description", ""),
                "leaked_category": crow.get("category", ""),
                "leaked_ingredients": crow.get("ingredients", "")[:300],
            })
        desc_token_cross_pack.update(pack_desc_tokens)
        ing_token_cross_pack.update(pack_ing_tokens)

    # Candidate lift: how often does the token appear in candidates vs in leaks?
    def score_suggestions(leak_counter: Counter[str], cand_counter: Counter[str]) -> list[tuple[str, int, int, float]]:
        cand_total = sum(cand_counter.values()) or 1
        out = []
        for tok, n in leak_counter.most_common():
            cand_n = cand_counter.get(tok, 0)
            # lift = leak rate / candidate rate (higher = better exclude candidate)
            leak_rate = n / max(pack_count, 1)
            cand_rate = cand_n / cand_total
            lift = leak_rate / cand_rate if cand_rate > 0 else float("inf") if n > 0 else 0.0
            out.append((tok, n, cand_n, lift))
        return out

    desc_sugg = score_suggestions(desc_token_cross_pack, candidate_desc_tokens)
    ing_sugg = score_suggestions(ing_token_cross_pack, candidate_ing_tokens)

    out_dir.mkdir(parents=True, exist_ok=True)
    base = out_dir / slug(category)

    with (base.with_name(base.name + ".csv")).open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=[
            "esha_code", "esha_description", "gtin_upc",
            "leaked_description", "leaked_category", "leaked_ingredients",
        ])
        writer.writeheader()
        writer.writerows(leak_rows)

    lines = [
        f"# Category walk: {category}",
        "",
        f"- leaky packs analyzed: {pack_count}",
        f"- leaked GTINs total: {len(leak_rows)}",
        "",
        "## Top description-token exclude candidates",
        "",
        "Ranked by cross-pack leak count; lift compares leak vs candidate frequency (higher lift = safer to exclude).",
        "",
        "| token | packs_leaked | candidate_freq | lift |",
        "| --- | ---: | ---: | ---: |",
    ]
    for tok, n, cand_n, lift in desc_sugg[:40]:
        lift_str = "inf" if lift == float("inf") else f"{lift:.1f}"
        lines.append(f"| {tok} | {n} | {cand_n} | {lift_str} |")
    lines.extend([
        "",
        "## Top ingredient-token exclude candidates",
        "",
        "| token | packs_leaked | candidate_freq | lift |",
        "| --- | ---: | ---: | ---: |",
    ])
    for tok, n, cand_n, lift in ing_sugg[:40]:
        lift_str = "inf" if lift == float("inf") else f"{lift:.1f}"
        lines.append(f"| {tok} | {n} | {cand_n} | {lift_str} |")

    summary = base.with_name(base.name + "_suggestions.md")
    summary.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(f"  {category}: {pack_count} packs, {len(leak_rows)} leaked GTINs")
    print(f"  wrote {base.with_name(base.name + '.csv').relative_to(ROOT)}")
    print(f"        {summary.relative_to(ROOT)}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Phase-2 category walk: mine shared exclude signal")
    parser.add_argument("--category", help="Single branded_food_category to walk")
    parser.add_argument("--all", action="store_true", help="Walk every category with >=20 leaky packs")
    parser.add_argument("--out-dir", type=Path, default=OUT_DIR)
    args = parser.parse_args()

    if args.all:
        sweep = list(csv.DictReader(SWEEP_CSV.open(encoding="utf-8")))
        leaky = [r for r in sweep if r["status"] == "semantic_validation_failed" and r["failure_mode"] == "excludes_too_loose"]
        by_cat = Counter(r["top_category"] for r in leaky)
        for category, n in by_cat.most_common():
            if n < 20:
                break
            walk_category(category, args.out_dir)
    elif args.category:
        walk_category(args.category, args.out_dir)
    else:
        parser.error("pass --category <name> or --all")


if __name__ == "__main__":
    main()
