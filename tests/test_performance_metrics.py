"""
Unit Tests for TASK-027: Performance Metrics against Deterministic Fixtures.

Verifies:
1. Max Drawdown, peak index, trough index, and duration.
2. Expectancy, Expectancy Ratio, Win Rate, and Profit Factor.
3. Conditional Value at Risk (CVaR / Expected Shortfall) & VaR.
4. Sharpe Ratio mathematical formula against reference calculations.
5. Sortino Ratio downside volatility formula.
6. Calmar Ratio (CAGR / Max DD).
7. Comprehensive performance metrics suite & edge case handling.
"""

import math
import pytest
import numpy as np
from engine.backtest import (
    calculate_max_drawdown,
    calculate_sharpe_ratio,
    calculate_sortino_ratio,
    calculate_calmar_ratio,
    calculate_expectancy,
    calculate_cvar,
    calculate_performance_metrics,
)


def test_max_drawdown_deterministic_fixture():
    """
    Tests Max Drawdown on a known deterministic 10-point equity curve.
    Curve: [100.0, 105.0, 102.0, 108.0, 104.0, 110.0, 107.0, 115.0, 112.0, 120.0]
    Peak = 108.0 (at idx 3), Trough = 104.0 (at idx 4).
    Max DD = (108 - 104) / 108 = 4 / 108 = 0.037037... -> 3.70%
    """
    equity_curve = [100.0, 105.0, 102.0, 108.0, 104.0, 110.0, 107.0, 115.0, 112.0, 120.0]
    res = calculate_max_drawdown(equity_curve)

    assert res["max_drawdown_pct"] == 3.70
    assert res["peak_idx"] == 3
    assert res["trough_idx"] == 4
    assert res["duration_bars"] == 1
    assert res["max_drawdown_decimal"] == pytest.approx(4.0 / 108.0, abs=1e-5)


def test_expectancy_deterministic_fixture():
    """
    Tests Expectancy and Profit Factor against known trade returns.
    Trades: [0.10, -0.05, 0.15, -0.05, 0.20, -0.10]
    Wins: [0.10, 0.15, 0.20] -> Avg Win = 0.45 / 3 = 0.15
    Losses: [0.05, 0.05, 0.10] -> Avg Loss = 0.20 / 3 = 0.066666...
    Win Rate = 50.0%
    Expectancy = (0.50 * 0.15) - (0.50 * 0.066666...) = 0.041666...
    Profit Factor = 0.45 / 0.20 = 2.25
    Expectancy Ratio = 0.041666... / 0.066666... = 0.625
    """
    trade_returns = [0.10, -0.05, 0.15, -0.05, 0.20, -0.10]
    res = calculate_expectancy(trade_returns)

    assert res["win_rate_pct"] == 50.0
    assert res["avg_win"] == pytest.approx(0.15, abs=1e-5)
    assert res["avg_loss"] == pytest.approx(0.0666666, abs=1e-5)
    assert res["expectancy"] == pytest.approx(0.0416666, abs=1e-5)
    assert res["profit_factor"] == 2.25
    assert res["expectancy_ratio"] == pytest.approx(0.625, abs=1e-3)


def test_cvar_deterministic_fixture():
    """
    Tests CVaR (Expected Shortfall at 95% confidence).
    Fixture: 95 daily returns of +0.01 (+1%) and 5 tail losses of [-0.05, -0.06, -0.07, -0.08, -0.09].
    Tail losses at/below 5th percentile quantile: [-0.05, -0.06, -0.07, -0.08, -0.09]
    Mean tail loss = -0.07 (-7.0%)
    CVaR 95% loss = 7.0%
    """
    returns = [0.01] * 95 + [-0.05, -0.06, -0.07, -0.08, -0.09]
    res = calculate_cvar(returns, alpha=0.95)

    assert res["cvar_pct"] == pytest.approx(7.0, abs=0.1)
    assert res["cvar_decimal"] <= -0.05


def test_sharpe_ratio_reference_calculation():
    """
    Tests Sharpe ratio calculation against mathematical reference definition.
    R_rf = 7.0% annual -> r_f = 0.07 / 252 daily.
    """
    daily_rets = [0.01, 0.02, -0.01, 0.015, -0.005, 0.02, 0.01, -0.015, 0.025, 0.01]
    eq = [100000.0]
    for r in daily_rets:
        eq.append(eq[-1] * (1.0 + r))

    daily_rf = 0.07 / 252.0
    excess = np.array(daily_rets) - daily_rf
    expected_sharpe = (np.mean(excess) / np.std(daily_rets, ddof=1)) * np.sqrt(252.0)

    actual_sharpe = calculate_sharpe_ratio(eq, risk_free_rate=0.07, periods_per_year=252)

    assert actual_sharpe == pytest.approx(round(expected_sharpe, 4), abs=1e-4)


def test_sortino_ratio_reference_calculation():
    """
    Tests Sortino ratio downside volatility calculation.
    """
    daily_rets = [0.01, 0.02, -0.01, 0.015, -0.005, 0.02, 0.01, -0.015, 0.025, 0.01]
    eq = [100000.0]
    for r in daily_rets:
        eq.append(eq[-1] * (1.0 + r))

    daily_rf = 0.07 / 252.0
    excess = np.array(daily_rets) - daily_rf
    downside = np.minimum(0.0, excess)
    downside_std = np.sqrt(np.mean(downside ** 2))
    expected_sortino = (np.mean(excess) / downside_std) * np.sqrt(252.0)

    actual_sortino = calculate_sortino_ratio(eq, risk_free_rate=0.07, periods_per_year=252)

    assert actual_sortino == pytest.approx(round(expected_sortino, 4), abs=1e-4)


def test_calmar_ratio():
    """Tests Calmar ratio (CAGR / Max DD)."""
    assert calculate_calmar_ratio(0.20, 0.10) == 2.0
    assert calculate_calmar_ratio(0.15, 0.05) == 3.0
    assert calculate_calmar_ratio(0.10, 0.0) == 0.0


def test_comprehensive_performance_metrics():
    """
    Tests calculate_performance_metrics returns complete metric dict.
    """
    eq = [100000.0 + i * 500 for i in range(100)]  # Smooth upward trend
    metrics = calculate_performance_metrics(eq)

    required_keys = [
        "cagr_pct",
        "total_return_pct",
        "max_drawdown_pct",
        "sharpe_ratio",
        "sortino_ratio",
        "calmar_ratio",
        "expectancy",
        "expectancy_ratio",
        "win_rate_pct",
        "profit_factor",
        "cvar_95_pct",
        "cvar_99_pct",
        "volatility_ann_pct",
    ]

    for k in required_keys:
        assert k in metrics, f"Missing metric key: {k}"

    assert metrics["total_return_pct"] > 0
    assert metrics["max_drawdown_pct"] == 0.0


def test_edge_cases():
    """Verifies edge case handling for empty or flat equity curves."""
    empty_metrics = calculate_performance_metrics([])
    assert empty_metrics["cagr_pct"] == 0.0
    assert empty_metrics["sharpe_ratio"] == 0.0

    single_metrics = calculate_performance_metrics([100.0])
    assert single_metrics["cagr_pct"] == 0.0

    flat_metrics = calculate_performance_metrics([100.0] * 50)
    assert flat_metrics["max_drawdown_pct"] == 0.0
    assert flat_metrics["sharpe_ratio"] == 0.0
