import pytest

from src.cn.errors import PermissionError
from src.cn.providers.tushare import TushareCallBudget


def test_tushare_budget_blocks_online_calls_by_default():
    budget = TushareCallBudget()
    with pytest.raises(PermissionError, match="budget exhausted"):
        budget.consume("daily")


def test_tushare_budget_allows_only_explicitly_approved_call_count():
    budget = TushareCallBudget(max_calls=2)
    budget.consume("stock_basic")
    budget.consume("daily")
    with pytest.raises(PermissionError):
        budget.consume("income")
    assert budget.used_calls == 2
