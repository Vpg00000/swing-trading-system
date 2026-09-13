import pytest
from engine.tax_calculator import TaxCalculator

def test_tax_calculator_stcg():
    calc = TaxCalculator()
    trades = [
        {"pnl": 10000, "holding_days": 100},
        {"pnl": -2000, "holding_days": 50}
    ]
    liability = calc.calculate_tax_liability(realized_trades=trades)
    assert liability["net_stcg_gain_inr"] == 8000
    assert liability["stcg_tax_liability_inr"] == 1600 # 20% of 8000

def test_tax_calculator_ltcg_below_exemption():
    calc = TaxCalculator()
    trades = [
        {"pnl": 100000, "holding_days": 400}
    ]
    liability = calc.calculate_tax_liability(realized_trades=trades)
    assert liability["net_ltcg_gain_inr"] == 100000
    assert liability["taxable_ltcg_gain_inr"] == 0
    assert liability["ltcg_tax_liability_inr"] == 0

def test_tax_calculator_ltcg_above_exemption():
    calc = TaxCalculator()
    trades = [
        {"pnl": 200000, "holding_days": 400}
    ]
    liability = calc.calculate_tax_liability(realized_trades=trades)
    assert liability["net_ltcg_gain_inr"] == 200000
    assert liability["taxable_ltcg_gain_inr"] == 75000 # 200000 - 125000
    assert liability["ltcg_tax_liability_inr"] == 9375 # 12.5% of 75000

def test_tax_loss_harvesting():
    calc = TaxCalculator()
    holdings = [
        {"symbol": "TCS", "quantity": 10, "buy_price": 4000, "current_price": 3500, "holding_days": 100},
        {"symbol": "INFY", "quantity": 10, "buy_price": 1500, "current_price": 1200, "holding_days": 400}
    ]
    res = calc.calculate_tax_loss_harvesting(holdings=holdings)
    assert res["total_harvestable_stcg_loss_inr"] == 5000
    assert res["total_harvestable_ltcg_loss_inr"] == 3000
    assert res["estimated_total_tax_savings_inr"] == (5000 * 0.20) + (3000 * 0.125)
