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
    EventDrivenBacktester,
)


# Mock Strategy for testing event-driven backtester and lookahead bias
class MockStrategy:
    def __init__(self, symbol="TEST", short_ma_period=5, long_ma_period=10):
        self.symbol = symbol
        self.short_ma_period = short_ma_period
        self.long_ma_period = long_ma_period
        self.data_history = pd.DataFrame(columns=['close'])
        self.position = 0 # 0: flat, 1: long, -1: short
        self.lookahead_detected = False
        self.last_processed_timestamp = None
        self.signals_generated = []

    def process_bar(self, bar_event):
        # bar_event is expected to be a dictionary mimicking a BarEvent
        timestamp = bar_event['timestamp']
        close_price = bar_event['close']

        # Strict chronological check: ensure current bar's timestamp is strictly AFTER the last processed one
        if self.last_processed_timestamp is not None and timestamp <= self.last_processed_timestamp:
            self.lookahead_detected = True
            return [] # Stop processing to avoid further issues if out of order

        self.last_processed_timestamp = timestamp

        # Add the current bar to history
        self.data_history.loc[timestamp] = {'close': close_price}
        # Ensure data_history is sorted by index (timestamp) in case of non-sequential adds
        self.data_history = self.data_history.sort_index()

        signals = []

        if len(self.data_history) < self.long_ma_period:
            return signals

        # Calculate MAs using *only* historical data up to the current timestamp
        # `iloc[-N:]` naturally uses the last N elements, which for a chronologically
        # ordered `data_history` corresponds to the most recent N bars including the current one.
        current_data = self.data_history['close']
        short_ma = current_data.iloc[-self.short_ma_period:].mean()
        long_ma = current_data.iloc[-self.long_ma_period:].mean()

        # Generate signals
        if short_ma > long_ma and self.position <= 0: # Buy if flat or short
            signal = {'timestamp': timestamp, 'symbol': self.symbol, 'signal_type': 'BUY', 'qty': 100}
            signals.append(signal)
            self.signals_generated.append(signal)
            self.position = 1
        elif short_ma < long_ma and self.position >= 0: # Sell if flat or long
            signal = {'timestamp': timestamp, 'symbol': self.symbol, 'signal_type': 'SELL', 'qty': 100}
            signals.append(signal)
            self.signals_generated.append(signal)
            self.position = -1

        return signals

    def get_lookahead_status(self):
        return self.lookahead_detected

    def get_signals_generated(self):
        return self.signals_generated


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
    # Generate sample OHLCV data
    start_date = pd.Timestamp("2023-01-01")
    dates = pd.date_range(start=start_date, periods=100, freq='D') # 100 bars
    # Some fluctuating data to ensure strategy generates signals
    closes = [100 + i * 0.5 + 5 * ((i % 10) - 5) for i in range(100)]
    open_prices = [c - 0.5 for c in closes]
    high_prices = [c + 1.0 for c in closes]
    low_prices = [c - 1.0 for c in closes]
    volumes = [100000 + i * 1000 for i in range(100)]

    data = pd.DataFrame({
        'open': open_prices,
        'high': high_prices,
        'low': low_prices,
        'close': closes,
        'volume': volumes
    }, index=dates)
    data.index.name = 'timestamp'

    # Convert DataFrame to a list of "BarEvent" dictionaries for the backtester
    bar_events = []
    for index, row in data.iterrows():
        bar_events.append({
            'timestamp': index,
            'symbol': 'TEST',
            'open': row['open'],
            'high': row['high'],
            'low': row['low'],
            'close': row['close'],
            'volume': row['volume'],
            'event_type': 'BAR'
        })

    strategy = MockStrategy()
    
    # Initialize EventDrivenBacktester with the strategy
    # Assuming EventDrivenBacktester now accepts a strategy during initialization
    backtester = EventDrivenBacktester(strategy=strategy) 
    
    # Run the backtest with the generated bar events
    # Assuming run_backtest now takes a list of events (e.g., bar_events)
    res = backtester.run_backtest(bar_events)

    # --- Assertions for chronological execution and zero lookahead leakage ---
    assert not strategy.get_lookahead_status(), "Lookahead bias or out-of-order data detected by the strategy!"
    
    # Assert that trades were generated (the simple MA strategy should generate some trades)
    assert res.get("total_trades", 0) > 0, "No trades were generated during the backtest."
    
    # Assert key performance metrics are present
    assert "final_equity" in res, "Final equity not found in backtest results."
    assert "sharpe_ratio" in res, "Sharpe Ratio not found in backtest results."
    assert "total_events_processed" in res, "Total events processed not found in backtest results."
    assert res["total_events_processed"] == len(bar_events), "Number of processed events does not match input."

    # Basic check for equity curve (should be a list and have an initial value)
    assert isinstance(res["equity_curve"], list), "Equity curve should be a list."
    assert len(res["equity_curve"]) > 0, "Equity curve should not be empty."
    # Assuming initial capital is 100,000 as a standard default
    assert res["equity_curve"][0] == 100000.0, "Initial equity value mismatch."
    
    # Additional checks for trade details if available in the result
    assert isinstance(res["trade_log"], list), "Trade log should be a list."
    if res["total_trades"] > 0:
        first_trade = res["trade_log"][0]
        assert "entry_timestamp" in first_trade, "Entry timestamp missing from trade log."
        assert "exit_timestamp" in first_trade, "Exit timestamp missing from trade log."
        assert "pnl" in first_trade, "PnL missing from trade log."