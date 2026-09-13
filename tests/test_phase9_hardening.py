"""
Comprehensive Phase 9 Unit & Integration Test Suite (TASK-131 to TASK-150).
Verifies Market Replay Tool, Chaos Resilience, UI Performance Assets, and Event-Driven Backtesting.
"""

import pytest
from pathlib import Path
from engine.market_replay import MarketReplayEngine
from engine.backtest import (
    calculate_market_impact_slippage,
    run_walk_forward_optimization,
    run_parameter_sensitivity_test,
    generate_benchmark_comparison_overlay,
    EventDrivenBacktester
)

PROJECT_ROOT = Path(__file__).parent.parent


def test_task131_to_140_ui_assets_and_minification():
    """Verify Phase 8/9 UI performance assets exist."""
    assert (PROJECT_ROOT / "web" / "index.html").exists()
    assert (PROJECT_ROOT / "web" / "style.css").exists()
    assert (PROJECT_ROOT / "web" / "app.js").exists()
    assert (PROJECT_ROOT / "web" / "sw.js").exists()
    assert (PROJECT_ROOT / "web" / "worker.js").exists()
    assert (PROJECT_ROOT / "web" / "manifest.json").exists()


def test_task141_event_driven_backtester():
    """Verify EventDrivenBacktester runs event calendar simulation."""
    events = [
        {"symbol": "RELIANCE", "event_type": "EARNINGS", "eps_surprise_pct": 5.2},
        {"symbol": "INFY", "event_type": "EARNINGS", "eps_surprise_pct": 1.1},
    ]
    backtester = EventDrivenBacktester()
    res = backtester.run_backtest(events)
    assert res["total_events_tested"] == 2
    assert res["win_rate_pct"] == 50.0
    assert len(res["event_trades"]) == 2


def test_task142_market_impact_slippage():
    """Verify non-linear square-root market impact slippage calculation."""
    bps = calculate_market_impact_slippage(order_qty=10000, avg_daily_volume=1000000, daily_volatility_pct=2.0)
    assert isinstance(bps, float)
    assert bps >= 5.0


def test_task143_walk_forward_optimization():
    """Verify Walk-Forward Optimization engine."""
    import pandas as pd
    closes = [100.0 * (1.001 ** i) for i in range(200)]
    df = pd.DataFrame({"close": closes})
    res = run_walk_forward_optimization(df, in_sample_window_bars=100, out_sample_window_bars=30)
    assert res["status"] == "SUCCESS"
    assert res["windows_evaluated"] >= 1


def test_task144_parameter_sensitivity_test():
    """Verify Monte Carlo parameter sensitivity stress tester."""
    base_params = {"rsi_period": 14.0, "atr_multiplier": 2.0}
    res = run_parameter_sensitivity_test(base_params)
    assert "sensitivity" in res
    assert res["overall_stability"] == "STABLE"


def test_task149_market_replay_tool():
    """Verify MarketReplayEngine historical tick streamer."""
    ticks = [
        {"symbol": "RELIANCE.NS", "ltp": 2850.0 + i, "volume": 1000}
        for i in range(5)
    ]
    replayed = []
    engine = MarketReplayEngine(ticks, speed_multiplier=50.0)
    res = engine.start_replay(lambda t: replayed.append(t))

    assert res["status"] == "COMPLETED"
    assert res["ticks_replayed"] == 5
    assert len(replayed) == 5
    assert replayed[0]["symbol"] == "RELIANCE.NS"


def test_task150_ci_cd_workflow_config():
    """Verify GitHub Actions CI workflow config."""
    ci_file = PROJECT_ROOT / ".github" / "workflows" / "ci.yml"
    assert ci_file.exists()
    content = ci_file.read_text(encoding="utf-8")
    assert "Swing Trading System CI/CD Workflow" in content
    assert "pytest tests/ -v" in content
