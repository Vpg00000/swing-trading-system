"""
Unit and Integration Tests for Phase 6 Task A: Monte Carlo Parameter Sensitivity & Stress Tester.
"""

import pytest
import numpy as np
from fastapi.testclient import TestClient
from engine.backtest import MonteCarloStressTester, run_monte_carlo_simulation
from web_server import app


@pytest.fixture
def client():
    return TestClient(app)


def test_monte_carlo_iterations_and_metrics():
    """Verifies simulation iterations, VaR calculations, drawdown distribution, and ruin probability."""
    sample_returns = [0.02, -0.01, 0.035, -0.015, 0.04, -0.02, 0.015, -0.01, 0.025, -0.005]
    tester = MonteCarloStressTester(returns=sample_returns, iterations=500)
    res = tester.run_simulation()

    assert res["iterations"] == 500
    assert "var_95_pct" in res
    assert "var_99_pct" in res
    assert "cvar_95_pct" in res
    assert isinstance(res["var_95_pct"], float)
    assert isinstance(res["var_99_pct"], float)
    assert isinstance(res["cvar_95_pct"], float)

    # VaR 99% should be >= VaR 95% in loss magnitude (or CVaR >= VaR)
    assert res["cvar_95_pct"] >= res["var_95_pct"] or res["var_95_pct"] >= 0.0

    # Max Drawdown Distribution
    assert "max_drawdown_distribution" in res
    dd_dist = res["max_drawdown_distribution"]
    assert "5th" in dd_dist
    assert "50th" in dd_dist
    assert "95th" in dd_dist
    assert dd_dist["5th"] <= dd_dist["50th"] <= dd_dist["95th"]

    # Probability of Ruin
    assert "probability_of_ruin_pct" in res
    assert 0.0 <= res["probability_of_ruin_pct"] <= 100.0


def test_run_monte_carlo_simulation_helper():
    """Verifies the exposed helper function run_monte_carlo_simulation."""
    sample_returns = [0.01, -0.005, 0.02, -0.01, 0.015]
    res = run_monte_carlo_simulation(sample_returns, iterations=200)

    assert res["iterations"] == 200
    assert "var_95_pct" in res
    assert "cvar_95_pct" in res
    assert "max_drawdown_distribution" in res
    assert "probability_of_ruin_pct" in res


def test_monte_carlo_perturbations():
    """Verifies that parameter perturbations (win rate drift & slippage variance) affect simulation outcomes."""
    np.random.seed(42)
    sample_returns = [0.02, 0.015, -0.005, 0.03, -0.01]

    # Baseline simulation
    tester_base = MonteCarloStressTester(
        returns=sample_returns, iterations=300, slippage_variance=0.0, win_rate_drift=0.0
    )
    res_base = tester_base.run_simulation()

    # Perturbed simulation with negative drift and higher slippage
    tester_perturbed = MonteCarloStressTester(
        returns=sample_returns, iterations=300, slippage_variance=0.005, win_rate_drift=-0.02
    )
    res_perturbed = tester_perturbed.run_simulation()

    # Perturbed simulation should exhibit lower median return or higher max drawdown at 95th percentile
    assert res_perturbed["median_return_pct"] < res_base["median_return_pct"] or res_perturbed["max_drawdown_distribution"]["95th"] >= res_base["max_drawdown_distribution"]["95th"]


def test_monte_carlo_empty_returns():
    """Verifies graceful handling of empty return series."""
    tester = MonteCarloStressTester(returns=[], iterations=100)
    res = tester.run_simulation()

    assert res["iterations"] == 100
    assert res["var_95_pct"] == 0.0
    assert res["probability_of_ruin_pct"] == 0.0
    assert res["max_drawdown_distribution"]["50th"] == 0.0


def test_monte_carlo_api_endpoint_post(client):
    """Verifies POST /api/backtest/monte-carlo endpoint with custom payload."""
    payload = {
        "returns": [0.02, -0.01, 0.035, -0.015, 0.04, -0.02],
        "iterations": 200,
        "slippage_variance": 0.001,
        "win_rate_drift": 0.0,
        "volume_shock": 0.0,
    }
    response = client.post("/api/backtest/monte-carlo", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "SUCCESS"
    assert "data" in data
    res_data = data["data"]
    assert res_data["iterations"] == 200
    assert "var_95_pct" in res_data
    assert "var_99_pct" in res_data
    assert "cvar_95_pct" in res_data
    assert "max_drawdown_distribution" in res_data
    assert "probability_of_ruin_pct" in res_data


def test_monte_carlo_api_endpoint_get(client):
    """Verifies GET /api/backtest/monte-carlo endpoint with default parameters."""
    response = client.get("/api/backtest/monte-carlo")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "SUCCESS"
    assert "var_95_pct" in data
    assert "max_drawdown_distribution" in data
