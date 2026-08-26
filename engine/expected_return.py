"""
engine/expected_return.py — Expected Return Engine (Module 21).

For each candidate, computes:
  Entry Zone     : current_price ± 0.5 × ATR (optimal entry band)
  Target Price   : prior swing high OR current_price + 1.5×ATR (nearest technical target)
  Stop Price     : current_price - 2×ATR (from momentum engine)
  Expected Upside: (target - entry_mid) / entry_mid
  Expected Loss  : (entry_mid - stop) / entry_mid
  R:R Ratio      : expected_upside / expected_loss
  Probability    : estimated from composite score percentile
  Expected Value : prob * upside - (1-prob) * loss  (positive = worthwhile)

Target price methodology: technical only (as per user preference).
  1. Prior swing high (highest close in last 52 weeks, capped at +30% from current)
  2. Fallback: current_price + 1.5 × ATR × 3  (3 ATR extension = typical swing target)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np
import pandas as pd


@dataclass
class ExpectedReturn:
    symbol: str
    current_price: float
    entry_low: float       # lower bound of entry zone
    entry_mid: float       # midpoint of entry zone (used for calculations)
    entry_high: float      # upper bound of entry zone
    target_price: float
    stop_price: float
    expected_upside_pct: float   # % gain if target hit
    expected_loss_pct: float     # % loss if stop hit
    risk_reward: float           # upside / loss ratio
    probability_estimate: float  # 0.0 to 1.0
    expected_value_pct: float    # EV = prob * upside - (1-prob) * loss
    atr: float
    target_method: str           # 'SWING_HIGH' or 'ATR_EXTENSION'
    status: str                  # 'COMPUTED', 'INSUFFICIENT_DATA'


def _find_swing_high(df: pd.DataFrame, current_price: float) -> Optional[float]:
    """
    Find the prior swing high: the highest close in the last 252 trading days
    (1 year), excluding the most recent 21 days to avoid using current peak.
    Cap at +30% above current price to avoid unrealistic targets.
    """
    if df is None or df.empty or len(df) < 63:
        return None
    # Use 22 to 252 days ago range
    look_back = df["Close"].iloc[:-21] if len(df) > 22 else df["Close"]
    high_52w = float(look_back.tail(252).max())
    # If swing high is below or very close to current price, it's not a target
    if high_52w <= current_price * 1.02:
        return None
    # Cap at +30%
    capped = min(high_52w, current_price * 1.30)
    return capped


def compute_expected_return(
    symbol: str,
    current_price: float,
    atr: float,
    stop_price: float,
    composite_score: float,   # /100 — used to estimate probability
    df: Optional[pd.DataFrame] = None,  # OHLCV dataframe for swing high
) -> ExpectedReturn:
    """
    Compute the expected return profile for a candidate.

    Parameters:
        composite_score: the /100 composite investment score
        df:              OHLCV dataframe from yfinance cache (for swing high)
    """
    if atr <= 0 or current_price <= 0:
        return ExpectedReturn(
            symbol=symbol, current_price=current_price,
            entry_low=current_price, entry_mid=current_price, entry_high=current_price,
            target_price=current_price, stop_price=stop_price,
            expected_upside_pct=0.0, expected_loss_pct=0.0,
            risk_reward=0.0, probability_estimate=0.0,
            expected_value_pct=0.0, atr=atr,
            target_method="INSUFFICIENT_DATA", status="INSUFFICIENT_DATA"
        )

    # ── Entry Zone: current ± 0.5 × ATR ───────────────────────────────────────
    entry_low = current_price - 0.5 * atr
    entry_high = current_price + 0.5 * atr
    entry_mid = current_price  # midpoint = current price

    # ── Target Price ───────────────────────────────────────────────────────────
    swing_high = _find_swing_high(df, current_price) if df is not None else None

    if swing_high is not None and swing_high > current_price * 1.05:
        target_price = swing_high
        target_method = "SWING_HIGH"
    else:
        # Fallback: 3 × ATR extension above current price
        target_price = current_price + 3.0 * atr
        target_method = "ATR_EXTENSION"

    # Ensure target is always above entry
    target_price = max(target_price, entry_mid * 1.02)

    # ── Expected Upside / Loss ─────────────────────────────────────────────────
    expected_upside = (target_price - entry_mid) / entry_mid
    stop_safe = min(stop_price, entry_low * 0.99)  # ensure stop is below entry zone
    expected_loss = (entry_mid - stop_safe) / entry_mid

    expected_loss = max(0.001, expected_loss)  # avoid div/0

    rr = round(expected_upside / expected_loss, 2)

    # ── Probability Estimate ───────────────────────────────────────────────────
    # Map composite_score /100 → probability
    # Score 80+ → ~70% probability, 60 → ~55%, 40 → ~40%, below 40 → <35%
    # Linear interpolation between anchor points
    prob_anchors = [(0, 0.20), (30, 0.30), (50, 0.45), (60, 0.55), (70, 0.62), (80, 0.70), (90, 0.75), (100, 0.80)]
    prob = float(np.interp(composite_score, [p[0] for p in prob_anchors], [p[1] for p in prob_anchors]))
    prob = round(prob, 3)

    # ── Expected Value ────────────────────────────────────────────────────────
    ev = prob * expected_upside - (1.0 - prob) * expected_loss
    ev_pct = round(ev * 100.0, 2)

    return ExpectedReturn(
        symbol=symbol,
        current_price=round(current_price, 2),
        entry_low=round(entry_low, 2),
        entry_mid=round(entry_mid, 2),
        entry_high=round(entry_high, 2),
        target_price=round(target_price, 2),
        stop_price=round(stop_safe, 2),
        expected_upside_pct=round(expected_upside * 100.0, 2),
        expected_loss_pct=round(expected_loss * 100.0, 2),
        risk_reward=rr,
        probability_estimate=prob,
        expected_value_pct=ev_pct,
        atr=round(atr, 2),
        target_method=target_method,
        status="COMPUTED",
    )


if __name__ == "__main__":
    # Quick self-test with realistic values for WELCORP
    result = compute_expected_return(
        symbol="WELCORP",
        current_price=2346.0,
        atr=65.0,            # realistic ATR
        stop_price=2216.0,   # 2×ATR below
        composite_score=72.0,
        df=None,
    )
    print(f"=== {result.symbol} ===")
    print(f"  Status:           {result.status}")
    print(f"  Current Price:    ₹{result.current_price}")
    print(f"  Entry Zone:       ₹{result.entry_low} – ₹{result.entry_high}")
    print(f"  Target Price:     ₹{result.target_price} ({result.target_method})")
    print(f"  Stop Price:       ₹{result.stop_price}")
    print(f"  Expected Upside:  {result.expected_upside_pct}%")
    print(f"  Expected Loss:    {result.expected_loss_pct}%")
    print(f"  Risk:Reward:      1 : {result.risk_reward}")
    print(f"  Probability:      {result.probability_estimate * 100:.0f}%")
    print(f"  Expected Value:   {result.expected_value_pct}%")
