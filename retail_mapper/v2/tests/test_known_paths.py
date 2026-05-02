"""Golden SKU spot tests — historical breakages we never want to regress.

Every fdc_id listed in tests/data/known_good_skus.json is checked here. Each
entry specifies a mode:
  - 'equals'           : path == expected (exact)
  - 'starts_with'      : path.startswith(expected)
  - 'contains'         : expected in path
  - 'not_starts_with'  : not path.startswith(expected)
  - 'not_contains'     : expected not in path
"""
from __future__ import annotations

import pytest


def _check(mode: str, path: str, expected: str) -> bool:
    if mode == "equals":          return path == expected
    if mode == "starts_with":     return path.startswith(expected)
    if mode == "contains":        return expected in path
    if mode == "not_starts_with": return not path.startswith(expected)
    if mode == "not_contains":    return expected not in path
    raise ValueError(f"unknown mode: {mode}")


def _entries(known: dict) -> list[tuple[str, str, str, str]]:
    """Yield (fdc_id, mode, expected_path, label) for each test entry,
    skipping `_*` documentation keys."""
    out = []
    for fdc, val in known.items():
        if fdc.startswith("_"):
            continue
        if isinstance(val, str):
            out.append((fdc, "equals", val, ""))
        else:
            out.append((fdc, val.get("mode", "equals"), val["path"], val.get("label", "")))
    return out


def test_known_skus_load(known_good_skus):
    """The golden file must load and have entries."""
    real = [k for k in known_good_skus if not k.startswith("_")]
    assert len(real) > 0, "tests/data/known_good_skus.json has no SKU entries"


def test_each_known_sku_present(known_good_skus, audit_by_fdc):
    """Every golden fdc_id must exist in the audit."""
    missing = [fdc for fdc, *_ in _entries(known_good_skus) if fdc not in audit_by_fdc]
    assert not missing, f"missing fdc_ids in audit: {missing[:20]}"


@pytest.mark.parametrize("fdc,mode,expected,label", [
    pytest.param(fdc, mode, exp, lbl, id=f"{fdc}-{lbl[:30]}" if lbl else fdc)
    for fdc, mode, exp, lbl in _entries({
        # NOTE: parametrize must be evaluated at collection time, but the
        # known_good_skus fixture is session-scoped. We re-load the JSON
        # directly here so parametrize sees the entries up front.
        **__import__("json").loads(
            (__import__("pathlib").Path(__file__).parent / "data" / "known_good_skus.json").read_text()
        )
    })
])
def test_golden_path(fdc, mode, expected, label, audit_by_fdc):
    """One pytest case per golden SKU — pinpoints exactly which one regressed."""
    if fdc not in audit_by_fdc:
        pytest.skip(f"fdc {fdc} not in audit")
    row = audit_by_fdc[fdc]
    actual = (row.get("canonical_path") or "").strip()
    title = (row.get("title") or "").strip()
    assert _check(mode, actual, expected), (
        f"\n  fdc:      {fdc}"
        f"\n  label:    {label}"
        f"\n  title:    {title[:120]}"
        f"\n  mode:     {mode}"
        f"\n  expected: {expected}"
        f"\n  actual:   {actual}"
    )
