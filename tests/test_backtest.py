"""
Unit and Integration Tests for TASK-026: No-Lookahead Backtesting Engine.

Verifies:
1. Strict point-in-time historical data access (raises LookaheadBiasError on future leakage).
2. 1-bar execution delay simulation (signal at t, execution at t+1).
3. Survivorship bias prevention (point-in-time active universe selection).
4. End-to-end BacktestEngine execution & equity compounding.
5. Walk-Forward Optimization dataset splitting.
"""

import pytest
import pandas as pd
import numpy as np
from engine.backtest import (
    PointInTimeDataFeed,
    LookaheadBiasError,
    BacktestEngine,
    Order,
    run_walk_forward_optimization,
    simulate_paper_trade,
)


@pytest.fixture
def sample_market_data():
    """Generates 50 bars of synthetic daily OHLCV data for 2 symbols."""
    dates = pd.date_range(start="2024-01-01", periods=50, freq="D")
    
    np.random.seed(42)
    prices_a = 100.0 + np.cumsum(np.random.normal(0.5, 1.0, 50))
    prices_b = 200.0 + np.cumsum(np.random.normal(0.2, 2.0, 50))
    
    df_a = pd.DataFrame({
        "date": dates,
        "open": prices_a,
        "high": prices_a + 1.0,
        "low": prices_a - 1.0,
        "close": prices_a + 0.5,
        "volume": 10000,
    })
    
    df_b = pd.DataFrame({
        "date": dates,
        "open": prices_b,
        "high": prices_b + 2.0,
        "low": prices_b - 2.0,
        "close": prices_b + 1.0,
        "volume": 20000,
    })
    
    return {"STOCK_A": df_a, "STOCK_B": df_b}


def test_point_in_time_feed_strict_access(sample_market_data):
    """Verifies that requesting future data raises LookaheadBiasError in strict mode."""
    feed = PointInTimeDataFeed(sample_market_data, strict=True)
    feed.set_clock(bar_index=10, date=sample_market_data["STOCK_A"]["date"].iloc[10])

    # Valid access: bar index 10 or earlier
    valid_df = feed.get_data_until("STOCK_A", target_bar_index=10)
    assert len(valid_df) == 11  # Index 0 through 10 inclusive

    # Invalid access: bar index 15 (> current clock 10)
    with pytest.raises(LookaheadBiasError, match="Lookahead bias detected"):
        feed.get_data_until("STOCK_A", target_bar_index=15)

    # Invalid access by date beyond set clock
    future_date = sample_market_data["STOCK_A"]["date"].iloc[20]
    with pytest.raises(LookaheadBiasError, match="Lookahead bias detected"):
        feed.get_data_until("STOCK_A", target_date=future_date)


def test_survivorship_bias_prevention():
    """Verifies that active universe at time t excludes non-listed or delisted stocks."""
    dates = pd.date_range(start="2024-01-01", periods=100, freq="D")
    df_active = pd.DataFrame({"date": dates, "close": 100.0})
    df_delisted = pd.DataFrame({"date": dates[:40], "close": 50.0})
    df_ipo_late = pd.DataFrame({"date": dates[60:], "close": 150.0})

    data = {
        "ALWAYS_LISTED": df_active,
        "DELISTED_EARLY": df_delisted,
        "IPO_LATE": df_ipo_late,
    }

    universe_meta = {
        "ALWAYS_LISTED": {"listed_date": "2024-01-01"},
        "DELISTED_EARLY": {"listed_date": "2024-01-01", "delisted_date": dates[39].strftime("%Y-%m-%d")},
        "IPO_LATE": {"listed_date": dates[60].strftime("%Y-%m-%d")},
    }

    feed = PointInTimeDataFeed(data, universe_metadata=universe_meta, strict=True)

    # At Day 20: ALWAYS_LISTED and DELISTED_EARLY should be active. IPO_LATE is not yet listed.
    feed.set_clock(20, dates[20])
    universe_t20 = feed.get_active_universe(dates[20])
    assert "ALWAYS_LISTED" in universe_t20
    assert "DELISTED_EARLY" in universe_t20
    assert "IPO_LATE" not in universe_t20

    # At Day 50: DELISTED_EARLY is delisted. IPO_LATE is not yet listed. Only ALWAYS_LISTED active.
    feed.set_clock(50, dates[50])
    universe_t50 = feed.get_active_universe(dates[50])
    assert universe_t50 == ["ALWAYS_LISTED"]

    # At Day 70: ALWAYS_LISTED and IPO_LATE active. DELISTED_EARLY is delisted.
    feed.set_clock(70, dates[70])
    universe_t70 = feed.get_active_universe(dates[70])
    assert "ALWAYS_LISTED" in universe_t70
    assert "IPO_LATE" in universe_t70
    assert "DELISTED_EARLY" not in universe_t70


def test_one_bar_execution_delay(sample_market_data):
    """Verifies that a signal generated at bar t is executed at bar t+1."""
    engine = BacktestEngine(
        sample_market_data,
        initial_capital=100000.0,
        execution_delay_bars=1,
        slippage_pct=0.0,
        commission_pct=0.0,
    )

    # Strategy: Buy 100 shares of STOCK_A on bar index 1
    def dummy_strategy(feed, bar_idx, current_date, portfolio):
        if bar_idx == 1:
            return [Order(symbol="STOCK_A", side="BUY", quantity=100)]
        elif bar_idx == 5:
            return [Order(symbol="STOCK_A", side="SELL", quantity=100)]
        return []

    res = engine.run(dummy_strategy)

    # Verify trades
    assert len(res["trades"]) == 1
    trade = res["trades"][0]
    
    # Fill price should be Open price of bar 2 (since signal was generated at bar 1)
    bar2_open = sample_market_data["STOCK_A"].iloc[2]["open"]
    assert trade["entry_price"] == pytest.approx(round(bar2_open, 2), abs=0.01)

    # Exit signal generated at bar 5 -> Filled at bar 6 Open price
    bar6_open = sample_market_data["STOCK_A"].iloc[6]["open"]
    assert trade["exit_price"] == pytest.approx(round(bar6_open, 2), abs=0.01)


def test_backtest_engine_end_to_end(sample_market_data):
    """Tests end-to-end backtest execution with equity tracking."""
    engine = BacktestEngine(
        sample_market_data,
        initial_capital=100000.0,
        commission_pct=0.001,
        slippage_pct=0.0005,
    )

    def simple_ma_strategy(feed, bar_idx, current_date, portfolio):
        orders = []
        if bar_idx >= 5:
            df = feed.get_data_until("STOCK_A")
            ma5 = df["close"].tail(5).mean()
            curr_close = df.iloc[-1]["close"]
            
            # Simple rule: if close > MA5 and no position, buy. If close < MA5 and in position, sell.
            has_pos = "STOCK_A" in portfolio["positions"]
            if curr_close > ma5 and not has_pos:
                orders.append(Order(symbol="STOCK_A", side="BUY", quantity=10))
            elif curr_close < ma5 and has_pos:
                orders.append(Order(symbol="STOCK_A", side="SELL", quantity=10))
        return orders

    res = engine.run(simple_ma_strategy)

    assert "equity_curve" in res
    assert len(res["equity_curve"]) == 50
    assert "metrics" in res
    assert res["initial_capital"] == 100000.0


def test_walk_forward_optimization(sample_market_data):
    """Verifies that walk-forward optimization splits data 60% Train, 20% Val, 20% Test without errors."""
    def dummy_strategy(feed, bar_idx, current_date, portfolio):
        return []

    wf_res = run_walk_forward_optimization(
        dummy_strategy,
        sample_market_data,
        train_pct=0.60,
        val_pct=0.20,
        test_pct=0.20,
    )

    assert "train_metrics" in wf_res
    assert "val_metrics" in wf_res
    assert "test_metrics" in wf_res
    assert wf_res["splits"]["train_bars"] == 30
    assert wf_res["splits"]["val_bars"] == 10
    assert wf_res["splits"]["test_bars"] == 10


def test_paper_trade_simulation():
    """Verifies paper trading simulation function."""
    res = simulate_paper_trade("RELIANCE.NS", 2500.0, side="BUY", slippage_pct=0.10)
    assert res["symbol"] == "RELIANCE.NS"
    assert res["signal_price"] == 2500.0
    assert res["execution_price"] == 2502.5  # 2500 * 1.001
    assert res["mode"] == "PAPER_TRADING_SANDBOX"
