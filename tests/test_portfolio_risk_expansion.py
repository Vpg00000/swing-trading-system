"""
Unit and Integration Tests for Portfolio Risk, Margin & Tax Expansion (TASK-056 to TASK-060).
"""

import pytest
from engine.portfolio_optimizer import (
    calculate_sebi_margin_requirement,
    calculate_correlation_matrix_risk,
    run_monte_carlo_ruin_simulation,
)
from engine.tax_calculator import identify_tax_loss_harvesting_candidates
from engine.portfolio_manager import aggregate_multi_account_portfolios


def test_task056_sebi_margin_requirement_calculator():
    positions = [
        {"symbol": "RELIANCE", "quantity": 100, "price": 2500.0, "type": "EQUITY_DELIVERY"},
        {"symbol": "INFY_FUT", "quantity": 400, "price": 1500.0, "type": "INTRADAY_FUTURES"},
    ]
    res = calculate_sebi_margin_requirement(positions, pledged_collateral_inr=500_000.0, cash_balance_inr=500_000.0)

    assert res["total_available_margin_inr"] == 900_000.0  # 500k cash + 400k haircut collateral
    assert res["total_margin_used_inr"] == 370_000.0       # 250k delivery + 120k futures margin
    assert res["free_margin_inr"] == 530_000.0
    assert res["margin_call_triggered"] is False


def test_task057_pairwise_correlation_matrix_risk():
    symbol_returns = {
        "STOCK_A": [0.01, 0.02, -0.01, 0.03, 0.01],
        "STOCK_B": [0.012, 0.019, -0.009, 0.029, 0.011],  # Highly correlated
        "STOCK_C": [-0.02, 0.01, 0.03, -0.01, 0.005],     # Uncorrelated / Negatively correlated
    }
    res = calculate_correlation_matrix_risk(symbol_returns, max_avg_correlation_threshold=0.60)
    assert "avg_pairwise_correlation" in res
    assert isinstance(res["correlation_matrix"], dict)


def test_task058_tax_loss_harvesting_candidates():
    holdings = [
        {"symbol": "TCS", "quantity": 10, "buy_price": 4000.0, "current_price": 3500.0, "holding_days": 120}, # Loss ₹5,000
        {"symbol": "INFY", "quantity": 20, "buy_price": 1200.0, "current_price": 1500.0, "holding_days": 60},  # Gain ₹6,000
    ]
    res = identify_tax_loss_harvesting_candidates(holdings, realized_stcg_gains_inr=10000.0, stcg_tax_rate=0.20)

    assert res["candidate_count"] == 1
    assert res["total_harvestable_loss_inr"] == 5000.0
    assert res["estimated_total_tax_savings_inr"] == 1000.0  # 20% of ₹5,000


def test_task059_multi_account_portfolio_aggregator():
    acc1 = {"account_name": "DHAN_PRIMARY", "cash": 200000.0, "holdings": [{"symbol": "SBIN", "quantity": 100, "price": 600.0}]}
    acc2 = {"account_name": "ZERODHA_SECONDARY", "cash": 300000.0, "holdings": [{"symbol": "SBIN", "quantity": 50, "price": 600.0}]}

    res = aggregate_multi_account_portfolios([acc1, acc2])
    assert res["account_count"] == 2
    assert res["total_cash_inr"] == 500000.0
    assert res["unique_symbols_count"] == 1
    assert res["holdings"][0]["quantity"] == 150


def test_task060_monte_carlo_ruin_simulator():
    res = run_monte_carlo_ruin_simulation(initial_capital_inr=1_000_000.0, num_simulations=500, trades_per_simulation=50)

    assert res["num_simulations"] == 500
    assert 0.0 <= res["ruin_probability_pct"] <= 100.0
    assert res["expected_final_capital_inr"] > 0
    assert res["status"] in ["PASS", "WARNING"]
