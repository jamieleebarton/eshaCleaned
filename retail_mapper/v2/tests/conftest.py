"""pytest fixtures shared across audit invariant tests.

Loads full_corpus_audit.csv once per session — 462k rows, ~300MB. Each test
gets the rows as a list[dict] keyed by column name.
"""
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

import pytest

V2 = Path(__file__).resolve().parents[1]
AUDIT = V2 / "full_corpus_audit.csv"
ENRICHED = V2 / "full_corpus_enriched.csv"
DATA = Path(__file__).parent / "data"

csv.field_size_limit(sys.maxsize)


@pytest.fixture(scope="session")
def audit_rows() -> list[dict]:
    """All rows from full_corpus_audit.csv as list[dict]."""
    if not AUDIT.exists():
        pytest.skip(f"missing {AUDIT}")
    with AUDIT.open(encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


@pytest.fixture(scope="session")
def audit_by_fdc(audit_rows) -> dict[str, dict]:
    """fdc_id → row dict."""
    return {r["fdc_id"]: r for r in audit_rows if r.get("fdc_id")}


@pytest.fixture(scope="session")
def enriched_by_fdc() -> dict[str, dict]:
    """fdc_id → enriched row dict (the pre-corruption baseline)."""
    if not ENRICHED.exists():
        return {}
    with ENRICHED.open(encoding="utf-8") as fh:
        return {r["fdc_id"]: r for r in csv.DictReader(fh) if r.get("fdc_id")}


@pytest.fixture(scope="session")
def known_good_skus() -> dict[str, str]:
    """fdc_id → expected canonical_path (golden SKUs from prior bug reports)."""
    p = DATA / "known_good_skus.json"
    if not p.exists():
        return {}
    return json.loads(p.read_text())


@pytest.fixture(scope="session")
def bfc_allowed_paths() -> dict[str, list[str]]:
    """BFC → list of allowed family+type prefixes (a path is OK if it starts with any of these)."""
    p = DATA / "bfc_allowed_paths.json"
    if not p.exists():
        return {}
    return json.loads(p.read_text())


@pytest.fixture(scope="session")
def valid_families() -> set[str]:
    """The fixed set of valid top-level family names."""
    return {
        "Bakery", "Beverage", "Dairy", "Frozen", "Meal",
        "Meat & Seafood", "Pantry", "Produce", "Snack",
        "Baby & Toddler", "Sports & Wellness",
    }


# ---------------------------------------------------------------------
# Reporting helpers — every failing assertion should call these to
# produce readable output (capped sample size).
# ---------------------------------------------------------------------

MAX_REPORT = 20


def fail_with_samples(message: str, samples: list[dict], extra_cols: list[str] | None = None) -> None:
    """Emit a pytest failure with up to MAX_REPORT sample SKUs.

    Each sample dict must have at least 'fdc_id', 'title', 'canonical_path'.
    Additional columns to display can be passed via extra_cols.
    """
    cols = ["fdc_id", "title", "canonical_path"] + (extra_cols or [])
    lines = [message, f"  ({len(samples)} violation(s); showing first {min(MAX_REPORT, len(samples))})"]
    for s in samples[:MAX_REPORT]:
        for c in cols:
            v = (s.get(c) or "")[:120]
            lines.append(f"    {c:20s}: {v}")
        lines.append("")
    pytest.fail("\n".join(lines))
