#!/usr/bin/env python3
"""Eyeball-quality audit of recipe normalization output.

Flags suspicious normalizations without requiring human review of every line:
- over-collapse (rewritten << original)
- lost percent/purity claims
- lost brand-bearing modifiers ("Worcestershire" -> "sauce")
- bone-in/shell-on/whole/dried/etc. without yield_or_role_flags
- "or" alternatives that didn't get role=alternative_group
- ranges (X to Y, X-Y, X–Y) without range_low/range_high preserved
- compound identities collapsed to head noun (peanut butter, coconut milk, milk chocolate)
- to-taste lines that lost the to-taste signal

Usage:
    python3 implementation/audit_recipe_normalization_quality.py \
      --candidate implementation/output/recipe_normalization_deepseek_smoke.jsonl
"""
from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any


COMPOUND_HEAD_NOUNS = {
    "peanut butter": "butter",
    "almond butter": "butter",
    "cashew butter": "butter",
    "coconut milk": "milk",
    "almond milk": "milk",
    "soy milk": "milk",
    "oat milk": "milk",
    "milk chocolate": "chocolate",
    "dark chocolate": "chocolate",
    "white chocolate": "chocolate",
    "baking chocolate": "chocolate",
    "cream cheese": "cheese",
    "cottage cheese": "cheese",
    "sour cream": "cream",
    "heavy cream": "cream",
    "whipping cream": "cream",
    "ice cream": "cream",
    "tomato sauce": "sauce",
    "soy sauce": "sauce",
    "fish sauce": "sauce",
    "worcestershire sauce": "sauce",
}

YIELD_KEYWORDS = (
    "bone-in", "bone in", "shell-on", "shell on", "rind-on", "with rind",
    "unpeeled", "peel-on", "with peel", "whole chicken", "whole turkey",
    "whole fish", "whole shrimp", "whole crab", "whole lobster",
    "drumstick", "thigh", "wing", "carcass", "ham bone", "ham hock",
    "oxtail", "short rib", "marrow bone",
)

REMOVED_AROMATIC_KEYWORDS = (
    "bay leaf", "cinnamon stick", "whole spice", "peppercorn", "cheesecloth",
    "kombu", "bouquet garni", "spice bag", "tea bag",
)

UPTAKE_HINTS = ("for frying", "for sautéing", "for sauteing", "for cooking", "to coat the pan")
SODIUM_HINTS = ("salted water", "pasta water", "boiling water", "for boiling", "blanching water", "brining")

RANGE_PATTERNS = [
    re.compile(r"\b\d+\s*(?:to|-|–|—)\s*\d+\b", re.IGNORECASE),
    re.compile(r"\b\d+\s*/\s*\d+\s*(?:to|-|–|—)\s*\d+", re.IGNORECASE),
]
PERCENT_PATTERN = re.compile(r"\d{1,3}\s*%")
TO_TASTE_PATTERN = re.compile(r"\bto taste\b", re.IGNORECASE)
OR_PATTERN = re.compile(r"\bor\b", re.IGNORECASE)


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def text(v: Any) -> str:
    if v is None:
        return ""
    if isinstance(v, str):
        return v
    return json.dumps(v, ensure_ascii=False)


def check_ingredient(recipe: dict, ing: dict) -> list[dict]:
    findings: list[dict] = []
    original = (ing.get("original_display") or "").strip()
    rewritten = (ing.get("rewritten_ingredient") or "").strip()
    normalized = ing.get("normalized") or {}
    matchability = ing.get("matchability") or {}
    consumption = ing.get("consumption") or {}
    quantity = ing.get("quantity") or {}
    role = (ing.get("role") or "").strip()
    line_index = ing.get("line_index")

    flag = lambda code, detail: findings.append({
        "recipe_id": recipe.get("recipe_id"),
        "line_index": line_index,
        "code": code,
        "detail": detail,
        "original": original[:120],
        "rewritten": rewritten[:120],
    })

    if not original:
        return findings

    haystack = " ".join([
        original.lower(),
        rewritten.lower(),
        text(normalized.get("machine_name")).lower(),
        text(normalized.get("product_identity")).lower(),
        text(normalized.get("culinary_use")).lower(),
    ])

    # Over-collapse
    if rewritten and len(rewritten) < max(8, len(original) * 0.3):
        flag("over_collapse", f"rewritten len {len(rewritten)} < 30% of original len {len(original)}")

    # Lost percent claim
    if PERCENT_PATTERN.search(original) and not PERCENT_PATTERN.search(rewritten + " " + text(normalized.get("purity_or_percent"))):
        flag("lost_percent_claim", "original had a % that did not survive")

    # Compound identity collapse
    for compound, head in COMPOUND_HEAD_NOUNS.items():
        if compound in original.lower():
            mn = text(normalized.get("machine_name")).lower().strip()
            pid = text(normalized.get("product_identity")).lower().strip()
            if compound not in mn and compound not in pid:
                # Either it disappeared entirely or got collapsed to the head noun
                if mn == head or pid == head or mn.endswith(f" {head}") or pid.endswith(f" {head}"):
                    flag("compound_collapsed_to_head", f"'{compound}' collapsed to '{mn or pid}'")

    # to-taste signal lost
    if TO_TASTE_PATTERN.search(original):
        policy = text(consumption.get("consumption_policy")).lower()
        if "to_taste" not in policy and "to taste" not in (rewritten or "").lower():
            flag("lost_to_taste", f"to-taste original; policy={policy}")

    # Bone-in / yield keywords without flag
    for kw in YIELD_KEYWORDS:
        if kw in original.lower():
            flags = matchability.get("yield_or_role_flags") or []
            policy = text(consumption.get("consumption_policy")).lower()
            if "yield_policy_required" not in flags and "yield_policy_required" not in policy:
                flag("yield_keyword_no_flag", f"contains '{kw}' but no yield_policy_required")
            break

    # Removed aromatic without retention flag
    for kw in REMOVED_AROMATIC_KEYWORDS:
        if kw in original.lower():
            flags = matchability.get("yield_or_role_flags") or []
            policy = text(consumption.get("consumption_policy")).lower()
            if "retention_policy_required" not in flags and "retention_policy_required" not in policy:
                flag("aromatic_no_retention_flag", f"contains '{kw}' but no retention_policy_required")
            break

    # Process-medium uptake
    if any(h in haystack for h in UPTAKE_HINTS):
        policy = text(consumption.get("consumption_policy")).lower()
        if "uptake_policy" not in policy and role != "process_medium":
            flag("uptake_hint_no_flag", "process oil/fat hint without uptake_policy or process_medium role")

    # Sodium-absorption
    if any(h in haystack for h in SODIUM_HINTS) and "salt" in haystack:
        policy = text(consumption.get("consumption_policy")).lower()
        if "sodium_absorption" not in policy and "to_taste" not in policy:
            flag("sodium_hint_no_flag", "salt-in-water hint without sodium_absorption_policy")

    # OR alternatives misclassified
    has_or = bool(re.search(r"\bor\b", original, re.IGNORECASE)) or " OR " in original
    if has_or and role not in ("alternative_group", "section_header", "non_food"):
        # Filter false positives like "or so", "(or to taste)" — quick heuristics
        words_around = re.findall(r"\b\w+\s+or\s+\w+\b", original, re.IGNORECASE)
        if words_around:
            flag("or_no_alternative_group", f"line has '...or...' but role={role!r}")

    # Range without range_low/range_high
    if any(p.search(original) for p in RANGE_PATTERNS):
        if quantity.get("range_low") is None or quantity.get("range_high") is None:
            flag("range_not_preserved", "X to Y / X-Y in original but range_low/range_high null")

    return findings


def audit(rows: list[dict]) -> list[dict]:
    findings: list[dict] = []
    for recipe in rows:
        for ing in recipe.get("ingredients") or []:
            if not isinstance(ing, dict):
                continue
            findings.extend(check_ingredient(recipe, ing))
    return findings


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--candidate", type=Path, required=True)
    p.add_argument("--findings-out", type=Path, default=None)
    p.add_argument("--limit", type=int, default=20, help="show this many examples per code")
    args = p.parse_args()

    rows = load_jsonl(args.candidate)
    findings = audit(rows)
    by_code = Counter(f["code"] for f in findings)

    print(f"\n=== Quality audit: {args.candidate} ===")
    print(f"recipes scanned: {len(rows)}")
    print(f"total findings : {len(findings)}\n")
    if not findings:
        print("clean.")
        return
    print(f"{'count':>6}  code")
    print(f"{'-' * 6}  {'-' * 30}")
    for code, count in by_code.most_common():
        print(f"{count:>6}  {code}")
    print()
    by_code_examples: dict[str, list[dict]] = {}
    for f in findings:
        by_code_examples.setdefault(f["code"], []).append(f)
    for code, examples in by_code_examples.items():
        print(f"--- {code} ({len(examples)}) ---")
        for ex in examples[: args.limit]:
            print(f"  recipe={ex['recipe_id']} L{ex['line_index']}  {ex['detail']}")
            print(f"    orig: {ex['original']}")
            print(f"    rew : {ex['rewritten']}")
        print()
    if args.findings_out:
        args.findings_out.parent.mkdir(parents=True, exist_ok=True)
        with args.findings_out.open("w", encoding="utf-8") as f:
            for finding in findings:
                f.write(json.dumps(finding, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    main()
