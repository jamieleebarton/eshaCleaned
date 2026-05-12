from __future__ import annotations
import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from .vocabularies import COMPOSITE_TRIGGERS

CATEGORY_MAP_PATH = Path(__file__).parent / "category_to_canonical_anchor.csv"


def is_composite(text: str) -> bool:
    if not text:
        return False
    tokens = text.lower().replace(",", " ").split()
    return any(t in COMPOSITE_TRIGGERS for t in tokens)


@dataclass(frozen=True)
class CompositeRouting:
    layer: str  # "L7_category" or "L7_unresolved"
    anchor_id: Optional[str]
    detected_secondary: tuple[str, ...]


def route_composite(
    description: str,
    *,
    branded_food_category: Optional[str],
    category_to_anchor: dict[str, str],
) -> CompositeRouting:
    if branded_food_category:
        key = branded_food_category.strip().lower()
        anchor = category_to_anchor.get(key)
        if anchor:
            return CompositeRouting(
                layer="L7_category",
                anchor_id=anchor,
                detected_secondary=(),
            )
    return CompositeRouting(
        layer="L7_unresolved",
        anchor_id=None,
        detected_secondary=(),
    )


def load_category_map(path: Path = CATEGORY_MAP_PATH) -> dict[str, str]:
    out: dict[str, str] = {}
    if not path.exists():
        return out
    with path.open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            cat = (row.get("branded_food_category") or "").strip().lower()
            anchor = (row.get("canonical_anchor_id") or "").strip()
            if cat and anchor:
                out[cat] = anchor
    return out
