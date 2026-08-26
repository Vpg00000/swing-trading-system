"""
Multi-Timeframe (MTF) Verification Engine.

Verifies trend alignment across Daily and Weekly timeframes before issuing high-conviction BUY signals.

Fixes Problem: 151.
"""

import pandas as pd
from typing import Dict, Any


def verify_multi_timeframe_trend(daily_df: pd.DataFrame) -> Dict[str, Any]:
    """
    Evaluates alignment between Daily and Weekly trend series.
    (Fixes Problem 151)
    """
    if daily_df.empty or "Close" not in daily_df.columns or len(daily_df) < 30:
        return {"mtf_aligned": True, "daily_trend": "NEUTRAL", "weekly_trend": "NEUTRAL"}

    df = daily_df.sort_index()

    # Daily trend check (Price > 20 SMA)
    daily_close = float(df["Close"].iloc[-1])
    daily_sma20 = float(df["Close"].tail(20).mean())
    daily_bullish = daily_close >= daily_sma20

    # Resample to Weekly OHLCV
    weekly_df = df["Close"].resample("W").last().dropna()
    if len(weekly_df) >= 5:
        weekly_close = float(weekly_df.iloc[-1])
        weekly_sma5 = float(weekly_df.tail(5).mean())
        weekly_bullish = weekly_close >= weekly_sma5
    else:
        weekly_bullish = daily_bullish

    mtf_aligned = (daily_bullish and weekly_bullish) or (not daily_bullish and not weekly_bullish)

    return {
        "mtf_aligned": mtf_aligned,
        "daily_trend": "BULLISH" if daily_bullish else "BEARISH",
        "weekly_trend": "BULLISH" if weekly_bullish else "BEARISH",
        "status": "STRONG_MTF_ALIGNMENT" if (daily_bullish and weekly_bullish) else "DIVERGENT_TIMEFRAMES"
    }


if __name__ == "__main__":
    print("Testing MTF Verification Engine...\n")
    dates = pd.date_range(end=pd.Timestamp.today(), periods=60)
    prices = [100.0 + i * 0.5 for i in range(60)]
    df = pd.DataFrame({"Close": prices}, index=dates)
    res = verify_multi_timeframe_trend(df)
    print(f"  MTF Verification: {res}")
