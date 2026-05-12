#!/usr/bin/env python3
"""Post-process cleanup over buyability_classifications.jsonl.

Fixes the LLM's known inconsistencies by enforcing rules deterministically:

  1. STRIP_BRANDS — strip brand names from canonical_buy_form. Keeps brands
     that ARE the canonical identity (Tabasco, Sriracha, A1, Heinz 57,
     Worcestershire — those genericized).
  2. STRIP_PERCENTAGE — strip leading % modifiers and capture as user
     facet claims. e.g. `1% low-fat milk` → `milk` + claims=[low_fat]
  3. STRIP_FAT_FACETS — same for fat-free / nonfat / low-fat / reduced-fat
  4. STRIP_SODIUM_FACETS — unsalted / no-salt-added / low-sodium
  5. STRIP_SUGAR_FACETS — unsweetened / sugar-free / no-sugar-added
  6. STRIP_100_PERCENT — `100% fruit jelly` → `jelly` + claim=no_sugar_added
  7. ASSORTED_TO_UNRESOLVED — `assorted X`, `mixed X`, `various X`,
     `any kind of X` → keep canonical_buy_form, force identity_resolved=false
  8. AUTHOR_NOISE — `additional seasoning`, `extra ingredients`, `more X`,
     `X of your choice`, `whatever X you have` → identity_resolved=false
  9. FORCE_00_FLOUR_SPECIALTY — Italian 00 flour isn't on every shelf
 10. WHITESPACE — trim doubled spaces, normalize hyphens

Adds new field `extracted_claims` to each classification: list of facet
flags stripped from canonical_buy_form (e.g. ['low_fat', 'unsalted']).

Reads:    recipe_pricing/buyability_classifications.jsonl
Writes:   recipe_pricing/buyability_classifications_cleaned.jsonl

Idempotent. Safe to run on partial output while classifier still going —
re-run when classifier finishes.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
IN = ROOT / "recipe_pricing" / "buyability_classifications.jsonl"
OUT = ROOT / "recipe_pricing" / "buyability_classifications_cleaned.jsonl"


# ---------------------------------------------------------------------------
# Brand strip — common brands that should be removed from canonical_buy_form.
# Order matters: strip multi-word brands first, then single-word.
# ---------------------------------------------------------------------------
# Brand-to-generic mapping — when the brand IS the entire canonical, swap
# in the generic equivalent rather than leave the brand standing.
BRAND_TO_GENERIC = {
    "cool whip":           "non-dairy whipped topping",
    "cool whip lite":      "non-dairy whipped topping",
    "cool whip free":      "non-dairy whipped topping",
    "cool whip topping":   "non-dairy whipped topping",
    "fat-free cool whip":  "non-dairy whipped topping",
    "kool-aid":            "powdered drink mix",
    "splenda":             "sugar substitute",
    "splenda granular":    "sugar substitute",
    "splenda granulated":  "sugar substitute",
    "granular":            "sugar substitute",  # leftover after Splenda strip
    "jello":               "gelatin dessert mix",
    "jell-o":              "gelatin dessert mix",
    "stove top":           "stuffing mix",
    "stove top stuffing":  "stuffing mix",
    "bisquick":            "all-purpose baking mix",
    "velveeta":            "processed cheese",
    "ranch":               "ranch dressing",
    "miracle whip":        "salad dressing",
    "spam":                "canned ham",
    "redhot":              "cayenne pepper hot sauce",
    "rotel":               "diced tomatoes with green chiles",
    "ro-tel":              "diced tomatoes with green chiles",
}

# After percentage stripping, sometimes "fat" sits dangling at the START
# of the canonical (e.g. `0% fat Greek yogurt` → `fat Greek yogurt`).
# Only sweep `fat` and only at the START of the text. Don't sweep `sugar`,
# `salt`, `sodium`, `calorie` because those are common identity head nouns
# (brown sugar, kosher salt, sea salt) and stripping them mangles the
# canonical.
DANGLING_FAT_RE = re.compile(r"^\s*fat\b\s*", re.I)

STRIP_BRANDS = [
    # Multi-word
    "Land O Lakes", "Land O'Lakes", "Hidden Valley Original Ranch",
    "Hidden Valley Ranch", "Hidden Valley", "Eagle Brand", "Old El Paso",
    "Cool Whip Lite", "Cool Whip Free", "Cool Whip", "Stove Top",
    "Better Than Bouillon", "Coffee-Mate", "Coffee Mate",
    "Heinz Chili Sauce", "Heinz Chili", "Spice Islands",
    # Single-word
    "Hellmann's", "Hellmanns",
    "Philadelphia",
    "Carnation",
    "Pillsbury", "Bisquick",
    "Kraft", "Velveeta",
    "Heinz",  # but Heinz 57 stays — handled below
    "Smucker's", "Smuckers", "Smucker",
    "Welch's", "Welchs", "Welch",
    "Knorr", "Lipton",
    "Hunt's", "Hunts", "Campbell's", "Campbell", "Progresso",
    "Kerrygold", "Cabot", "Daisy",
    "Betty Crocker", "General Mills",
    "Kroger", "Great Value",
    "McCormick", "Nabisco",
    "Ortega", "Rotel", "Ro-Tel",
    "Maruchan", "Nissin", "Top Ramen",
    "Bertolli", "Barilla",
    "Spice Islands", "Trader Joe's", "Trader Joe",
    "Aji-no-moto", "Ajinomoto",
    "Karo", "Domino",
    "Goya",
    "Splenda",
    "Frank's RedHot",
    "Pepperidge Farm",
]
BRAND_STRIP_RE = re.compile(
    r"\s*\b(?:" + "|".join(re.escape(b) for b in STRIP_BRANDS) + r")\b\s*",
    re.I,
)
# Brand-strip exception phrases — keep these intact (brand IS the identity)
BRAND_KEEP_PHRASES = [
    "Heinz 57", "A-1", "A1", "Tabasco", "Sriracha", "Worcestershire",
    "Old Bay", "Mrs. Dash", "Mrs Dash",
    # Frank's RedHot is the canonical category for cayenne pepper sauce
    # but brand-strip is fine since the cleanup leaves "cayenne pepper hot sauce".
]


# ---------------------------------------------------------------------------
# Facet strip — capture as claims, remove from canonical
# ---------------------------------------------------------------------------
PERCENT_RE = re.compile(r"\b(\d+)\s*%\s*", re.I)
# 100% fruit jelly / pure / all natural — captured as no_sugar_added or similar
HUNDRED_PERCENT_RE = re.compile(r"\b100\s*%\s*", re.I)

FAT_FACETS = [
    (re.compile(r"\bfat[-\s]?free\b", re.I),       "fat_free"),
    (re.compile(r"\bnon[-\s]?fat\b", re.I),         "fat_free"),
    (re.compile(r"\blow[-\s]?fat\b", re.I),         "low_fat"),
    (re.compile(r"\blowfat\b", re.I),               "low_fat"),
    (re.compile(r"\breduced[-\s]?fat\b", re.I),     "reduced_fat"),
    (re.compile(r"\b1/3[-\s]?(less[-\s]?)?fat\b", re.I), "reduced_fat"),
    (re.compile(r"\b1/3[-\s]?less\b", re.I),        "reduced_fat"),
    (re.compile(r"\bpart[-\s]?skim\b", re.I),       "reduced_fat"),  # part-skim is reduced not fat-free
    (re.compile(r"\bskim\b", re.I),                 "fat_free"),
]
SODIUM_FACETS = [
    (re.compile(r"\bunsalted\b", re.I),                "unsalted"),
    (re.compile(r"\bno[-\s]?salt(?:[-\s]?added)?\b", re.I), "no_salt"),
    (re.compile(r"\blow[-\s]?sodium\b", re.I),         "low_sodium"),
    (re.compile(r"\breduced[-\s]?sodium\b", re.I),     "low_sodium"),
]
SUGAR_FACETS = [
    (re.compile(r"\bunsweetened\b", re.I),                  "unsweetened"),
    (re.compile(r"\bsugar[-\s]?free\b", re.I),              "sugar_free"),
    (re.compile(r"\bno[-\s]?sugar(?:[-\s]?added)?\b", re.I), "no_sugar_added"),
]


# ---------------------------------------------------------------------------
# "Assorted" / "mixed" / "your choice" prefixes — flag identity_resolved=false
# ---------------------------------------------------------------------------
ASSORTED_PREFIX_RE = re.compile(
    r"^\s*(?:assorted|mixed|various|any\s+kind\s+of|"
    r"(?:your|of)\s+choice\s+of|miscellaneous|"
    r"variety\s+of|selection\s+of)\b",
    re.I,
)

# "Author noise" — author-recipe filler that doesn't pin down a SKU.
# These should force identity_resolved=false. Differs from "extra virgin
# olive oil" (real identity) — those don't match these patterns.
AUTHOR_NOISE_RE = re.compile(
    r"^\s*(?:additional|more|extra(?!\s+(?:virgin|firm|sharp|lean|"
    r"large|wide|light|bold|hot|long|short|small|fine|aged))|"
    r"some|any|optional|favorite|preferred|whatever|"
    r"unspecified|generic|other|leftover|reserved)\s+",
    re.I,
)


def strip_brands(text: str) -> str:
    """Strip brand prefixes/suffixes from canonical_buy_form, keep brand-as-identity intact."""
    if not text:
        return text
    # Brand-to-generic swap takes precedence: if entire text matches a known
    # brand-as-canonical, swap the whole thing for the generic equivalent.
    key = text.lower().strip()
    if key in BRAND_TO_GENERIC:
        return BRAND_TO_GENERIC[key]
    # Skip if any brand-keep phrase is present
    for keep in BRAND_KEEP_PHRASES:
        if keep.lower() in text.lower():
            return text
    cleaned = BRAND_STRIP_RE.sub(" ", text)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" ,;-")
    # If brand-strip emptied the text (e.g. canonical was JUST a brand),
    # fall back to brand-to-generic for the original or keep the original.
    if not cleaned and key in BRAND_TO_GENERIC:
        return BRAND_TO_GENERIC[key]
    return cleaned or text


def sweep_dangling_facet_tokens(text: str) -> str:
    """After % stripping, sometimes 'fat' sits alone at the START of the text
    where a modifier was removed. e.g. `0% fat Greek yogurt` → after `0%`
    strip → `fat Greek yogurt`. Sweep ONLY this leading 'fat' case.

    DO NOT sweep `sugar`/`salt`/`sodium`/`calorie` — those are real
    identity head nouns (brown sugar, kosher salt, sea salt) that we
    must not strip."""
    if not text:
        return text
    cleaned = DANGLING_FAT_RE.sub("", text)
    return re.sub(r"\s+", " ", cleaned).strip(" ,;-")


def strip_facet_modifiers(text: str) -> tuple[str, list[str]]:
    """Strip user-facet modifiers (%, fat-free, low-fat, unsalted, unsweetened, etc.)
    Return (cleaned_text, [extracted_claim_flags])."""
    claims: list[str] = []
    if not text:
        return text, claims

    # Percentage tokens. 0% / 1% / 2% / 100% — convert to claim where meaningful.
    def _pct_repl(m: re.Match) -> str:
        n = int(m.group(1))
        if n == 0:
            claims.append("fat_free")
        elif n == 1:
            claims.append("low_fat")
        elif n == 2:
            claims.append("reduced_fat")
        elif n == 100:
            claims.append("100_percent")
        # else: leave the % info as-is in claim (10% cream stays without claim)
        return " "

    text = PERCENT_RE.sub(_pct_repl, text)

    # Fat / sodium / sugar facets
    for pat, claim in FAT_FACETS + SODIUM_FACETS + SUGAR_FACETS:
        if pat.search(text):
            claims.append(claim)
            text = pat.sub(" ", text)

    # Whole milk / whole — `whole milk` stays whole because that's a milk
    # variety. We don't strip "whole" because the user might want
    # `whole milk` as the canonical for full-fat dairy.

    text = re.sub(r"\s+", " ", text).strip(" ,;-")
    # Dedupe claim list
    return text, sorted(set(claims))


def is_assorted_prefix(canonical: str) -> bool:
    return bool(canonical and ASSORTED_PREFIX_RE.match(canonical))


def is_author_noise_prefix(canonical: str) -> bool:
    return bool(canonical and AUTHOR_NOISE_RE.match(canonical))


def force_specialty_for_00_flour(canonical: str, buyability: str) -> str:
    """`00 flour` (any quote form) is Italian specialty — force buyability=specialty."""
    if not canonical:
        return buyability
    if re.search(r"^['\"\(]?00['\"\)]?\s+(?:bread\s+|strong\s+)?flour\b",
                 canonical, re.I):
        return "specialty"
    return buyability


def cleanup_one(c: dict) -> dict:
    """Return cleaned classification dict with extracted_claims."""
    canon = (c.get("canonical_buy_form") or "").strip()
    bu = c.get("buyability") or ""
    res = c.get("identity_resolved", False)

    if not canon:
        c["extracted_claims"] = []
        return c

    # 1. Strip brands first (so percentage detect doesn't get confused)
    canon = strip_brands(canon)

    # 2. Strip facet modifiers, capture claims
    canon, claims = strip_facet_modifiers(canon)

    # 2b. Sweep dangling 'fat'/'salt'/'sugar' tokens left over after % strip
    canon = sweep_dangling_facet_tokens(canon)

    # 3. assorted / mixed / various → not a SKU
    if is_assorted_prefix(canon):
        res = False

    # 4. Author noise prefixes → not a SKU
    if is_author_noise_prefix(canon):
        res = False

    # 5. 00 flour → specialty
    bu = force_specialty_for_00_flour(canon, bu)

    # If everything got stripped (canon empty), keep original
    if not canon:
        canon = (c.get("canonical_buy_form") or "").strip()
        # No claims captured in this edge case
        claims = []

    c["canonical_buy_form"] = canon
    c["identity_resolved"] = res
    c["buyability"] = bu
    c["extracted_claims"] = claims
    return c


def main() -> int:
    if not IN.exists():
        raise SystemExit(f"missing {IN}")
    n_records = 0
    n_lines = 0
    n_changed = 0
    n_claims_added = 0
    n_assorted_flagged = 0
    n_brand_stripped = 0
    n_specialty_forced = 0

    with IN.open() as fin, OUT.open("w") as fout:
        for line in fin:
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            n_records += 1
            for c in r.get("classifications", []):
                n_lines += 1
                before_canon = c.get("canonical_buy_form") or ""
                before_buy = c.get("buyability") or ""
                before_res = c.get("identity_resolved")
                cleanup_one(c)
                after_canon = c.get("canonical_buy_form") or ""
                if before_canon != after_canon:
                    n_changed += 1
                if c.get("extracted_claims"):
                    n_claims_added += 1
                if before_res and not c.get("identity_resolved"):
                    n_assorted_flagged += 1
                if before_canon != after_canon and BRAND_STRIP_RE.search(before_canon or ""):
                    n_brand_stripped += 1
                if before_buy != c.get("buyability") and c.get("buyability") == "specialty":
                    n_specialty_forced += 1
            fout.write(json.dumps(r) + "\n")
            if n_records % 100_000 == 0:
                print(f"  processed {n_records:,} recipes", file=sys.stderr)

    print(f"\nTotal recipes processed: {n_records:,}", file=sys.stderr)
    print(f"Total ingredient lines:  {n_lines:,}", file=sys.stderr)
    print(f"  canonical_buy_form changed: {n_changed:,}", file=sys.stderr)
    print(f"  brand-strip applied:        {n_brand_stripped:,}", file=sys.stderr)
    print(f"  facet claims captured:      {n_claims_added:,}", file=sys.stderr)
    print(f"  assorted/noise flagged:     {n_assorted_flagged:,}", file=sys.stderr)
    print(f"  forced 00-flour specialty:  {n_specialty_forced:,}", file=sys.stderr)
    print(f"\n  → {OUT}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
