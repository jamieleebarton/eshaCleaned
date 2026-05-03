#!/usr/bin/env python3
"""For each SKU, check whether FNDDS/SR28/ESHA descriptions conceptually
match the title + canonical_path. Flag clear mismatches.

Common mismatch patterns:
  - title="FRESH X" but code desc says "cooked", "sauteed", "roasted", "fried", "powder", "extract", "dried"
  - title="X LEAVES" but code desc says "X root" or vice versa
  - title="X" (single ingredient) but code desc is a multi-ingredient dish
  - title and path agree on type but code desc is a different type entirely

Output: retail_mapper/v2/code_concept_mismatch_report.csv
  fdc_id, title, canonical_path, code_type (FNDDS/SR28/ESHA), code, code_desc, mismatch_reason
"""
from __future__ import annotations

import csv
import re
import sys
from collections import Counter
from pathlib import Path

V2 = Path(__file__).resolve().parent
AUDIT = V2 / "consensus_full_corpus_audit.csv"
OUT = V2 / "code_concept_mismatch_report.csv"

csv.field_size_limit(sys.maxsize)

# Words that flip the concept (state/form contradictions)
FRESH_WORDS = {"fresh", "raw", "uncooked"}  # 'whole' removed (false positives on whole-product names)
COOKED_WORDS = {"cooked", "sauteed", "sautéed", "roasted", "fried", "baked",
                "boiled", "steamed", "grilled", "broiled", "stewed"}
DRIED_WORDS = {"dried", "dehydrated", "freeze dried", "freeze-dried"}
PROCESSED_WORDS = {"powder", "powdered", "extract", "concentrate", "puree",
                   "paste", "syrup", "juice", "oil"}

# Plant parts (catches "Parsley Root" vs leafy parsley)
PLANT_PARTS = {"leaf", "leaves", "root", "stem", "seed", "seeds",
               "bulb", "tuber", "shoot", "sprout"}

# Multi-ingredient indicator words in code descriptions
DISH_INDICATORS = {"with", "and", "&", "in sauce", "in syrup", "in juice"}


def _words(s: str) -> set[str]:
    s = (s or "").lower()
    return set(re.findall(r"[a-z]+", s))


def _has_word(text: str, word: str) -> bool:
    return bool(re.search(rf"\b{re.escape(word)}\b", (text or "").lower()))


def check_one(row: dict) -> list[dict]:
    """Return list of mismatch reasons for this row (one per code-type that mismatches)."""
    title = (row.get("title") or "").lower()
    cp = (row.get("canonical_path") or "").lower()
    title_words = _words(title)
    out = []

    for code_type, code_col, desc_col in (
        ("FNDDS", "fndds_code", "fndds_desc"),
        ("SR28", "sr28_code", "sr28_desc"),
        ("ESHA", "esha_code", "esha_desc"),
    ):
        code = (row.get(code_col) or "").strip()
        desc = (row.get(desc_col) or "").lower()
        if not (code and desc):
            continue
        desc_words = _words(desc)

        reasons = []

        # Pattern 1: title has FRESH but desc has cooked/processed indicators
        if any(_has_word(title, w) for w in FRESH_WORDS):
            cooked_in_desc = [w for w in COOKED_WORDS if _has_word(desc, w)]
            processed_in_desc = [w for w in PROCESSED_WORDS if _has_word(desc, w)]
            dried_in_desc = [w for w in DRIED_WORDS if _has_word(desc, w)]
            if cooked_in_desc:
                reasons.append(f"title=FRESH but desc says {cooked_in_desc[0]!r}")
            elif processed_in_desc:
                reasons.append(f"title=FRESH but desc is processed form {processed_in_desc[0]!r}")
            elif dried_in_desc:
                reasons.append(f"title=FRESH but desc says {dried_in_desc[0]!r}")

        # Pattern 2: title and desc disagree on plant part (leaf vs root)
        title_parts = {p for p in PLANT_PARTS if _has_word(title, p) or _has_word(cp, p)}
        desc_parts = {p for p in PLANT_PARTS if _has_word(desc, p)}
        # Specific check: "Parsley/Cilantro/Dill" implies leaves; if desc has "root", flag
        if any(w in title_words for w in {"parsley", "cilantro", "dill", "basil", "mint", "rosemary", "thyme", "sage", "oregano", "chives", "tarragon"}):
            if "root" in desc_parts and "leaf" not in desc_parts and "leaves" not in desc_parts:
                reasons.append(f"title=herb leaves but desc says ROOT")

        # Pattern 3: title is whole-fruit but desc is processed
        whole_fruit_words = {"blueberries", "strawberries", "raspberries",
                             "blackberries", "grapes", "cherries", "apples",
                             "pears", "peaches", "plums", "oranges", "lemons",
                             "limes"}
        if any(w in title_words for w in whole_fruit_words):
            if any(w in desc for w in ("extract", "concentrate", "powder", "syrup", "puree")):
                if not any(w in title_words for w in ("juice", "syrup", "powder", "extract")):
                    reasons.append(f"title=whole fruit but desc is processed form")

        # Pattern 4: title says PEPPER (capsicum) but desc is "pepper dressing"
        if "bell pepper" in title or " pepper " in title:
            if "dressing" in desc or "sauce" in desc:
                if "dressing" not in title and "sauce" not in title:
                    reasons.append("title=fresh pepper but desc is dressing/sauce")

        # Pattern 5 disabled — too noisy. Use specific cross-family checks only.
        # E.g., title is fish but desc is meat, title is fruit but desc is vegetable.
        FRUIT_NOUNS = {"blueberry", "blueberries", "strawberry", "strawberries",
                       "raspberry", "raspberries", "blackberry", "blackberries",
                       "cherry", "cherries", "grape", "grapes", "apple", "apples",
                       "orange", "oranges", "lemon", "lemons", "lime", "limes",
                       "peach", "peaches", "pear", "pears", "plum", "plums",
                       "mango", "mangoes", "pineapple", "watermelon", "cantaloupe"}
        VEG_NOUNS = {"broccoli", "carrot", "carrots", "spinach", "lettuce", "kale",
                     "onion", "onions", "garlic", "celery", "cucumber", "cucumbers",
                     "tomato", "tomatoes", "potato", "potatoes", "pepper", "peppers"}
        MEAT_NOUNS = {"beef", "chicken", "pork", "turkey", "lamb", "veal", "duck",
                      "bacon", "ham", "sausage"}
        FISH_NOUNS = {"salmon", "tuna", "cod", "halibut", "shrimp", "lobster",
                      "crab", "tilapia", "scallop", "mussel", "clam", "oyster"}

        title_food_class = None
        if any(w in title_words for w in FRUIT_NOUNS):
            title_food_class = "fruit"
        elif any(w in title_words for w in MEAT_NOUNS):
            title_food_class = "meat"
        elif any(w in title_words for w in FISH_NOUNS):
            title_food_class = "fish"

        desc_food_class = None
        if any(w in desc for w in MEAT_NOUNS):
            desc_food_class = "meat"
        elif any(w in desc for w in FISH_NOUNS):
            desc_food_class = "fish"
        elif any(w in desc for w in FRUIT_NOUNS):
            desc_food_class = "fruit"

        if title_food_class and desc_food_class and title_food_class != desc_food_class:
            reasons.append(f"title is {title_food_class}, desc is {desc_food_class}")

        for reason in reasons:
            out.append({
                "fdc_id": row.get("fdc_id", ""),
                "title": (row.get("title") or "")[:120],
                "canonical_path": row.get("canonical_path", ""),
                "code_type": code_type,
                "code": code,
                "code_desc": (row.get(desc_col) or "")[:120],
                "mismatch_reason": reason,
            })
    return out


# Tiny food-noun extractor — first noun before commas/parens
_FIRST_NOUN_RX = re.compile(r"^([a-z]+(?:\s+[a-z]+)?)", re.I)


def _extract_main_food(text: str) -> str:
    text = (text or "").strip()
    if not text:
        return ""
    # Take first comma-separated chunk
    head = text.split(",")[0].strip().lower()
    head = re.sub(r"^\s*(fresh|raw|whole|organic|natural|premium)\s+", "", head)
    return head.split()[0] if head.split() else ""


def _related_foods(a: str, b: str) -> bool:
    """Loose matcher — return True if two food words are related."""
    if a == b: return True
    if a in b or b in a: return True
    # Common related-pairs
    related = [
        ({"blueberry", "blueberries"}, {"blueberry", "blueberries"}),
        ({"strawberry", "strawberries"}, {"strawberry", "strawberries"}),
        ({"raspberry", "raspberries"}, {"raspberry", "raspberries"}),
        ({"apple", "apples"}, {"apple", "apples"}),
        ({"orange", "oranges"}, {"orange", "oranges"}),
        ({"pepper", "peppers"}, {"pepper", "peppers"}),
    ]
    for s1, s2 in related:
        if a in s1 and b in s2: return True
    return False


def main() -> None:
    print(f"Reading {AUDIT.name}...")
    issues = []
    n = 0
    with AUDIT.open(encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            n += 1
            issues.extend(check_one(r))
            if n % 50000 == 0:
                print(f"  scanned {n:,}, issues so far: {len(issues):,}")

    print(f"  scanned {n:,} SKUs, found {len(issues):,} mismatch flags")

    cols = ["fdc_id", "title", "canonical_path", "code_type", "code", "code_desc", "mismatch_reason"]
    with OUT.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        for issue in issues:
            w.writerow(issue)
    print(f"  wrote {OUT.name}")

    # Summary by code_type
    print()
    by_type = Counter(i["code_type"] for i in issues)
    print(f"=== Mismatches by code type ===")
    for t, c in by_type.most_common():
        print(f"  {t}: {c:,}")

    # Top reasons
    print()
    by_reason = Counter(i["mismatch_reason"] for i in issues)
    print(f"=== Top 15 mismatch patterns ===")
    for r, c in by_reason.most_common(15):
        print(f"  [{c:>6,}] {r}")


if __name__ == "__main__":
    main()
