#!/usr/bin/env python3
"""Build a small human-audit packet from a generated planner JSON."""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from planner.concept_routing import (  # noqa: E402
    choose_recipe_canonical_path,
    encode_recipe_line_htc,
    load_form_path_authority,
    load_htc_to_path,
    load_item_overrides,
    load_title_maps,
    valid_htc_form,
)

UNIFIED = ROOT / "recipe_mapper" / "v1" / "output" / "recipes_unified.csv"
RESOLUTION = ROOT / "planner" / "data" / "concept_resolution.json"

TARGETS = [
    ("head_lettuce", re.compile(r"\blettuce\b.*\b(head|leaves?)\b|\b(head|leaves?)\b.*\blettuce\b", re.I)),
    ("fresh_tomato", re.compile(r"\b(?:fresh|ripe|raw|roma|plum|cherry|grape|medium|large)?\s*tomato(?:es)?\b", re.I)),
    ("avocado", re.compile(r"\bavocados?\b", re.I)),
    ("tap_water", re.compile(r"^(?:hot |cold |ice |warm )?water$|\b(?:hot|cold|ice|warm)?\s*water\b", re.I)),
    ("cheddar", re.compile(r"\bcheddar\b", re.I)),
    ("cream_cheese", re.compile(r"\bcream cheese\b", re.I)),
    ("pork", re.compile(r"\b(pork|pork chops?|pork loin|pork shoulder|ham|bacon)\b", re.I)),
    ("chicken", re.compile(r"\b(chicken|chicken breast|chicken thigh|ground chicken)\b", re.I)),
    ("ham", re.compile(r"\bham\b", re.I)),
]

BAD_WATER_RE = re.compile(r"\b(watermelon|water chestnuts?|coconut water|sparkling water)\b", re.I)
TOMATO_NON_FRESH_RE = re.compile(r"\b(can|canned|sauce|paste|puree|purée|stewed|crushed|diced|sun.?dried|juice)\b", re.I)


def norm(text: str | None) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", text or "").lower()).strip()


def selected_recipe_ids(plan: dict) -> set[str]:
    ids: set[str] = set()
    for week in plan.get("weeks", []) or []:
        for rid in week.get("recipe_ids", []) or []:
            ids.add(str(rid))
    return ids


def recipe_lines(recipe_ids: set[str]) -> dict[str, list[dict]]:
    htc_to_path = load_htc_to_path()
    title_to_path, _ = load_title_maps()
    item_overrides = load_item_overrides()
    form_path_authority = load_form_path_authority()
    htc_encode_cache: dict[tuple[str, str, str], str] = {}
    intent_encode_cache: dict[tuple[str, str], str] = {}
    out: dict[str, list[dict]] = defaultdict(list)

    with UNIFIED.open(encoding="utf-8", errors="replace") as f:
        for row in csv.DictReader(f):
            rid = str(row.get("recipe_id") or "").strip()
            if rid not in recipe_ids:
                continue
            item = (row.get("ingredient_item") or "").strip().lower()
            display = row.get("display") or ""
            source_htc = (row.get("htc_code") or "").strip().lstrip("~")
            cp = choose_recipe_canonical_path(
                item=item,
                display=display,
                source_htc=source_htc,
                title_path=title_to_path.get(item, ""),
                item_overrides=item_overrides,
                htc_to_path=htc_to_path,
                form_path_authority=form_path_authority,
                intent_cache=intent_encode_cache,
            )
            if not cp or cp.startswith("Non-Food"):
                continue
            htc = encode_recipe_line_htc(item, display, cp, source_htc, htc_encode_cache)
            if not valid_htc_form(htc):
                continue
            line = dict(row)
            line["recipe_concept_key"] = f"{cp}|{htc}"
            out[rid].append(line)
    return out


def package_label(purchase: dict) -> str:
    packages = purchase.get("selected_packages") or []
    if packages:
        return " | ".join(
            f"{pkg.get('n_packages', 0):g}x {pkg.get('name', '')}"
            for pkg in packages
            if pkg.get("name")
        )
    if purchase.get("selected_sku"):
        return f"{purchase.get('n_packages', 0):g}x {purchase.get('selected_sku')}"
    return ""


def is_tap_water_line(line: dict) -> bool:
    recipe_key = line.get("recipe_concept_key", "")
    if recipe_key.startswith("Beverage > Water|") or recipe_key.startswith("Beverage > Water > Tap Water|"):
        return True
    item = norm(line.get("ingredient_item", ""))
    display = norm(line.get("display", ""))
    water_terms = {
        "water", "hot water", "cold water", "warm water", "ice water",
        "boiling water", "tap water",
    }
    return item in water_terms or display in water_terms


def target_names(line: dict, priced_key: str) -> list[str]:
    text = " ".join([
        line.get("display", ""),
        line.get("ingredient_item", ""),
        line.get("recipe_concept_key", ""),
        priced_key,
    ])
    found: list[str] = []
    for name, pattern in TARGETS:
        if name == "tap_water" and not is_tap_water_line(line):
            continue
        if not pattern.search(text):
            continue
        if name == "tap_water" and BAD_WATER_RE.search(text):
            continue
        if name == "fresh_tomato" and TOMATO_NON_FRESH_RE.search(text):
            continue
        found.append(name)
    return found


def build_rows(plan_path: Path) -> list[dict]:
    plan = json.loads(plan_path.read_text())
    resolution = json.loads(RESOLUTION.read_text())
    lines_by_recipe = recipe_lines(selected_recipe_ids(plan))
    rows: list[dict] = []

    for week in plan.get("weeks", []) or []:
        purchases = {
            row.get("concept_key", ""): row
            for row in week.get("ingredient_purchases", []) or []
            if row.get("concept_key")
        }
        names_by_id = {
            str(rid): name
            for rid, name in zip(week.get("recipe_ids", []) or [], week.get("recipe_names", []) or [])
        }
        for rid in week.get("recipe_ids", []) or []:
            rid_s = str(rid)
            for line in lines_by_recipe.get(rid_s, []):
                recipe_key = line["recipe_concept_key"]
                res = resolution.get(recipe_key) or {}
                priced_key = res.get("priced_key") or ""
                if not priced_key:
                    continue
                hit_targets = target_names(line, priced_key)
                if not hit_targets:
                    continue
                purchase = purchases.get(priced_key)
                if not purchase:
                    continue
                rows.append({
                    "targets": ",".join(hit_targets),
                    "week": week.get("week", ""),
                    "recipe_id": rid_s,
                    "recipe_title": names_by_id.get(rid_s) or line.get("recipe_title", ""),
                    "display": line.get("display", ""),
                    "ingredient_item": line.get("ingredient_item", ""),
                    "grams_resolved": line.get("grams_resolved", ""),
                    "grams_source": line.get("grams_source", ""),
                    "recipe_concept_key": recipe_key,
                    "resolution_tier": res.get("tier", ""),
                    "priced_concept_key": priced_key,
                    "selected_packages": package_label(purchase),
                    "purchase_grams": purchase.get("purchased_grams", ""),
                    "purchase_cost": purchase.get("cost", ""),
                })
    return rows


def write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "targets", "week", "recipe_id", "recipe_title", "display",
        "ingredient_item", "grams_resolved", "grams_source",
        "recipe_concept_key", "resolution_tier", "priced_concept_key",
        "selected_packages", "purchase_grams", "purchase_cost",
    ]
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def write_md(path: Path, rows: list[dict], limit_per_target: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    grouped: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        for target in row["targets"].split(","):
            grouped[target].append(row)

    lines = ["# Planner Eyeball Packet", ""]
    lines.append(f"Rows matched: {len(rows)}")
    lines.append("")
    for target, target_rows in sorted(grouped.items()):
        lines.append(f"## {target} ({len(target_rows)} lines)")
        lines.append("")
        lines.append("| Week | Recipe | Line | Grams | Tier | Priced concept | Selected package | Cost |")
        lines.append("|---:|---|---|---:|---|---|---|---:|")
        for row in target_rows[:limit_per_target]:
            recipe = f"{row['recipe_title']} ({row['recipe_id']})"
            selected = str(row["selected_packages"]).replace("|", "/")
            lines.append(
                f"| {row['week']} | {recipe} | {row['display']} | "
                f"{row['grams_resolved']} | {row['resolution_tier']} | "
                f"{row['priced_concept_key']} | {selected} | ${float(row['purchase_cost']):.2f} |"
            )
        lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("plan_json", type=Path)
    parser.add_argument("--out-csv", type=Path, required=True)
    parser.add_argument("--out-md", type=Path, required=True)
    parser.add_argument("--limit-per-target", type=int, default=8)
    args = parser.parse_args()

    rows = build_rows(args.plan_json)
    write_csv(args.out_csv, rows)
    write_md(args.out_md, rows, args.limit_per_target)
    print(f"matched {len(rows)} risky-class lines")
    print(f"-> {args.out_csv}")
    print(f"-> {args.out_md}")


if __name__ == "__main__":
    main()
