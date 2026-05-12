"""Independent ledger helpers for sparse planner outputs.

The planner returns weekly aggregate nutrition, daily nutrition tensors, and a
final list of visible meal selections. This module deliberately re-sums the
per-selection audit events instead of trusting the weekly aggregate.
"""
from __future__ import annotations

from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence

try:
    import torch
except Exception:  # pragma: no cover - tests can run without torch importing cleanly
    torch = None  # type: ignore[assignment]


NUTRIENT_KEYS = ("calories", "protein", "carbs", "fat")
EVENT_FIELD_BY_NUTRIENT = {
    "calories": ("cal_per_serving", "calories_per_serving"),
    "protein": ("protein_per_serving", "protein_g_per_serving"),
    "carbs": ("carbs_per_serving", "carbs_g_per_serving"),
    "fat": ("fat_per_serving", "fat_g_per_serving"),
}


def _as_float(value: Any, default: float = 0.0) -> float:
    if value is None:
        return default
    if torch is not None and isinstance(value, torch.Tensor):
        if value.numel() != 1:
            return default
        return float(value.item())
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _as_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _nutrition_matrix(value: Any) -> List[List[float]]:
    if value is None:
        return []
    if torch is not None and isinstance(value, torch.Tensor):
        return [[float(x) for x in row[:4]] for row in value.detach().cpu().tolist()]
    if isinstance(value, Sequence):
        matrix = []
        for row in value:
            if isinstance(row, Sequence):
                matrix.append([_as_float(x) for x in list(row)[:4]])
        return matrix
    return []


def _blank_daily() -> List[List[float]]:
    return [[0.0, 0.0, 0.0, 0.0] for _ in range(7)]


def _add_to_daily(daily: List[List[float]], day: int, values: Sequence[float]) -> None:
    if 0 <= day < len(daily):
        for idx, value in enumerate(values[:4]):
            daily[day][idx] += float(value)


def _selection_cost(selection: Sequence[Any]) -> float:
    if len(selection) >= 10:
        return _as_float(selection[6])
    if len(selection) > 4:
        return _as_float(selection[4])
    return 0.0


def _selection_has_food(selection: Sequence[Any]) -> bool:
    if not selection:
        return False
    ids = []
    for idx in range(min(3, len(selection))):
        ids.append(_as_int(selection[idx]))
    return any(rid > 0 for rid in ids)


def selection_audit_events(selection: Sequence[Any]) -> List[Mapping[str, Any]]:
    """Return ledger events from the current extended selection tuple.

    Index 18 is intentionally beyond the API-facing tuple fields. Existing
    consumers ignore it, while audit code can sum exact delivered servings.
    """
    if len(selection) > 18 and isinstance(selection[18], list):
        return [event for event in selection[18] if isinstance(event, Mapping)]
    return []


def _event_nutrient(event: Mapping[str, Any], nutrient: str) -> float:
    for field in EVENT_FIELD_BY_NUTRIENT[nutrient]:
        if field in event:
            return _as_float(event[field])
    return 0.0


def _event_totals(event: Mapping[str, Any]) -> List[float]:
    servings = _as_float(event.get("servings"))
    return [servings * _event_nutrient(event, key) for key in NUTRIENT_KEYS]


def _snack_totals(snacks: Iterable[Mapping[str, Any]]) -> List[float]:
    totals = [0.0, 0.0, 0.0, 0.0]
    for snack in snacks:
        totals[0] += _as_float(snack.get("calories"))
        totals[1] += _as_float(snack.get("protein"))
        totals[2] += _as_float(snack.get("carbs"))
        totals[3] += _as_float(snack.get("fat"))
    return totals


def _distribute_snacks_daily(
    daily: List[List[float]],
    snacks: Sequence[Mapping[str, Any]],
) -> List[List[float]]:
    with_snacks = [row[:] for row in daily]
    if not snacks:
        return with_snacks
    per_day = len(snacks) // 7
    remainder = len(snacks) % 7
    for day_idx in range(7):
        start = day_idx * per_day + min(day_idx, remainder)
        end = start + per_day + (1 if day_idx < remainder else 0)
        _add_to_daily(with_snacks, day_idx, _snack_totals(snacks[start:end]))
    return with_snacks


def ledger_from_audit_events(
    selections: Sequence[Sequence[Any]],
    *,
    snacks_added: Optional[Sequence[Mapping[str, Any]]] = None,
    snacks_cost: float = 0.0,
) -> Dict[str, Any]:
    """Sum calories/protein/cost from final selection audit events."""
    daily = _blank_daily()
    weekly = [0.0, 0.0, 0.0, 0.0]
    selection_cost = 0.0
    slots_with_food = 0
    slots_with_events = 0
    slots_missing_events: List[int] = []
    event_count = 0

    for slot, selection in enumerate(selections):
        selection_cost += _selection_cost(selection)
        has_food = _selection_has_food(selection)
        if has_food:
            slots_with_food += 1

        events = selection_audit_events(selection)
        if events:
            slots_with_events += 1
        elif has_food:
            slots_missing_events.append(slot)

        for event in events:
            totals = _event_totals(event)
            event_count += 1
            for idx, value in enumerate(totals):
                weekly[idx] += value
            _add_to_daily(daily, slot // 3, totals)

    snacks = list(snacks_added or [])
    snack_totals = _snack_totals(snacks)
    weekly_with_snacks = [weekly[idx] + snack_totals[idx] for idx in range(4)]
    daily_with_snacks = _distribute_snacks_daily(daily, snacks)

    return {
        "weekly_without_snacks": dict(zip(NUTRIENT_KEYS, weekly)),
        "weekly": dict(zip(NUTRIENT_KEYS, weekly_with_snacks)),
        "daily_without_snacks": daily,
        "daily": daily_with_snacks,
        "selection_cost": selection_cost,
        "snacks_cost": float(snacks_cost),
        "total_cost": selection_cost + float(snacks_cost),
        "slots_with_food": slots_with_food,
        "slots_with_events": slots_with_events,
        "slots_missing_events": slots_missing_events,
        "event_count": event_count,
    }


def reported_ledger_from_result(result: Mapping[str, Any]) -> Dict[str, Any]:
    daily_without_snacks = _nutrition_matrix(result.get("daily_nutrition"))
    if not daily_without_snacks:
        daily_without_snacks = _blank_daily()
    weekly_without_snacks = [sum(day[idx] for day in daily_without_snacks) for idx in range(4)]

    snacks = list(result.get("snacks_added") or [])
    snack_totals = _snack_totals(snacks)
    weekly = [weekly_without_snacks[idx] + snack_totals[idx] for idx in range(4)]
    daily = _distribute_snacks_daily(daily_without_snacks, snacks)

    return {
        "weekly_without_snacks": dict(zip(NUTRIENT_KEYS, weekly_without_snacks)),
        "weekly": dict(zip(NUTRIENT_KEYS, weekly)),
        "daily_without_snacks": daily_without_snacks,
        "daily": daily,
        "total_cost": _as_float(result.get("total_cost")),
        "snacks_cost": _as_float(result.get("snacks_cost")),
        "calories_from_compliance": None,
        "protein_g": _as_float(result.get("protein_g")),
    }


def _max_daily_delta(
    left_daily: Sequence[Sequence[float]],
    right_daily: Sequence[Sequence[float]],
    nutrient_idx: int,
) -> float:
    if not left_daily or not right_daily:
        return 0.0
    count = min(len(left_daily), len(right_daily))
    if count == 0:
        return 0.0
    return max(abs(float(left_daily[i][nutrient_idx]) - float(right_daily[i][nutrient_idx])) for i in range(count))


def audit_result_ledger(
    *,
    planner: Any,
    result: Mapping[str, Any],
    cell_id: Optional[str] = None,
    week: Optional[int] = None,
    calorie_abs_tolerance: float = 25.0,
    calorie_pct_tolerance: float = 0.005,
    protein_abs_tolerance: float = 2.0,
    cost_abs_tolerance: float = 0.02,
) -> Dict[str, Any]:
    """Compare final-selection event ledger against reported planner totals."""
    selections = list(result.get("selections") or [])
    snacks = list(result.get("snacks_added") or [])
    event_ledger = ledger_from_audit_events(
        selections,
        snacks_added=snacks,
        snacks_cost=_as_float(result.get("snacks_cost")),
    )
    reported = reported_ledger_from_result(result)

    weekly_target = _as_float(getattr(planner, "weekly_calories", None))
    protein_target = _as_float(getattr(planner, "weekly_protein", None))
    if weekly_target > 0 and result.get("cal_compliance") is not None:
        reported["calories_from_compliance"] = _as_float(result.get("cal_compliance")) * weekly_target

    ledger_cal = event_ledger["weekly"]["calories"]
    reported_cal = reported["weekly"]["calories"]
    ledger_protein = event_ledger["weekly"]["protein"]
    reported_protein = reported["weekly"]["protein"]
    ledger_cost = event_ledger["total_cost"]
    reported_cost = reported["total_cost"]

    calorie_delta = ledger_cal - reported_cal
    compliance_calories = reported["calories_from_compliance"]
    compliance_calorie_delta = (
        ledger_cal - compliance_calories
        if compliance_calories is not None
        else None
    )
    calorie_delta_pct = calorie_delta / reported_cal if reported_cal else 0.0
    protein_delta = ledger_protein - reported_protein
    protein_g_delta = ledger_protein - reported["protein_g"]
    cost_delta = ledger_cost - reported_cost
    max_daily_calorie_delta = _max_daily_delta(event_ledger["daily"], reported["daily"], 0)
    max_daily_protein_delta = _max_daily_delta(event_ledger["daily"], reported["daily"], 1)

    allowed_cal_delta = max(calorie_abs_tolerance, abs(reported_cal) * calorie_pct_tolerance)
    failures = []
    if event_ledger["slots_missing_events"]:
        failures.append("missing_selection_audit_events")
    if abs(calorie_delta) > allowed_cal_delta:
        failures.append("weekly_calorie_delta")
    if compliance_calorie_delta is not None and abs(compliance_calorie_delta) > allowed_cal_delta:
        failures.append("cal_compliance_delta")
    if abs(protein_delta) > protein_abs_tolerance:
        failures.append("weekly_protein_delta")
    if abs(protein_g_delta) > protein_abs_tolerance:
        failures.append("protein_g_delta")
    if abs(cost_delta) > cost_abs_tolerance:
        failures.append("weekly_cost_delta")
    if max_daily_calorie_delta > allowed_cal_delta:
        failures.append("daily_calorie_delta")

    compliance_from_ledger = ledger_cal / weekly_target if weekly_target > 0 else None
    protein_compliance_from_ledger = ledger_protein / protein_target if protein_target > 0 else None

    return {
        "cell_id": cell_id,
        "week": week,
        "status": "pass" if not failures else "fail",
        "failures": failures,
        "weekly_calorie_target": weekly_target,
        "weekly_protein_target": protein_target,
        "ledger_calories": ledger_cal,
        "reported_calories": reported_cal,
        "reported_calories_from_compliance": reported["calories_from_compliance"],
        "calorie_delta": calorie_delta,
        "cal_compliance_calorie_delta": compliance_calorie_delta,
        "calorie_delta_pct": calorie_delta_pct,
        "ledger_cal_compliance": compliance_from_ledger,
        "reported_cal_compliance": _as_float(result.get("cal_compliance")),
        "ledger_protein_g": ledger_protein,
        "reported_protein_g": reported_protein,
        "reported_protein_g_field": reported["protein_g"],
        "protein_delta_g": protein_delta,
        "protein_g_field_delta": protein_g_delta,
        "ledger_prot_compliance": protein_compliance_from_ledger,
        "reported_prot_compliance": _as_float(result.get("prot_compliance")),
        "ledger_total_cost": ledger_cost,
        "reported_total_cost": reported_cost,
        "cost_delta": cost_delta,
        "max_daily_calorie_delta": max_daily_calorie_delta,
        "max_daily_protein_delta": max_daily_protein_delta,
        "slots_with_food": event_ledger["slots_with_food"],
        "slots_with_events": event_ledger["slots_with_events"],
        "slots_missing_events": event_ledger["slots_missing_events"],
        "event_count": event_ledger["event_count"],
    }


def summarize_audits(records: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    records = list(records)
    failed = [record for record in records if record.get("status") != "pass"]
    return {
        "status": "pass" if records and not failed else "fail",
        "audit_count": len(records),
        "failed_count": len(failed),
        "max_abs_calorie_delta": max((abs(_as_float(r.get("calorie_delta"))) for r in records), default=0.0),
        "max_abs_protein_delta_g": max((abs(_as_float(r.get("protein_delta_g"))) for r in records), default=0.0),
        "max_abs_cost_delta": max((abs(_as_float(r.get("cost_delta"))) for r in records), default=0.0),
        "max_daily_calorie_delta": max((_as_float(r.get("max_daily_calorie_delta")) for r in records), default=0.0),
        "records": records,
    }
