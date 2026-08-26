"""
engine/fundamental.py — Fundamental Quality Score engine (Module 12).

Takes ScreenerData and produces a normalized FundamentalScore /100.

Score composition:
  Profitability (ROCE, ROE, OPM)        → /35
  Growth (Sales CAGR, Profit CAGR)      → /25
  Financial Strength (Debt/Equity)      → /20
  Cash Flow Quality (proxy via OPM)     → /20
  ─────────────────────────────────────
  TOTAL                                 /100

All fields gracefully handle None — missing data lowers the score only
for the sub-components that cannot be computed, and the status string
clearly distinguishes 'DATA_UNAVAILABLE' from 'POOR'.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from data.screener import ScreenerData


@dataclass
class FundamentalScore:
    symbol: str
    # Sub-scores (/100 scale each, then weighted)
    profitability_score: float   # /35
    growth_score: float          # /25
    strength_score: float        # /20
    cashflow_score: float        # /20
    total_score: float           # /100
    # Data quality
    status: str  # 'SCORED', 'PARTIAL_DATA', 'DATA_UNAVAILABLE'
    missing_fields: list[str]
    # Raw inputs used
    roce: Optional[float]
    roe: Optional[float]
    opm_pct: Optional[float]
    debt_to_equity: Optional[float]
    sales_growth: Optional[float]
    profit_growth: Optional[float]


def _score_roce(roce: Optional[float]) -> float:
    """ROCE → /100 component. Excellent >25%, Good 15-25%, Fair 10-15%, Weak <10%."""
    if roce is None:
        return 50.0  # neutral when unavailable (not 0, to avoid silent penalizing)
    if roce >= 25:
        return 100.0
    elif roce >= 20:
        return 85.0
    elif roce >= 15:
        return 70.0
    elif roce >= 10:
        return 50.0
    elif roce >= 5:
        return 25.0
    else:
        return 0.0


def _score_roe(roe: Optional[float]) -> float:
    """ROE → /100 component. Excellent >20%, Good 15-20%, Fair 10-15%, Weak <10%."""
    if roe is None:
        return 50.0
    if roe >= 20:
        return 100.0
    elif roe >= 15:
        return 80.0
    elif roe >= 10:
        return 60.0
    elif roe >= 5:
        return 30.0
    else:
        return 0.0


def _score_opm(opm: Optional[float]) -> float:
    """OPM → /100 component. Excellent >25%, Good 15-25%, Fair 8-15%, Weak <8%."""
    if opm is None:
        return 50.0
    if opm >= 25:
        return 100.0
    elif opm >= 15:
        return 80.0
    elif opm >= 10:
        return 60.0
    elif opm >= 5:
        return 35.0
    else:
        return 0.0


def _score_growth(growth_pct: Optional[float]) -> float:
    """CAGR % → /100 component. Excellent >20%, Good 12-20%, Fair 5-12%, Weak <5%."""
    if growth_pct is None:
        return 50.0
    if growth_pct >= 20:
        return 100.0
    elif growth_pct >= 15:
        return 80.0
    elif growth_pct >= 10:
        return 60.0
    elif growth_pct >= 5:
        return 35.0
    elif growth_pct >= 0:
        return 15.0
    else:
        return 0.0  # negative growth


def _score_debt(d_e: Optional[float]) -> float:
    """Debt/Equity → /100 component. Debt-free excellent, 0-0.5 good, >2 weak."""
    if d_e is None:
        return 50.0
    if d_e == 0:
        return 100.0
    elif d_e <= 0.25:
        return 90.0
    elif d_e <= 0.5:
        return 75.0
    elif d_e <= 1.0:
        return 55.0
    elif d_e <= 1.5:
        return 35.0
    elif d_e <= 2.0:
        return 15.0
    else:
        return 0.0


def compute_fundamental_score(screener: ScreenerData) -> FundamentalScore:
    """
    Compute the FundamentalScore /100 from ScreenerData.

    Weight breakdown:
      Profitability: ROCE(40%) + ROE(35%) + OPM(25%) → weighted /100, then scaled to /35
      Growth:        Sales CAGR(50%) + Profit CAGR(50%) → /100, scaled to /25
      Strength:      Debt/Equity → /100, scaled to /20
      CashFlow:      OPM as proxy (high OPM = better cash generation) → /100, scaled to /20
    """
    missing: list[str] = []

    # ── 1. Profitability (35 points) ──────────────────────────────────────────
    roce_100 = _score_roce(screener.roce)
    roe_100 = _score_roe(screener.roe)
    opm_100_prof = _score_opm(screener.opm_pct)
    if screener.roce is None:
        missing.append("ROCE")
    if screener.roe is None:
        missing.append("ROE")

    profitability_100 = roce_100 * 0.40 + roe_100 * 0.35 + opm_100_prof * 0.25
    profitability_35 = (profitability_100 / 100.0) * 35.0

    # ── 2. Growth (25 points) ─────────────────────────────────────────────────
    sales_100 = _score_growth(screener.sales_growth_3yr)
    profit_100 = _score_growth(screener.profit_growth_3yr)
    if screener.sales_growth_3yr is None:
        missing.append("Sales_Growth_CAGR")
    if screener.profit_growth_3yr is None:
        missing.append("Profit_Growth_CAGR")

    growth_100 = sales_100 * 0.50 + profit_100 * 0.50
    growth_25 = (growth_100 / 100.0) * 25.0

    # ── 3. Financial Strength (20 points) ────────────────────────────────────
    debt_100 = _score_debt(screener.debt_to_equity)
    if screener.debt_to_equity is None:
        missing.append("Debt_Equity")
    strength_20 = (debt_100 / 100.0) * 20.0

    # ── 4. Cash Flow Quality (20 points) — use OPM as proxy ─────────────────
    # High OPM → strong operating cash generation → good cash flow quality
    opm_100_cf = _score_opm(screener.opm_pct)
    if screener.opm_pct is None:
        missing.append("OPM")
    cashflow_20 = (opm_100_cf / 100.0) * 20.0

    # ── Total ──────────────────────────────────────────────────────────────────
    total = profitability_35 + growth_25 + strength_20 + cashflow_20
    total = round(max(0.0, min(100.0, total)), 1)

    # Status
    n_missing = len(set(missing))  # unique missing fields
    if screener.data_source == "UNAVAILABLE":
        status = "DATA_UNAVAILABLE"
    elif n_missing >= 4:
        status = "PARTIAL_DATA"
    else:
        status = "SCORED"

    return FundamentalScore(
        symbol=screener.symbol,
        profitability_score=round(profitability_35, 1),
        growth_score=round(growth_25, 1),
        strength_score=round(strength_20, 1),
        cashflow_score=round(cashflow_20, 1),
        total_score=total,
        status=status,
        missing_fields=list(set(missing)),
        roce=screener.roce,
        roe=screener.roe,
        opm_pct=screener.opm_pct,
        debt_to_equity=screener.debt_to_equity,
        sales_growth=screener.sales_growth_3yr,
        profit_growth=screener.profit_growth_3yr,
    )


if __name__ == "__main__":
    import time
    from data.screener import fetch_screener_data

    for sym in ["RELIANCE", "WELCORP", "HFCL"]:
        sd = fetch_screener_data(sym)
        fs = compute_fundamental_score(sd)
        print(f"=== {sym} ===")
        print(f"  Fundamental Score: {fs.total_score}/100 ({fs.status})")
        print(f"  Profitability:     {fs.profitability_score}/35")
        print(f"  Growth:            {fs.growth_score}/25")
        print(f"  Strength:          {fs.strength_score}/20")
        print(f"  Cash Flow:         {fs.cashflow_score}/20")
        if fs.missing_fields:
            print(f"  Missing:           {', '.join(fs.missing_fields)}")
        print()
        time.sleep(0.5)
