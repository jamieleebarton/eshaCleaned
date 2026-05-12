from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import torch


_UNSET = object()


def _clone_tensor(value: Optional[torch.Tensor]) -> Optional[torch.Tensor]:
    return value.clone() if value is not None else None


@dataclass
class PlannerCarryoverState:
    pantry: torch.Tensor
    leftovers: Optional[torch.Tensor] = None
    pantry_ttl: Optional[torch.Tensor] = None
    pantry_frozen: Optional[torch.Tensor] = None
    historical_banned_ids: List[int] = field(default_factory=list)
    week_number: int = 0


class SparseCascadePlanningSession:
    """Owns multi-week carryover so cooldown cannot be forgotten."""

    def __init__(
        self,
        planner,
        *,
        initial_pantry: Optional[torch.Tensor] = None,
        historical_banned_ids: Optional[List[int]] = None,
        initial_leftovers: Optional[torch.Tensor] = None,
        week_number: int = 0,
        initial_pantry_ttl: Optional[torch.Tensor] = None,
        initial_pantry_frozen: Optional[torch.Tensor] = None,
    ) -> None:
        history = [int(rid) for rid in (historical_banned_ids or []) if int(rid) > 0]
        needs_history = (
            initial_leftovers is not None
            or initial_pantry_ttl is not None
            or initial_pantry_frozen is not None
            or week_number > 0
        )
        if needs_history and not history:
            raise ValueError(
                "Cross-week carryover requires prior used_recipe_ids. "
                "Continue a plan with the previous week’s usedRecipeIds."
            )

        pantry = initial_pantry.clone() if initial_pantry is not None else torch.zeros(
            planner.num_ingredients,
            device=planner.device,
        )
        self._planner = planner
        self._state = PlannerCarryoverState(
            pantry=pantry,
            leftovers=_clone_tensor(initial_leftovers),
            pantry_ttl=_clone_tensor(initial_pantry_ttl),
            pantry_frozen=_clone_tensor(initial_pantry_frozen),
            historical_banned_ids=history,
            week_number=week_number,
        )

    @property
    def pantry(self) -> torch.Tensor:
        return self._state.pantry

    @property
    def leftovers(self) -> Optional[torch.Tensor]:
        return self._state.leftovers

    @property
    def pantry_ttl(self) -> Optional[torch.Tensor]:
        return self._state.pantry_ttl

    @property
    def pantry_frozen(self) -> Optional[torch.Tensor]:
        return self._state.pantry_frozen

    @property
    def week_number(self) -> int:
        return self._state.week_number

    def plan_next_week(self) -> Dict[str, Any]:
        result = self._planner._plan_with_carryover(
            initial_pantry=self._state.pantry,
            historical_banned_ids=self._state.historical_banned_ids,
            initial_leftovers=self._state.leftovers,
            week_number=self._state.week_number,
            initial_pantry_ttl=self._state.pantry_ttl,
            initial_pantry_frozen=self._state.pantry_frozen,
        )
        self._advance(result)
        return result

    def replace_carryover(
        self,
        *,
        pantry=_UNSET,
        leftovers=_UNSET,
        pantry_ttl=_UNSET,
        pantry_frozen=_UNSET,
    ) -> None:
        if pantry is not _UNSET:
            self._state.pantry = pantry.clone()
        if leftovers is not _UNSET:
            self._state.leftovers = _clone_tensor(leftovers)
        if pantry_ttl is not _UNSET:
            self._state.pantry_ttl = _clone_tensor(pantry_ttl)
        if pantry_frozen is not _UNSET:
            self._state.pantry_frozen = _clone_tensor(pantry_frozen)

    def _advance(self, result: Dict[str, Any]) -> None:
        final_pantry = result.get("final_pantry")
        self._state.pantry = final_pantry.clone() if final_pantry is not None else torch.zeros(
            self._planner.num_ingredients,
            device=self._planner.device,
        )
        self._state.leftovers = _clone_tensor(result.get("final_leftovers"))
        self._state.pantry_ttl = _clone_tensor(result.get("final_pantry_ttl"))
        self._state.pantry_frozen = _clone_tensor(result.get("final_pantry_frozen"))
        used_ids = [int(rid) for rid in (result.get("used_recipe_ids") or []) if int(rid) > 0]
        self._state.historical_banned_ids.extend(used_ids)
        self._state.week_number += 1
