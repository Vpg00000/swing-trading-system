"""
Regime filter: classifies current market state using Nifty vs its 200-day
moving average and India VIX level. Drives the maximum equity exposure cap
for the day. See DESIGN.md "Regime filter" section for the source rules.
"""

import sys
import datetime
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Dict, Any, Tuple

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

    # Institutional Score (Sector Indices with staleness decay)
    institutional_score, _ = get_institutional_score_with_staleness(macro)

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


def get_institutional_score_with_staleness(macro: Optional[dict]) -> tuple[float, float]:
    """
    Computes institutional score with exponential staleness decay.
    Uses cached values and decays confidence towards neutral (50.0) as data ages,
    rather than jumping discontinuously to a default.
    Returns: (decayed_score, confidence_weight)
    """
    if not macro or "nifty_sectors" not in macro or not macro["nifty_sectors"]:
        return 50.0, 0.5

    sectors = macro["nifty_sectors"]
    avg_sector_chg = sum(getattr(s, "change_pct", 0.0) if hasattr(s, "change_pct") else s.get("change_pct", 0.0) for s in sectors) / max(1, len(sectors))
    base_score = max(0.0, min(100.0, (avg_sector_chg + 1.0) / 2.0 * 100.0))

    data_age_days = 0.0
    first_sec = sectors[0]
    date_val = getattr(first_sec, "data_date", None) if hasattr(first_sec, "data_date") else (first_sec.get("data_date") if isinstance(first_sec, dict) else None)
    if date_val:
        try:
            if isinstance(date_val, str):
                dt = datetime.date.fromisoformat(date_val)
            else:
                dt = date_val
            data_age_days = max(0.0, (datetime.date.today() - dt).days)
        except Exception:
            data_age_days = 0.0
    elif "data_age_days" in macro:
        data_age_days = float(macro["data_age_days"])

    confidence = max(0.5, 1.0 - (data_age_days / 7.0))
    decayed_score = 50.0 + (base_score - 50.0) * confidence

    return round(decayed_score, 1), round(confidence, 2)


def monitor_vix_spike(vix_level: float, prev_vix: Optional[float] = None) -> dict[str, Any]:
    """
    Real-time India VIX spike monitor and circuit breaker.
    DESIGN.md:
      - VIX > 35: Extreme Crisis / Emergency derisking
      - VIX > 30: Elevated High-Vol Alert
      - VIX > 20: Volatile Caution
      - Sudden intraday spike >= 5.0 pts: Spike Emergency Trigger
    """
    spike_detected = False
    if prev_vix is not None and (vix_level - prev_vix) >= 5.0:
        spike_detected = True

    if vix_level >= 35.0 or spike_detected:
        status = "SPIKE_EMERGENCY"
        action = "HALVE_EQUITY_AND_ACTIVATE_HEDGE"
    elif vix_level >= 30.0:
        status = "ELEVATED"
        action = "REDUCE_POSITION_SIZES_AND_TIGHTEN_STOPS"
    elif vix_level >= 20.0:
        status = "CAUTION"
        action = "SELECTIVE_ENTRY_ONLY"
    else:
        status = "NORMAL"
        action = "STANDARD_EXECUTION"

    return {
        "vix": vix_level,
        "prev_vix": prev_vix,
        "vix_change": round(vix_level - prev_vix, 2) if prev_vix is not None else 0.0,
        "status": status,
        "action": action,
        "emergency_mode_triggered": (status == "SPIKE_EMERGENCY")
    }


def should_hedge_portfolio(regime_score: float, vix: float) -> bool:
    """
    Determines whether tail-risk protective hedge should be activated.
    Hedge triggered if VIX > 20.0 or Regime Score < 45.0.
    """
    return bool(vix > 20.0 or regime_score < 45.0)


def calculate_hedge_size(
    total_capital: float,
    portfolio_beta: float = 1.0,
    vix: float = 18.0
) -> dict[str, Any]:
    """
    Computes recommended allocation for tail-risk hedging (protective puts / VIX calls).
    Typically 2-5% of total capital scaled by portfolio beta and volatility regime.
    """
    base_pct = 0.02
    if vix > 25.0:
        base_pct = 0.045
    elif vix > 20.0:
        base_pct = 0.035
    elif portfolio_beta > 1.2:
        base_pct = 0.03

    hedge_capital = round(total_capital * base_pct, 2)
    instrument = "VIX_CALLS" if vix < 15.0 else "NIFTY_PUT_SPREAD"

    return {
        "hedge_pct": round(base_pct * 100.0, 2),
        "hedge_capital_inr": hedge_capital,
        "recommended_instrument": instrument,
        "rationale": f"Hedge sized at {base_pct*100:.1f}% for Beta={portfolio_beta:.2f} and VIX={vix:.1f}"
    }


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
