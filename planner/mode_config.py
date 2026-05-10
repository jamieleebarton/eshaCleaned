"""Planner mode configuration helpers.

Keep audit scripts aligned with the production batch mode semantics:
protein_pct is the macro target; mode/tier controls the scoring preset.
"""
from __future__ import annotations

from typing import Any, Callable


def build_scoring_config(
    scoring_config_cls: type,
    replace_fn: Callable[..., Any],
    *,
    mode: str,
    protein_pct: float,
    daily_cal: float | None = None,
    leftover_pct: float | None = None,
) -> Any:
    """Build a ScoringConfig using production-compatible mode semantics."""
    protein_pct = float(protein_pct)

    if mode in {"thrifty", "low_cost", "moderate", "liberal"}:
        config = getattr(scoring_config_cls, mode)(protein_pct=protein_pct)
    elif mode == "balanced":
        config = scoring_config_cls.balanced()
    elif mode == "high_protein":
        config = scoring_config_cls.high_protein(target_pct=protein_pct)
    elif mode == "budget":
        config = scoring_config_cls.budget()
    else:
        raise ValueError(f"unsupported planner mode: {mode}")

    overrides: dict[str, float] = {"protein_pct_target": protein_pct}
    if daily_cal is not None:
        overrides["daily_cal_target"] = float(daily_cal)
    if leftover_pct is not None:
        overrides["leftover_pct_target"] = float(leftover_pct)

    return replace_fn(config, **overrides)
