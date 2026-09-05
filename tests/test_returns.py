"""
tests/test_returns.py — Unit tests for TASK-018: Net Return Calculation.

Verifies mathematical accuracy of transaction costs (STT, brokerage, exchange charges,
stamp duty, GST, SEBI fee, slippage), capital gains tax (STCG/LTCG), gross-to-net bridge,
and zero hardcoded values via custom configuration overrides.
"""

import pytest
from engine.returns import (
    TaxAndCostConfig,
    calculate_transaction_costs,
    calculate_capital_gains_tax,
    calculate_net_return,
    calculate_expected_net_return,
)
from engine.tax_calculator import calculate_net_return as calculate_net_return_alias


def test_dhan_zero_brokerage_delivery_costs():
    """Verify delivery costs using default Dhan brokerage (₹0)."""
    cfg = TaxAndCostConfig()
    costs = calculate_transaction_costs(
        symbol="TATASTEEL",
        buy_price=150.0,
        sell_price=160.0,
        quantity=1000,
        config=cfg,
    )

    buy_val = 150.0 * 1000  # ₹1,50,000
    sell_val = 160.0 * 1000 # ₹1,60,000

    # STT: 0.1% buy + 0.1% sell
    expected_stt_buy = round(buy_val * 0.001, 2)
    expected_stt_sell = round(sell_val * 0.001, 2)
    assert costs.stt_buy_inr == expected_stt_buy
    assert costs.stt_sell_inr == expected_stt_sell
    assert costs.total_stt_inr == expected_stt_buy + expected_stt_sell

    # Brokerage: ₹0
    assert costs.brokerage_inr == 0.0

    # Stamp duty: 0.015% on buy
    assert costs.stamp_duty_inr == round(buy_val * 0.00015, 2)

    # Exchange charges: 0.00297% on total turnover
    turnover = buy_val + sell_val
    expected_exchange = round(turnover * 0.0000297, 2)
    assert costs.exchange_charges_inr == expected_exchange

    # GST: 18% on exchange charges (since brokerage is 0)
    assert costs.gst_inr == round(expected_exchange * 0.18, 2)


def test_custom_brokerage_and_gst():
    """Verify costs with non-zero brokerage rate and verify GST is 18% of (brokerage + exchange)."""
    cfg = TaxAndCostConfig(
        brokerage_per_order=20.0,
        brokerage_pct=0.0005,  # 0.05%
        gst_rate=0.18,
    )
    costs = calculate_transaction_costs(
        symbol="INFY",
        buy_price=1000.0,
        sell_price=1100.0,
        quantity=100,
        config=cfg,
    )

    buy_val = 1000.0 * 100
    sell_val = 1100.0 * 100
    expected_brokerage = (20.0 + buy_val * 0.0005) + (20.0 + sell_val * 0.0005)
    assert costs.brokerage_inr == round(expected_brokerage, 2)

    expected_gst = (costs.brokerage_inr + costs.exchange_charges_inr) * 0.18
    assert abs(costs.gst_inr - round(expected_gst, 2)) <= 0.01


def test_stcg_tax_under_365_days():
    """Short-term capital gains tax (holding < 365 days) @ 20%."""
    cfg = TaxAndCostConfig(stcg_rate=0.20)
    tax = calculate_capital_gains_tax(
        gross_gain_inr=10000.0,
        holding_days=180,
        deductible_expenses_inr=500.0,
        config=cfg,
    )

    assert tax.is_ltcg is False
    assert tax.tax_type == "STCG"
    assert tax.taxable_gain_inr == 9500.0
    assert tax.tax_rate == 0.20
    assert tax.tax_inr == 1900.0  # 20% of 9500


def test_ltcg_tax_over_365_days_exemption():
    """Long-term capital gains tax (holding >= 365 days) @ 12.5% above ₹1.25L exemption."""
    cfg = TaxAndCostConfig(ltcg_rate=0.125, ltcg_exemption_annual_inr=125_000.0)

    # Case A: Gain below exemption limit
    tax_below = calculate_capital_gains_tax(
        gross_gain_inr=100_000.0,
        holding_days=400,
        config=cfg,
    )
    assert tax_below.is_ltcg is True
    assert tax_below.tax_type == "LTCG"
    assert tax_below.ltcg_exemption_applied_inr == 100_000.0
    assert tax_below.taxable_gain_inr == 0.0
    assert tax_below.tax_inr == 0.0

    # Case B: Gain above exemption limit
    tax_above = calculate_capital_gains_tax(
        gross_gain_inr=200_000.0,
        holding_days=400,
        deductible_expenses_inr=0.0,
        config=cfg,
        ltcg_exemption_used_inr=0.0,
    )
    assert tax_above.is_ltcg is True
    assert tax_above.ltcg_exemption_applied_inr == 125_000.0
    assert tax_above.taxable_gain_inr == 75_000.0
    assert tax_above.tax_inr == round(75_000.0 * 0.125, 2)  # 9,375.00


def test_loss_trade_zero_tax():
    """Loss trades pay zero capital gains tax."""
    res = calculate_net_return(
        symbol="RELIANCE",
        buy_price=2500.0,
        sell_price=2300.0,  # Loss of ₹200/share
        quantity=50,
        holding_days=30,
    )

    assert res.gross_profit_inr == -10000.0
    assert res.tax.tax_inr == 0.0
    assert res.tax.tax_type == "NONE"
    assert res.net_profit_inr < res.gross_profit_inr  # Costs make net loss larger than gross loss


def test_gross_to_net_bridge_correctness():
    """Verify gross to net bridge components and mathematical identity."""
    res = calculate_net_return(
        symbol="HDFCBANK",
        buy_price=1600.0,
        sell_price=1800.0,
        quantity=100,
        holding_days=90,
    )

    # Mathematical identity: Net Profit = Gross Profit - Total Costs - Tax
    expected_net = round(res.gross_profit_inr - res.transaction_costs.total_costs_inr - res.tax.tax_inr, 2)
    assert res.net_profit_inr == expected_net

    # Check bridge structure
    assert len(res.gross_to_net_bridge) >= 10
    bridge_dict = {item["step"]: item["amount_inr"] for item in res.gross_to_net_bridge}
    assert "Gross Profit" in bridge_dict
    assert "STT (Securities Transaction Tax)" in bridge_dict
    assert "Net Realized Profit" in bridge_dict
    assert bridge_dict["Net Realized Profit"] == res.net_profit_inr


def test_zero_hardcoded_values_custom_config():
    """Verify that calculations strictly honor dynamic custom tax and fee configurations."""
    custom_cfg = TaxAndCostConfig(
        stt_delivery_buy_rate=0.002,   # 0.2%
        stt_delivery_sell_rate=0.002,  # 0.2%
        stcg_rate=0.15,               # 15% custom rate
        gst_rate=0.12,                # 12% custom GST
        stamp_duty_buy_rate=0.0002,   # 0.02%
    )

    res = calculate_net_return(
        symbol="TESTCO",
        buy_price=500.0,
        sell_price=600.0,
        quantity=200,
        holding_days=100,
        config=custom_cfg,
    )

    # Verify custom STT rate was used
    buy_val = 500.0 * 200  # ₹1,00,000
    sell_val = 600.0 * 200 # ₹1,20,000
    assert res.transaction_costs.stt_buy_inr == round(buy_val * 0.002, 2)
    assert res.transaction_costs.stt_sell_inr == round(sell_val * 0.002, 2)

    # Verify custom STCG rate was used (15%)
    assert res.tax.tax_rate == 0.15


def test_alias_import():
    """Verify that importing from engine.tax_calculator yields exact same functionality."""
    res = calculate_net_return_alias(
        symbol="SBIN",
        buy_price=800.0,
        sell_price=850.0,
        quantity=100,
        holding_days=50,
    )
    assert res.symbol == "SBIN"
    assert res.gross_profit_inr == 5000.0


def test_expected_net_return_screening():
    """Verify estimated net return screening calculation for upside/downside."""
    screen = calculate_expected_net_return(
        expected_upside_pct=15.0,
        expected_downside_pct=5.0,
        holding_days=60,
    )

    assert screen["gross_upside_pct"] == 15.0
    assert screen["net_upside_pct"] < 15.0
    assert screen["net_downside_pct"] > 5.0
