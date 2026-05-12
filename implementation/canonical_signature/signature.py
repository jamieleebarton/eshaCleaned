from __future__ import annotations
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class CanonicalSignature:
    head_noun: str
    modifiers: frozenset[str]
    form: Optional[str] = None
    state: Optional[str] = None
    flavor: Optional[str] = None
    style: Optional[str] = None
    composite: bool = False
    secondary_ingredients: tuple[str, ...] = ()


@dataclass(frozen=True)
class MatchTrace:
    match_layer: str
    stripped_brand: str
    stripped_fluff: tuple[str, ...]
    extracted_attributes: dict[str, Optional[str]]
    residual: str
    top_candidates: tuple[tuple[str, float], ...]
    match_confidence: float
    match_reason: str
