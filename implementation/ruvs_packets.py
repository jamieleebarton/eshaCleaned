"""B1: build verification packets per (recipe_id, line_idx, config)."""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any

from ruvs.schemas import Packet, ProductCandidate
from ruvs.tools.walmart import walmart_search
from ruvs.tools.kroger import kroger_search


@dataclass
class ReferenceData:
    fndds_desc_by_code: dict[str, str] = field(default_factory=dict)
    sr28_desc_by_code: dict[str, str] = field(default_factory=dict)
    esha_desc_by_code: dict[str, str] = field(default_factory=dict)
    audit_rows_by_canonical: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    hestia_canonical_by_line: tuple[str, str] = ("", "")  # (label, fndds_code)


def build_packet(
    *, recipe_id: int, line_idx: int, config_bucket: str,
    recipe_text: str, parsed_item: str, recipe_grams: float,
    ref: ReferenceData, config: dict[str, Any] | None = None,
    walmart_limit: int = 5, kroger_limit: int = 5,
) -> Packet:
    fndds_label, fndds_code = ref.hestia_canonical_by_line
    audit_candidates = ref.audit_rows_by_canonical.get(parsed_item.lower(), [])[:3]
    return Packet(
        recipe_id=recipe_id,
        line_idx=line_idx,
        config_bucket=config_bucket,
        recipe_text=recipe_text,
        parsed_item=parsed_item,
        recipe_grams=recipe_grams,
        hestia_canonical=fndds_label,
        audit_candidates=audit_candidates,
        fndds_desc=ref.fndds_desc_by_code.get(fndds_code, ""),
        sr28_desc=_lookup_desc(ref.sr28_desc_by_code, audit_candidates, "sr28_code", fndds_label),
        esha_desc=_lookup_desc(ref.esha_desc_by_code, audit_candidates, "esha_code", fndds_label),
        walmart_candidates=walmart_search(parsed_item, limit=walmart_limit),
        kroger_candidates=kroger_search(parsed_item, limit=kroger_limit),
        config=config or {},
    )


def _lookup_desc(
    desc_by_code: dict[str, str],
    audit: list[dict[str, Any]],
    code_field: str,
    hestia_label: str,
) -> str:
    """Resolve a reference description by trying, in order:
    1. The explicit code field on any audit row (e.g. sr28_code, esha_code).
    2. The fdc_id on any audit row (FDC IDs subsume SR28 NDB numbers).
    3. A case-insensitive match of the Hestia canonical label against dict values.
    """
    for row in audit:
        v = row.get(code_field)
        if v and str(v) in desc_by_code:
            return desc_by_code[str(v)]
    for row in audit:
        v = row.get("fdc_id")
        if v and str(v) in desc_by_code:
            return desc_by_code[str(v)]
    if hestia_label:
        target = hestia_label.strip().lower()
        for desc in desc_by_code.values():
            if desc.strip().lower() == target:
                return desc
    return ""
