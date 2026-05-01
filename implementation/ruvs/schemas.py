"""RUVS v1 dataclass schemas.

Convention: stdlib-only, dataclasses + json serialization. JSON is the wire format.
"""
from __future__ import annotations
import json
from dataclasses import dataclass, field, asdict
from typing import Any

FACETS: list[str] = [
    "canonical_correct",
    "form_correct",
    "granularity_correct",
    "grams_plausible",
    "cook_state_handled",
    "package_math_sane",
    "ambiguity_flagged",
]

FACET_ENUMS: dict[str, tuple[str, ...]] = {
    "canonical_correct":   ("ok", "wrong", "ambiguous"),
    "form_correct":        ("ok", "wrong_form", "n/a"),
    "granularity_correct": ("ok", "too_specific", "too_generic"),
    "grams_plausible":     ("ok", "suspect"),
    "cook_state_handled":  ("ok", "wrong_state", "n/a"),
    "package_math_sane":   ("ok", "suspect"),
    "ambiguity_flagged":   ("none", "range", "or_option", "generic_term"),
}

CLEAN_VALUES: dict[str, set[str]] = {
    "canonical_correct":   {"ok"},
    "form_correct":        {"ok", "n/a"},
    "granularity_correct": {"ok"},
    "grams_plausible":     {"ok"},
    "cook_state_handled":  {"ok", "n/a"},
    "package_math_sane":   {"ok"},
    "ambiguity_flagged":   {"none"},
}


@dataclass
class ProductCandidate:
    upc: str
    title: str
    grams: float
    price_cents: int
    retail: str = ""           # "walmart" | "kroger"
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class Packet:
    recipe_id: int
    line_idx: int
    config_bucket: str
    recipe_text: str           # raw line, e.g. "1 lb butter"
    parsed_item: str           # e.g. "butter"
    recipe_grams: float
    hestia_canonical: str      # current Hestia guess (UNTRUSTED, included for compare)
    audit_candidates: list[dict[str, Any]]   # top-3 from full_corpus_audit by match_score
    fndds_desc: str
    sr28_desc: str
    esha_desc: str
    walmart_candidates: list[ProductCandidate]
    kroger_candidates: list[ProductCandidate]
    config: dict[str, Any] = field(default_factory=dict)  # household, dietary, pattern, pantry

    def to_json(self) -> str:
        return json.dumps(asdict(self))

    @classmethod
    def from_json(cls, s: str) -> "Packet":
        d = json.loads(s)
        d["walmart_candidates"] = [ProductCandidate(**c) for c in d["walmart_candidates"]]
        d["kroger_candidates"] = [ProductCandidate(**c) for c in d["kroger_candidates"]]
        return cls(**d)


@dataclass
class LineVerdict:
    recipe_id: int
    line_idx: int
    config_bucket: str
    model: str                 # e.g. "deepseek-v3.2-fast"
    run_id: str                # e.g. "ruvs.run.2026-05-01T20:00Z"
    facets: dict[str, str]     # facet_name -> enum value
    evidence: dict[str, Any]   # tool_calls, retrieved, audit_match
    fix_proposed: dict[str, Any] | None
    ts: str

    def __post_init__(self):
        for f, v in self.facets.items():
            if f not in FACET_ENUMS:
                raise ValueError(f"unknown facet: {f}")
            if v not in FACET_ENUMS[f]:
                raise ValueError(f"invalid facet value: {f}={v} (allowed: {FACET_ENUMS[f]})")

    def is_clean(self) -> bool:
        return all(self.facets[f] in CLEAN_VALUES[f] for f in FACETS)

    def to_json(self) -> str:
        return json.dumps(asdict(self))


@dataclass
class FixRow:
    canonical: str
    facet: str                 # which facet triggered the fix
    proposed_patch_type: str   # wishlist | alias | portion | exclusion | audit_correction | recipe_text_edit
    delta: dict[str, Any]      # the patch delta
    affected_recipes: list[int]
    source_run_id: str
    review_status: str = "pending"   # pending | approved | rejected | escalated


@dataclass
class Patch:
    patch_type: str            # wishlist | alias | portion | exclusion | audit_correction
    canonical: str
    delta: dict[str, Any]
    affected_recipes: list[int]
    source_run_id: str
    reviewed_by: str = ""      # "T1" | "T2:claude" | "T3:jamie"

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2)
