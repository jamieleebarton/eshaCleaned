#!/usr/bin/env python3
"""Audit CSV joining recipe ingredients to retail and Walmart/Kroger by htc_code.

For each recipe ingredient, we look up the retail audit and the Walmart/Kroger
cache by code equality. The output lets a human eyeball whether the join is
sensible — e.g. the ingredient "garlic" (htc_code 6503000D) should pull retail
rows whose canonical_path is "Produce > Vegetables > Garlic" and sr28_desc
mentions garlic, not something unrelated.

Output columns:
  item, recipe_count, grams_total,
  htc_code, htc_group, htc_family, htc_food,
  retail_count, retail_top_product_identity_fixed, retail_top_canonical_path,
  retail_sample_retail_leaf_path, retail_top_fndds_code, retail_top_fndds_desc,
  retail_top_sr28_code, retail_top_sr28_desc, retail_sample_title,
  walmart_count, walmart_top_product_identity_fixed,
  walmart_top_canonical_path, walmart_sample_name,
  join_status   (both | retail_only | walmart_only | unmatched | non_joinable)
"""
from __future__ import annotations

import argparse
import csv
import sys
from collections import Counter, defaultdict
from pathlib import Path

csv.field_size_limit(sys.maxsize)

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
DEFAULT_AUDIT = HERE / "output" / "consensus_htc_tagged.csv"
DEFAULT_AUDIT_FULL = ROOT / "retail_mapper" / "v2" / "consensus_full_corpus_audit.csv"
DEFAULT_INGREDIENT = HERE / "output" / "recipe_ingredient_htc_tagged.csv"
DEFAULT_API = ROOT / "recipe_pricing" / "output" / "api_cache_htc_tagged.csv"
DEFAULT_OUT = HERE / "output" / "recipe_ingredient_join_audit.csv"


def mode(counter: Counter) -> str:
    return counter.most_common(1)[0][0] if counter else ""


def is_joinable_htc(row: dict[str, str]) -> bool:
    """Only item-level food slots are valid recipe-to-product join keys."""
    return (
        bool(row.get("htc_code"))
        and (row.get("htc_group") or "") not in {"", "0", "N"}
        and (row.get("htc_food") or "") not in {"", "00"}
    )


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--audit", type=Path, default=DEFAULT_AUDIT)
    ap.add_argument("--audit-full", type=Path, default=DEFAULT_AUDIT_FULL)
    ap.add_argument("--ingredient", type=Path, default=DEFAULT_INGREDIENT)
    ap.add_argument("--api", type=Path, default=DEFAULT_API)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = ap.parse_args()

    # Index retail audit (HTC overlay) by htc_code.
    # fdc_ids_by_code_fndds[(htc_code, fndds_code)] -> fdc_id (any row that
    # uses that fndds_code at this htc_code; lets us join to the full audit
    # to get fndds_desc / sr28_desc for the *mode* code, not the first row.
    retail_by_code: dict[str, dict] = defaultdict(lambda: {
        "count": 0,
        "pid": Counter(),
        "canonical_path": Counter(),
        "fndds": Counter(),
        "sr28": Counter(),
        "sample_title": "",
        "exemplar_fdc": "",         # any fdc_id at this code (for retail_leaf_path)
    })
    fdc_for_code_fndds: dict[tuple[str, str], str] = {}
    fdc_for_code_sr28: dict[tuple[str, str], str] = {}
    print(f"reading retail audit ({args.audit}) ...", file=sys.stderr)
    with args.audit.open() as f:
        for row in csv.DictReader(f):
            if not is_joinable_htc(row):
                continue
            c = row["htc_code"]
            slot = retail_by_code[c]
            slot["count"] += 1
            slot["pid"][row.get("product_identity_fixed", "")] += 1
            slot["canonical_path"][row.get("canonical_path", "")] += 1
            fc = row.get("fndds_code", "")
            sc = row.get("sr28_code", "")
            if fc:
                slot["fndds"][fc] += 1
            if sc:
                slot["sr28"][sc] += 1
            if not slot["sample_title"]:
                slot["sample_title"] = row.get("title", "")
            fid = row.get("fdc_id", "")
            if fid and not slot["exemplar_fdc"]:
                slot["exemplar_fdc"] = fid
            if fid and fc and (c, fc) not in fdc_for_code_fndds:
                fdc_for_code_fndds[(c, fc)] = fid
            if fid and sc and (c, sc) not in fdc_for_code_sr28:
                fdc_for_code_sr28[(c, sc)] = fid

    # Pull retail_leaf_path + nutrition descs from the full audit, keyed by fdc_id.
    # Need: every fdc_id stored as exemplar_fdc, plus the per-code-mode-fndds
    # and per-code-mode-sr28 fdc_ids so descs match the mode code.
    print(f"reading full audit columns ({args.audit_full}) ...", file=sys.stderr)
    fdc_meta: dict[str, dict] = {}
    needed_fdc: set[str] = set()
    for slot in retail_by_code.values():
        if slot["exemplar_fdc"]:
            needed_fdc.add(slot["exemplar_fdc"])
    needed_fdc.update(fdc_for_code_fndds.values())
    needed_fdc.update(fdc_for_code_sr28.values())
    with args.audit_full.open() as f:
        for row in csv.DictReader(f):
            fid = row.get("fdc_id", "")
            if fid in needed_fdc:
                fdc_meta[fid] = {
                    "retail_leaf_path": row.get("retail_leaf_path", ""),
                    "fndds_desc": row.get("fndds_desc", ""),
                    "sr28_desc": row.get("sr28_desc", ""),
                }

    # Index API cache by htc_code.
    print(f"reading api cache ({args.api}) ...", file=sys.stderr)
    api_by_code: dict[str, dict] = defaultdict(lambda: {
        "count": 0,
        "pid": Counter(),
        "canonical_path": Counter(),
        "sample_name": "",
        "sample_by_pid": {},
        "sample_by_path": {},
    })
    with args.api.open() as f:
        for row in csv.DictReader(f):
            if not is_joinable_htc(row):
                continue
            c = row["htc_code"]
            slot = api_by_code[c]
            slot["count"] += 1
            pid = (row.get("product_identity_fixed") or "").strip()
            path = (row.get("canonical_path") or "").strip()
            name = row.get("name", "")
            if pid:
                slot["pid"][pid] += 1
                slot["sample_by_pid"].setdefault(pid, name)
            if path:
                slot["canonical_path"][path] += 1
                slot["sample_by_path"].setdefault(path, name)
            if not slot["sample_name"]:
                slot["sample_name"] = name

    # Stream ingredients and write the audit CSV.
    print(f"writing audit ({args.out}) ...", file=sys.stderr)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    n_total = n_both = n_retail = n_wmt = n_none = n_non_joinable = 0

    with args.ingredient.open() as inp, args.out.open("w", newline="") as out:
        r = csv.DictReader(inp)
        cols = [
            "item", "recipe_count", "grams_total",
            "htc_code", "htc_group", "htc_family", "htc_food",
            "retail_count", "retail_top_product_identity_fixed",
            "retail_top_canonical_path", "retail_sample_retail_leaf_path",
            "retail_top_fndds_code", "retail_top_fndds_desc",
            "retail_top_sr28_code", "retail_top_sr28_desc",
            "retail_sample_title",
            "walmart_count", "walmart_top_product_identity_fixed",
            "walmart_top_canonical_path", "walmart_sample_name",
            "join_status",
        ]
        w = csv.DictWriter(out, fieldnames=cols)
        w.writeheader()
        for row in r:
            n_total += 1
            code = row["htc_code"]
            joinable = is_joinable_htc(row)
            ret = retail_by_code.get(code) if joinable else None
            api = api_by_code.get(code) if joinable else None
            retail_top_pid = mode(ret["pid"]) if ret else ""
            retail_top_path = mode(ret["canonical_path"]) if ret else ""
            api_top_pid = mode(api["pid"]) if api else ""
            api_top_path = mode(api["canonical_path"]) if api else ""
            api_sample = ""
            if api:
                if retail_top_pid:
                    api_sample = api["sample_by_pid"].get(retail_top_pid, "")
                if not api_sample and retail_top_path:
                    api_sample = api["sample_by_path"].get(retail_top_path, "")
                if not api_sample and api_top_pid:
                    api_sample = api["sample_by_pid"].get(api_top_pid, "")
                if not api_sample and api_top_path:
                    api_sample = api["sample_by_path"].get(api_top_path, "")
                if not api_sample:
                    api_sample = api["sample_name"]
            top_fndds = mode(ret["fndds"]) if ret else ""
            top_sr28 = mode(ret["sr28"]) if ret else ""
            # Pull descs from the row that carries the MODE code, not from a
            # random exemplar — otherwise an Onion bucket could surface an
            # 'Egg' fndds_desc just because the first row cached happened to
            # use a stray fndds_code.
            fndds_desc = ""
            sr28_desc = ""
            if top_fndds:
                meta_f = fdc_meta.get(fdc_for_code_fndds.get((code, top_fndds), ""), {})
                fndds_desc = meta_f.get("fndds_desc", "")
            if top_sr28:
                meta_s = fdc_meta.get(fdc_for_code_sr28.get((code, top_sr28), ""), {})
                sr28_desc = meta_s.get("sr28_desc", "")
            # retail_leaf_path: any exemplar from this bucket
            meta = fdc_meta.get(ret["exemplar_fdc"], {}) if ret else {}

            if not joinable:
                status = "non_joinable"; n_non_joinable += 1
            elif ret and api:
                status = "both"; n_both += 1
            elif ret:
                status = "retail_only"; n_retail += 1
            elif api:
                status = "walmart_only"; n_wmt += 1
            else:
                status = "unmatched"; n_none += 1

            w.writerow({
                "item": row["item"],
                "recipe_count": row.get("recipe_count", ""),
                "grams_total": row.get("grams_total", ""),
                "htc_code": code,
                "htc_group": row.get("htc_group", ""),
                "htc_family": row.get("htc_family", ""),
                "htc_food": row.get("htc_food", ""),
                "retail_count": ret["count"] if ret else 0,
                "retail_top_product_identity_fixed": retail_top_pid,
                "retail_top_canonical_path": retail_top_path,
                "retail_sample_retail_leaf_path": meta.get("retail_leaf_path", ""),
                "retail_top_fndds_code": top_fndds,
                "retail_top_fndds_desc": fndds_desc,
                "retail_top_sr28_code": top_sr28,
                "retail_top_sr28_desc": sr28_desc,
                "retail_sample_title": ret["sample_title"] if ret else "",
                "walmart_count": api["count"] if api else 0,
                "walmart_top_product_identity_fixed": api_top_pid,
                "walmart_top_canonical_path": api_top_path,
                "walmart_sample_name": api_sample,
                "join_status": status,
            })

    print(f"\n  ingredients:  {n_total:,}")
    print(f"  both:         {n_both:,} ({n_both/n_total:.1%})")
    print(f"  retail_only:  {n_retail:,} ({n_retail/n_total:.1%})")
    print(f"  walmart_only: {n_wmt:,} ({n_wmt/n_total:.1%})")
    print(f"  unmatched:    {n_none:,} ({n_none/n_total:.1%})")
    print(f"  non_joinable: {n_non_joinable:,} ({n_non_joinable/n_total:.1%})")
    print(f"  -> {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
