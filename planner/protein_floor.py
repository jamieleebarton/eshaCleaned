"""Protein floor helpers for synthetic planner runs."""
from __future__ import annotations


def daily_protein_floor_g(calories_per_person: float, protein_pct: float, floor_mode: str) -> float:
    """Return the per-person gram floor used by AttendanceSchedule.

    ``protein_pct`` is the macro-ratio target used by ScoringConfig. It should
    not automatically become the hard gram floor; Hestia batch configs keep the
    profile protein floor independent from the macro target.
    """
    if floor_mode == "flat50":
        return 50.0
    if floor_mode == "pct":
        return float(calories_per_person) * (float(protein_pct) / 100.0) / 4.0
    raise ValueError(f"unknown protein floor mode: {floor_mode}")
