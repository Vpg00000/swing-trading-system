"""
Unit tests for Non-Linear Market Impact & Volume Friction Model (Phase 6 Task C).
Verifies MarketFrictionModel, square-root market impact formula, statutory tax calculations,
helper functions, and POST /api/backtest/friction endpoint.
"""

import pytest
import math
from fastapi.testclient import TestClient

from engine.backtest import MarketFrictionModel, calculate_trade_friction
from web_server import app


def test_square_root_market_impact():
    """Verify square-root law of market impact: Impact = gamma * volatility * sqrt(Order_Qty / Daily_Volume)."""
    model = MarketFrictionModel(gamma=0.5)

    order_qty = 1000
    daily_volume = 100000
    volatility = 0.02  # 2.0%

    impact = model.calculate_market_impact(order_qty, daily_volume, volatility)
    # Expected: 0.5 * 0.02 * sqrt(1000 / 100000) = 0.5 * 0.02 * sqrt(0.01) = 0.5 * 0.02 * 0.1 = 0.001 (0.1%)
    assert math.isclose(impact, 0.001, rel_tol=1e-5)

    # Test volatility as percentage (2.0 instead of 0.02)
    impact_pct_input = model.calculate_market_impact(order_qty, daily_volume, 2.0)
    assert math.isclose(impact_pct_input, 0.001, rel_tol=1e-5)


def test_non_linear_scaling():
    """Verify non-linear market impact scaling (quadrupling volume share doubles impact)."""
    model = MarketFrictionModel(gamma=0.5)

    impact_base = model.calculate_market_impact(1000, 100000, 0.02)
    impact_quad = model.calculate_market_impact(4000, 100000, 0.02)

    # sqrt(4000/100000) / sqrt(1000/100000) = sqrt(4) = 2.0
    assert math.isclose(impact_quad / impact_base, 2.0, rel_tol=1e-5)


def test_edge_cases_zero_volume_or_qty():
    """Verify market impact handles zero or negative volume/qty safely."""
    model = MarketFrictionModel(gamma=0.5)

    assert model.calculate_market_impact(0, 100000, 0.02) == 0.0
    assert model.calculate_market_impact(1000, 0, 0.02) == 0.0
    assert model.calculate_market_impact(1000, -500, 0.02) == 0.0


def test_statutory_tax_and_friction_breakdown():
    """Verify breakdown of statutory taxes (STT 0.1%, SEBI, GST 18%, Stamp Duty 0.015%)."""
    model = MarketFrictionModel(
        gamma=0.5,
        bid_ask_spread_pct=0.0005,
        brokerage=0.0,
        stt_rate=0.001,
        sebi_rate=0.000001,
        gst_rate=0.18,
        stamp_duty_rate=0.00015,
        exchange_rate=0.0000297,
    )

    order_qty = 1000
    price = 500.0
    trade_val = 500000.0  # 1000 * 500

    friction = model.calculate_friction(
        order_qty=order_qty,
        price=price,
        daily_volume=100000,
        volatility=0.02,
        side="BUY",
        gross_return_pct=5.0,
    )

    # STT @ 0.1% = ₹500
    assert math.isclose(friction["stt_inr"], 500.0, rel_tol=1e-3)
    # Stamp Duty @ 0.015% = ₹75
    assert math.isclose(friction["stamp_duty_inr"], 75.0, rel_tol=1e-3)
    # SEBI charges @ ₹10/Cr = ₹0.50
    assert math.isclose(friction["sebi_charges_inr"], 0.50, rel_tol=1e-3)
    # Exchange charges @ 0.00297% = ₹14.85
    assert math.isclose(friction["exchange_charges_inr"], 14.85, rel_tol=1e-3)

    # GST @ 18% on exchange + SEBI (14.85 + 0.50) * 0.18 = ₹2.76
    expected_gst = (14.85 + 0.50) * 0.18
    assert math.isclose(friction["gst_inr"], expected_gst, rel_tol=1e-2)

    # Total statutory tax sum
    expected_stat_tax = 500.0 + 75.0 + 0.50 + 14.85 + expected_gst
    assert math.isclose(friction["total_statutory_tax_inr"], expected_stat_tax, rel_tol=1e-2)

    # Net realized return = gross_return_pct - total_friction_pct
    expected_net_return = 5.0 - friction["total_friction_pct"]
    assert math.isclose(friction["net_realized_return_pct"], expected_net_return, rel_tol=1e-3)


def test_calculate_trade_friction_helper():
    """Verify helper function calculate_trade_friction."""
    friction = calculate_trade_friction(
        order_qty=500,
        price=200.0,
        daily_volume=50000,
        volatility=0.02,
        gross_return_pct=3.0,
    )

    assert "market_impact_pct" in friction
    assert "total_statutory_tax_inr" in friction
    assert "net_realized_return_pct" in friction
    assert friction["trade_value"] == 100000.0


def test_api_endpoint_post_friction():
    """Verify POST /api/backtest/friction endpoint via FastAPI TestClient."""
    client = TestClient(app)

    payload = {
        "order_qty": 1000,
        "price": 500.0,
        "daily_volume": 100000,
        "volatility": 0.02,
        "gamma": 0.5,
        "side": "BUY",
        "gross_return_pct": 5.0,
    }

    response = client.post("/api/backtest/friction", json=payload)
    assert response.status_code == 200

    data = response.json()
    assert data.get("status") == "SUCCESS"
    assert "data" in data or "friction_details" in data

    details = data.get("data") or data.get("friction_details")
    assert details["trade_value"] == 500000.0
    assert details["stt_inr"] == 500.0
    assert details["market_impact_pct"] > 0
    assert details["net_realized_return_pct"] < 5.0
