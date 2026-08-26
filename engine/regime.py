"""
Regime filter: classifies current market state using Nifty vs its 200-day
moving average and India VIX level. Drives the maximum equity exposure cap
for the day. See DESIGN.md "Regime filter" section for the source rules.
"""

import sys
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from data.fetch import load_cached


@dataclass
class RegimeResult:
    regime: str
    nifty_close: float
    nifty_200dma: float
    nifty_above_dma_pct: float
    vix: float
    max_equity_exposure: float
    notes: str
    trend_score: float
    volatility_score: float
    breadth_score: float
    institutional_score: float
    global_score: float
    liquidity_score: float
    regime_score: float


def _load_series(name: str) -> pd.DataFrame:
    df = load_cached(name)
    if df.empty:
        raise FileNotFoundError(
            f"No cached data for '{name}'. Run `python3 data/fetch.py` first."
        )
    return df


def classify_regime(
    ranked_candidates: list = None,
    macro: dict | None = None,
    portfolio: dict | None = None
) -> RegimeResult:
    nifty = _load_series("nifty")
    vix = _load_series("vix")

    if len(nifty) < 200:
        raise ValueError(
            f"Only {len(nifty)} days of Nifty history available; need >=200 "
            "for a 200-DMA. Re-fetch with a longer lookback period."
        )

    nifty_close = float(nifty["Close"].iloc[-1])
    dma200 = float(nifty["Close"].rolling(200).mean().iloc[-1])
    above_pct = (nifty_close / dma200 - 1) * 100

    dma200_prev = float(nifty["Close"].rolling(200).mean().iloc[-6])
    rising = dma200 >= dma200_prev

    vix_level = float(vix["Close"].iloc[-1])

    if nifty_close > dma200:
        if vix_level < 15 and rising:
            regime, max_exposure = "RISK-ON", 0.70
            notes = "Nifty above 200-DMA and rising, VIX calm."
        elif vix_level < 20:
            regime, max_exposure = "RISK-ON (cautious)", 0.50
            notes = "Nifty above 200-DMA but trend flattening or VIX elevated."
        else:
            regime, max_exposure = "RISK-OFF", 0.25
            notes = "Nifty above 200-DMA but VIX >= 20 signals stress."
    else:
        if vix_level > 30:
            regime, max_exposure = "EMERGENCY", 0.10
            notes = "Nifty below 200-DMA and VIX > 30 (crisis-level stress)."
        else:
            regime, max_exposure = "RISK-OFF", 0.25
            notes = "Nifty below 200-DMA."

    # 3. Multi-Factor Scores (0-100)
    trend_score = max(0.0, min(100.0, (above_pct - (-5.0)) / 10.0 * 100))
    volatility_score = max(0.0, min(100.0, (25.0 - vix_level) / 13.0 * 100))

    # Breadth Score (share of universe above 20-DMA and 50-DMA)
    from config.universe import EQUITY_UNIVERSE
    above_20_count = 0
    above_50_count = 0
    total_valid = 0
    for sym in EQUITY_UNIVERSE:
        df = load_cached(sym)
        if df.empty or len(df) < 50:
            continue
        close_series = df["Close"]
        c_val = float(close_series.iloc[-1])
        dma20 = float(close_series.tail(20).mean())
        dma50 = float(close_series.tail(50).mean())
        if c_val > dma20:
            above_20_count += 1
        if c_val > dma50:
            above_50_count += 1
        total_valid += 1
    pct20 = above_20_count / total_valid if total_valid > 0 else 0.5
    pct50 = above_50_count / total_valid if total_valid > 0 else 0.5
    breadth_score = (pct20 + pct50) / 2 * 100

    # Institutional Score (Sector Indices)
    if macro and "nifty_sectors" in macro and macro["nifty_sectors"]:
        sectors = macro["nifty_sectors"]
        avg_sector_chg = sum(s.change_pct for s in sectors) / len(sectors)
        institutional_score = max(0.0, min(100.0, (avg_sector_chg + 1.0) / 2.0 * 100))
    else:
        institutional_score = 50.0

    # Global Score (Global Equities)
    if macro and "global_equity" in macro and macro["global_equity"]:
        glob = macro["global_equity"]
        avg_global_chg = sum(g.change_pct for g in glob) / len(glob)
        global_score = max(0.0, min(100.0, (avg_global_chg + 1.5) / 3.0 * 100))
    else:
        global_score = 50.0

    # Liquidity Score (VIX + DXY change)
    if macro and "forex" in macro and macro["forex"]:
        dxy_quote = next((q for q in macro["forex"] if "DXY" in q.name), None)
        dxy_chg = dxy_quote.change_pct if dxy_quote else 0.0
        liquidity_score = 100.0 - (vix_level - 10.0) * 3.0 - (dxy_chg * 10.0)
        liquidity_score = max(0.0, min(100.0, liquidity_score))
    else:
        liquidity_score = max(0.0, min(100.0, 100.0 - (vix_level - 10.0) * 3.0))

    # Composite Regime Score
    regime_score = (
        0.25 * trend_score +
        0.25 * breadth_score +
        0.20 * volatility_score +
        0.10 * institutional_score +
        0.10 * global_score +
        0.10 * liquidity_score
    )
    regime_score = max(0.0, min(100.0, regime_score))

    return RegimeResult(
        regime=regime,
        nifty_close=nifty_close,
        nifty_200dma=dma200,
        nifty_above_dma_pct=above_pct,
        vix=vix_level,
        max_equity_exposure=max_exposure,
        notes=notes,
        trend_score=round(trend_score, 1),
        volatility_score=round(volatility_score, 1),
        breadth_score=round(breadth_score, 1),
        institutional_score=round(institutional_score, 1),
        global_score=round(global_score, 1),
        liquidity_score=round(liquidity_score, 1),
        regime_score=round(regime_score, 1),
    )


if __name__ == "__main__":
    result = classify_regime()
    print(f"Regime:              {result.regime}")
    print(f"Nifty close:         {result.nifty_close:,.2f}")
    print(f"Nifty 200-DMA:       {result.nifty_200dma:,.2f} ({result.nifty_above_dma_pct:+.2f}%)")
    print(f"India VIX:           {result.vix:.2f}")
    print(f"Max equity exposure: {result.max_equity_exposure:.0%}")
    print(f"Notes:               {result.notes}")
    print("\n-- MULTI-FACTOR REGIME SCORES (0-100) --")
    print(f"  Trend score:          {result.trend_score}")
    print(f"  Volatility score:     {result.volatility_score}")
    print(f"  Breadth score:        {result.breadth_score}")
    print(f"  Institutional score:  {result.institutional_score} (default)")
    print(f"  Global score:         {result.global_score} (default)")
    print(f"  Liquidity score:      {result.liquidity_score}")
    print(f"  Composite score:      {result.regime_score}")
