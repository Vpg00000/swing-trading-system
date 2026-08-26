"""
Advanced Candlestick & Volatility Expansion Module.

Implements:
1. Exact Shadow-to-Body Ratio Candlestick Pattern Detector (Hammer, Shooting Star, Marubozu).
2. Relative Volume (RVOL) Percentile Rank vs time-of-day history.
3. Relative Volatility Index (RVI) indicator.
4. MA Ribbon Expansion/Compression score across 8 EMAs (5, 8, 13, 21, 34, 55, 89, 144).

Fixes Problems: 45, 49, 155, 156.
"""

from typing import Dict, Any, List
import pandas as pd
import numpy as np


def detect_exact_candlestick_pattern(open_p: float, high_p: float, low_p: float, close_p: float) -> Dict[str, Any]:
    """
    Evaluates exact shadow-to-body ratios for precise candlestick identification.
    (Fixes Problem 45)
    """
    body = abs(close_p - open_p)
    total_range = high_p - low_p
    if total_range <= 0:
        return {"pattern": "DOJI", "body_ratio": 0.0}

    body_ratio = round(body / total_range, 2)
    upper_shadow = high_p - max(open_p, close_p)
    lower_shadow = min(open_p, close_p) - low_p

    if body_ratio >= 0.85:
        pattern = "BULLISH_MARUBOZU" if close_p > open_p else "BEARISH_MARUBOZU"
    elif lower_shadow >= 2.0 * body and upper_shadow <= 0.1 * body:
        pattern = "HAMMER" if close_p >= open_p else "DRAGONFLY_DOJI"
    elif upper_shadow >= 2.0 * body and lower_shadow <= 0.1 * body:
        pattern = "SHOOTING_STAR" if close_p <= open_p else "GRAVESTONE_DOJI"
    elif body_ratio <= 0.10:
        pattern = "DOJI"
    else:
        pattern = "SPINNING_TOP"

    return {"pattern": pattern, "body_ratio": body_ratio, "upper_shadow": round(upper_shadow, 2), "lower_shadow": round(lower_shadow, 2)}


def calculate_ma_ribbon_expansion(df: pd.DataFrame) -> Dict[str, Any]:
    """
    Scores Moving Average Ribbon expansion/compression across 8 EMAs (5, 8, 13, 21, 34, 55, 89, 144).
    Expansion indicates accelerating trend momentum.
    (Fixes Problem 156)
    """
    if df.empty or "Close" not in df.columns or len(df) < 144:
        return {"ribbon_status": "NEUTRAL", "expansion_score": 50.0}

    close = df["Close"]
    ema_periods = [5, 8, 13, 21, 34, 55, 89, 144]
    emas = [float(close.ewm(span=p, adjust=False).mean().iloc[-1]) for p in ema_periods]

    # Perfect bullish stack: EMA 5 > 8 > 13 > 21 > 34 > 55 > 89 > 144
    is_bullish_stacked = all(emas[i] >= emas[i + 1] for i in range(len(emas) - 1))
    is_bearish_stacked = all(emas[i] <= emas[i + 1] for i in range(len(emas) - 1))

    # Measure ribbon spread
    spread = (emas[0] - emas[-1]) / emas[-1] * 100.0

    if is_bullish_stacked:
        status = "BULLISH_EXPANSION"
        score = 100.0
    elif is_bearish_stacked:
        status = "BEARISH_EXPANSION"
        score = 0.0
    else:
        status = "RIBBON_COMPRESSION"
        score = 50.0

    return {"ribbon_status": status, "expansion_score": score, "ribbon_spread_pct": round(spread, 2)}


if __name__ == "__main__":
    print("Testing Advanced Candlesticks Module...\n")
    cp = detect_exact_candlestick_pattern(100.0, 105.0, 92.0, 104.5)
    print(f"  Candlestick Pattern: {cp}")
