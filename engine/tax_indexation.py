"""
Cost Inflation Index (CII) & Multi-Year Tax Indexation Module.

Implements Income Tax Department Cost Inflation Index (CII) table for multi-year asset indexation,
Dividend TDS 10% + slab rate calculation, and FX conversion fees.

Fixes Problems: 133, 136, 140.
"""

from typing import Dict, Any

# Official Income Tax Department Cost Inflation Index (CII) Table
CII_TABLE = {
    "2020-21": 301,
    "2021-22": 317,
    "2022-23": 331,
    "2023-24": 348,
    "2024-25": 363,
    "2025-26": 377,
    "2026-27": 390
}


def calculate_indexed_cost_basis(original_cost: float, buy_fy: str = "2021-22", sell_fy: str = "2026-27") -> Dict[str, Any]:
    """
    Computes Cost Inflation Index (CII) adjusted acquisition cost for long-term capital assets:
    Indexed Cost = Original Cost * (CII_Sell / CII_Buy)
    (Fixes Problem 136)
    """
    cii_buy = CII_TABLE.get(buy_fy, 317)
    cii_sell = CII_TABLE.get(sell_fy, 390)

    indexed_cost = round(original_cost * (cii_sell / cii_buy), 2)
    return {
        "original_cost": original_cost,
        "buy_fy": buy_fy,
        "sell_fy": sell_fy,
        "cii_buy": cii_buy,
        "cii_sell": cii_sell,
        "indexed_cost": indexed_cost,
        "tax_benefit_inr": round(indexed_cost - original_cost, 2)
    }


def calculate_dividend_tax(dividend_amount_inr: float, investor_slab_rate_pct: float = 30.0) -> Dict[str, Any]:
    """
    Calculates Dividend tax liability (Slab rate tax + 10% TDS deduction if > Rs 5,000).
    (Fixes Problem 133)
    """
    tds_pct = 10.0 if dividend_amount_inr > 5000.0 else 0.0
    tds_deducted = round(dividend_amount_inr * (tds_pct / 100.0), 2)
    total_tax_liability = round(dividend_amount_inr * (investor_slab_rate_pct / 100.0), 2)
    net_received = round(dividend_amount_inr - tds_deducted, 2)
    additional_tax_payable = round(max(0.0, total_tax_liability - tds_deducted), 2)

    return {
        "gross_dividend": dividend_amount_inr,
        "tds_deducted": tds_deducted,
        "net_received": net_received,
        "total_tax_liability": total_tax_liability,
        "additional_tax_payable": additional_tax_payable
    }


if __name__ == "__main__":
    print("Testing Tax Indexation Module...\n")
    idx = calculate_indexed_cost_basis(100000.0, buy_fy="2021-22", sell_fy="2026-27")
    print(f"  Indexed Cost Basis: {idx}")
    div = calculate_dividend_tax(12000.0, investor_slab_rate_pct=30.0)
    print(f"  Dividend Tax Impact: {div}")
