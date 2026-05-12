"""Non-food lexicon. Guardrail #8: non_food state requires a lexicon hit here.
Never infer non_food from grams=0.
"""
import csv
from pathlib import Path

ROOT = Path(__file__).resolve().parent
LEXICON_PATH = ROOT / "non_food_words.csv"

_TERMS: set[str] | None = None


def _load() -> set[str]:
    global _TERMS
    if _TERMS is not None:
        return _TERMS
    out: set[str] = set()
    with LEXICON_PATH.open() as f:
        reader = csv.DictReader(f)
        for row in reader:
            term = (row.get("term") or "").strip().lower()
            if term and not term.startswith("#"):
                out.add(term)
    _TERMS = out
    return _TERMS


def is_non_food(text: str) -> bool:
    if not text:
        return False
    t = text.strip().lower()
    terms = _load()
    if t in terms:
        return True
    # Substring check against the lexicon — "wooden bamboo skewers" hits "bamboo skewers"
    for term in terms:
        if term in t:
            return True
    return False
