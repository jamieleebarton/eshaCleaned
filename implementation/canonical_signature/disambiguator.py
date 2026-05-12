from __future__ import annotations
from dataclasses import dataclass
from typing import Optional, Sequence

ATTR_MATCH_BONUS = 1.0
ATTR_MISMATCH_PENALTY = 0.5
LEXICAL_TIEBREAK_WEIGHT = 0.001


@dataclass(frozen=True)
class CanonicalCandidate:
    id: str
    form: Optional[str]
    state: Optional[str]
    flavor: Optional[str]
    style: Optional[str]


def _attr_score(c_val: Optional[str], p_val: Optional[str]) -> float:
    if p_val is None or c_val is None:
        return 0.0
    if c_val == p_val:
        return ATTR_MATCH_BONUS
    return -ATTR_MISMATCH_PENALTY


def disambiguate(
    candidates: Sequence[tuple[CanonicalCandidate, float]],
    *,
    product_form: Optional[str],
    product_state: Optional[str],
    product_flavor: Optional[str],
    product_style: Optional[str],
) -> CanonicalCandidate:
    if not candidates:
        raise ValueError("disambiguate requires at least one candidate")

    def score(item: tuple[CanonicalCandidate, float]) -> float:
        cand, lex = item
        s = 0.0
        s += _attr_score(cand.form, product_form)
        s += _attr_score(cand.state, product_state)
        s += _attr_score(cand.flavor, product_flavor)
        s += _attr_score(cand.style, product_style)
        s += LEXICAL_TIEBREAK_WEIGHT * lex
        return s

    return max(candidates, key=score)[0]
