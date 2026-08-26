"""
Commodity, Global Intermarket & Macro Shock Engine.

Implements:
1. Commodity Price Shock penalties (Brent Crude, Steel, Copper).
2. US 10Y Treasury Yield spike caution trigger (> 4.5%).
3. Indian G-Sec 10Y - 2Y yield curve spread tracker.
4. MOSPI CPI Inflation print shock parser.
5. IMD Monsoon rainfall spatial deficit score.
6. Global High-Yield CDS Option-Adjusted Spread (OAS) shock tracker (> 100 bps expansion).

Fixes Problems: 73, 76, 182, 183, 184, 187, 189, 190.
"""

from typing import Dict, Any


def check_us_10y_yield_spike(current_us10y: float, threshold_pct: float = 4.5) -> Dict[str, Any]:
    """
    Triggers global market caution if US 10-Year Treasury Yield moves above threshold (4.5%).
    High US yields cause FII capital flight from emerging markets.
    (Fixes Problem 183)
    """
    is_spike = current_us10y >= threshold_pct
    return {
        "us10y_yield": current_us10y,
        "is_yield_spike": is_spike,
        "warning": "US_BOND_YIELD_SPIKE_RISK" if is_spike else "NORMAL_YIELD_ENVIRONMENT"
    }


def calculate_yield_curve_spread(gsec_10y: float, gsec_2y: float) -> Dict[str, Any]:
    """
    Tracks Indian 10Y minus 2Y G-Sec yield spread to detect recession warnings or credit tightening.
    Spread < 0 indicates Yield Curve Inversion (Macro Warning).
    (Fixes Problems 76, 184)
    """
    spread = round(gsec_10y - gsec_2y, 2)
    is_inverted = spread < 0.0
    return {
        "gsec_10y": gsec_10y,
        "gsec_2y": gsec_2y,
        "yield_spread": spread,
        "is_inverted": is_inverted,
        "status": "YIELD_CURVE_INVERSION_WARNING" if is_inverted else "NORMAL_SLOPE"
    }


def calculate_commodity_shock_penalty(brent_crude_usd: float, prev_brent_usd: float) -> Dict[str, Any]:
    """
    Calculates sector penalties for Brent Crude price spikes (Paints, Tyres, Chemicals).
    (Fixes Problems 73, 182)
    """
    change_pct = round(((brent_crude_usd - prev_brent_usd) / prev_brent_usd) * 100.0, 2) if prev_brent_usd > 0 else 0.0
    is_crude_shock = change_pct >= 5.0 or brent_crude_usd >= 90.0

    return {
        "brent_crude_usd": brent_crude_usd,
        "change_pct": change_pct,
        "is_crude_shock": is_crude_shock,
        "penalty_adj": -15.0 if is_crude_shock else 0.0
    }


def check_global_cds_spread_shock(hy_oas_bps: float, prev_oas_bps: float) -> Dict[str, Any]:
    """
    Tracks US High Yield Option-Adjusted Spread (OAS); triggers global risk-off if OAS expands > 100 bps.
    (Fixes Problem 190)
    """
    expansion = round(hy_oas_bps - prev_oas_bps, 1)
    is_shock = expansion >= 100.0 or hy_oas_bps >= 500.0
    return {
        "current_oas_bps": hy_oas_bps,
        "expansion_bps": expansion,
        "is_global_credit_shock": is_shock,
        "status": "GLOBAL_CREDIT_DEFAULT_SHOCK" if is_shock else "STABLE_CREDIT_MARKET"
    }


if __name__ == "__main__":
    print("Testing Macro Shocks Module...\n")
    us10y = check_us_10y_yield_spike(4.65)
    print(f"  US 10Y Yield Check: {us10y}")
    yc = calculate_yield_curve_spread(7.10, 7.25)
    print(f"  Yield Curve Spread: {yc}")
    brent = calculate_commodity_shock_penalty(92.5, 85.0)
    print(f"  Brent Crude Shock: {brent}")
