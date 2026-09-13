"""
Unit Tests for Benchmark Comparison & Comprehensive Verification (Phase 6 Task D).

Tests:
1. BenchmarkOverlayEngine class (fetching data, metric calculations).
2. Alpha, Beta, Tracking Error, Information Ratio, Treynor Ratio, and Outperformance %.
3. compare_equity_with_benchmark helper function.
4. FastAPI GET/POST /api/backtest/benchmark API endpoints.
"""

import pytest
import numpy as np
from fastapi.testclient import TestClient

from engine.backtest import (
    BenchmarkOverlayEngine,
    compare_equity_with_benchmark,
    generate_benchmark_comparison_overlay,
)
from web_server import app

client = TestClient(app)


def test_benchmark_overlay_engine_fetch():
    """Verify BenchmarkOverlayEngine data fetching fallback mechanism."""
    engine_nifty50 = BenchmarkOverlayEngine(benchmark_symbol="^NSEI")
    df50 = engine_nifty50.fetch_benchmark_data(num_bars=50)
    assert not df50.empty
    assert "close" in df50.columns
    assert "date" in df50.columns
    assert len(df50) >= 50

    engine_nifty500 = BenchmarkOverlayEngine(benchmark_symbol="NIFTY500")
    df500 = engine_nifty500.fetch_benchmark_data(num_bars=50)
    assert not df500.empty
    assert "close" in df500.columns


def test_benchmark_overlay_metrics():
    """Verify calculation of Alpha, Beta, Tracking Error, Information Ratio, Treynor Ratio."""
    engine = BenchmarkOverlayEngine(benchmark_symbol="^NSEI", risk_free_rate=0.07)
    
    # 100 days strategy equity curve with steady positive growth
    np.random.seed(42)
    base = 100000.0
    returns = np.random.normal(0.001, 0.005, 100)
    equity_series = [base]
    for r in returns[1:]:
        equity_series.append(equity_series[-1] * (1.0 + r))

    res = engine.compare(strategy_equity=equity_series)

    assert res["benchmark_symbol"] == "^NSEI"
    assert "jensens_alpha" in res
    assert "beta" in res
    assert "tracking_error" in res
    assert "information_ratio" in res
    assert "treynor_ratio" in res
    assert "cumulative_outperformance_pct" in res
    assert "strategy_equity" in res
    assert "benchmark_equity" in res

    assert isinstance(res["jensens_alpha"], float)
    assert isinstance(res["beta"], float)
    assert isinstance(res["tracking_error"], float)
    assert res["tracking_error"] >= 0.0


def test_compare_equity_with_benchmark_helper():
    """Verify compare_equity_with_benchmark helper function for Nifty 50 and Nifty 500."""
    equity_series = [100000.0 + i * 300.0 for i in range(60)]

    # Nifty 50
    res50 = compare_equity_with_benchmark(equity_series, benchmark_symbol="^NSEI")
    assert res50["benchmark_symbol"] == "^NSEI"
    assert "jensens_alpha" in res50
    assert "beta" in res50
    assert "tracking_error" in res50

    # Nifty 500
    res500 = compare_equity_with_benchmark(equity_series, benchmark_symbol="NIFTY500")
    assert res500["benchmark_symbol"] in ["NIFTY500", "^CRSLDX"]
    assert "jensens_alpha" in res500
    assert "beta" in res500


def test_generate_benchmark_comparison_overlay_backwards_compatibility():
    """Verify backwards compatibility with generate_benchmark_comparison_overlay."""
    equity_series = [100000.0, 101000.0, 102500.0, 103000.0, 105000.0]
    res = generate_benchmark_comparison_overlay(equity_series, benchmark_symbol="NIFTY50")
    assert "strategy_equity" in res
    assert "benchmark_equity" in res
    assert "alpha_generated_pct" in res


def test_benchmark_api_endpoint_get():
    """Verify GET /api/backtest/benchmark endpoint."""
    response = client.get("/api/backtest/benchmark?benchmark_symbol=^NSEI")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "SUCCESS"
    assert "metrics" in data
    assert "jensens_alpha" in data["metrics"]
    assert "beta" in data["metrics"]
    assert "tracking_error" in data["metrics"]


def test_benchmark_api_endpoint_post():
    """Verify POST /api/backtest/benchmark endpoint with custom strategy equity series."""
    payload = {
        "equity_series": [100000.0 + i * 500.0 for i in range(50)],
        "benchmark_symbol": "NIFTY500",
        "dates": [f"2025-01-{i+1:02d}" for i in range(50)]
    }
    response = client.post("/api/backtest/benchmark", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "SUCCESS"
    assert data["metrics"]["beta"] is not None
    assert data["metrics"]["jensens_alpha"] is not None
    assert data["metrics"]["tracking_error"] is not None
    assert len(data["data"]["strategy_equity"]) == 50


def test_edge_case_short_equity_curve():
    """Verify graceful handling of short equity series."""
    res_short = compare_equity_with_benchmark([100000.0], benchmark_symbol="^NSEI")
    assert res_short["jensens_alpha"] == 0.0
    assert res_short["beta"] == 0.0
    assert res_short["tracking_error"] == 0.0
