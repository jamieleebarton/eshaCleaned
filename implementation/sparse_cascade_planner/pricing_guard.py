#!/usr/bin/env python3
"""Pricing coverage guardrails for the local sparse cascade planner."""

from __future__ import annotations

from typing import Any


def unpriced_ingredient_keys(ingredient_index: Any, package_index: Any) -> list[str]:
    """Return tensor ingredient keys that would hit PackageIndex's default price."""
    package_keys = set(getattr(package_index, "packages_by_fndds", {}) or {})
    missing: list[str] = []
    for idx in range(int(getattr(ingredient_index, "num_ingredients", 0) or 0)):
        key = str(getattr(ingredient_index, "idx_to_fpid", {}).get(idx, "") or "")
        if key and key not in package_keys:
            missing.append(key)
    return missing


def assert_no_default_priced_ingredients(
    ingredient_index: Any,
    package_index: Any,
    *,
    context: str,
) -> None:
    missing = unpriced_ingredient_keys(ingredient_index, package_index)
    if not missing:
        return
    sample = ", ".join(missing[:25])
    extra = "" if len(missing) <= 25 else f", ... +{len(missing) - 25} more"
    raise RuntimeError(
        f"{context} has {len(missing)} tensor ingredient keys with no Walmart/Kroger "
        f"package row. Refusing to use PackageIndex's $3/kg default: {sample}{extra}"
    )
