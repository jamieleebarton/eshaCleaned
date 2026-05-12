"""Card-audit verdict layer — consumed by price_resolver.

Loads two-model consensus verdicts (card_contract_applied.csv) into memory and
exposes `is_rejected(upc, canonical)` for the shopping resolver.

Verdict semantics (from nebius_card_full_audit.py):
  FULL_AGREE: accept = intersection of both models' accepted products
              reject = everything else
  PARTIAL/LOW_AGREE: accept = intersection; reject = union-complement
              (products BOTH models rejected); disagreement → review queue
  DISAGREE: everything → review queue (not applied here)

Only REJECT verdicts gate shopping. ACCEPT verdicts are informational
(shopping already finds them via SR28/FNDDS code match).
"""
from __future__ import annotations
import csv
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
APPLIED_CSV = ROOT / "implementation" / "output" / "card_contract_applied.csv"
C2E_CSV = ROOT / "implementation" / "canonical_to_esha.csv"

_REJECT_SET: set[tuple[str, int]] | None = None
_C2E: dict[str, int] | None = None


def _norm_upc(u: str) -> str:
    return (u or "").lstrip("0").strip()


def _load() -> None:
    global _REJECT_SET, _C2E
    if _REJECT_SET is not None:
        return
    rs: set[tuple[str, int]] = set()
    if APPLIED_CSV.exists():
        for r in csv.DictReader(APPLIED_CSV.open()):
            if r.get("verdict") == "REJECT" and r.get("esha_code", "").isdigit():
                rs.add((_norm_upc(r["gtin_upc"]), int(r["esha_code"])))
    _REJECT_SET = rs
    c2e: dict[str, int] = {}
    if C2E_CSV.exists():
        for r in csv.DictReader(C2E_CSV.open()):
            name = (r.get("canonical_name") or "").strip().lower()
            code = r.get("esha_code", "")
            if name and code.isdigit():
                c2e[name] = int(code)
    _C2E = c2e


def esha_for_canonical(canonical: str) -> int | None:
    _load()
    return _C2E.get((canonical or "").strip().lower())


def is_rejected(upc: str, canonical: str) -> bool:
    """True when both audit models agreed this UPC is not the right product
    for the ESHA code this canonical maps to."""
    _load()
    if not upc or not canonical:
        return False
    ec = _C2E.get(canonical.strip().lower())
    if ec is None:
        return False
    return (_norm_upc(upc), ec) in _REJECT_SET


def reject_count() -> int:
    _load()
    return len(_REJECT_SET)
