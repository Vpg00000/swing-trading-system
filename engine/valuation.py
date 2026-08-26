"""
engine/valuation.py — Valuation Score engine (Module 13).

Takes ScreenerData and sector-median P/E to produce a ValuationScore /100.
A low P/E vs sector median = cheap → higher score.
A high P/E vs sector median = expensive → lower score.
Combines P/E, P/B and OPM-based quality adjustment.

Score composition (all /100, then weighted to /5 for composite):
  P/E vs historical / sector            → /50
  P/B vs book value quality             → /30
  FCF Yield proxy (OPM-based)           → /20
  ─────────────────────────────────────
  TOTAL (internal /100), exported as /5 for composite score
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from data.screener import ScreenerData

# Sector-median P/E lookup table — approximate NSE sector medians (2024-2025).
# Used when no live sector-median is available. Conservative values.
SECTOR_MEDIAN_PE: dict[str, float] = {
    "Technology": 30.0,
    "Telecom": 35.0,
    "Pharma": 32.0,
    "Consumer": 45.0,
    "Auto": 25.0,
    "Banking": 15.0,
    "NBFC": 20.0,
    "Infra": 22.0,
    "Metals": 12.0,
    "Energy": 18.0,
    "Cement": 28.0,
    "Real Estate": 35.0,
    "Default": 25.0,   # fallback
}


@dataclass
class ValuationScore:
    symbol: str
    pe_score: float            # /50 (higher = cheaper vs sector)
    pb_score: float            # /30
    fcf_proxy_score: float     # /20
    total_100: float           # /100
    total_5: float             # /5 (for composite score)
    pe_ratio: Optional[float]
    pb_ratio: Optional[float]
    sector_median_pe: Optional[float]
    pe_vs_sector_pct: Optional[float]  # negative = cheaper, positive = pricier
    status: str   # 'SCORED', 'PARTIAL_DATA', 'DATA_UNAVAILABLE'
    missing_fields: list[str]


def _score_pe_vs_sector(pe: Optional[float], sector_median_pe: float) -> tuple[float, Optional[float]]:
    """
    Score P/E relative to sector median.
    Discount ≥40% → full score. Premium >50% → 0.
    Returns (score_50, pct_vs_median).
    """
    if pe is None:
        return 25.0, None  # neutral

    pct = (pe - sector_median_pe) / sector_median_pe * 100.0  # +ve = more expensive

    if pct <= -40:
        score = 50.0   # significantly cheap
    elif pct <= -20:
        score = 42.0   # meaningfully cheap
    elif pct <= -5:
        score = 35.0   # slightly cheap
    elif pct <= 10:
        score = 28.0   # fairly valued
    elif pct <= 25:
        score = 18.0   # slightly expensive
    elif pct <= 50:
        score = 8.0    # expensive
    else:
        score = 0.0    # very expensive

    return score, round(pct, 1)


def _score_pb(pb: Optional[float], roe: Optional[float]) -> float:
    """
    Score P/B. Adjust for ROE — high-ROE companies deserve higher P/B.
    If ROE > 20%, P/B < 4 is fair. If ROE < 10%, P/B < 1.5 is fair.
    """
    if pb is None:
        return 15.0  # neutral

    # Compute justified P/B = ROE / cost_of_equity (≈ 12%)
    if roe is not None and roe > 0:
        justified_pb = roe / 12.0
    else:
        justified_pb = 1.5  # default

    ratio = pb / justified_pb if justified_pb > 0 else float("inf")

    if ratio <= 0.5:
        return 30.0   # very cheap vs justified value
    elif ratio <= 0.8:
        return 25.0   # cheap
    elif ratio <= 1.1:
        return 20.0   # fair
    elif ratio <= 1.5:
        return 12.0   # slightly expensive
    elif ratio <= 2.0:
        return 5.0    # expensive
    else:
        return 0.0    # very expensive


def _score_fcf_proxy(opm: Optional[float]) -> float:
    """
    FCF Yield proxy: high OPM companies typically have better cash conversion.
    OPM >20% → excellent cash gen, OPM <5% → poor.
    """
    if opm is None:
        return 10.0  # neutral

    if opm >= 25:
        return 20.0
    elif opm >= 20:
        return 17.0
    elif opm >= 15:
        return 14.0
    elif opm >= 10:
        return 10.0
    elif opm >= 5:
        return 5.0
    else:
        return 0.0


def compute_valuation_score(
    screener: ScreenerData,
    sector: Optional[str] = None,
) -> ValuationScore:
    """
    Compute ValuationScore from ScreenerData.
    sector: if provided, used to look up sector-median P/E.
    """
    if screener.data_source == "UNAVAILABLE":
        return ValuationScore(
            symbol=screener.symbol,
            pe_score=0.0, pb_score=0.0, fcf_proxy_score=0.0,
            total_100=0.0, total_5=0.0,
            pe_ratio=None, pb_ratio=None,
            sector_median_pe=None, pe_vs_sector_pct=None,
            status="DATA_UNAVAILABLE", missing_fields=["ALL"]
        )

    missing: list[str] = []
    sector_med_pe = SECTOR_MEDIAN_PE.get(sector or "Default", SECTOR_MEDIAN_PE["Default"])

    pe_score_50, pct = _score_pe_vs_sector(screener.pe_ratio, sector_med_pe)
    if screener.pe_ratio is None:
        missing.append("P/E")

    pb_score_30 = _score_pb(screener.pb_ratio, screener.roe)
    if screener.pb_ratio is None:
        missing.append("P/B")

    fcf_score_20 = _score_fcf_proxy(screener.opm_pct)
    if screener.opm_pct is None:
        missing.append("OPM")

    total_100 = pe_score_50 + pb_score_30 + fcf_score_20
    total_100 = round(max(0.0, min(100.0, total_100)), 1)
    total_5 = round((total_100 / 100.0) * 5.0, 2)

    status = "DATA_UNAVAILABLE" if len(missing) == 3 else (
        "PARTIAL_DATA" if missing else "SCORED"
    )

    return ValuationScore(
        symbol=screener.symbol,
        pe_score=round(pe_score_50, 1),
        pb_score=round(pb_score_30, 1),
        fcf_proxy_score=round(fcf_score_20, 1),
        total_100=total_100,
        total_5=total_5,
        pe_ratio=screener.pe_ratio,
        pb_ratio=screener.pb_ratio,
        sector_median_pe=sector_med_pe,
        pe_vs_sector_pct=pct,
        status=status,
        missing_fields=missing,
    )


if __name__ == "__main__":
    from data.screener import fetch_screener_data
    import time

    test_cases = [
        ("RELIANCE", "Energy"),
        ("WELCORP", "Metals"),
        ("HFCL", "Technology"),
    ]
    for sym, sector in test_cases:
        sd = fetch_screener_data(sym)
        vs = compute_valuation_score(sd, sector=sector)
        print(f"=== {sym} (sector={sector}) ===")
        print(f"  Valuation Score: {vs.total_100}/100 → {vs.total_5}/5 ({vs.status})")
        print(f"  P/E:             {vs.pe_ratio} (sector median: {vs.sector_median_pe})")
        print(f"  P/E vs Sector:   {vs.pe_vs_sector_pct}%  → score {vs.pe_score}/50")
        print(f"  P/B:             {vs.pb_ratio}  → score {vs.pb_score}/30")
        print(f"  FCF proxy:       score {vs.fcf_proxy_score}/20")
        if vs.missing_fields:
            print(f"  Missing:         {', '.join(vs.missing_fields)}")
        print()
        time.sleep(0.5)
