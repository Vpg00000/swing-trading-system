"""
Unit tests for Phase 6 Task B: Walk-Forward Strategy Parameter Optimizer.

Verifies:
1. WalkForwardOptimizer sliding window logic (in-sample train vs out-of-sample test).
2. Parameter grid optimization across EMA periods, RSI bounds, stop loss ATR multiplier.
3. In-Sample vs Out-of-Sample Efficiency Ratio computation.
4. FastAPI POST /api/backtest/walk-forward endpoint integration.
"""

import pytest
import pandas as pd
import numpy as np
from fastapi.testclient import TestClient

from engine.backtest import (
    WalkForwardOptimizer,
    run_walk_forward_optimization,
    default_parameterized_strategy_factory,
)
from web_server import app


@pytest.fixture
def sample_price_df():
    """Generates 250 bars of synthetic OHLCV daily data."""
    np.random.seed(42)
    n_bars = 250
    dates = pd.date_range(start="2024-01-01", periods=n_bars, freq="B")
    returns = np.random.normal(0.0008, 0.012, n_bars)
    prices = 500.0 * np.exp(np.cumsum(returns))

    return pd.DataFrame({
        "date": dates,
        "open": prices * (1.0 - np.random.uniform(0, 0.003, n_bars)),
        "high": prices * (1.0 + np.random.uniform(0.001, 0.008, n_bars)),
        "low": prices * (1.0 - np.random.uniform(0.001, 0.008, n_bars)),
        "close": prices,
        "volume": np.random.randint(50000, 200000, n_bars),
    })


def test_walk_forward_optimizer_sliding_window(sample_price_df):
    """Verifies sliding window creation, optimization execution, and metric reporting."""
    optimizer = WalkForwardOptimizer(
        historical_data=sample_price_df,
        in_sample_bars=100,
        out_sample_bars=30,
        step_bars=30,
        param_grid={
            "ema_fast": [5, 10],
            "ema_slow": [20, 30],
            "rsi_upper": [70],
            "rsi_lower": [30],
            "stop_loss_atr_mult": [2.0],
        }
    )

    results = optimizer.optimize()

    assert results["status"] == "SUCCESS"
    assert results["windows_evaluated"] > 0
    assert "efficiency_ratio" in results
    assert "in_sample_sharpe" in results
    assert "out_of_sample_sharpe" in results
    assert "overall_best_params" in results
    assert isinstance(results["is_robust"], bool)

    # Check window metrics
    for win in results["windows"]:
        assert "is_range" in win
        assert "oos_range" in win
        assert "best_params" in win
        assert "is_sharpe" in win
        assert "oos_sharpe" in win


def test_walk_forward_parameter_selection(sample_price_df):
    """Verifies parameter selection grid search across EMA fast/slow, RSI, and ATR stop-loss."""
    param_grid = {
        "ema_fast": [10, 15],
        "ema_slow": [25, 35],
        "rsi_upper": [65, 75],
        "rsi_lower": [25, 35],
        "stop_loss_atr_mult": [1.5, 2.5],
    }

    res = run_walk_forward_optimization(
        sample_price_df,
        param_grid=param_grid,
        in_sample_bars=120,
        out_sample_bars=40,
    )

    assert res["status"] == "SUCCESS"
    assert res["param_grid_size"] == 2 * 2 * 2 * 2 * 2  # 32 combinations
    assert "ema_fast" in res["overall_best_params"]
    assert "ema_slow" in res["overall_best_params"]
    assert "stop_loss_atr_mult" in res["overall_best_params"]


def test_walk_forward_api_endpoint():
    """Verifies POST /api/backtest/walk-forward endpoint using FastAPI TestClient."""
    client = TestClient(app)

    payload = {
        "symbol": "TATASTEEL",
        "in_sample_bars": 100,
        "out_sample_bars": 30,
        "param_grid": {
            "ema_fast": [5, 10],
            "ema_slow": [20, 30],
            "rsi_upper": [70],
            "rsi_lower": [30],
            "stop_loss_atr_mult": [2.0],
        }
    }

    response = client.post("/api/backtest/walk-forward", json=payload)
    assert response.status_code == 200

    data = response.json()
    assert data["status"] == "SUCCESS"
    assert data["symbol"] == "TATASTEEL"
    assert "efficiency_ratio" in data
    assert "in_sample_sharpe" in data
    assert "out_of_sample_sharpe" in data
    assert "is_robust" in data
    assert "overall_best_params" in data
    assert data["windows_evaluated"] > 0
