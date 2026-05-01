import os
import pytest
from ruvs.budget import Budget, BudgetExceeded


def test_budget_default_from_env(monkeypatch):
    monkeypatch.setenv("RUVS_BUDGET_USD", "12.34")
    b = Budget()
    assert b.cap_usd == 12.34
    assert b.spent_usd == 0.0


def test_budget_default_when_no_env(monkeypatch):
    monkeypatch.delenv("RUVS_BUDGET_USD", raising=False)
    b = Budget()
    assert b.cap_usd == 50.0


def test_budget_add_under_cap_does_not_raise():
    b = Budget(cap_usd=1.00)
    b.add(0.50)
    b.add(0.49)
    assert b.spent_usd == 0.99
    assert abs(b.remaining() - 0.01) < 1e-9


def test_budget_add_over_cap_raises():
    b = Budget(cap_usd=1.00)
    b.add(0.99)
    with pytest.raises(BudgetExceeded, match=r"spent \$1\.\d+ > cap \$1\.00"):
        b.add(0.02)
    # state still updated
    assert b.spent_usd == pytest.approx(1.01)


def test_budget_explicit_cap_overrides_env(monkeypatch):
    monkeypatch.setenv("RUVS_BUDGET_USD", "999")
    b = Budget(cap_usd=5.0)
    assert b.cap_usd == 5.0
