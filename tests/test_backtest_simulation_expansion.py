"""
Unit and Integration Tests for Backtesting, Slippage & Event Simulation Expansion (TASK-066 to TASK-070).
"""

import pytest
import pandas as pd
from engine.backtest import (
    calculate_market_impact_slippage,
    run_walk_forward_optimization,
    run_parameter_sensitivity_test,
    generate_benchmark_comparison_overlay,
    run_event_driven_backtest,
)


def test_task066_market_impact_slippage():
    impact_bps = calculate_market_impact_slippage(order_qty=10000, avg_daily_volume=1000000, daily_volatility_pct=2.0)
    assert impact_bps >= 5.0
    assert isinstance(impact_bps, float)


def test_task067_walk_forward_optimization():
    closes = [100.0 * (1.001 ** i) for i in range(200)]
    df = pd.DataFrame({"close": closes})

    res = run_walk_forward_optimization(df, in_sample_window_bars=100, out_sample_window_bars=30)
    assert res["status"] == "SUCCESS"
    assert res["windows_evaluated"] >= 1
    assert "out_of_sample_sharpe" in res


def test_task068_parameter_sensitivity_test():
    base_params = {"rsi_period": 14.0, "atr_multiplier": 2.0}
    res = run_parameter_sensitivity_test(base_params)

    assert "sensitivity" in res
    assert res["overall_stability"] == "STABLE"
    assert res["sensitivity"]["rsi_period"]["minus_15_pct"] == 11.9


def test_task069_benchmark_comparison_overlay():
    eq_curve = [100.0, 102.0, 101.5, 105.0, 108.0]
    res = generate_benchmark_comparison_overlay(eq_curve, benchmark_symbol="NIFTY50")

    assert res["benchmark_symbol"] == "NIFTY50"
    assert len(res["strategy_equity"]) == len(eq_curve)
    assert len(res["benchmark_equity"]) == len(eq_curve)
    assert "alpha_generated_pct" in res


def test_task070_event_driven_backtest():
    events = [
        {"symbol": "RELIANCE", "event_type": "EARNINGS", "eps_surprise_pct": 5.2},
        {"symbol": "INFY", "event_type": "EARNINGS", "eps_surprise_pct": 1.1},
    ]
    res = run_event_driven_backtest(events)

    assert res["total_events_tested"] == 2
    assert res["win_rate_pct"] == 50.0
    assert len(res["event_trades"]) == 2
