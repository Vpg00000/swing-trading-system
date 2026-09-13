"""
Unit tests for Portfolio P&L & Position Tracker (Phase 3 Task B).

Verifies:
- PositionTracker calculations (unrealized P&L, realized P&L, cost basis, daily change %, sector allocation %, Sharpe/Sortino ratios)
- Reconcile live holdings with orders & trades
- get_portfolio_summary() helper function
- FastAPI GET /api/portfolio endpoint output format and metrics
"""

import pytest
from fastapi.testclient import TestClient
from engine.position_tracker import PositionTracker, get_portfolio_summary
from web_server import app


@pytest.fixture
def sample_portfolio_data():
    holdings = [
        {
            "symbol": "RELIANCE",
            "quantity": 100,
            "cost_price": 2400.0,
            "current_price": 2500.0,
            "previous_close": 2450.0,
            "sector": "Energy"
        },
        {
            "symbol": "TCS",
            "quantity": 50,
            "cost_price": 3500.0,
            "current_price": 3400.0,
            "previous_close": 3450.0,
            "sector": "Technology"
        },
        {
            "symbol": "HDFCBANK",
            "quantity": 200,
            "cost_price": 1500.0,
            "current_price": 1600.0,
            "previous_close": 1580.0,
            "sector": "Financial Services"
        }
    ]

    trades = [
        {"symbol": "RELIANCE", "side": "BUY", "quantity": 100, "price": 2400.0},
        {"symbol": "TCS", "side": "BUY", "quantity": 50, "price": 3500.0},
        {"symbol": "HDFCBANK", "side": "BUY", "quantity": 200, "price": 1500.0},
        {"symbol": "INFY", "side": "BUY", "quantity": 50, "price": 1400.0},
        {"symbol": "INFY", "side": "SELL", "quantity": 50, "price": 1500.0}  # Closed trade: Realized P&L = +5000
    ]

    orders = [
        {"order_id": "ORD001", "symbol": "RELIANCE", "status": "FILLED", "quantity": 100, "price": 2400.0},
        {"order_id": "ORD002", "symbol": "ICICIBANK", "status": "PENDING", "quantity": 100, "price": 900.0}
    ]

    returns = [0.01, 0.015, -0.005, 0.02, -0.01, 0.008, 0.012, -0.003, 0.018, 0.005]

    return {
        "holdings": holdings,
        "trades": trades,
        "orders": orders,
        "returns": returns,
        "cash": 100000.0
    }


def test_position_tracker_pnl_calculations(sample_portfolio_data):
    tracker = PositionTracker(
        holdings=sample_portfolio_data["holdings"],
        trades=sample_portfolio_data["trades"],
        orders=sample_portfolio_data["orders"],
        cash=sample_portfolio_data["cash"],
        historical_returns=sample_portfolio_data["returns"]
    )

    # Cost Basis: (100*2400) + (50*3500) + (200*1500) = 240000 + 175000 + 300000 = 715000
    cost_basis = tracker.calculate_cost_basis()
    assert cost_basis == 715000.0

    # Holdings Current Value: (100*2500) + (50*3400) + (200*1600) = 250000 + 170000 + 320000 = 740000
    # Unrealized P&L: 740000 - 715000 = +25000
    unrealized_pnl, unrealized_pnl_pct = tracker.calculate_unrealized_pnl()
    assert unrealized_pnl == 25000.0
    assert round(unrealized_pnl_pct, 2) == round((25000.0 / 715000.0) * 100.0, 2)

    # Realized P&L from INFY buy 50@1400 sell 50@1500 = 50 * (1500 - 1400) = 5000
    realized_pnl = tracker.calculate_realized_pnl()
    assert realized_pnl == 5000.0

    # Daily Change P&L:
    # RELIANCE: 100 * (2500 - 2450) = +5000
    # TCS: 50 * (3400 - 3450) = -2500
    # HDFCBANK: 200 * (1600 - 1580) = +4000
    # Total Daily P&L = 5000 - 2500 + 4000 = +6500
    daily_pnl, daily_pct = tracker.calculate_daily_change()
    assert daily_pnl == 6500.0
    assert daily_pct > 0.0


def test_sector_allocation(sample_portfolio_data):
    tracker = PositionTracker(
        holdings=sample_portfolio_data["holdings"],
        cash=sample_portfolio_data["cash"]
    )
    sector_alloc = tracker.calculate_sector_allocation()

    # Total NAV = 740000 (holdings) + 100000 (cash) = 840000
    # Energy: 250000 / 840000 = 29.76%
    # Technology: 170000 / 840000 = 20.24%
    # Financial Services: 320000 / 840000 = 38.10%
    # Cash: 100000 / 840000 = 11.90%
    assert "Energy" in sector_alloc
    assert "Technology" in sector_alloc
    assert "Financial Services" in sector_alloc
    assert "Cash" in sector_alloc
    assert round(sum(sector_alloc.values()), 1) == 100.0


def test_sharpe_and_sortino_ratios(sample_portfolio_data):
    tracker = PositionTracker(
        historical_returns=sample_portfolio_data["returns"]
    )
    sharpe = tracker.calculate_sharpe_ratio()
    sortino = tracker.calculate_sortino_ratio()

    assert isinstance(sharpe, float)
    assert isinstance(sortino, float)
    assert sharpe > 0  # Mean return is positive in sample data
    assert sortino > 0


def test_reconciliation(sample_portfolio_data):
    tracker = PositionTracker(
        holdings=sample_portfolio_data["holdings"],
        trades=sample_portfolio_data["trades"],
        orders=sample_portfolio_data["orders"]
    )
    rec = tracker.reconcile_holdings_with_orders()

    assert "is_reconciled" in rec
    assert rec["is_reconciled"] is True
    assert rec["pending_orders_count"] == 1
    assert rec["total_executed_trades"] == 5


def test_reconciliation_discrepancy():
    holdings = [{"symbol": "RELIANCE", "quantity": 100}]
    trades = [{"symbol": "RELIANCE", "side": "BUY", "quantity": 80}]
    tracker = PositionTracker(holdings=holdings, trades=trades)
    rec = tracker.reconcile_holdings_with_orders()

    assert rec["is_reconciled"] is False
    assert len(rec["discrepancies"]) == 1
    assert rec["discrepancies"][0]["symbol"] == "RELIANCE"
    assert rec["discrepancies"][0]["discrepancy"] == 20.0


def test_get_portfolio_summary_helper(sample_portfolio_data):
    summary = get_portfolio_summary(
        holdings=sample_portfolio_data["holdings"],
        trades=sample_portfolio_data["trades"],
        orders=sample_portfolio_data["orders"],
        cash=sample_portfolio_data["cash"],
        historical_returns=sample_portfolio_data["returns"]
    )

    assert summary["total_value"] == 840000.0
    assert summary["total_cost_basis"] == 715000.0
    assert summary["unrealized_pnl"] == 25000.0
    assert summary["realized_pnl"] == 5000.0
    assert summary["daily_change_pnl"] == 6500.0
    assert len(summary["active_positions"]) == 3
    assert "sector_allocation" in summary
    assert "metrics" in summary
    assert "sharpe_ratio" in summary["metrics"]
    assert "sortino_ratio" in summary["metrics"]


def test_api_portfolio_endpoint():
    client = TestClient(app)
    response = client.get("/api/portfolio")
    assert response.status_code == 200

    data = response.json()
    assert isinstance(data, dict)
    assert "total_value" in data
    assert "total_cost_basis" in data
    assert "unrealized_pnl" in data
    assert "realized_pnl" in data
    assert "daily_change_pct" in data
    assert "active_positions" in data
    assert "sector_allocation" in data
    assert "metrics" in data
    assert "sharpe_ratio" in data["metrics"]
    assert "sortino_ratio" in data["metrics"]
    assert "reconciliation" in data
