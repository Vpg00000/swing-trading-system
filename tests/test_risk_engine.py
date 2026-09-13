"""
Unit tests for engine/risk_engine.py (Task T-274).
Tests VaR, CVaR, Stress Testing, Kill-Switch, Single-Stock Guard, Sector Concentration Guard,
Circuit Breaker, and Margin Call De-leveraging.
"""

import pytest
import numpy as np
from engine.risk_engine import (
    calculate_var,
    calculate_cvar,
    run_stress_test,
    check_drawdown_kill_switch,
    check_single_stock_position_limit,
    check_sector_concentration_limit,
    check_daily_loss_circuit_breaker,
    check_circuit_proximity,
    evaluate_margin_call_and_deleverage,
    evaluate_full_portfolio_risk
)


def test_calculate_var():
    # Synthetic normal returns with mean 0.001 and std 0.02
    np.random.seed(42)
    returns = np.random.normal(0.001, 0.02, 500).tolist()

    res_hist = calculate_var(returns, confidence_level=0.95, method="historical", portfolio_value=1000000.0)
    assert res_hist["var_pct"] > 0.0
    assert res_hist["var_amount"] > 0.0
    assert res_hist["metrics_summary"]["historical_var_95_pct"] > 0
    assert res_hist["metrics_summary"]["historical_var_99_pct"] >= res_hist["metrics_summary"]["historical_var_95_pct"]

    res_param = calculate_var(returns, confidence_level=0.95, method="parametric", portfolio_value=1000000.0)
    assert res_param["var_pct"] > 0.0
    assert res_param["metrics_summary"]["parametric_var_99_pct"] >= res_param["metrics_summary"]["parametric_var_95_pct"]


def test_calculate_cvar():
    returns = [-0.05, -0.04, -0.03, -0.02, -0.01, 0.0, 0.01, 0.02, 0.03, 0.04]
    cvar_res = calculate_cvar(returns, confidence_level=0.90, portfolio_value=100000.0)

    assert cvar_res["cvar_pct"] > cvar_res["var_threshold_pct"]
    assert cvar_res["cvar_amount"] > 0.0
    assert cvar_res["tail_sample_count"] > 0


def test_run_stress_test():
    positions = [
        {"symbol": "RELIANCE", "sector": "ENERGY", "position_value": 300000.0, "beta": 1.1},
        {"symbol": "HDFCBANK", "sector": "FINANCIALS", "position_value": 400000.0, "beta": 1.2},
        {"symbol": "INFY", "sector": "TECHNOLOGY", "position_value": 300000.0, "beta": 0.9}
    ]

    corona_res = run_stress_test(positions, total_portfolio_value=1000000.0, scenario_key="corona_2020")
    assert corona_res["projected_drawdown_pct"] > 15.0
    assert corona_res["post_stress_portfolio_value"] < 1000000.0
    assert len(corona_res["position_details"]) == 3

    lehman_res = run_stress_test(positions, total_portfolio_value=1000000.0, scenario_key="lehman_2008")
    assert lehman_res["projected_drawdown_pct"] > corona_res["projected_drawdown_pct"]


def test_check_drawdown_kill_switch():
    normal = check_drawdown_kill_switch(current_portfolio_value=950000.0, peak_portfolio_value=1000000.0, max_drawdown_limit_pct=15.0)
    assert not normal["kill_switch_triggered"]
    assert normal["status"] == "ACTIVE"

    halted = check_drawdown_kill_switch(current_portfolio_value=800000.0, peak_portfolio_value=1000000.0, max_drawdown_limit_pct=15.0)
    assert halted["kill_switch_triggered"]
    assert halted["status"] == "HALTED"
    assert halted["action"] == "HALT_ALL_ALGOS_AND_CANCEL_ORDERS"


def test_check_single_stock_position_limit():
    positions = [
        {"symbol": "TCS", "position_value": 120000.0},  # 12% > 10% limit
        {"symbol": "INFY", "position_value": 80000.0}    # 8% <= 10%
    ]
    res = check_single_stock_position_limit(positions, total_portfolio_value=1000000.0, max_weight_pct=10.0)
    assert not res["is_passed"]
    assert res["violation_count"] == 1
    assert res["violations"][0]["symbol"] == "TCS"


def test_check_sector_concentration_limit():
    positions = [
        {"symbol": "HDFCBANK", "sector": "FINANCIALS", "position_value": 200000.0},
        {"symbol": "ICICIBANK", "sector": "FINANCIALS", "position_value": 150000.0}, # Total Financials = 35% > 25% limit
        {"symbol": "TCS", "sector": "TECHNOLOGY", "position_value": 100000.0}
    ]
    res = check_sector_concentration_limit(positions, total_portfolio_value=1000000.0, max_sector_weight_pct=25.0)
    assert not res["is_passed"]
    assert res["violation_count"] == 1
    assert res["violations"][0]["sector"] == "FINANCIALS"


def test_check_daily_loss_circuit_breaker():
    normal = check_daily_loss_circuit_breaker(realized_daily_pnl=-10000, unrealized_daily_pnl=-5000, total_portfolio_value=1000000.0, max_daily_loss_pct=3.0)
    assert not normal["circuit_breaker_triggered"]
    assert normal["order_entry_enabled"]

    breached = check_daily_loss_circuit_breaker(realized_daily_pnl=-25000, unrealized_daily_pnl=-10000, total_portfolio_value=1000000.0, max_daily_loss_pct=3.0)
    assert breached["circuit_breaker_triggered"]
    assert not breached["order_entry_enabled"]


def test_evaluate_margin_call_and_deleverage():
    positions = [
        {"symbol": "RELIANCE", "position_value": 500000.0, "beta": 1.3, "unrealized_pnl": -20000, "qty": 200, "margin_required": 100000.0},
        {"symbol": "INFY", "position_value": 300000.0, "beta": 0.9, "unrealized_pnl": 5000, "qty": 150, "margin_required": 60000.0}
    ]

    safe = evaluate_margin_call_and_deleverage(total_equity=1000000.0, margin_used=500000.0, positions=positions)
    assert safe["alert_level"] == "SAFE"

    critical = evaluate_margin_call_and_deleverage(total_equity=1000000.0, margin_used=960000.0, positions=positions)
    assert critical["alert_level"] == "CRITICAL_AUTO_DELEVERAGE"
    assert critical["auto_deleverage_triggered"]
    assert len(critical["deleveraging_plan"]) > 0
    assert critical["deleveraging_plan"][0]["symbol"] == "RELIANCE"


def test_evaluate_full_portfolio_risk():
    positions = [
        {"symbol": "RELIANCE", "sector": "ENERGY", "position_value": 80000.0, "beta": 1.1},
        {"symbol": "TCS", "sector": "TECHNOLOGY", "position_value": 70000.0, "beta": 0.9}
    ]
    res = evaluate_full_portfolio_risk(
        positions=positions,
        total_equity=1000000.0,
        peak_equity=1050000.0,
        realized_daily_pnl=2000.0,
        unrealized_daily_pnl=5000.0,
        margin_used=200000.0,
        historical_returns=[0.01, -0.005, 0.02, -0.015, 0.005]
    )

    assert res["overall_status"] == "HEALTHY"
    assert "var" in res
    assert "cvar" in res
    assert "stress_test" in res
    assert "kill_switch" in res


def test_check_circuit_proximity():
    # Test safe middle price
    safe = check_circuit_proximity("COALINDIA.NS", price=105.0, prev_close=100.0, circuit_limit_pct=10.0, buffer_pct=1.0)
    assert safe["status"] == "PASSED"
    assert not safe["is_near_circuit"]
    assert safe["order_entry_allowed"]

    # Test near upper circuit (110 is upper circuit for 10% limit)
    near_upper = check_circuit_proximity("COALINDIA.NS", price=109.5, prev_close=100.0, circuit_limit_pct=10.0, buffer_pct=1.0)
    assert near_upper["is_near_upper_circuit"]
    assert near_upper["is_near_circuit"]
    assert not near_upper["order_entry_allowed"]

    # Test near lower circuit (90 is lower circuit for 10% limit)
    near_lower = check_circuit_proximity("COALINDIA.NS", price=90.5, prev_close=100.0, circuit_limit_pct=10.0, buffer_pct=1.0)
    assert near_lower["is_near_lower_circuit"]
    assert near_lower["is_near_circuit"]
    assert "Stop-loss execution may fail" in near_lower["warning"]

