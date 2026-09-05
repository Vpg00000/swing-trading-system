"""
tests/test_position_sizing.py — Unit tests for TASK-020: Position Sizing Engine.

Verifies exact quantity, investment INR, max loss INR calculations and bottleneck enforcement
under account risk, single position cap, sector cap, Kelly, drawdown stop, and volume limits.
"""

import pytest
from engine.portfolio_optimizer import (
    RiskConfig,
    PositionSizeResult,
    calculate_position_size,
    calculate_kelly_position_size,
)


def test_position_sizing_account_risk_bottleneck():
    """
    Capital = ₹10,00,000, 1% risk = ₹10,000 max loss.
    Entry = ₹500, Stop = ₹450 -> Risk per share = ₹50.
    Expected shares by account risk = 10,000 / 50 = 200 shares (₹1,00,000 investment = 10% capital < 15% cap).
    Bottleneck should be ACCOUNT_RISK.
    """
    res = calculate_position_size(
        symbol="TATASTEEL.NS",
        entry_price=500.0,
        stop_loss_price=450.0,
        total_capital_inr=1_000_000.0,
    )

    assert res.is_allowed is True
    assert res.quantity == 200
    assert res.investment_inr == 100_000.0
    assert res.max_loss_inr == 10_000.0
    assert res.position_pct == 10.0
    assert res.max_loss_pct == 1.0
    assert res.sizing_bottleneck == "ACCOUNT_RISK"


def test_position_sizing_position_cap_bottleneck():
    """
    Capital = ₹10,00,000, 1% risk = ₹10,000. 15% position cap = ₹1,50,000.
    Entry = ₹100, Stop = ₹99 -> Risk per share = ₹1.
    Account risk would allow 10,000 shares (₹10,00,000 investment), but position cap limits to ₹1,50,000 / ₹100 = 1,500 shares.
    Bottleneck should be POSITION_CAP.
    """
    res = calculate_position_size(
        symbol="PENNY.NS",
        entry_price=100.0,
        stop_loss_price=99.0,
        total_capital_inr=1_000_000.0,
    )

    assert res.is_allowed is True
    assert res.quantity == 1500
    assert res.investment_inr == 150_000.0
    assert res.position_pct == 15.0
    assert res.max_loss_inr == 1500.0  # 1500 shares * ₹1
    assert res.sizing_bottleneck == "POSITION_CAP"


def test_position_sizing_sector_cap_bottleneck():
    """
    Capital = ₹10,00,000. Sector cap = 20% (₹2,00,000). Existing sector exposure = ₹1,80,000.
    Remaining sector capacity = ₹20,000.
    Entry = ₹1000, Stop = ₹900 (Risk/share = ₹100).
    Account risk allows 100 shares (₹1,00,000), but remaining sector cap limits to ₹20,000 / ₹1000 = 20 shares.
    Bottleneck should be SECTOR_CAP.
    """
    res = calculate_position_size(
        symbol="IT_STOCK.NS",
        entry_price=1000.0,
        stop_loss_price=900.0,
        total_capital_inr=1_000_000.0,
        current_sector_exposure_inr=180_000.0,
    )

    assert res.is_allowed is True
    assert res.quantity == 20
    assert res.investment_inr == 20_000.0
    assert res.sizing_bottleneck == "SECTOR_CAP"


def test_position_sizing_drawdown_limit_blocking():
    """
    When current drawdown reaches/exceeds max_drawdown_limit_pct (15%),
    new trade creation is strictly BLOCKED (quantity = 0, is_allowed = False).
    """
    res = calculate_position_size(
        symbol="INFY.NS",
        entry_price=1500.0,
        stop_loss_price=1400.0,
        total_capital_inr=1_000_000.0,
        current_drawdown_pct=16.0,  # 16% > 15% limit
    )

    assert res.is_allowed is False
    assert res.quantity == 0
    assert res.sizing_bottleneck == "DRAWDOWN_LIMIT"
    assert any("Drawdown" in r for r in res.blocking_reasons)


def test_position_sizing_kelly_constraint():
    """
    Fractional Kelly criterion capping position size when win rate and win/loss ratio are given.
    Win rate = 55%, Win/Loss = 1.2 -> Kelly fraction = 0.5 * (0.55*1.2 - 0.45)/1.2 = 0.0875 (8.75%).
    Entry = ₹1000, Stop = ₹990.
    Account risk allows 1000 shares (₹10L), but Kelly caps at 87 shares (₹87,000).
    """
    res = calculate_position_size(
        symbol="KELLY_TEST.NS",
        entry_price=1000.0,
        stop_loss_price=990.0,
        total_capital_inr=1_000_000.0,
        win_rate=0.55,
        win_loss_ratio=1.2,
    )

    assert res.is_allowed is True
    assert res.sizing_bottleneck == "KELLY"
    assert res.position_pct <= 9.0


def test_position_sizing_liquidity_cap():
    """Average daily volume cap (5% of ADV)."""
    res = calculate_position_size(
        symbol="ILLIQUID.NS",
        entry_price=100.0,
        stop_loss_price=90.0,
        total_capital_inr=10_000_000.0,
        avg_daily_volume_shares=1000.0,  # ADV = 1,000 shares -> 5% cap = 50 shares
    )

    assert res.is_allowed is True
    assert res.quantity == 50
    assert res.sizing_bottleneck == "LIQUIDITY"


def test_position_sizing_invalid_inputs():
    """Stop loss >= entry price or non-positive capital returns blocked result."""
    res_sl = calculate_position_size(
        symbol="BAD_SL.NS",
        entry_price=100.0,
        stop_loss_price=105.0,  # Invalid stop loss above entry
        total_capital_inr=1_000_000.0,
    )
    assert res_sl.is_allowed is False
    assert res_sl.quantity == 0
    assert res_sl.sizing_bottleneck == "INVALID_INPUT"

    res_cap = calculate_position_size(
        symbol="BAD_CAP.NS",
        entry_price=100.0,
        stop_loss_price=90.0,
        total_capital_inr=0.0,  # Invalid capital
    )
    assert res_cap.is_allowed is False
    assert res_cap.quantity == 0
    assert res_cap.sizing_bottleneck == "INVALID_INPUT"
