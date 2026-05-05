"""Part-whole and prep-of-whole substitutions for recipe-shopping logic.

Most recipes ask for the prep-form ('lemon zest', 'minced garlic', 'egg
whites') but shoppers buy the whole product and prepare it themselves. This
module maps prep-form → buy-this-instead targets.

Each substitution has:
  match_pattern  — regex against the recipe ingredient (lowercase)
  buy_canonical  — canonical_path or PID to look up in the priced db
  reason         — short explanation for audit trail

Match order matters: more-specific first.
"""
from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class Sub:
    pattern: re.Pattern
    canonical_paths: tuple[str, ...]   # try in order
    pids: tuple[str, ...]              # consensus PIDs to accept
    item_replacement: str              # rewrite the recipe item to this for the matcher
    reason: str


SUBSTITUTIONS: list[Sub] = [
    # ── Citrus zest / peel → whole fruit ────────────────────────────────
    Sub(re.compile(r"^(grated\s+)?lemon\s+(zest|peel|rind)$"),
        ("Produce > Fruit > Lemons", "Produce > Fruit > Lemon"),
        ("Lemons", "Lemon"), "lemon",
        "zest comes from a whole lemon"),
    Sub(re.compile(r"^(grated\s+)?lime\s+(zest|peel|rind)$"),
        ("Produce > Fruit > Limes", "Produce > Fruit > Lime"),
        ("Limes", "Lime"), "lime",
        "zest comes from a whole lime"),
    Sub(re.compile(r"^(grated\s+)?orange\s+(zest|peel|rind)$"),
        ("Produce > Fruit > Oranges", "Produce > Fruit > Orange"),
        ("Oranges", "Orange"), "orange",
        "zest comes from a whole orange"),
    Sub(re.compile(r"^(grated\s+)?grapefruit\s+(zest|peel|rind)$"),
        ("Produce > Fruit > Grapefruit",),
        ("Grapefruit",), "grapefruit",
        "zest comes from a whole grapefruit"),
    # ── Egg parts → whole eggs ───────────────────────────────────────────
    Sub(re.compile(r"^(\d+\s+)?egg\s+(whites?|yolks?)$"),
        ("Dairy > Eggs > Eggs", "Dairy > Eggs"),
        ("Eggs", "Egg"), "eggs",
        "whites/yolks come from whole eggs"),
    Sub(re.compile(r"^(beaten\s+)?eggs?$"),
        ("Dairy > Eggs > Eggs", "Dairy > Eggs"),
        ("Eggs", "Egg"), "eggs",
        "whole eggs"),
    Sub(re.compile(r"^large\s+eggs?$"),
        ("Dairy > Eggs > Eggs",),
        ("Eggs",), "eggs",
        "whole eggs (large is the default size)"),
    # ── Garlic preps → whole garlic ─────────────────────────────────────
    Sub(re.compile(r"^(minced|chopped|crushed|pressed|grated)\s+garlic$"),
        ("Produce > Vegetables > Garlic",),
        ("Garlic",), "garlic",
        "prep from whole garlic head"),
    Sub(re.compile(r"^garlic\s+cloves?$"),
        ("Produce > Vegetables > Garlic",),
        ("Garlic",), "garlic",
        "garlic clove from a whole garlic head"),
    # ── Onion preps → whole onion ───────────────────────────────────────
    Sub(re.compile(r"^(diced|chopped|sliced|minced)\s+onion$"),
        ("Produce > Vegetables > Onions",),
        ("Onions", "Onion"), "onion",
        "prep from whole onion"),
    Sub(re.compile(r"^(diced|chopped|sliced|minced|fresh)\s+(yellow|white|red|sweet|spanish)\s+onion$"),
        ("Produce > Vegetables > Onions",),
        ("Onions", "Onion"), "onion",
        "prep from whole onion"),
    # ── Cheese preps → block/wedge ──────────────────────────────────────
    Sub(re.compile(r"^(grated|shredded|sliced)\s+parmesan(\s+cheese)?$"),
        ("Dairy > Cheese > Parmesan", "Dairy > Cheese"),
        ("Parmesan", "Cheese"), "parmesan",
        "shred from a parmesan wedge"),
    Sub(re.compile(r"^(grated|shredded)\s+mozzarella(\s+cheese)?$"),
        ("Dairy > Cheese > Mozzarella",),
        ("Mozzarella",), "mozzarella",
        "shred from a mozzarella block"),
    Sub(re.compile(r"^(grated|shredded)\s+cheddar(\s+cheese)?$"),
        ("Dairy > Cheese > Cheddar",),
        ("Cheddar",), "cheddar cheese",
        "shred from a cheddar block"),
    # ── Whole meat → cut/prep on the fly ────────────────────────────────
    Sub(re.compile(r"^shredded\s+chicken$"),
        ("Meat & Seafood > Poultry > Chicken Breast", "Meat & Seafood > Poultry"),
        ("Chicken Breast",), "chicken breast",
        "shred from cooked chicken breast"),
    # ── Frozen → fresh fallback ─────────────────────────────────────────
    Sub(re.compile(r"^frozen\s+(.*)$"),
        (), (), r"\1",
        "frozen variant — try fresh if frozen unavailable"),
    Sub(re.compile(r"^fresh\s+(.*)$"),
        (), (), r"\1",
        "fresh variant — fall back to plain if needed"),
    # ── Ripe → plain ─────────────────────────────────────────────────────
    Sub(re.compile(r"^ripe\s+(.*)$"),
        (), (), r"\1",
        "ripeness is shopper's choice; match plain"),
    # ── Misc ─────────────────────────────────────────────────────────────
    Sub(re.compile(r"^ice\s*(cubes?)?$"),
        (), ("Water",), "water",
        "ice is just frozen water"),
    Sub(re.compile(r"^lemon\s+juice$"),
        ("Pantry > Sauces & Salsas > Lemon Juice",),
        ("Lemon Juice",), "lemon juice",
        "bottled lemon juice"),
]


def apply_substitution(item: str) -> Sub | None:
    """Return the first matching Sub, or None if no rule fires."""
    item = (item or "").lower().strip()
    for s in SUBSTITUTIONS:
        if s.pattern.match(item):
            return s
    return None


def rewrite_item(item: str) -> str:
    """If a substitution exists with item_replacement, apply it; else return item."""
    s = apply_substitution(item)
    if s is None:
        return item
    if "\\1" in s.item_replacement:
        return s.pattern.sub(s.item_replacement, (item or "").lower())
    return s.item_replacement
