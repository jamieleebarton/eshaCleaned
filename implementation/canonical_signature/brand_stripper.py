from __future__ import annotations
from typing import Optional


def _try_strip(text: str, candidate: str) -> Optional[str]:
    """Strip candidate from start of text (with optional trailing comma + space)."""
    if not candidate:
        return None
    cand = candidate.strip().lower()
    lowered = text.strip().lower()
    if not lowered.startswith(cand):
        return None
    rest = text[len(cand):].lstrip()
    if rest.startswith(","):
        rest = rest[1:].lstrip()
    return rest


def strip_brand(
    text: str,
    *,
    brand_name: Optional[str] = None,
    brand_owner: Optional[str] = None,
    brand_vocabulary: frozenset[str] = frozenset(),
) -> tuple[str, str]:
    """Return (residual_text, stripped_brand). Empty stripped_brand means no strip occurred."""
    candidates: list[str] = []
    for c in (brand_name, brand_owner):
        if c and c.strip():
            candidates.append(c.strip().lower())

    for cand in candidates:
        stripped = _try_strip(text, cand)
        if stripped is not None and stripped:
            return stripped, cand

    if brand_vocabulary:
        for cand in sorted(brand_vocabulary, key=len, reverse=True):
            stripped = _try_strip(text, cand)
            if stripped is not None and stripped:
                return stripped, cand

    return text, ""
