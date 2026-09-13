"""
Unit tests for Advanced Backtester & Strategy Analytics (Phase 21 - Tasks T-255 to T-264).
"""

import pytest
import pandas as pd
import numpy as np
from engine.backtest import (
    run_vectorized_backtest,
    run_event_driven_backtest,
    EventDrivenBacktester,
    run_multi_asset_backtest,
    run_parameter_grid_search,
    run_bayesian_optimization,
    calculate_execution_friction,
    analyze_drawdown_underwater,
    generate_monthly_return_heatmap,
    breakdown_trade_log,
    compare_strategies,
    generate_strategy_tear_sheet
)


def test_t255_vectorized_backtest():
    """T-255: Verify high-speed vectorized strategy simulation engine."""
    dates = pd.date_range("2024-01-01", periods=50)
    prices = 100.0 + np.cumsum(np.random.normal(0.5, 1.0, 50))
    df = pd.DataFrame({"date": dates, "close": prices})

    res = run_vectorized_backtest(df, initial_capital=100000.0)
    assert "sharpe_ratio" in res
    assert "max_drawdown_pct" in res
    assert "equity_curve" in res
    assert len(res["equity_curve"]) == 50
    assert res["equity_curve"][0] > 0


def test_t256_event_driven_backtest():
    """T-256: Verify event-driven backtest engine for tick/bar level validation."""
    events = [
        {"symbol": "NIFTY", "close": 22000.0, "eps_surprise_pct": 5.0, "event_type": "EARNINGS"},
        {"symbol": "NIFTY", "close": 22100.0, "eps_surprise_pct": 1.0, "event_type": "BAR"},
        {"symbol": "NIFTY", "close": 22200.0, "eps_surprise_pct": 4.5, "event_type": "BAR"}
    ]
    engine = EventDrivenBacktester()
    res = engine.run_backtest(events)

    assert res["total_events_processed"] == 3
    assert res["total_trades"] == 3
    assert "final_equity" in res
    assert "sharpe_ratio" in res
    assert isinstance(res["equity_curve"], list)
    assert res["equity_curve"][0] == 100000.0


def test_t257_multi_asset_portfolio_backtest():
    """T-257: Verify multi-asset basket portfolio backtest engine."""
    dates = pd.date_range("2024-01-01", periods=30)
    data = {
        "RELIANCE": pd.DataFrame({"close": 2500 + np.cumsum(np.random.normal(0.2, 1.0, 30))}),
        "TCS": pd.DataFrame({"close": 3500 + np.cumsum(np.random.normal(0.3, 1.2, 30))}),
        "INFY": pd.DataFrame({"close": 1500 + np.cumsum(np.random.normal(0.1, 0.8, 30))})
    }
    res = run_multi_asset_backtest(data, initial_capital=1000000.0, max_stock_weight=0.20)
    assert res["num_assets"] == 3
    assert len(res["asset_symbols"]) == 3
    assert "equity_curve" in res
    assert len(res["equity_curve"]) == 30


def test_t258_parameter_grid_search_and_bayesian_optimization():
    """T-258: Verify parameter grid search & Bayesian optimization engine."""
    prices = 100.0 + np.cumsum(np.random.normal(0.2, 1.0, 40))
    df = pd.DataFrame({"close": prices})
    data = {"NIFTY": df}

    # Grid search
    grid_res = run_parameter_grid_search(data, param_grid={"fast_period": [3, 5], "slow_period": [10, 20]})
    assert "best_params" in grid_res
    assert "top_sharpe" in grid_res
    assert len(grid_res["grid_results"]) == 4

    # Bayesian optimization
    bayes_res = run_bayesian_optimization(data, param_bounds={"fast_period": (3, 8), "slow_period": (12, 25)}, n_iterations=5)
    assert "best_params" in bayes_res
    assert bayes_res["iterations_evaluated"] == 5
    assert len(bayes_res["trials"]) == 5


def test_t259_execution_friction_model():
    """T-259: Verify realistic execution friction model calculations."""
    friction = calculate_execution_friction(
        order_size=100, price=2500.0, adv_volume=100000, volatility=0.02, is_intraday=False
    )
    assert friction["turnover"] == 250000.0
    assert friction["stt"] > 0
    assert friction["brokerage"] <= 20.0
    assert friction["total_friction"] > 0
    assert friction["total_bps"] > 0


def test_t260_underwater_drawdown_analysis():
    """T-260: Verify equity curve drawdown duration & underwater chart calculation."""
    eq_curve = [100.0, 110.0, 105.0, 100.0, 108.0, 115.0]
    underwater = analyze_drawdown_underwater(eq_curve)
    assert "underwater_pct" in underwater
    assert len(underwater["underwater_pct"]) == 6
    assert underwater["max_drawdown_pct"] > 0
    assert underwater["max_drawdown_duration_bars"] == 3


def test_t261_monthly_return_heatmap_matrix():
    """T-261: Verify Monthly Return Heatmap UI grid matrix generation."""
    eq_curve = [100.0 + i * 2 for i in range(30)]
    heatmap = generate_monthly_return_heatmap(eq_curve, start_year=2024)
    assert "years" in heatmap
    assert "months" in heatmap
    assert "matrix" in heatmap
    assert 2024 in heatmap["matrix"]
    assert "Jan" in heatmap["matrix"][2024]
    assert "YTD" in heatmap["matrix"][2024]


def test_t262_trade_log_breakdown():
    """T-262: Verify Trade Log filter & breakdown by side, sector, and time of day."""
    trades = [
        {"side": "BUY", "sector": "IT", "time_of_day": "MORNING", "trade_return_pct": 3.0},
        {"side": "SELL", "sector": "BANK", "time_of_day": "MIDDAY", "trade_return_pct": -1.5},
        {"side": "BUY", "sector": "IT", "time_of_day": "AFTERNOON", "trade_return_pct": 2.0}
    ]
    bd = breakdown_trade_log(trades)
    assert "by_side" in bd
    assert "by_sector" in bd
    assert "by_time_of_day" in bd
    assert bd["by_side"]["LONG"]["count"] == 2
    assert bd["by_side"]["SHORT"]["count"] == 1
    assert bd["by_sector"]["IT"]["count"] == 2


def test_t263_strategy_comparison_mode():
    """T-263: Verify Strategy Backtest comparison mode."""
    strategies = {
        "Strat_A": {"equity_curve": [100.0, 105.0, 110.0], "sharpe_ratio": 2.0, "max_drawdown_pct": 2.0},
        "Strat_B": {"equity_curve": [100.0, 98.0, 104.0], "sharpe_ratio": 1.2, "max_drawdown_pct": 4.0}
    }
    comp = compare_strategies(strategies)
    assert "normalized_equity_curves" in comp
    assert "comparison_table" in comp
    assert len(comp["comparison_table"]) == 2
    assert comp["comparison_table"][0]["strategy"] == "Strat_A"


def test_t264_strategy_tear_sheet_generator(tmp_path):
    """T-264: Verify automated HTML/PDF Strategy Tear-Sheet generator."""
    out_file = str(tmp_path / "tear_sheet.html")
    results = {
        "strategy_name": "Test Strategy Alpha",
        "equity_curve": [100.0, 102.0, 105.0, 108.0],
        "sharpe_ratio": 2.5,
        "max_drawdown_pct": 3.0,
        "win_rate_pct": 70.0
    }
    report = generate_strategy_tear_sheet(results, output_path=out_file)
    assert report["status"] == "SUCCESS"
    assert "QuantStats Tear-Sheet" in report["html_report"]
    with open(out_file, "r") as f:
        content = f.read()
    assert "Test Strategy Alpha" in content
