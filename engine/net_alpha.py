"""
Net Alpha Engine — After-tax net return calculator.

Chains:
  Gross Expected Upside %
  - Transaction Costs (Slippage, Brokerage, STT, Exchange fees)
  - Tax Liabilities (LTCG 12.5% vs STCG 20.0%)
  = Net Alpha % (true after-tax, after-cost expected return)

Usage:
    from engine.net_alpha import calculate_net_alpha
    net = calculate_net_alpha(gross_upside_pct=12.5, holding_days=45, capital_inr=100000)
"""

from dataclasses import dataclass
from typing import Dict, Any


@dataclass
class NetAlphaResult:
    gross_upside_pct: float
    slippage_pct: float
    stt_brokerage_pct: float
    total_cost_pct: float
    tax_rate_pct: float
    tax_type: str            # STCG (20%) or LTCG (12.5%)
    tax_impact_pct: float
    net_alpha_pct: float     # After cost and tax net return
    net_profit_inr: float    # ₹ net profit on capital


def calculate_net_alpha(
    gross_upside_pct: float,
    holding_days: int = 30,
    capital_inr: float = 100000.0,
    slippage_pct: float = 0.20,      # 0.20% entry/exit slippage
    stt_brokerage_pct: float = 0.15   # 0.10% STT + 0.05% brokerage/taxes
) -> NetAlphaResult:
    """
    Computes true after-cost, after-tax net return (Net Alpha).
    """
    total_cost_pct = slippage_pct + stt_brokerage_pct
    gross_after_cost = max(0.0, gross_upside_pct - total_cost_pct)

    # Tax rules: <365 days = STCG (20%), >=365 days = LTCG (12.5%)
    if holding_days >= 365:
        tax_type = "LTCG"
        tax_rate = 12.5
    else:
        tax_type = "STCG"
        tax_rate = 20.0

    tax_impact_pct = gross_after_cost * (tax_rate / 100.0)
    net_alpha_pct = round(gross_after_cost - tax_impact_pct, 2)
    net_profit_inr = round(capital_inr * (net_alpha_pct / 100.0), 2)

    return NetAlphaResult(
        gross_upside_pct=round(gross_upside_pct, 2),
        slippage_pct=round(slippage_pct, 2),
        stt_brokerage_pct=round(stt_brokerage_pct, 2),
        total_cost_pct=round(total_cost_pct, 2),
        tax_rate_pct=tax_rate,
        tax_type=tax_type,
        tax_impact_pct=round(tax_impact_pct, 2),
        net_alpha_pct=net_alpha_pct,
        net_profit_inr=net_profit_inr
    )


if __name__ == "__main__":
    print("Testing Net Alpha Engine...\n")
    res = calculate_net_alpha(gross_upside_pct=15.0, holding_days=45, capital_inr=250000.0)
    print(f"  Gross Upside:   +{res.gross_upside_pct}%")
    print(f"  Execution Cost: -{res.total_cost_pct}% (Slippage: {res.slippage_pct}%, STT/Tax: {res.stt_brokerage_pct}%)")
    print(f"  Tax Type:       {res.tax_type} ({res.tax_rate_pct}%) → -{res.tax_impact_pct}% impact")
    print(f"  NET ALPHA:      +{res.net_alpha_pct}%  (₹{res.net_profit_inr:,} net profit on ₹2.5L)")
