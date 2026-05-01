"""Per-run budget enforcement (RUVS_BUDGET_USD)."""
from __future__ import annotations
import os


class BudgetExceeded(RuntimeError):
    pass


class Budget:
    def __init__(self, cap_usd: float | None = None):
        self.cap_usd = cap_usd if cap_usd is not None else float(os.environ.get("RUVS_BUDGET_USD", "50"))
        self.spent_usd = 0.0

    def add(self, usd: float) -> None:
        self.spent_usd += usd
        if self.spent_usd > self.cap_usd:
            raise BudgetExceeded(f"spent ${self.spent_usd:.4f} > cap ${self.cap_usd:.2f}")

    def remaining(self) -> float:
        return self.cap_usd - self.spent_usd
